"""
Monthly pipeline CLI.

Commands:
  channel-stat  — channel_stat by category (do near midnight 1st; fastest, time-sensitive)
  videos        — fetch new videos + detail/is_short (anytime; resume via DB holes)
  video-stat    — video_stat by category (near midnight after channel-stat; cat 1 first)
  publish       — build report in BQ + sync to PG
  channel-report — materialize report_view → channel_report table in PG

Examples:
  python -m app.main channel-stat --cats 1
  python -m app.main channel-stat --cats 1 --force
  python -m app.main videos
  python -m app.main video-stat --force
  python -m app.main publish
  python -m app.main channel-report
  python -m app.main channel-stat video-stat --period 2026-07
  python -m app.main videos --cats 1 --priority 50
  python -m app.main videos --cats 1 --skip-shorts
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
    # category 1 first (quota), then sort_order, then id
    rows.sort(
        key=lambda r: (
            0 if r["id"] == 1 else 1,
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
    logger.info(f"publish build_in_bq period={period} cats={category_ids}")
    await ReportDAO.build_in_bq(period, category_ids)
    logger.info(f"publish sync_from_bq period={period} cats={category_ids}")
    await ReportDAO.sync_from_bq(period, category_ids)


async def cmd_channel_report() -> None:
    logger.info("channel-report: materialize report_view → channel_report")
    await ReportDAO.refresh_channel_report()


COMMANDS = {
    "channel-stat": cmd_channel_stat,
    "videos": cmd_videos,
    "video-stat": cmd_video_stat,
    "publish": cmd_publish,
    "channel-report": cmd_channel_report,
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
        help="one or more: channel-stat | videos | video-stat | publish | channel-report",
    )
    p.add_argument(
        "--period",
        default=None,
        help=f"YYYY-MM or YYYY-MM-DD (default: prev month if day<{PERIOD_ROLLOVER_DAY}, else current)",
    )
    p.add_argument(
        "--cats",
        default=None,
        help="category ids, e.g. 1,3,5-8 (default: all active, id=1 first)",
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
        else:
            raise SystemExit(f"unknown command: {name}")


if __name__ == "__main__":
    main()
