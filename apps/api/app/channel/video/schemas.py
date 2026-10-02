from pydantic import BaseModel, ConfigDict, Field


class SVideoStat(BaseModel):
    duration: int | None
    score: int | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None

    model_config = ConfigDict(from_attributes=True)


class SVideo(BaseModel):
    video_id: str
    title: str
    is_short: int | None
    is_clickbait: int | None
    clickbait_comment: str | None
    video_url: str
    thumbnail_url: str | None
    stat: SVideoStat

    model_config = ConfigDict(from_attributes=True)
