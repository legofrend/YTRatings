"""
YouTube API → DB write safety (same idea as app.bq.write pending dumps).

Flow: fetch from YT → dump rows to logs/yt_pending/ → write DB → delete dump.
On failure the dump stays; flush_pending() / next commit for that op replays it
so we do not re-hit the YouTube API.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.logger import logger

PENDING_DIR = Path("logs/yt_pending")

# Fields revived from ISO strings after JSON round-trip
_DT_KEYS = frozenset(
    {
        "published_at",
        "data_at",
        "created_at",
        "updated_at",
        "last_video_fetch_dt",
        "last_shorts_fetch_dt",
    }
)
_DATE_KEYS = frozenset({"published_at_period", "report_period"})

Writer = Callable[[list[dict], dict], Awaitable[bool]]


def _safe_scope(scope: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", scope.strip()) or "default"
    return s[:120]


def pending_path(op: str, scope: str = "default") -> Path:
    return PENDING_DIR / f"{_safe_scope(op)}__{_safe_scope(scope)}.json"


def _convert(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _convert(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_convert(v) for v in value]
    return value


def _normalize_rows(rows: list[dict]) -> list[dict]:
    return [{k: _convert(v) for k, v in row.items()} for row in rows]


def _revive_value(key: str, value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    if key in _DT_KEYS:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(
                tzinfo=None
            )
        except ValueError:
            return value
    if key in _DATE_KEYS:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return value
    return value


def _revive_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        out.append({k: _revive_value(k, v) for k, v in row.items()})
    return out


def _save_pending(path: Path, payload: dict) -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8"
    )
    tmp.replace(path)
    n = len(payload.get("rows") or [])
    logger.info(f"YT pending dump written: {path.name} ({n} rows)")


def _clear_pending(path: Path) -> None:
    if path.exists():
        path.unlink()
        logger.info(f"YT pending dump cleared: {path.name}")


def _load_pending(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


async def _write_video_detail(rows: list[dict], meta: dict) -> bool:
    from app.channel.video.dao import VideoDAO

    # Match skip_shorts path: duration only; is_short via UUSH later
    payload = []
    for row in rows:
        r = dict(row)
        r.pop("is_short", None)
        payload.append(r)
    return await VideoDAO.update_bulk(payload)


async def _write_video_insert(rows: list[dict], meta: dict) -> bool:
    from app.channel.video.dao import VideoDAO

    return await VideoDAO.add_update_bulk(rows, do_nothing=True)


async def _write_playlist_shorts(rows: list[dict], meta: dict) -> bool:
    from app.channel.playlist_shorts.dao import PlaylistShortsDAO

    return await PlaylistShortsDAO.add_update_bulk(rows)


async def _write_channel_detail_update(rows: list[dict], meta: dict) -> bool:
    from app.channel.dao import ChannelDAO

    return await ChannelDAO.update_bulk(rows, identifier="channel_id")


async def _write_channel_detail_upsert(rows: list[dict], meta: dict) -> bool:
    from app.channel.dao import ChannelDAO

    do_nothing = bool(meta.get("do_nothing"))
    return await ChannelDAO.add_update_bulk(rows, do_nothing=do_nothing)


async def _write_channel_detail_handles(rows: list[dict], meta: dict) -> bool:
    from app.channel.dao import ChannelDAO

    return await ChannelDAO.upsert_yt_handle_rows(rows)


async def _write_video_stat(rows: list[dict], meta: dict) -> bool:
    from app.channel.video.dao import VideoStatDAO
    from app.config import settings

    if settings.RAW_DB == "bigquery":
        from app.channel.video.dao_bq import VideoStatBqDAO

        await VideoStatBqDAO.add_bulk(rows)
        return True
    res = await VideoStatDAO.add_bulk(rows)
    return res is not False


async def _write_channel_stat(rows: list[dict], meta: dict) -> bool:
    from app.channel.dao import ChannelStatDAO
    from app.config import settings

    if settings.RAW_DB == "bigquery":
        from app.channel.dao_bq import ChannelStatBqDAO

        await ChannelStatBqDAO.add_bulk(rows)
        return True
    res = await ChannelStatDAO.add_bulk(rows)
    return res is not False


async def _write_video_status(rows: list[dict], meta: dict) -> bool:
    from app.channel.video.dao import VideoDAO
    from app.config import settings

    if settings.RAW_DB == "bigquery":
        from app.channel.video.dao_bq import VideoBqDAO

        await VideoBqDAO.update_bulk(rows)
        return True
    return await VideoDAO.update_bulk(rows)


WRITERS: dict[str, Writer] = {
    "video_detail": _write_video_detail,
    "video_insert": _write_video_insert,
    "playlist_shorts": _write_playlist_shorts,
    "channel_detail_update": _write_channel_detail_update,
    "channel_detail_upsert": _write_channel_detail_upsert,
    "channel_detail_handles": _write_channel_detail_handles,
    "video_stat": _write_video_stat,
    "channel_stat": _write_channel_stat,
    "video_status": _write_video_status,
}


async def _replay(path: Path) -> int:
    payload = _load_pending(path)
    if not payload:
        return 0
    op = payload.get("op")
    rows = _revive_rows(payload.get("rows") or [])
    meta = payload.get("meta") or {}
    writer = WRITERS.get(op)
    if not writer:
        logger.error(f"YT pending unknown op={op} in {path}; leaving file")
        return 0
    logger.info(f"YT replaying pending {path.name} op={op} rows={len(rows)}")
    ok = await writer(rows, meta)
    if ok:
        _clear_pending(path)
        return len(rows)
    logger.error(f"YT replay failed; kept {path}")
    return 0


async def flush_pending() -> int:
    """Replay all dumps in logs/yt_pending/. Call at pipeline start."""
    if not PENDING_DIR.exists():
        return 0
    total = 0
    for path in sorted(PENDING_DIR.glob("*.json")):
        total += await _replay(path)
    if total:
        logger.info(f"YT flushed pending dumps: {total} rows")
    return total


async def commit_rows(
    op: str,
    rows: list[dict],
    *,
    scope: str = "default",
    meta: dict | None = None,
) -> bool:
    """
    Dump-first write. If a pending file for (op, scope) already exists, replay it
    first (same as BQ). On write failure the new dump is kept for the next run.
    """
    if op not in WRITERS:
        raise ValueError(f"unknown YT pending op: {op}")

    path = pending_path(op, scope)
    if path.exists():
        await _replay(path)

    if not rows:
        return True

    meta = meta or {}
    _save_pending(
        path,
        {
            "op": op,
            "scope": scope,
            "meta": meta,
            "rows": _normalize_rows(rows),
        },
    )
    try:
        ok = await WRITERS[op](rows, meta)
        if ok:
            _clear_pending(path)
        else:
            logger.error(f"YT write failed; pending kept at {path}")
        return ok
    except Exception:
        logger.error(f"YT write exception; pending kept at {path}", exc_info=True)
        raise
