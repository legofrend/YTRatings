"""
Monthly pipeline CLI.

Commands:
  channel-stat  — channel_stat by category (do near midnight 1st; fastest, time-sensitive)
  videos        — fetch new videos only (use video-detail / shorts-sync separately or chained)
  video-detail  — fill video.duration via videos.list (no shorts HTTP)
  video-stat    — video_stat by category (near midnight after channel-stat; order=sort_order)
  channel-report — alias: backfill-denorm → backfill-channel-denorm (v2 denorm for period)
  shorts-sync   — fetch UUSH playlist into playlist_shorts (API quota)
  apply-is-short — set video.is_short from playlist_shorts (--cats / --channel-id optional)
  shorts-orphans — count/sample playlist_shorts missing from video (diagnostic only)
  backfill-denorm — fill NULL video_stat denorm cols (channel_id/is_short/is_new/period_*)
  backfill-channel-denorm — fill channel_stat denorm (pc_*/pv_*/ppcs_id/ranks) from video_stat
  refresh-thumbnails — HEAD/GET channel.thumbnail_url; YT detail refresh for broken (--cats optional)
  sync-logos — missing channel logos → download on VPS (channel priority<=N, cat sort_order<=5)
  add-channels — upsert channels by @handle into a category (YT forHandle, ~1 quota unit each)
  edit-channels — set category_id/status/priority (single id or --file csv/json/jsonl; dry-run unless --apply)
  quota-status — print local YT quota estimate (PT day, logs/yt_quota/current.json)
  sync-priority — channel.priority = best pv_score_rank over last N months (default 12)
  wordstat-fill — fill wordstat top-N lexemes (longs) for cats×periods; type=NULL
  wordstat-type — backfill wordstat.type from MoM sets (−1/0/1/2)
  auto          — close (days 1–5) and/or harvest by calendar (see scenarios/)

Examples:
  python -m app.main channel-stat --cats 1
  python -m app.main channel-stat --cats 1 --force
  python -m app.main videos
  python -m app.main video-stat --force
  python -m app.main channel-report --period 2026-08
  python -m app.main channel-stat video-stat --period 2026-07
  python -m app.main videos --cats 1 --priority 50
  python -m app.main videos --cats 1 --skip-shorts
  python -m app.main video-detail --cats 19
  python -m app.main shorts-sync --period 2026-08 --cats 1 --channel-id UCxxxxxxxx
  python -m app.main shorts-sync --cats 1 --priority 9999 --only-missing
  python -m app.main apply-is-short --cats 1
  python -m app.main shorts-orphans
  python -m app.main shorts-orphans --cats 1
  python -m app.main videos video-detail shorts-sync apply-is-short --cats 19
  python -m app.main backfill-denorm --period 2026-08
  python -m app.main backfill-denorm --period 2025-05 --period-to 2026-07
  python -m app.main backfill-channel-denorm --period 2025-05 --period-to 2026-08
  python -m app.main refresh-thumbnails
  python -m app.main refresh-thumbnails --cats 7
  python -m app.main sync-logos --cats 1
  python -m app.main sync-logos --cats 1 --dry-run
  python -m app.main sync-logos --cats 1,7,8 --workers 24
  python -m app.main add-channels --cats 19 --handles @mrbeast,@tseries
  python -m app.main add-channels --cats 19 --handles @mrbeast --priority 50
  python -m app.main edit-channels --id UCxxx --status 0
  python -m app.main edit-channels --id @handle --category-id 19
  python -m app.main edit-channels --file scripts/channel_edits.example.jsonl
  python -m app.main edit-channels --file edits.csv --apply
  python -m app.main quota-status
  python -m app.main sync-priority
  python -m app.main sync-priority --cats 1 --months 12
  python -m app.main wordstat-fill --cats 1 --period 2026-02 --period-to 2026-08
  python -m app.main wordstat-fill --cats 1 --period 2026-08 --top 40
  python -m app.main wordstat-type --cats 1
  python -m app.main apply-is-short --cats 1 --ntfy info
  python -m app.main channel-stat --ntfy error
  python -m app.main auto
  python -m app.main auto --force
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
from app.channel.playlist_shorts.dao import PlaylistShortsDAO
from app.logger import logger
from app import ntfy
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
    priority: int | None,
    priority_gt: int | None = None,
    skip_shorts: bool = False,
    skip_detail: bool = False,
) -> str | None:
    # Exclusive end of report month (e.g. Aug → 2026-09-01). Videos on/after
    # this date belong to the next period.
    date_to = period.next(1)
    logger.info(
        f"videos fetch period={period} until={date_to} "
        f"cats={category_ids} priority={priority} priority_gt={priority_gt}"
    )
    status = await ChannelDAO.fetch_new_videos(
        category_ids=category_ids,
        date_to=date_to,
        priority=priority,
        priority_gt=priority_gt,
    )
    if status != "ok":
        logger.warning(f"videos fetch stopped: {status}")
        return status
    if skip_detail:
        logger.info("videos detail/shorts skipped (--skip-detail / scenario)")
        return None
    # Duration/detail — separate from shorts (UUSH path below or video-detail cmd)
    logger.info("videos detail (duration / missing fields)")
    import app.api.ytapi as yt

    detail = await VideoDAO.update_detail(category_ids=category_ids)
    if detail is None:
        raise SystemExit(
            "videos detail failed (duration not written); aborting shorts-sync"
        )
    if yt.IS_QUOTA_EXCEEDED:
        logger.warning(
            "yt quota exceeded after video-detail; skipping shorts-sync"
        )
        return "quota_exceeded"
    if skip_shorts:
        logger.info("videos is_short skipped (--skip-shorts)")
        return None
    # New path: UUSH playlist → playlist_shorts → video.is_short
    logger.info("videos shorts-sync (UUSH API) + apply-is-short")
    short_status = await cmd_shorts_sync(
        period,
        category_ids,
        priority=priority,
        priority_gt=priority_gt,
        channel_id=None,
    )
    if short_status:
        return short_status
    await cmd_apply_is_short(category_ids=category_ids, channel_id=None)
    return None


async def cmd_video_detail(category_ids: list[int] | None) -> None:
    """Fill video.duration via YouTube videos.list (no shorts checks)."""
    logger.info(f"video-detail cats={category_ids}")
    result = await VideoDAO.update_detail(category_ids=category_ids)
    if result is None:
        raise SystemExit("video-detail failed")
    logger.info("video-detail finished OK")


async def cmd_video_stat(
    period: Period, category_ids: list[int], *, force: bool = False
) -> None:
    logger.info(f"video-stat period={period} cats={category_ids} force={force}")
    await VideoStatDAO.update_stat(
        report_period=period, category_ids=category_ids, force=force
    )


async def cmd_publish(period: Period, category_ids: list[int]) -> None:
    """OBSOLETE: nested JSONB in `report` — фронт читает v2 из channel_stat/video_stat.

    Kept for one-off legacy rebuilds; not registered in CLI. Prefer
    channel-stat → video-stat → backfill-denorm → backfill-channel-denorm.
    """
    from app.config import settings

    logger.warning(
        "publish is obsolete (report JSONB unused by frontend v2); "
        f"period={period} cats={category_ids}"
    )
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


async def cmd_channel_report(
    period_from: Period,
    period_to: Period | None = None,
    *,
    batch_size: int = 10_000,
) -> None:
    """Alias for the paired denorm backfills used by API v2.

    Old materialize report_view→channel_report is obsolete (ReportDAO.refresh_channel_report).
    """
    logger.info(
        "channel-report: alias → backfill-denorm + backfill-channel-denorm "
        f"period={period_from.strf('%p')}"
        + (f"..{period_to.strf('%p')}" if period_to else "")
    )
    await cmd_backfill_denorm(period_from, period_to, batch_size=batch_size)
    await cmd_backfill_channel_denorm(period_from, period_to)


async def cmd_shorts_sync(
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
        f"shorts-sync period={period} window=[{date_from} .. {date_to}) "
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
        logger.warning(f"shorts-sync stopped: {status}")
        return status
    return None


async def cmd_shorts_orphans(
    *,
    category_ids: list[int] | None = None,
    channel_id: str | None = None,
) -> None:
    """Diagnostic: playlist_shorts rows with no matching video row."""
    channel_ids = [channel_id] if channel_id else None
    logger.info(
        f"shorts-orphans cats={category_ids} channel_id={channel_id}"
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


async def cmd_sync_logos(
    category_ids: list[int],
    *,
    priority: int,
    workers: int,
    dry_run: bool,
    force: bool,
) -> None:
    import asyncio

    from app.report.sync_logos import sync_category_logos

    if not category_ids:
        raise SystemExit("sync-logos requires --cats (e.g. --cats 1)")

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
        raise SystemExit("add-channels requires --handles (e.g. --handles @mrbeast,@tseries)")
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


async def cmd_quota_status() -> None:
    from app.api import yt_quota

    snap = yt_quota.status()
    msg = yt_quota.format_status(snap)
    logger.info(msg)
    print(msg)


async def cmd_sync_priority(
    category_ids: list[int] | None,
    *,
    months: int = 12,
) -> None:
    logger.info(f"sync-priority months={months} cats={category_ids}")
    stats = await ChannelDAO.sync_priority(
        months=months,
        category_ids=category_ids,
    )
    logger.info(f"sync-priority done: {stats}")


async def cmd_wordstat_fill(
    category_ids: list[int],
    period: Period,
    period_to: Period | None,
    *,
    top_n: int = 40,
) -> None:
    from app.wordstat import WordstatDAO

    logger.info(
        f"wordstat-fill cats={category_ids} period={period} "
        f"period_to={period_to} top={top_n}"
    )
    stats = await WordstatDAO.fill(
        category_ids=category_ids,
        period_from=period,
        period_to=period_to,
        top_n=top_n,
    )
    logger.info(f"wordstat-fill done: {stats}")


async def cmd_wordstat_type(category_ids: list[int] | None) -> None:
    from app.wordstat import WordstatDAO

    logger.info(f"wordstat-type cats={category_ids}")
    stats = await WordstatDAO.backfill_type(category_ids=category_ids)
    logger.info(f"wordstat-type done: {stats}")


async def cmd_wordstat_svg(
    category_ids: list[int],
    period: Period,
    period_to: Period | None,
) -> None:
    from app.wordstat import wordstat2svg_range

    if not category_ids:
        raise SystemExit("wordstat-svg requires --cats")
    logger.info(
        f"wordstat-svg cats={category_ids} period={period} period_to={period_to}"
    )
    stats = await wordstat2svg_range(
        category_ids=category_ids,
        period_from=period,
        period_to=period_to,
    )
    logger.info(f"wordstat-svg done: {stats}")


COMMANDS = {
    "channel-stat": cmd_channel_stat,
    "videos": cmd_videos,
    "video-detail": cmd_video_detail,
    "video-stat": cmd_video_stat,
    "channel-report": cmd_channel_report,
    "shorts-sync": cmd_shorts_sync,
    "apply-is-short": cmd_apply_is_short,
    "shorts-orphans": cmd_shorts_orphans,
    "backfill-denorm": cmd_backfill_denorm,
    "backfill-channel-denorm": cmd_backfill_channel_denorm,
    "refresh-thumbnails": cmd_refresh_thumbnails,
    "sync-logos": cmd_sync_logos,
    "add-channels": cmd_add_channels,
    "edit-channels": cmd_edit_channels,
    "quota-status": cmd_quota_status,
    "sync-priority": cmd_sync_priority,
    "wordstat-fill": cmd_wordstat_fill,
    "wordstat-type": cmd_wordstat_type,
    "wordstat-svg": cmd_wordstat_svg,
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
        help="one or more: channel-stat | videos | video-detail | video-stat | channel-report | shorts-sync | apply-is-short | shorts-orphans | backfill-denorm | backfill-channel-denorm | refresh-thumbnails | sync-logos | add-channels | edit-channels | quota-status | sync-priority | wordstat-fill | wordstat-type | wordstat-svg | auto",
    )
    p.add_argument(
        "--period",
        default=None,
        help=f"YYYY-MM or YYYY-MM-DD (default: prev month if day<{PERIOD_ROLLOVER_DAY}, else current)",
    )
    p.add_argument(
        "--period-to",
        default=None,
        help="backfill-denorm / channel-report / wordstat-fill / wordstat-svg: inclusive end period YYYY-MM (with --period as start)",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=10_000,
        help="backfill-denorm / channel-report: rows per UPDATE batch (default 10000)",
    )
    p.add_argument(
        "--top",
        type=int,
        default=40,
        help="wordstat-fill: top-N lexemes per category×period (default 40)",
    )
    p.add_argument(
        "--months",
        type=int,
        default=12,
        help="sync-priority: lookback months for best pv_score_rank (default 12)",
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
        help="channel.priority ceiling for videos/sync-logos (default 100); "
        "add-channels: set priority (default 100); edit-channels: set priority",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="channel-stat / video-stat: refresh all rows (upsert), not only missing",
    )
    p.add_argument(
        "--skip-shorts",
        action="store_true",
        help="videos: skip UUSH shorts-sync + apply-is-short after detail",
    )
    p.add_argument(
        "--skip-detail",
        action="store_true",
        help="videos: only fetch playlist items (no duration / shorts)",
    )
    p.add_argument(
        "--priority-gt",
        type=int,
        default=None,
        help="videos/shorts-sync: only channels with priority > N (or NULL)",
    )
    p.add_argument(
        "--channel-id",
        default=None,
        help="shorts-sync / apply-is-short / shorts-orphans: single channel_id (UC…)",
    )
    p.add_argument(
        "--only-missing",
        action="store_true",
        help="shorts-sync: only channels with last_shorts_fetch_dt IS NULL (backfill)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=20,
        help="sync-logos: parallel download threads on VPS (default 20)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="sync-logos: only list missing, do not download",
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
    from app.bq import write as bq_write
    from app.config import settings

    yt_quota.ensure_loaded()
    logger.info(yt_quota.format_status())
    logger.info(f"ntfy level={ntfy.effective_level()}")

    if args.commands == ["quota-status"]:
        await _with_ntfy("quota-status", cmd_quota_status())
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

    if settings.RAW_DB == "bigquery":
        n = bq_write.flush_pending_writes()
        if n:
            logger.info(f"recovered {n} pending BQ rows before commands")

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
        if name == "videos":
            coro = cmd_videos(
                period,
                category_ids,
                priority=priority,
                priority_gt=priority_gt,
                skip_shorts=args.skip_shorts,
                skip_detail=args.skip_detail,
            )
        elif name == "video-detail":
            # None/--cats omitted → all; else only listed cats
            cats = parse_cats(args.cats)
            coro = cmd_video_detail(cats)
        elif name == "channel-stat":
            coro = cmd_channel_stat(period, category_ids, force=args.force)
        elif name == "video-stat":
            coro = cmd_video_stat(period, category_ids, force=args.force)
        elif name == "channel-report":
            if not args.period:
                raise SystemExit("channel-report requires --period")
            coro = cmd_channel_report(
                Period.parse(args.period),
                Period.parse(args.period_to) if args.period_to else None,
                batch_size=args.batch_size,
            )
        elif name == "shorts-sync":
            coro = cmd_shorts_sync(
                period,
                category_ids,
                priority=priority,
                priority_gt=priority_gt,
                channel_id=args.channel_id,
                only_missing=args.only_missing,
            )
        elif name == "apply-is-short":
            # None when --cats omitted → all synced channels; else only listed cats
            cats = parse_cats(args.cats)
            coro = cmd_apply_is_short(
                category_ids=cats,
                channel_id=args.channel_id,
            )
        elif name == "shorts-orphans":
            cats = parse_cats(args.cats)
            coro = cmd_shorts_orphans(
                category_ids=cats,
                channel_id=args.channel_id,
            )
        elif name == "backfill-denorm":
            if not args.period:
                raise SystemExit("backfill-denorm requires --period")
            coro = cmd_backfill_denorm(
                Period.parse(args.period),
                Period.parse(args.period_to) if args.period_to else None,
                batch_size=args.batch_size,
            )
        elif name == "backfill-channel-denorm":
            if not args.period:
                raise SystemExit("backfill-channel-denorm requires --period")
            coro = cmd_backfill_channel_denorm(
                Period.parse(args.period),
                Period.parse(args.period_to) if args.period_to else None,
            )
        elif name == "refresh-thumbnails":
            coro = cmd_refresh_thumbnails(parse_cats(args.cats))
        elif name == "sync-logos":
            cats = parse_cats(args.cats)
            if not cats:
                raise SystemExit("sync-logos requires --cats (e.g. --cats 1)")
            coro = cmd_sync_logos(
                cats,
                priority=priority,
                workers=args.workers,
                dry_run=args.dry_run,
                force=args.force,
            )
        elif name == "add-channels":
            cats = parse_cats(args.cats)
            if not cats or len(cats) != 1:
                raise SystemExit("add-channels requires exactly one --cats id (e.g. --cats 19)")
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
        elif name == "quota-status":
            coro = cmd_quota_status()
        elif name == "sync-priority":
            # None/--cats omitted → all ACTIVE channels
            coro = cmd_sync_priority(parse_cats(args.cats), months=args.months)
        elif name == "wordstat-fill":
            if not args.period:
                raise SystemExit("wordstat-fill requires --period")
            coro = cmd_wordstat_fill(
                category_ids,
                Period.parse(args.period),
                Period.parse(args.period_to) if args.period_to else None,
                top_n=args.top,
            )
        elif name == "wordstat-type":
            coro = cmd_wordstat_type(parse_cats(args.cats))
        elif name == "wordstat-svg":
            if not args.period:
                raise SystemExit("wordstat-svg requires --period")
            cats = parse_cats(args.cats)
            if not cats:
                raise SystemExit("wordstat-svg requires --cats")
            coro = cmd_wordstat_svg(
                cats,
                Period.parse(args.period),
                Period.parse(args.period_to) if args.period_to else None,
            )
        else:
            raise SystemExit(f"unknown command: {name}")

        await _with_ntfy(name, coro)

        # Persist between long multi-command runs
        yt_quota.flush(reason=f"after-{name}")
        logger.info(yt_quota.format_status())


if __name__ == "__main__":
    main()
