"""Push notifications via ntfy (https://ntfy.sh).

Levels mirror logging verbosity:
  off   — nothing
  error — failures only
  info  — step start/stop + failures

Config: NTFY_SERVER, NTFY_TOPIC, NTFY_LEVEL.
CLI: --ntfy off|error|info overrides LEVEL for one run.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Literal

from app.config import settings
from app.logger import logger

NtfyLevel = Literal["off", "error", "info"]

_LEVEL_RANK: dict[str, int] = {"off": 0, "error": 1, "info": 2}

_level: NtfyLevel = settings.NTFY_LEVEL  # type: ignore[assignment]
_topic: str = (settings.NTFY_TOPIC or "").strip()
_server: str = (settings.NTFY_SERVER or "https://ntfy.sh").rstrip("/")


def configure(
    *,
    level: NtfyLevel | None = None,
    topic: str | None = None,
    server: str | None = None,
) -> None:
    """Apply runtime overrides (CLI). Call once at process start."""
    global _level, _topic, _server
    if level is not None:
        if level not in _LEVEL_RANK:
            raise ValueError(f"invalid ntfy level: {level}")
        _level = level
    if topic is not None:
        _topic = topic.strip()
    if server is not None:
        _server = server.rstrip("/")


def effective_level() -> NtfyLevel:
    return _level


def _enabled_for(msg_level: NtfyLevel) -> bool:
    if not _topic:
        return False
    return _LEVEL_RANK[msg_level] <= _LEVEL_RANK[_level] and _level != "off"


def notify(
    message: str,
    *,
    level: NtfyLevel = "info",
    title: str | None = None,
    priority: str | None = None,
    tags: str | None = None,
) -> bool:
    """POST to ntfy. Never raises — notify must not break the pipeline."""
    if level == "off" or not _enabled_for(level):
        return False
    url = f"{_server}/{_topic}"
    headers: dict[str, str] = {}
    if title:
        headers["Title"] = title
    if priority:
        headers["Priority"] = priority
    if tags:
        headers["Tags"] = tags
    # default priority: errors louder
    if priority is None and level == "error":
        headers["Priority"] = "high"
        headers.setdefault("Tags", "x")
    try:
        req = urllib.request.Request(
            url,
            data=message.encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        logger.warning(f"ntfy failed: {e}")
        return False


def info(message: str, *, title: str | None = None) -> bool:
    return notify(message, level="info", title=title, tags="information_source")


def error(message: str, *, title: str | None = None) -> bool:
    return notify(message, level="error", title=title, priority="high", tags="x")
