from pydantic import BaseModel, ConfigDict, Field
from typing import TYPE_CHECKING, List, Dict, Optional
from app.channel.video.schemas import SVideo

# Убирает предупреждения отсутствия импорта и неприятные подчеркивания в PyCharm и VSCode
# if TYPE_CHECKING:
#     from app.video.schemas import SVideo


class SChannelStat(BaseModel):
    videos: int | None = Field(ge=0)
    video_clickbaits: int | None  # new
    shorts: int | None
    duration: int | None
    score: int | None
    score_change: int | None
    view_count: int | None
    view_count_new_video: int | None  # new
    view_count_new_short: int | None  # new
    view_count_old_video: int | None  # new
    view_count_old_short: int | None  # new
    total_view_count_change: int | None  # new
    view_count_check: int | None  # new
    like_count: int | None
    comment_count: int | None
    subscriber_count: int | None
    subscriber_count_change: int | None  # new

    model_config = ConfigDict(from_attributes=True)


class SChannel(BaseModel):
    channel_id: str
    channel_title: str
    description: Optional[str] = ""
    rank: int
    rank_change: int | None
    custom_url: str | None
    thumbnail_url: str | None
    stat: SChannelStat
    top_videos: List[SVideo]

    model_config = ConfigDict(from_attributes=True)


# print("ok")
