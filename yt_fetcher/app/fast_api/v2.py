"""YTRatings API v2 — channel_stat / video_stat backed endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.channel import CategoryDAO, ChannelStatDAO, VideoStatDAO
from app.period import Period

router = APIRouter(prefix="/ytr/v2", tags=["ytr-v2"])


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

    return {
        "category_id": category_id,
        "period": report_period.strf(),
        "limit": limit,
        "channels": channels,
    }


@router.get("/videos")
async def list_videos(
    channel_id: str = Query(..., description="YouTube channel id"),
    period: str = Query(..., description="Report period YYYY-MM-DD"),
    limit: int = Query(10, ge=1, le=50, description="Top N videos"),
):
    """Top new videos for channel+period from video_stat JOIN video."""
    report_period = Period.parse(period)
    videos = await VideoStatDAO.top_for_channel(
        channel_id=channel_id,
        report_period=report_period,
        limit=limit,
    )
    return {
        "channel_id": channel_id,
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
