"""
Local YouTube Data API quota estimate (not Google's source of truth).

- In-memory counter + atomic JSON under logs/yt_quota/
- Day key = America/Los_Angeles (YouTube daily reset)
- Flush every FLUSH_EVERY units, on atexit / SIGINT / SIGTERM, and on demand
"""
from __future__ import annotations

import atexit
import json
import os
import signal
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.logger import logger

QUOTA_DIR = Path("logs/yt_quota")
STATE_NAME = "current.json"
FLUSH_EVERY = 1000
DEFAULT_LIMIT = 10_000
WARN_RATIO = 0.85
PT = ZoneInfo("America/Los_Angeles")

# Classic Data API unit costs (combined daily pool). Approximate.
COSTS: dict[str, int] = {
    "search.list": 100,
    "videos.list": 1,
    "channels.list": 1,
    "playlistItems.list": 1,
}

_lock = threading.Lock()
_used = 0
_by_op: dict[str, int] = {}
_day_pt: str | None = None
_since_flush = 0
_limit = DEFAULT_LIMIT
_hooks_installed = False
_warned = False
_prev_signals: dict[int, Any] = {}


def _day_key(now: datetime | None = None) -> str:
    now = now or datetime.now(tz=PT)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc).astimezone(PT)
    else:
        now = now.astimezone(PT)
    return now.date().isoformat()


def _state_path() -> Path:
    return QUOTA_DIR / STATE_NAME


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _snapshot() -> dict[str, Any]:
    return {
        "day_pt": _day_pt,
        "used": _used,
        "by_op": dict(sorted(_by_op.items())),
        "limit": _limit,
        "flush_every": FLUSH_EVERY,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def _load_unlocked() -> None:
    global _used, _by_op, _day_pt, _since_flush, _limit, _warned
    today = _day_key()
    path = _state_path()
    if not path.exists():
        _used = 0
        _by_op = {}
        _day_pt = today
        _since_flush = 0
        _warned = False
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"yt_quota: bad state file {path}: {e}; starting fresh")
        _used = 0
        _by_op = {}
        _day_pt = today
        _since_flush = 0
        _warned = False
        return

    file_day = str(raw.get("day_pt") or "")
    if file_day != today:
        logger.info(
            f"yt_quota: new PT day {today} (was {file_day or '?'}); reset counter"
        )
        _used = 0
        _by_op = {}
        _day_pt = today
        _since_flush = 0
        _warned = False
        return

    _day_pt = today
    _used = int(raw.get("used") or 0)
    by = raw.get("by_op") or {}
    _by_op = {str(k): int(v) for k, v in by.items()} if isinstance(by, dict) else {}
    _limit = int(raw.get("limit") or DEFAULT_LIMIT)
    _since_flush = 0
    _warned = _used >= int(_limit * WARN_RATIO)


def _flush_unlocked(*, reason: str = "") -> None:
    global _since_flush
    if _day_pt is None:
        _load_unlocked()
    payload = _snapshot()
    _atomic_write(_state_path(), payload)
    _since_flush = 0
    if reason:
        logger.debug(f"yt_quota flush ({reason}): used={_used}")


def ensure_loaded() -> None:
    with _lock:
        if _day_pt is None:
            _load_unlocked()
        install_hooks()


def flush(reason: str = "manual") -> dict[str, Any]:
    with _lock:
        if _day_pt is None:
            _load_unlocked()
        else:
            today = _day_key()
            if _day_pt != today:
                _load_unlocked()
        _flush_unlocked(reason=reason)
        return _snapshot()


def status() -> dict[str, Any]:
    with _lock:
        if _day_pt is None:
            _load_unlocked()
        else:
            today = _day_key()
            if _day_pt != today:
                _load_unlocked()
        snap = _snapshot()
        snap["remaining"] = max(0, int(snap["limit"]) - int(snap["used"]))
        snap["warn_at"] = int(int(snap["limit"]) * WARN_RATIO)
        return snap


def add(op: str, units: int | None = None) -> int:
    """Record one successful (or quotaExceeded) API call. Returns running used."""
    global _used, _since_flush, _warned
    cost = COSTS.get(op) if units is None else units
    if cost is None:
        logger.warning(f"yt_quota: unknown op={op!r}, counting as 1")
        cost = 1
    if cost <= 0:
        return _used

    with _lock:
        if _day_pt is None:
            _load_unlocked()
        today = _day_key()
        if _day_pt != today:
            _flush_unlocked(reason="before-day-roll")
            _load_unlocked()

        _used += cost
        _by_op[op] = _by_op.get(op, 0) + cost
        _since_flush += cost

        if not _warned and _used >= int(_limit * WARN_RATIO):
            _warned = True
            logger.warning(
                f"yt_quota: {_used}/{_limit} units (~{100 * _used / _limit:.0f}%) "
                f"day_pt={_day_pt}"
            )

        if _since_flush >= FLUSH_EVERY:
            _flush_unlocked(reason=f"every-{FLUSH_EVERY}")

        return _used


def _atexit_flush() -> None:
    try:
        flush(reason="atexit")
    except Exception:
        pass


def _signal_flush(signum, frame) -> None:  # noqa: ANN001
    try:
        flush(reason=f"signal-{signum}")
    except Exception:
        pass
    prev = _prev_signals.get(signum)
    if callable(prev):
        prev(signum, frame)
    elif prev == signal.SIG_DFL:
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
    elif signum == getattr(signal, "SIGINT", None):
        raise KeyboardInterrupt


def install_hooks() -> None:
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True
    atexit.register(_atexit_flush)
    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            _prev_signals[sig] = signal.getsignal(sig)
            signal.signal(sig, _signal_flush)
        except (ValueError, OSError):
            # Not main thread / unsupported on platform
            pass


def format_status(snap: dict[str, Any] | None = None) -> str:
    s = snap or status()
    lines = [
        f"yt_quota day_pt={s.get('day_pt')} used={s.get('used')}/"
        f"{s.get('limit')} remaining={s.get('remaining')}",
    ]
    by = s.get("by_op") or {}
    if by:
        parts = [f"{k}={v}" for k, v in by.items()]
        lines.append("  by_op: " + ", ".join(parts))
    return "\n".join(lines)
