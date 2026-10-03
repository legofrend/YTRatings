from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class SPlaylistShorts(BaseModel):
    video_id: str
    channel_id: str
    title: str | None = None
    published_at: datetime
    published_at_period: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
