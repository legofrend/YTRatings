from pydantic import BaseModel, ConfigDict, Field
from typing import TYPE_CHECKING, List, Dict, Optional
from app.channel.video.schemas import SVideo

# Убирает предупреждения отсутствия импорта и неприятные подчеркивания в PyCharm и VSCode
# if TYPE_CHECKING:
#     from app.video.schemas import SVideo


class SChannelStat(BaseModel):
    videos: int | None = Field(ge=0)
    shorts: int | None
    duration: int | None
    score: int | None
    score_change: int | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None
    subscriber_count: int | None
    score_new: int | None
    score_old: int | None
    score_shorts: int | None

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
