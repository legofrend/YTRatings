from typing import Optional

from sqlalchemy import Date, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from datetime import datetime, date

from app.database import Base


class PlaylistShorts(Base):
    __tablename__ = "playlist_shorts"

    video_id: Mapped[str] = mapped_column(unique=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channel.channel_id"))
    title: Mapped[Optional[str]]
    published_at: Mapped[datetime]
    published_at_period: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
