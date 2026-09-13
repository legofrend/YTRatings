"""
Monthly pipeline CLI.

Commands:
  channel-stat  — channel_stat by category (do near midnight 1st; fastest, time-sensitive)
  videos        — fetch new videos + detail/is_short (anytime; resume via DB holes)
  video-stat    — video_stat by category (near midnight after channel-stat; order=sort_order)
  publish       — build report JSON (PG SQL upsert, or BQ+sync if RAW_DB=bigquery)
  channel-report — materialize report_view → channel_report table in PG
  shorts-sync   — fetch UUSH playlist into playlist_shorts (API quota)
  apply-is-short — set video.is_short from playlist_shorts (--cats / --channel-id optional)
  backfill-denorm — fill NULL video_stat denorm cols (channel_id/is_short/is_new/period_*)
  backfill-channel-denorm — fill channel_stat denorm (pc_*/pv_*/ppcs_id/ranks) from video_stat

Examples:
  python -m app.main channel-stat --cats 1
  python -m app.main channel-stat --cats 1 --force
  python -m app.main videos
  python -m app.main video-stat --force
  python -m app.main publish --period 2026-08 --cats 1
  python -m app.main channel-report
  python -m app.main channel-stat video-stat --period 2026-07
  python -m app.main videos --cats 1 --priority 50
  python -m app.main videos --cats 1 --skip-shorts
  python -m app.main shorts-sync --period 2026-08 --cats 1 --channel-id UCxxxxxxxx
  python -m app.main apply-is-short --channel-id UCxxxxxxxx
  python -m app.main apply-is-short --cats 1
  python -m app.main backfill-denorm --period 2026-08
  python -m app.main backfill-denorm --period 2025-05 --period-to 2026-07
  python -m app.main backfill-channel-denorm --period 2025-05 --period-to 2026-08
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime
from pathlib import Path

# Running as file (VS Code F5 on app/main.py) puts .../app on sys.path, not project root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.channel import (
    CategoryDAO,
    ChannelDAO,
    ChannelStatDAO,
    PlaylistShortsDAO,
    VideoDAO,
    VideoStatDAO,
)
from app.logger import logger
from app.period import Period
from app.report.dao import ReportDAO

# Day-of-month cutoff: before this → previous month; on/after → current month.
PERIOD_ROLLOVER_DAY = 10


def default_period(today: date | None = None) -> Period:
    today = today or date.today()
    cur = Period(today.month, today.year)
    return cur.next(-1) if today.day < PERIOD_ROLLOVER_DAY else cur


def parse_period(s: str | None) -> Period:
    if not s:
        return default_period()
    return Period.parse(s)


def parse_cats(s: str | None) -> list[int] | None:
    """'1,3,5-8' → [1,3,5,6,7,8]. None → use all active."""
    if not s:
        return None
    out: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    # preserve order, unique
    seen: set[int] = set()
    ordered: list[int] = []
    for i in out:
        if i not in seen:
            seen.add(i)
            ordered.append(i)
    return ordered


async def resolve_category_ids(cats: list[int] | None) -> list[int]:
    if cats is not None:
        return cats
    rows = await CategoryDAO.find_all(active=1)
    rows = list(rows)
    rows.sort(
        key=lambda r: (
            r["sort_order"] if r["sort_order"] is not None else 1000,
            r["id"],
        )
    )
    ids = [r["id"] for r in rows]
    if not ids:
        logger.warning("no active categories in PG")
    return ids


async def cmd_channel_stat(
    period: Period, category_ids: list[int], *, force: bool = False
) -> None:
    logger.info(f"channel-stat period={period} cats={category_ids} force={force}")
    await ChannelStatDAO.update_stat(
        report_period=period, category_ids=category_ids, force=force
    )


async def cmd_videos(
    period: Period,
    category_ids: list[int],
    *,
    priority: int,
    skip_shorts: bool = False,
) -> None:
    # Exclusive end of report month (e.g. Aug → 2026-09-01). Videos on/after
    # this date belong to the next period.
    date_to = period.next(1)
    logger.info(
        f"videos fetch period={period} until={date_to} "
        f"cats={category_ids} priority={priority}"
    )
    await ChannelDAO.fetch_new_videos(
        category_ids=category_ids,
        date_to=date_to,
        priority=priority,
    )
    logger.info("videos detail (duration / missing fields)")
    await VideoDAO.update_detail(skip_shorts=skip_shorts)
    if skip_shorts:
        logger.info("videos is_short skipped (--skip-shorts)")
    else:
        logger.info("videos is_short")
        await VideoDAO.update_is_short()


async def cmd_video_stat(
    period: Period, category_ids: list[int], *, force: bool = False
) -> None:
    logger.info(f"video-stat period={period} cats={category_ids} force={force}")
    await VideoStatDAO.update_stat(
        report_period=period, category_ids=category_ids, force=force
    )


async def cmd_publish(period: Period, category_ids: list[int]) -> None:
    from app.config import settings

    if settings.RAW_DB == "bigquery":
        logger.info(f"publish build_in_bq period={period} cats={category_ids}")
        await ReportDAO.build_in_bq(period, category_ids)
        logger.info(f"publish sync_from_bq period={period} cats={category_ids}")
        await ReportDAO.sync_from_bq(period, category_ids)
    else:
        logger.info(f"publish build_in_pg period={period} cats={category_ids}")
        ok = await ReportDAO.build_in_pg(period, category_ids)
        if not ok:
            raise SystemExit("publish build_in_pg failed")


async def cmd_channel_report() -> None:
    logger.info("channel-report: materialize report_view → channel_report")
    await ReportDAO.refresh_channel_report()


async def cmd_shorts_sync(
    period: Period,
    category_ids: list[int],
    *,
    priority: int,
    channel_id: str | None = None,
) -> None:
    date_from = datetime.combine(period, datetime.min.time())
    date_to = datetime.combine(period.next(1), datetime.min.time())
    channel_ids = [channel_id] if channel_id else None
    logger.info(
        f"shorts-sync period={period} window=[{date_from} .. {date_to}) "
        f"cats={category_ids} channel_id={channel_id}"
    )
    await PlaylistShortsDAO.sync_channels(
        category_ids=category_ids,
        date_from=date_from,
        date_to=date_to,
        channel_ids=channel_ids,
        priority=priority,
    )


async def cmd_apply_is_short(
    *,
    category_ids: list[int] | None = None,
    channel_id: str | None = None,
) -> None:
    """Set video.is_short from playlist_shorts. Window = first short .. last_shorts_fetch_dt."""
    channel_ids = [channel_id] if channel_id else None
    logger.info(
        f"apply-is-short cats={category_ids} channel_id={channel_id}"
    )

    orphans = await PlaylistShortsDAO.find_orphans_not_in_video(
        category_ids=category_ids,
        channel_ids=channel_ids,
    )
    if orphans["count"]:
        logger.warning(
            f"orphans playlist_shorts not in video: {orphans['count']}; "
            f"sample={orphans['sample'][:5]}"
        )
    else:
        logger.info("orphans check: 0 (all playlist_shorts present in video)")

    stats = await VideoDAO.update_is_short_new(
        category_ids=category_ids,
        channel_ids=channel_ids,
        only_null=True,
    )
    logger.info(f"apply-is-short done: {stats}")


def _period_range(start: Period, end: Period) -> list[Period]:
    if end < start:
        start, end = end, start
    out: list[Period] = []
    p = start
    while p <= end:
        out.append(p)
        p = p.next(1)
    return out


async def cmd_backfill_denorm(
    period_from: Period,
    period_to: Period | None = None,
    *,
    batch_size: int = 10_000,
) -> None:
    """Fill video_stat denorm NULLs for one period or inclusive --period-to range."""
    periods = _period_range(period_from, period_to or period_from)
    logger.info(
        f"backfill-denorm periods={[p.strf('%p') for p in periods]} "
        f"batch_size={batch_size}"
    )
    for i, p in enumerate(periods, start=1):
        logger.info(f"=== backfill-denorm {p.strf('%p')} ({i}/{len(periods)}) ===")
        n = await VideoStatDAO.backfill_denorm(
            report_period=p, batch_size=batch_size
        )
        logger.info(f"backfill-denorm {p.strf('%p')}: updated {n}")


async def cmd_backfill_channel_denorm(
    period_from: Period,
    period_to: Period | None = None,
) -> None:
    """Fill channel_stat denorm for one period or inclusive --period-to range."""
    periods = _period_range(period_from, period_to or period_from)
    logger.info(
        f"backfill-channel-denorm periods={[p.strf('%p') for p in periods]}"
    )
    for i, p in enumerate(periods, start=1):
        logger.info(
            f"=== backfill-channel-denorm {p.strf('%p')} ({i}/{len(periods)}) ==="
        )
        stats = await ChannelStatDAO.backfill_denorm(report_period=p)
        logger.info(f"backfill-channel-denorm {p.strf('%p')}: {stats}")


COMMANDS = {
    "channel-stat": cmd_channel_stat,
    "videos": cmd_videos,
    "video-stat": cmd_video_stat,
    "publish": cmd_publish,
    "channel-report": cmd_channel_report,
    "shorts-sync": cmd_shorts_sync,
    "apply-is-short": cmd_apply_is_short,
    "backfill-denorm": cmd_backfill_denorm,
    "backfill-channel-denorm": cmd_backfill_channel_denorm,
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m app.main",
        description="YT ratings monthly pipeline",
    )
    p.add_argument(
        "commands",
        nargs="*",
        choices=list(COMMANDS),
        help="one or more: channel-stat | videos | video-stat | publish | channel-report | shorts-sync | apply-is-short | backfill-denorm | backfill-channel-denorm",
    )
    p.add_argument(
        "--period",
        default=None,
        help=f"YYYY-MM or YYYY-MM-DD (default: prev month if day<{PERIOD_ROLLOVER_DAY}, else current)",
    )
    p.add_argument(
        "--period-to",
        default=None,
        help="backfill-denorm: inclusive end period YYYY-MM (with --period as start)",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=10_000,
        help="backfill-denorm: rows per UPDATE batch (default 10000)",
    )
    p.add_argument(
        "--cats",
        default=None,
        help="category ids, e.g. 1,3,5-8 (default: all active by sort_order)",
    )
    p.add_argument(
        "--priority",
        type=int,
        default=100,
        help="channel.priority ceiling for videos fetch (default 100)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="channel-stat / video-stat: refresh all rows (upsert), not only missing",
    )
    p.add_argument(
        "--skip-shorts",
        action="store_true",
        help="videos: skip HTTP is_short checks (update_detail + update_is_short)",
    )
    p.add_argument(
        "--channel-id",
        default=None,
        help="shorts-sync / apply-is-short: single channel_id (UC…). optional for apply-is-short",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.commands:
        parser.print_help()
        return

    start_dt = datetime.now()
    print("Start", start_dt)
    try:
        asyncio.run(_run_parsed(args))
    except BaseException:
        print("FAILED after ", datetime.now() - start_dt)
        raise
    else:
        print("Finish after ", datetime.now() - start_dt)
        print("\a")


async def _run_parsed(args: argparse.Namespace) -> None:
    from app.bq import write as bq_write
    from app.config import settings

    if settings.RAW_DB == "bigquery":
        n = bq_write.flush_pending_writes()
        if n:
            logger.info(f"recovered {n} pending BQ rows before commands")

    period = parse_period(args.period)
    category_ids = await resolve_category_ids(parse_cats(args.cats))

    logger.info(f"period={period} cats={category_ids} commands={args.commands}")

    for name in args.commands:
        logger.info(f"=== {name} ===")
        if name == "videos":
            await cmd_videos(
                period,
                category_ids,
                priority=args.priority,
                skip_shorts=args.skip_shorts,
            )
        elif name == "channel-stat":
            await cmd_channel_stat(period, category_ids, force=args.force)
        elif name == "video-stat":
            await cmd_video_stat(period, category_ids, force=args.force)
        elif name == "publish":
            await cmd_publish(period, category_ids)
        elif name == "channel-report":
            await cmd_channel_report()
        elif name == "shorts-sync":
            await cmd_shorts_sync(
                period,
                category_ids,
                priority=args.priority,
                channel_id=args.channel_id,
            )
        elif name == "apply-is-short":
            # None when --cats omitted → all synced channels; else only listed cats
            cats = parse_cats(args.cats)
            await cmd_apply_is_short(
                category_ids=cats,
                channel_id=args.channel_id,
            )
        elif name == "backfill-denorm":
            if not args.period:
                raise SystemExit("backfill-denorm requires --period")
            await cmd_backfill_denorm(
                Period.parse(args.period),
                Period.parse(args.period_to) if args.period_to else None,
                batch_size=args.batch_size,
            )
        elif name == "backfill-channel-denorm":
            if not args.period:
                raise SystemExit("backfill-channel-denorm requires --period")
            await cmd_backfill_channel_denorm(
                Period.parse(args.period),
                Period.parse(args.period_to) if args.period_to else None,
            )
        else:
            raise SystemExit(f"unknown command: {name}")


if __name__ == "__main__":
    main()
