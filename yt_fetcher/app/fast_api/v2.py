"""YTRatings API v2 — channel_stat / video_stat backed endpoints."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.channel import CategoryDAO, ChannelStatDAO, VideoStatDAO
from app.period import Period

router = APIRouter(prefix="/ytr/v2", tags=["ytr-v2"])

SEARCH_VIDEOS_CHANNEL_ID = "__search_videos__"
SEARCH_VIDEOS_TITLE = "Видео"


def _parse_period_opt(value: str | None) -> Period | None:
    if not value:
        return None
    return Period.parse(value)


def _synthetic_videos_channel(
    *,
    videos: list[dict],
    report_period: date,
    category_id: int | None,
) -> dict:
    row = {
        "channel_id": SEARCH_VIDEOS_CHANNEL_ID,
        "channel_title": SEARCH_VIDEOS_TITLE,
        "description": "Видео, найденные по названию",
        "custom_url": None,
        "thumbnail_url": None,
        "category_id": category_id,
        "category_name": None,
        "top_videos": videos,
        "force_expanded": True,
    }
    return ChannelStatDAO._zero_channel_stats(row, report_period)


@router.get("/categories")
async def list_categories():
    """Active categories: id, name, title, description, sys_name, sort_order."""
    return await CategoryDAO.list_active()


@router.get("/periods")
async def list_periods(category_id: int = Query(..., description="Category id")):
    """Periods that have ranked channel_stat for the category (newest first)."""
    periods = await ChannelStatDAO.periods_for_category(category_id)
    if not periods:
        raise HTTPException(status_code=404, detail="No periods for category")
    return {
        "category_id": category_id,
        "periods": [p.isoformat() for p in periods],
    }


@router.get("/channels")
async def list_channels(
    category_id: int = Query(..., description="Category id"),
    period: str | None = Query(
        None, description="Report period YYYY-MM-DD; default = latest available"
    ),
    limit: int = Query(20, ge=1, le=100, description="Top N channels"),
    videos_limit: int = Query(
        0,
        ge=0,
        le=20,
        description="If >0, attach top N new videos for first videos_for channels",
    ),
    videos_for: int = Query(
        10,
        ge=0,
        le=50,
        description="How many top channels get embedded videos (when videos_limit>0)",
    ),
):
    """Top channels for category+period from channel_stat JOIN channel."""
    if period:
        report_period = Period.parse(period)
    else:
        latest = await ChannelStatDAO.latest_period(category_id)
        if not latest:
            raise HTTPException(status_code=404, detail="No data for category")
        report_period = Period.parse(str(latest))

    channels = await ChannelStatDAO.top_channels(
        category_id=category_id,
        report_period=report_period,
        limit=limit,
    )
    if not channels:
        raise HTTPException(status_code=404, detail="No channels for category/period")

    if videos_limit > 0 and videos_for > 0:
        ids = [c["channel_id"] for c in channels[:videos_for] if c.get("channel_id")]
        by_ch = await VideoStatDAO.top_for_channels(
            channel_ids=ids,
            report_period=report_period,
            limit=videos_limit,
        )
        for ch in channels:
            cid = ch.get("channel_id")
            if cid in by_ch:
                ch["top_videos"] = by_ch[cid]

    return {
        "category_id": category_id,
        "period": report_period.strf(),
        "limit": limit,
        "videos_limit": videos_limit,
        "videos_for": videos_for if videos_limit > 0 else 0,
        "channels": channels,
    }


@router.get("/search")
async def search(
    query: str = Query(..., min_length=1, description="Search string"),
    type: Literal["channel", "video", "all"] = Query(
        "channel",
        description="Search channels, videos, or both (default: channel)",
    ),
    category_id: int | None = Query(None, description="Optional category filter"),
    channel_id: str | None = Query(
        None, description="Optional channel filter (video title search)"
    ),
    period: str | None = Query(
        None,
        description="Period for channel/video stats YYYY-MM-DD; default = latest",
    ),
    period_from: str | None = Query(
        None,
        description=(
            "Video publish range start (month date). "
            "Default = period (stats month)"
        ),
    ),
    period_to: str | None = Query(
        None,
        description=(
            "Video publish range end exclusive (next month date). "
            "Default = period + 1 month"
        ),
    ),
    limit_ch: int = Query(20, ge=1, le=100, description="Max channels in response"),
    limit_v: int = Query(20, ge=1, le=100, description="Max videos in response"),
):
    """Search channels (title/handle) and/or videos (title). Same shape as /channels."""
    q = query.strip()
    if not q:
        raise HTTPException(status_code=422, detail="query must not be empty")

    if channel_id and type == "channel":
        raise HTTPException(
            status_code=422,
            detail="channel_id only applies to type=video|all",
        )
    if (period_from or period_to) and type == "channel":
        raise HTTPException(
            status_code=422,
            detail="period_from/period_to only apply to type=video|all",
        )

    p_from = _parse_period_opt(period_from)
    p_to = _parse_period_opt(period_to)

    if period:
        report_period = Period.parse(period)
    elif category_id is not None:
        latest = await ChannelStatDAO.latest_period(category_id)
        if not latest:
            latest = await ChannelStatDAO.latest_period_any()
        if not latest:
            raise HTTPException(status_code=404, detail="No periods available")
        report_period = Period.parse(str(latest))
    else:
        latest = await ChannelStatDAO.latest_period_any()
        if not latest:
            raise HTTPException(status_code=404, detail="No periods available")
        report_period = Period.parse(str(latest))

    # Video publish window: default = [period, period+1month) exclusive end
    if type in ("video", "all"):
        if p_from is None:
            p_from = report_period
        if p_to is None:
            p_to = Period.parse(str(p_from)).next(1)
        if p_from >= p_to:
            raise HTTPException(
                status_code=422,
                detail="period_from must be < period_to (period_to is exclusive)",
            )

    report_date = date(report_period.year, report_period.month, 1)
    channels: list[dict] = []
    category_fallback = False

    if type in ("channel", "all"):
        channels = await ChannelStatDAO.search_channels(
            query=q,
            report_period=report_period,
            limit=limit_ch,
            category_id=category_id,
        )
        # If nothing in category — broaden to all categories (before video block).
        if category_id is not None and not channels:
            channels = await ChannelStatDAO.search_channels(
                query=q,
                report_period=report_period,
                limit=limit_ch,
                category_id=None,
            )
            category_fallback = bool(channels)

    if type in ("video", "all"):
        videos = await VideoStatDAO.search_by_title(
            query=q,
            report_period=report_period,
            limit=limit_v,
            category_id=category_id if type == "video" else None,
            channel_id=channel_id,
            period_from=p_from,
            period_to=p_to,
        )
        if videos:
            channels.append(
                _synthetic_videos_channel(
                    videos=videos,
                    report_period=report_date,
                    category_id=category_id,
                )
            )

    return {
        "category_id": category_id,
        "period": report_period.strf(),
        "period_from": p_from.strf() if p_from else None,
        "period_to": p_to.strf() if p_to else None,
        "query": q,
        "type": type,
        "limit_ch": limit_ch,
        "limit_v": limit_v,
        "category_fallback": category_fallback,
        "channels": channels,
    }


@router.get("/videos")
async def list_videos(
    period: str = Query(..., description="Report period YYYY-MM-DD"),
    channel_id: str | None = Query(None, description="YouTube channel id"),
    category_id: int | None = Query(
        None, description="Category id (top videos across category)"
    ),
    limit: int = Query(10, ge=1, le=50, description="Top N videos"),
):
    """Top new videos for channel+period, or category+period if channel omitted."""
    if not channel_id and category_id is None:
        raise HTTPException(
            status_code=422,
            detail="Provide channel_id or category_id",
        )
    if channel_id and category_id is not None:
        raise HTTPException(
            status_code=422,
            detail="Pass only one of channel_id or category_id",
        )

    report_period = Period.parse(period)
    if channel_id:
        videos = await VideoStatDAO.top_for_channel(
            channel_id=channel_id,
            report_period=report_period,
            limit=limit,
        )
        return {
            "channel_id": channel_id,
            "category_id": None,
            "period": report_period.strf(),
            "limit": limit,
            "videos": videos,
        }

    videos = await VideoStatDAO.top_for_category(
        category_id=category_id,
        report_period=report_period,
        limit=limit,
    )
    return {
        "channel_id": None,
        "category_id": category_id,
        "period": report_period.strf(),
        "limit": limit,
        "videos": videos,
    }


@router.get("/channel")
async def channel_dynamics(
    channel_id: str = Query(..., description="YouTube channel id"),
    months: int = Query(12, ge=1, le=60, description="How many latest months"),
):
    """Channel rank + view-index (pv_score) over the last M months."""
    data = await ChannelStatDAO.channel_dynamics(
        channel_id=channel_id,
        months=months,
    )
    if not data or not data["points"]:
        raise HTTPException(status_code=404, detail="No history for channel")

    points = data["points"]
    return {
        "channel": data["channel"],
        "months": months,
        "period_from": points[0]["report_period"],
        "period_to": points[-1]["report_period"],
        "points": points,
    }


@router.get("/category")
async def category_dynamics(
    category_id: int = Query(..., description="Category id"),
    limit: int = Query(
        20, ge=1, le=100, description="Top N channels per month to sum"
    ),
    months: int = Query(12, ge=1, le=60, description="How many latest months"),
):
    """Sum of score / view buckets for top-N channels in category, per month."""
    data = await ChannelStatDAO.category_dynamics(
        category_id=category_id,
        limit=limit,
        months=months,
    )
    if not data or not data["points"]:
        raise HTTPException(status_code=404, detail="No history for category")

    points = data["points"]
    return {
        "category_id": data["category_id"],
        "limit": data["limit"],
        "months": data["months"],
        "period_from": points[0]["report_period"],
        "period_to": points[-1]["report_period"],
        "points": points,
    }
