from typing import Optional
from unicodedata import digit
from sqlalchemy.orm import mapped_column, Mapped, relationship
from sqlalchemy import (
    BigInteger,
    Date,
    func,
    UniqueConstraint,
    Computed,
    ForeignKey,
    text,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB

from datetime import datetime, date

from app.database import Base


# if TYPE_CHECKING:
# Убирает предупреждения отсутствия импорта и неприятные подчеркивания в PyCharm и VSCode


class Category(Base):
    __tablename__ = "category"
    active: Mapped[bool] = mapped_column(default=True)
    name: Mapped[str | None]
    title: Mapped[str | None]
    description: Mapped[str | None]


class Channel(Base):
    __tablename__ = "channel"
    category_id: Mapped[Optional[int]]
    channel_id: Mapped[str] = mapped_column(unique=True)
    channel_title: Mapped[str]
    description: Mapped[Optional[str]]
    published_at: Mapped[Optional[datetime]]
    thumbnail_url: Mapped[Optional[str]]
    custom_url: Mapped[Optional[str]]
    status: Mapped[Optional[int]]


class ChannelStat(Base):
    __tablename__ = "channel_stat"
    channel_id: Mapped[str] = mapped_column(ForeignKey("channel.channel_id"))
    data_at: Mapped[datetime]
    report_period: Mapped[Optional[date]] = mapped_column(
        Date, default=func.date_trunc("month", func.current_date).cast(Date)
    )
    channel_view_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    subscriber_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    video_count: Mapped[Optional[int]]


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


class VideoStat(Base):
    __tablename__ = "video_stat"
    video_id: Mapped[str] = mapped_column(ForeignKey("video.video_id"))
    data_at: Mapped[datetime]
    view_count: Mapped[int] = mapped_column(BigInteger)
    like_count: Mapped[int] = mapped_column(BigInteger)
    comment_count: Mapped[int] = mapped_column(BigInteger)
    report_period: Mapped[Optional[date]] = mapped_column(
        Date, default=func.date_trunc("month", func.current_date).cast(Date)
    )
    prev_period: Mapped[date] = mapped_column(
        Computed("report_period - interval '1 month' ")
    )


class Report(Base):
    __tablename__ = "report"
    report_period: Mapped[date]
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"))
    data: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("report_period", "category_id", name="uq_period_category"),
    )


# print("ok")
