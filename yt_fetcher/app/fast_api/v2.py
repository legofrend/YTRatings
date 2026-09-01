"""YTRatings API v2 — channel-grain friendly endpoints.

Backed by the existing report blob for now; later swap to channel-level tables.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.report.dao import ReportDAO

router = APIRouter(prefix="/ytr/v2", tags=["ytr-v2"])


@router.get("/report")
async def get_report_v2(
    period: str,
    category_id: int,
    limit: int = Query(10, ge=1, le=100, description="How many channels to return"),
):
    """Same shape as /ytr/report, but truncated and without top_videos payloads."""
    report = await ReportDAO.get(period, category_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    data = deepcopy(report["data"][:limit])
    for ch in data:
        ch["top_videos"] = []

    return {**report, "data": data, "limit": limit}


@router.get("/videos")
async def get_channel_videos_v2(
    period: str,
    channel_id: str,
    limit: int = Query(5, ge=1, le=50, description="Top N videos for the channel"),
):
    """Top videos for one channel in a period (lazy-load on expand)."""
    meta = await ReportDAO.metadata()
    channel = None
    report_period = None

    for cat in meta:
        report = await ReportDAO.get(period, cat.id)
        if not report:
            continue
        channel = next(
            (c for c in report["data"] if c.get("channel_id") == channel_id),
            None,
        )
        if channel:
            report_period = report["period"]
            break

    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found in period")

    videos = list(channel.get("top_videos") or [])[:limit]
    return {
        "period": report_period,
        "channel_id": channel_id,
        "limit": limit,
        "videos": videos,
    }


@router.get("/channel")
async def get_channel_history_v2(
    channel_id: str,
    period_from: str | None = Query(
        None, description="Inclusive start period YYYY-MM-DD; default = last 12 months"
    ),
    period_to: str | None = Query(
        None, description="Inclusive end period YYYY-MM-DD; default = latest available"
    ),
):
    """Channel metrics over time. Default window: last 12 months from latest data."""
    from app.period import Period

    meta = await ReportDAO.metadata()
    points: list[dict[str, Any]] = []
    channel_meta: dict[str, Any] | None = None

    # Collect all appearances across categories/periods (channel belongs to one category).
    for cat in meta:
        for period in cat.periods:
            period_str = period.isoformat() if hasattr(period, "isoformat") else str(period)
            report = await ReportDAO.get(period_str, cat.id)
            if not report:
                continue
            ch = next(
                (c for c in report["data"] if c.get("channel_id") == channel_id),
                None,
            )
            if not ch:
                continue

            if channel_meta is None:
                channel_meta = {
                    "channel_id": ch.get("channel_id"),
                    "channel_title": ch.get("channel_title"),
                    "custom_url": ch.get("custom_url"),
                    "thumbnail_url": ch.get("thumbnail_url"),
                    "category_id": cat.id,
                }

            points.append(
                {
                    "period": report["period"],
                    "rank": ch.get("rank"),
                    "rank_change": ch.get("rank_change"),
                    "stat": ch.get("stat"),
                }
            )

    if not points:
        raise HTTPException(status_code=404, detail="No history for channel")

    def _as_period(value: str | Any) -> Period:
        return Period.parse(str(value))

    points.sort(key=lambda p: _as_period(p["period"]))
    latest = _as_period(points[-1]["period"])

    end = _as_period(period_to) if period_to else latest
    start = _as_period(period_from) if period_from else end.next(-11)

    filtered = [p for p in points if start <= _as_period(p["period"]) <= end]
    if not filtered:
        raise HTTPException(status_code=404, detail="No history in requested period range")

    return {
        "channel": channel_meta,
        "period_from": start.strf(),
        "period_to": end.strf(),
        "points": filtered,
    }
