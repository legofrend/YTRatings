from typing import Optional
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import (
    BigInteger,
    Date,
    func,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSONB

from datetime import datetime, date

from app.database import Base


# if TYPE_CHECKING:
# Убирает предупреждения отсутствия импорта и неприятные подчеркивания в PyCharm и VSCode


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
    last_video_fetch_dt: Mapped[Optional[datetime]]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    data: Mapped[dict] = mapped_column(JSONB, server_default="{}")


class ChannelStat(Base):
    __tablename__ = "channel_stat"
    channel_id: Mapped[str] = mapped_column(ForeignKey("channel.channel_id"))
    data_at: Mapped[datetime]
    report_period: Mapped[Optional[date]] = mapped_column(
        Date, default=func.date_trunc("month", func.current_date()).cast(Date)
    )
    channel_view_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    subscriber_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    video_count: Mapped[Optional[int]]
