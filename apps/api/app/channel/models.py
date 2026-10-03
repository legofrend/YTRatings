from enum import IntEnum
from typing import Optional
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import (
    BigInteger,
    Date,
    UniqueConstraint,
    func,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSONB

from datetime import datetime, date

from app.database import Base


class ChannelStatus(IntEnum):
    DELETED = 0  # удалён / недоступен
    ACTIVE = 1
    NO_RECENT_VIDEOS = 2  # нет видео за последние 6 мес
    LOW_VIEWS = 3  # слишком мало просмотров
    LOW_SUBS = 4  # мало подписчиков
    WRONG_LANGUAGE = 5  # канал не на том языке
    WRONG_CATEGORY = 6  # канал не в той категории
    MANUAL_OFF = 7  # ручная деактивация


class Channel(Base):
    __tablename__ = "channel"
    channel_id: Mapped[str] = mapped_column(unique=True)
    channel_title: Mapped[str]
    description: Mapped[Optional[str]]
    custom_url: Mapped[Optional[str]]
    thumbnail_url: Mapped[Optional[str]]

    category_id: Mapped[Optional[int]]
    status: Mapped[Optional[int]]  # ChannelStatus
    priority: Mapped[Optional[int]]

    published_at: Mapped[Optional[datetime]]
    last_video_fetch_dt: Mapped[Optional[datetime]]
    last_shorts_fetch_dt: Mapped[Optional[datetime]]

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    data: Mapped[dict] = mapped_column(JSONB, server_default="{}")


class ChannelStat(Base):
    """YT channel snapshot × period (raw ingest)."""

    __tablename__ = "channel_stat"

    channel_id: Mapped[str] = mapped_column(ForeignKey("channel.channel_id"))

    data_at: Mapped[datetime]
    report_period: Mapped[Optional[date]] = mapped_column(
        Date, default=func.date_trunc("month", func.current_date()).cast(Date)
    )

    channel_view_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    subscriber_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    video_count: Mapped[Optional[int]]

    # legacy denorm (still on VPS until cleanup migrate); unused by API
    pc_view: Mapped[Optional[int]] = mapped_column(BigInteger)
    pc_subscriber: Mapped[Optional[int]] = mapped_column(BigInteger)
    pc_video: Mapped[Optional[int]]
    ppcs_id: Mapped[Optional[int]]
    updated_at: Mapped[Optional[datetime]]


class ChannelRating(Base):
    """Materialized monthly rating — API product (self-contained snapshot)."""

    __tablename__ = "channel_rating"
    __table_args__ = (
        UniqueConstraint("channel_id", "report_period", name="uq_channel_rating"),
    )

    channel_id: Mapped[str] = mapped_column(ForeignKey("channel.channel_id"))
    report_period: Mapped[date] = mapped_column(Date)

    channel_title: Mapped[Optional[str]]
    description: Mapped[Optional[str]]
    custom_url: Mapped[Optional[str]]
    thumbnail_url: Mapped[Optional[str]]
    category_id: Mapped[Optional[int]]

    stats_at: Mapped[Optional[datetime]]

    channel_views: Mapped[Optional[int]] = mapped_column(BigInteger)
    channel_subscribers: Mapped[Optional[int]] = mapped_column(BigInteger)
    channel_videos: Mapped[Optional[int]]

    channel_views_mom: Mapped[Optional[int]] = mapped_column(BigInteger)
    channel_subscribers_mom: Mapped[Optional[int]] = mapped_column(BigInteger)
    channel_videos_mom: Mapped[Optional[int]]

    new_longs: Mapped[Optional[int]]
    new_shorts: Mapped[Optional[int]]
    duration_sec: Mapped[Optional[int]] = mapped_column(BigInteger)
    video_views: Mapped[Optional[int]] = mapped_column(BigInteger)
    views_new_long: Mapped[Optional[int]] = mapped_column(BigInteger)
    views_new_short: Mapped[Optional[int]] = mapped_column(BigInteger)
    views_old_long: Mapped[Optional[int]] = mapped_column(BigInteger)
    views_old_short: Mapped[Optional[int]] = mapped_column(BigInteger)
    video_likes: Mapped[Optional[int]] = mapped_column(BigInteger)
    video_comments: Mapped[Optional[int]] = mapped_column(BigInteger)

    score: Mapped[Optional[int]] = mapped_column(BigInteger)
    score_mom: Mapped[Optional[int]] = mapped_column(BigInteger)
    rank: Mapped[Optional[int]]
    rank_mom: Mapped[Optional[int]]

    meta: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    _created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    _updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
