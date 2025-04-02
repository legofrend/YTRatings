from typing import Optional
from sqlalchemy.orm import mapped_column, Mapped, relationship
from sqlalchemy import (
    BigInteger,
    Date,
    func,
    Computed,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB

from datetime import datetime, date

from app.database import Base


# if TYPE_CHECKING:
# Убирает предупреждения отсутствия импорта и неприятные подчеркивания в PyCharm и VSCode


class Video(Base):
    __tablename__ = "video"
    video_id: Mapped[str] = mapped_column(unique=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channel.channel_id"))
    title: Mapped[str]
    description: Mapped[Optional[str]]
    published_at: Mapped[datetime]
    published_at_period: Mapped[date | None]
    # mapped_column(Computed("cast(date_trunc('month', published_at::date) as Date)"))
    # Date, server_default=func.date_trunc("month", published_at).cast(Date)

    video_url: Mapped[Optional[str]]
    thumbnail_url: Mapped[Optional[str]]
    duration: Mapped[int | None]
    is_short: Mapped[bool | None]
    is_clickbait: Mapped[bool | None]
    clickbait_comment: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    data: Mapped[dict] = mapped_column(JSONB, server_default="{}")


class VideoStat(Base):
    __tablename__ = "video_stat"
    video_id: Mapped[str] = mapped_column(ForeignKey("video.video_id"))
    data_at: Mapped[datetime]
    view_count: Mapped[int] = mapped_column(BigInteger)
    like_count: Mapped[int] = mapped_column(BigInteger)
    comment_count: Mapped[int] = mapped_column(BigInteger)
    report_period: Mapped[Optional[date]] = mapped_column(
        Date, default=func.date_trunc("month", func.current_date()).cast(Date)
    )
    prev_period: Mapped[date] = mapped_column(
        Computed("report_period - interval '1 month' ")
    )


# print("ok")
