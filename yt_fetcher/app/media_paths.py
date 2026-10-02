"""Repo-level generated media (channel logos, wordstat SVGs) — not part of the Nuxt build."""

from __future__ import annotations

import os
from pathlib import Path

# yt_fetcher/app/media_paths.py → parents[2] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]


def repo_root() -> Path:
    return _REPO_ROOT


def media_root() -> Path:
    """Override: YTR_MEDIA_ROOT=/var/www/.../YTRatings/media"""
    if env := os.environ.get("YTR_MEDIA_ROOT"):
        return Path(env)
    return _REPO_ROOT / "media"


def channel_logo_dir() -> Path:
    if env := os.environ.get("CHANNEL_LOGO_DIR"):
        return Path(env)
    return media_root() / "channel_logo"


def wordstat_img_dir() -> Path:
    if env := os.environ.get("WORDSTAT_OUT_DIR"):
        return Path(env)
    return media_root() / "wordstat_img"
