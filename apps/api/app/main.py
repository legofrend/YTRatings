"""
Monthly pipeline CLI.

Commands:
  auto
      close (days 1–5 UTC) XOR harvest by calendar (never both; see scenarios/)
      [--force]

  fetch-channel-stats
      channel_stat by category (near midnight 1st; fastest, time-sensitive)
      [--force] [--period] [--cats]

  fetch-videos
      playlist → duration → UUSH shorts → apply is_short
      [--skip-duration] [--skip-shorts] [--skip-apply]
      [--only-duration] [--only-shorts]
      [--period] [--cats] [--priority N] [--priority-gt N]
      [--channel-id UC…] [--only-missing]   # with --only-shorts

  fetch-video-stats
      video_stat by category (near midnight after fetch-channel-stats)
      [--force] [--period] [--cats]

  denorm
      video_stat denorm NULLs only (requires --period)
      --period [--period-to] [--batch-size N]

  build-rating
      rebuild channel_rating product table (requires --period)
      --period [--period-to]

  wordstat
      fill (if missing, top N default 40) → MoM type on top 20 by freq → SVG
      [--force] [--skip-svg] [--top N] [--period] [--period-to] [--cats]

  set-channel-priority
      channel.priority = best channel_rating.rank over last N months
      [--months N] [--cats]                 # default months=12

  fetch-logos
      download missing channel logos (VPS; priority<=N, cat sort_order<=5)
      --cats [--priority N] [--workers N] [--dry-run] [--force]

  refresh-thumbnails
      HEAD/GET thumbnail_url; YT detail refresh for broken
      [--cats]

  add-channels
      upsert by @handle into a category (YT forHandle)
      --cats ID --handles @a,@b [--priority N]

  edit-channels
      set category_id / status / priority (dry-run unless --apply)
      --id UC…|@handle | --file PATH
      [--category-id N] [--status 0|1] [--priority N] [--apply]

  diagnose-shorts
      playlist_shorts missing from video (diagnostic)
      [--cats] [--channel-id UC…]

  quota
      local YT quota estimate (PT day, logs/yt_quota/current.json)

Shared:
  --period YYYY-MM|YYYY-MM-DD   default: prev month if day<10, else current
  --cats 1,3,5-8                default: all active by sort_order
  --ntfy off|error|info         override NTFY_LEVEL for this run

Examples:
  python -m app.main fetch-channel-stats --cats 1
  python -m app.main fetch-channel-stats --cats 1 --force
  python -m app.main fetch-videos
  python -m app.main fetch-video-stats --force
  python -m app.main denorm --period 2026-08
  python -m app.main fetch-channel-stats fetch-video-stats --period 2026-07
  python -m app.main fetch-videos --cats 1 --priority 50
  python -m app.main fetch-videos --cats 1 --skip-shorts
  python -m app.main fetch-videos --cats 1 --skip-duration
  python -m app.main fetch-videos --only-duration --cats 19
  python -m app.main fetch-videos --only-shorts --period 2026-08 --cats 1 --channel-id UCxxxxxxxx
  python -m app.main fetch-videos --only-shorts --cats 1 --priority 9999 --only-missing
  python -m app.main fetch-videos --only-shorts --cats 1 --skip-apply
  python -m app.main diagnose-shorts
  python -m app.main diagnose-shorts --cats 1
  python -m app.main denorm --period 2026-08
  python -m app.main build-rating --period 2026-08
  python -m app.main build-rating --period 2025-05 --period-to 2026-07
  python -m app.main refresh-thumbnails
  python -m app.main refresh-thumbnails --cats 7
  python -m app.main fetch-logos --cats 1
  python -m app.main fetch-logos --cats 1 --dry-run
  python -m app.main fetch-logos --cats 1,7,8 --workers 24
  python -m app.main add-channels --cats 19 --handles @mrbeast,@tseries
  python -m app.main add-channels --cats 19 --handles @mrbeast --priority 50
  python -m app.main edit-channels --id UCxxx --status 0
  python -m app.main edit-channels --id @handle --category-id 19
  python -m app.main edit-channels --file edits.jsonl --apply
  # edits.jsonl: {"channel_id":"UCxxx","status":0} or {"id":"@handle","category_id":3,"status":1,"priority":50}
  # edits.csv:   channel_id,category_id,status,priority
  python -m app.main edit-channels --file edits.csv --apply
  python -m app.main quota
  python -m app.main set-channel-priority
  python -m app.main set-channel-priority --cats 1 --months 12
  python -m app.main wordstat
  python -m app.main wordstat --cats 1
  python -m app.main wordstat --cats 1 --period 2026-08 --top 40
  python -m app.main wordstat --cats 1 --period 2026-02 --period-to 2026-08 --force
  python -m app.main wordstat --cats 1 --skip-svg
  python -m app.main fetch-channel-stats --ntfy error
  python -m app.main auto
  python -m app.main auto --force
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime
from pathlib import Path

# Running as file (VS Code F5 on app/main.py) puts .../app on sys.path, not project root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.channel import (
    CategoryDAO,
    ChannelDAO,
    ChannelRatingDAO,
    ChannelStatDAO,
    VideoDAO,
    VideoStatDAO,
)
from app.channel.playlist_shorts.dao import PlaylistShortsDAO
from app.logger import logger
from app import ntfy
from app.period import Period

# Day-of-month cutoff: before this → previous month; on/after → current month.
PERIOD_ROLLOVER_DAY = 10


def default_period(today: date | None = None) -> Period:
    today = today or datetime.now(UTC).date()
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


async def cmd_fetch_channel_stats(
    period: Period, category_ids: list[int], *, force: bool = False
) -> None:
    logger.info(
        f"fetch-channel-stats period={period} cats={category_ids} force={force}"
    )
    await ChannelStatDAO.update_stat(
        report_period=period, category_ids=category_ids, force=force
    )


async def _video_detail(category_ids: list[int] | None) -> None:
    """Fill video.duration via YouTube videos.list (no shorts checks)."""
    logger.info(f"fetch-videos duration cats={category_ids}")
    result = await VideoDAO.update_detail(category_ids=category_ids)
    if result is None:
        raise SystemExit("fetch-videos duration failed")
    logger.info("fetch-videos duration finished OK")


async def _shorts_sync(
    period: Period,
    category_ids: list[int],
    *,
    priority: int | None,
    priority_gt: int | None = None,
    channel_id: str | None = None,
    only_missing: bool = False,
) -> str | None:
    date_from = datetime.combine(period, datetime.min.time())
    date_to = datetime.combine(period.next(1), datetime.min.time())
    channel_ids = [channel_id] if channel_id else None
    logger.info(
        f"fetch-videos shorts-sync period={period} window=[{date_from} .. {date_to}) "
        f"cats={category_ids} channel_id={channel_id} only_missing={only_missing} "
        f"priority={priority} priority_gt={priority_gt}"
    )
    status = await PlaylistShortsDAO.sync_channels(
        category_ids=category_ids,
        date_from=date_from,
        date_to=date_to,
        channel_ids=channel_ids,
        priority=priority,
        priority_gt=priority_gt,
        only_missing=only_missing,
    )
    if status != "ok":
        logger.warning(f"fetch-videos shorts-sync stopped: {status}")
        return status
    return None


async def _apply_is_short(
    *,
    category_ids: list[int] | None = None,
    channel_id: str | None = None,
) -> None:
    """Set video.is_short from playlist_shorts. Window = first short .. last_shorts_fetch_dt."""
    channel_ids = [channel_id] if channel_id else None
    logger.info(f"fetch-videos apply-is-short cats={category_ids} channel_id={channel_id}")
    stats = await VideoDAO.update_is_short_new(
        category_ids=category_ids,
        channel_ids=channel_ids,
        only_null=True,
    )
    logger.info(f"fetch-videos apply-is-short done: {stats}")


async def cmd_fetch_videos(
    period: Period,
    category_ids: list[int] | None,
    *,
    priority: int | None,
    priority_gt: int | None = None,
    skip_shorts: bool = False,
    skip_duration: bool = False,
    skip_apply: bool = False,
    only_duration: bool = False,
    only_shorts: bool = False,
    channel_id: str | None = None,
    only_missing: bool = False,
) -> str | None:
    if only_duration and only_shorts:
        raise SystemExit(
            "fetch-videos: --only-duration and --only-shorts are mutually exclusive"
        )

    if only_duration:
        # None/--cats omitted → all (same as old video-detail)
        await _video_detail(category_ids)
        return None

    if category_ids is None:
        raise SystemExit("fetch-videos requires category_ids (or --only-duration)")

    if only_shorts:
        short_status = await _shorts_sync(
            period,
            category_ids,
            priority=priority,
            priority_gt=priority_gt,
            channel_id=channel_id,
            only_missing=only_missing,
        )
        if short_status:
            return short_status
        if skip_apply:
            logger.info("fetch-videos apply-is-short skipped (--skip-apply)")
            return None
        await _apply_is_short(category_ids=category_ids, channel_id=channel_id)
        return None

    # Exclusive end of report month (e.g. Aug → 2026-09-01). Videos on/after
    # this date belong to the next period.
    date_to = period.next(1)
    logger.info(
        f"fetch-videos period={period} until={date_to} "
        f"cats={category_ids} priority={priority} priority_gt={priority_gt}"
    )
    status = await ChannelDAO.fetch_new_videos(
        category_ids=category_ids,
        date_to=date_to,
        priority=priority,
        priority_gt=priority_gt,
    )
    if status != "ok":
        logger.warning(f"fetch-videos stopped: {status}")
        return status

    if not skip_duration:
        logger.info("fetch-videos duration (missing fields)")
        import app.api.ytapi as yt

        detail = await VideoDAO.update_detail(category_ids=category_ids)
        if detail is None:
            raise SystemExit(
                "fetch-videos duration failed; aborting shorts-sync"
            )
        if yt.IS_QUOTA_EXCEEDED:
            logger.warning(
                "yt quota exceeded after duration; skipping shorts-sync"
            )
            return "quota_exceeded"
    else:
        logger.info("fetch-videos duration skipped (--skip-duration)")

    if skip_shorts:
        logger.info("fetch-videos shorts skipped (--skip-shorts)")
        return None

    logger.info("fetch-videos shorts-sync (UUSH API) + apply-is-short")
    short_status = await _shorts_sync(
        period,
        category_ids,
        priority=priority,
        priority_gt=priority_gt,
        channel_id=None,
    )
    if short_status:
        return short_status
    if skip_apply:
        logger.info("fetch-videos apply-is-short skipped (--skip-apply)")
        return None
    await _apply_is_short(category_ids=category_ids, channel_id=None)
    return None


async def cmd_fetch_video_stats(
    period: Period, category_ids: list[int], *, force: bool = False
) -> None:
    logger.info(
        f"fetch-video-stats period={period} cats={category_ids} force={force}"
    )
    await VideoStatDAO.update_stat(
        report_period=period, category_ids=category_ids, force=force
    )


async def cmd_diagnose_shorts(
    *,
    category_ids: list[int] | None = None,
    channel_id: str | None = None,
) -> None:
    """Diagnostic: playlist_shorts rows with no matching video row."""
    channel_ids = [channel_id] if channel_id else None
    logger.info(f"diagnose-shorts cats={category_ids} channel_id={channel_id}")
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


def _period_range(start: Period, end: Period) -> list[Period]:
    if end < start:
        start, end = end, start
    out: list[Period] = []
    p = start
    while p <= end:
        out.append(p)
        p = p.next(1)
    return out


async def _backfill_video_denorm(
    period_from: Period,
    period_to: Period | None = None,
    *,
    batch_size: int = 10_000,
) -> None:
    """Fill video_stat denorm NULLs for one period or inclusive --period-to range."""
    periods = _period_range(period_from, period_to or period_from)
    logger.info(
        f"denorm video periods={[p.strf('%p') for p in periods]} "
        f"batch_size={batch_size}"
    )
    for i, p in enumerate(periods, start=1):
        logger.info(f"=== denorm video {p.strf('%p')} ({i}/{len(periods)}) ===")
        n = await VideoStatDAO.backfill_denorm(report_period=p, batch_size=batch_size)
        logger.info(f"denorm video {p.strf('%p')}: updated {n}")


async def cmd_denorm(
    period_from: Period,
    period_to: Period | None = None,
    *,
    batch_size: int = 10_000,
) -> None:
    """Fill NULL denorm cols on video_stat (safety net after ingest)."""
    logger.info(
        "denorm video "
        f"period={period_from.strf('%p')}"
        + (f"..{period_to.strf('%p')}" if period_to else "")
    )
    await _backfill_video_denorm(period_from, period_to, batch_size=batch_size)


async def cmd_build_rating(
    period_from: Period,
    period_to: Period | None = None,
) -> None:
    """Rebuild channel_rating for one period or inclusive --period-to range."""
    periods = _period_range(period_from, period_to or period_from)
    logger.info(
        f"build-rating periods={[p.strf('%p') for p in periods]}"
    )
    for i, p in enumerate(periods, start=1):
        logger.info(
            f"=== build-rating {p.strf('%p')} ({i}/{len(periods)}) ==="
        )
        stats = await ChannelRatingDAO.build_rating(report_period=p)
        logger.info(f"build-rating {p.strf('%p')}: {stats}")


async def cmd_refresh_thumbnails(category_ids: list[int] | None) -> None:
    """Check logo URLs; refresh YT detail for broken ones. None cats → all ACTIVE."""
    if not category_ids:
        r = await ChannelDAO.refresh_broken_thumbnails(category_id=None)
        logger.info(
            f"refresh-thumbnails all: checked={r['checked']} "
            f"broken={r['broken']} updated={r['updated']}"
        )
        return
    for cid in category_ids:
        r = await ChannelDAO.refresh_broken_thumbnails(category_id=cid)
        logger.info(
            f"refresh-thumbnails cat={cid}: checked={r['checked']} "
            f"broken={r['broken']} updated={r['updated']}"
        )


async def cmd_fetch_logos(
    category_ids: list[int],
    *,
    priority: int,
    workers: int,
    dry_run: bool,
    force: bool,
) -> None:
    import asyncio

    from app.channel.sync_logos import sync_category_logos

    if not category_ids:
        raise SystemExit("fetch-logos requires --cats (e.g. --cats 1)")

    # SSH/psql/downloads are blocking; run in a thread so the event loop stays sane
    await asyncio.to_thread(
        sync_category_logos,
        category_ids,
        priority=priority,
        workers=workers,
        dry_run=dry_run,
        force=force,
    )


def parse_handles(s: str | None) -> list[str]:
    if not s:
        return []
    out: list[str] = []
    for part in s.replace("\n", ",").split(","):
        part = part.strip()
        if part:
            out.append(part)
    return out


async def cmd_add_channels(
    category_id: int,
    handles: list[str],
    *,
    priority: int = 100,
) -> None:
    if not handles:
        raise SystemExit(
            "add-channels requires --handles (e.g. --handles @mrbeast,@tseries)"
        )
    r = await ChannelDAO.add_by_handles(
        handles,
        category_id=category_id,
        priority=priority,
    )
    logger.info(
        f"add-channels cat={category_id} priority={priority}: "
        f"requested={r['requested']} fetched={r['fetched']} upserted={r['upserted']}"
    )


async def cmd_edit_channels(
    *,
    file: str | None,
    channel_ref: str | None,
    category_id: int | None,
    status: int | None,
    priority: int | None,
    apply: bool,
) -> None:
    from app.channel.edit_channels import (
        ChannelEdit,
        apply_edits,
        edit_from_mapping,
        parse_edits_file,
    )

    edits: list[ChannelEdit] = []
    if file:
        edits.extend(parse_edits_file(Path(file)))
    if channel_ref:
        if category_id is None and status is None and priority is None:
            raise SystemExit(
                "edit-channels --id needs at least one of "
                "--category-id / --status / --priority"
            )
        edits.append(
            edit_from_mapping(
                {
                    "channel_id": channel_ref,
                    "category_id": category_id,
                    "status": status,
                    "priority": priority,
                }
            )
        )
    if not edits:
        raise SystemExit(
            "edit-channels requires --file and/or --id "
            "(with --category-id / --status / --priority)"
        )

    await apply_edits(edits, apply=apply)


async def cmd_quota() -> None:
    from app.api import yt_quota

    snap = yt_quota.status()
    msg = yt_quota.format_status(snap)
    logger.info(msg)
    print(msg)


async def cmd_set_channel_priority(
    category_ids: list[int] | None,
    *,
    months: int = 12,
) -> None:
    logger.info(f"set-channel-priority months={months} cats={category_ids}")
    stats = await ChannelDAO.sync_priority(
        months=months,
        category_ids=category_ids,
    )
    logger.info(f"set-channel-priority done: {stats}")


async def cmd_wordstat(
    category_ids: list[int],
    period: Period,
    period_to: Period | None,
    *,
    top_n: int = 40,
    force: bool = False,
    skip_svg: bool = False,
) -> None:
    """Fill missing cat×periods → MoM type → SVG (unless --skip-svg).

    Default (no --force): skip fill when rows exist; type last 2 months
    relative to end. After any fill / --force: type from period−1 through end.
    SVG covers the same type window (colors depend on MoM type).
    """
    from app.wordstat import WordstatDAO, wordstat2svg_range
    from app.wordstat.dao import _period_range

    end = period_to or period
    periods = _period_range(
        date(period.year, period.month, 1),
        date(end.year, end.month, 1),
    )
    logger.info(
        f"wordstat cats={category_ids} period={period} period_to={period_to} "
        f"top={top_n} force={force} skip_svg={skip_svg}"
    )

    filled_any = False
    for category_id in category_ids:
        for p in periods:
            exists = await WordstatDAO.has_period(category_id, p)
            if not force and exists:
                logger.info(f"wordstat skip fill cat={category_id} period={p} (exists)")
                continue
            stats = await WordstatDAO.fill(
                category_ids=[category_id],
                period_from=p,
                period_to=p,
                top_n=top_n,
            )
            filled_any = True
            logger.info(f"wordstat fill done: {stats}")

    if force or filled_any:
        type_from = period.next(-1)
        type_to = end
    else:
        type_from = end.next(-1)
        type_to = end

    type_stats = await WordstatDAO.backfill_type(
        category_ids=category_ids,
        period_from=type_from,
        period_to=type_to,
    )
    logger.info(
        f"wordstat type done: {type_stats} range={type_from}..{type_to} "
        f"filled_any={filled_any} force={force}"
    )

    if skip_svg:
        logger.info("wordstat skip svg (--skip-svg)")
        return

    svg_stats = await wordstat2svg_range(
        category_ids=category_ids,
        period_from=type_from,
        period_to=type_to,
    )
    logger.info(f"wordstat svg done: {svg_stats}")


COMMANDS = {
    "fetch-channel-stats": cmd_fetch_channel_stats,
    "fetch-videos": cmd_fetch_videos,
    "fetch-video-stats": cmd_fetch_video_stats,
    "denorm": cmd_denorm,
    "build-rating": cmd_build_rating,
    "diagnose-shorts": cmd_diagnose_shorts,
    "refresh-thumbnails": cmd_refresh_thumbnails,
    "fetch-logos": cmd_fetch_logos,
    "add-channels": cmd_add_channels,
    "edit-channels": cmd_edit_channels,
    "quota": cmd_quota,
    "set-channel-priority": cmd_set_channel_priority,
    "wordstat": cmd_wordstat,
    "auto": None,  # handled in _run_parsed
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
        help="one or more: fetch-channel-stats | fetch-videos | fetch-video-stats | denorm | build-rating | diagnose-shorts | refresh-thumbnails | fetch-logos | add-channels | edit-channels | quota | set-channel-priority | wordstat | auto",
    )
    p.add_argument(
        "--period",
        default=None,
        help=f"YYYY-MM or YYYY-MM-DD (default: prev month if day<{PERIOD_ROLLOVER_DAY}, else current); denorm/build-rating require --period",
    )
    p.add_argument(
        "--period-to",
        default=None,
        help="denorm / build-rating / wordstat: inclusive end period YYYY-MM (with --period as start)",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=10_000,
        help="denorm: rows per video_stat UPDATE batch (default 10000)",
    )
    p.add_argument(
        "--top",
        type=int,
        default=40,
        help="wordstat fill: store top-N lexemes (default 40); MoM type uses top 20",
    )
    p.add_argument(
        "--months",
        type=int,
        default=12,
        help="set-channel-priority: lookback months for best channel_rating.rank (default 12)",
    )
    p.add_argument(
        "--cats",
        default=None,
        help="category ids, e.g. 1,3,5-8 (default: all active by sort_order)",
    )
    p.add_argument(
        "--priority",
        type=int,
        default=None,
        help="channel.priority ceiling for fetch-videos/fetch-logos (default 100); "
        "add-channels: set priority (default 100); edit-channels: set priority",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="fetch-channel-stats / fetch-video-stats: refresh all rows (upsert), not only missing; "
        "wordstat: re-fill even if cat×period already exists",
    )
    p.add_argument(
        "--skip-shorts",
        action="store_true",
        help="fetch-videos: skip UUSH shorts-sync + apply-is-short",
    )
    p.add_argument(
        "--skip-svg",
        action="store_true",
        help="wordstat: skip SVG render after fill/type (debug)",
    )
    p.add_argument(
        "--skip-duration",
        action="store_true",
        help="fetch-videos: skip duration backfill (shorts still run unless --skip-shorts)",
    )
    p.add_argument(
        "--skip-apply",
        action="store_true",
        help="fetch-videos: UUSH sync, skip apply is_short",
    )
    p.add_argument(
        "--only-duration",
        action="store_true",
        help="fetch-videos: duration backfill only",
    )
    p.add_argument(
        "--only-shorts",
        action="store_true",
        help="fetch-videos: shorts sync+apply only (mutually exclusive with --only-duration)",
    )
    p.add_argument(
        "--priority-gt",
        type=int,
        default=None,
        help="fetch-videos: only channels with priority > N (or NULL)",
    )
    p.add_argument(
        "--channel-id",
        default=None,
        help="fetch-videos --only-shorts / diagnose-shorts: single channel_id (UC…)",
    )
    p.add_argument(
        "--only-missing",
        action="store_true",
        help="fetch-videos --only-shorts: only channels with last_shorts_fetch_dt IS NULL",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=20,
        help="fetch-logos: parallel download threads on VPS (default 20)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch-logos: only list missing, do not download",
    )
    p.add_argument(
        "--handles",
        default=None,
        help="add-channels: comma-separated @handles or UC… ids (e.g. @mrbeast,@tseries)",
    )
    p.add_argument(
        "--file",
        default=None,
        help="edit-channels: path to .csv / .json / .jsonl batch of edits",
    )
    p.add_argument(
        "--id",
        dest="edit_id",
        default=None,
        help="edit-channels: single UC… id or @handle (with --category-id/--status/--priority)",
    )
    p.add_argument(
        "--category-id",
        type=int,
        default=None,
        help="edit-channels: set channel.category_id",
    )
    p.add_argument(
        "--status",
        type=int,
        default=None,
        help="edit-channels: set channel.status (0=off, 1=on)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="edit-channels: write changes (default is dry-run)",
    )
    p.add_argument(
        "--ntfy",
        choices=["off", "error", "info"],
        default=None,
        help="override NTFY_LEVEL for this run: off | error | info "
        "(default: NTFY_LEVEL from .env)",
    )
    return p


async def _with_ntfy(name: str, coro):
    """Notify step start/done (info) or failure (error)."""
    ntfy.info(f"start {name}", title=f"ytr · {name}")
    try:
        await coro
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            ntfy.error(f"aborted {name}: {e}", title=f"ytr · {name} aborted")
        else:
            ntfy.error(f"FAILED {name}: {e}", title=f"ytr · {name} FAILED")
        raise
    else:
        ntfy.info(f"done {name}", title=f"ytr · {name}")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.commands:
        parser.print_help()
        return

    if args.ntfy is not None:
        ntfy.configure(level=args.ntfy)

    cmds = " ".join(args.commands)
    start_dt = datetime.now()
    print("Start", start_dt)
    ntfy.info(f"pipeline start: {cmds}", title="ytr · start")
    try:
        asyncio.run(_run_parsed(args))
    except BaseException as e:
        elapsed = datetime.now() - start_dt
        print("FAILED after ", elapsed)
        if not isinstance(e, SystemExit) or e.code not in (0, None):
            ntfy.error(
                f"pipeline FAILED after {elapsed}: {cmds}\n{e}",
                title="ytr · FAILED",
            )
        raise
    else:
        elapsed = datetime.now() - start_dt
        print("Finish after ", elapsed)
        print("\a")
        ntfy.info(f"pipeline done after {elapsed}: {cmds}", title="ytr · done")
    finally:
        try:
            from app.api import yt_quota

            yt_quota.flush(reason="main-exit")
            print(yt_quota.format_status())
        except Exception:
            pass


async def _run_parsed(args: argparse.Namespace) -> None:
    from app.api import yt_pending
    from app.api import yt_quota

    yt_quota.ensure_loaded()
    logger.info(yt_quota.format_status())
    logger.info(f"ntfy level={ntfy.effective_level()}")

    if args.commands == ["quota"]:
        await _with_ntfy("quota", cmd_quota())
        return

    if args.commands == ["auto"]:
        from app.pipeline.runner import run_auto

        cats = await resolve_category_ids(parse_cats(args.cats))
        await _with_ntfy(
            "auto",
            run_auto(category_ids=cats, force=args.force),
        )
        return

    if args.commands == ["edit-channels"]:
        await _with_ntfy(
            "edit-channels",
            cmd_edit_channels(
                file=args.file,
                channel_ref=args.edit_id,
                category_id=args.category_id,
                status=args.status,
                priority=args.priority,
                apply=args.apply,
            ),
        )
        return

    n_yt = await yt_pending.flush_pending()
    if n_yt:
        logger.info(f"recovered {n_yt} pending YT rows before commands")

    period = parse_period(args.period)
    category_ids = await resolve_category_ids(parse_cats(args.cats))
    priority = 100 if args.priority is None else args.priority
    priority_gt = args.priority_gt

    logger.info(
        f"period={period} cats={category_ids} commands={args.commands} "
        f"priority={priority} priority_gt={priority_gt}"
    )

    for name in args.commands:
        logger.info(f"=== {name} ===")
        if name == "fetch-videos":
            if args.only_duration and args.only_shorts:
                raise SystemExit(
                    "fetch-videos: --only-duration and --only-shorts "
                    "are mutually exclusive"
                )
            # --only-duration: None/--cats omitted → all (old video-detail)
            fv_cats: list[int] | None = (
                parse_cats(args.cats) if args.only_duration else category_ids
            )
            coro = cmd_fetch_videos(
                period,
                fv_cats,
                priority=priority,
                priority_gt=priority_gt,
                skip_shorts=args.skip_shorts,
                skip_duration=args.skip_duration,
                skip_apply=args.skip_apply,
                only_duration=args.only_duration,
                only_shorts=args.only_shorts,
                channel_id=args.channel_id,
                only_missing=args.only_missing,
            )
        elif name == "fetch-channel-stats":
            coro = cmd_fetch_channel_stats(
                period, category_ids, force=args.force
            )
        elif name == "fetch-video-stats":
            coro = cmd_fetch_video_stats(
                period, category_ids, force=args.force
            )
        elif name == "denorm":
            if not args.period:
                raise SystemExit("denorm requires --period")
            coro = cmd_denorm(
                Period.parse(args.period),
                Period.parse(args.period_to) if args.period_to else None,
                batch_size=args.batch_size,
            )
        elif name == "build-rating":
            if not args.period:
                raise SystemExit("build-rating requires --period")
            coro = cmd_build_rating(
                Period.parse(args.period),
                Period.parse(args.period_to) if args.period_to else None,
            )
        elif name == "diagnose-shorts":
            cats = parse_cats(args.cats)
            coro = cmd_diagnose_shorts(
                category_ids=cats,
                channel_id=args.channel_id,
            )
        elif name == "refresh-thumbnails":
            coro = cmd_refresh_thumbnails(parse_cats(args.cats))
        elif name == "fetch-logos":
            cats = parse_cats(args.cats)
            if not cats:
                raise SystemExit("fetch-logos requires --cats (e.g. --cats 1)")
            coro = cmd_fetch_logos(
                cats,
                priority=priority,
                workers=args.workers,
                dry_run=args.dry_run,
                force=args.force,
            )
        elif name == "add-channels":
            cats = parse_cats(args.cats)
            if not cats or len(cats) != 1:
                raise SystemExit(
                    "add-channels requires exactly one --cats id (e.g. --cats 19)"
                )
            coro = cmd_add_channels(
                cats[0],
                parse_handles(args.handles),
                priority=priority,
            )
        elif name == "edit-channels":
            coro = cmd_edit_channels(
                file=args.file,
                channel_ref=args.edit_id,
                category_id=args.category_id,
                status=args.status,
                priority=args.priority,
                apply=args.apply,
            )
        elif name == "quota":
            coro = cmd_quota()
        elif name == "set-channel-priority":
            # None/--cats omitted → all ACTIVE channels
            coro = cmd_set_channel_priority(
                parse_cats(args.cats), months=args.months
            )
        elif name == "wordstat":
            coro = cmd_wordstat(
                category_ids,
                period,
                Period.parse(args.period_to) if args.period_to else None,
                top_n=args.top,
                force=args.force,
                skip_svg=args.skip_svg,
            )
        else:
            raise SystemExit(f"unknown command: {name}")

        await _with_ntfy(name, coro)

        # Persist between long multi-command runs
        yt_quota.flush(reason=f"after-{name}")
        logger.info(yt_quota.format_status())


if __name__ == "__main__":
    main()
