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
