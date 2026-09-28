from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, SmallInteger, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Wordstat(Base):
    __tablename__ = "wordstat"
    __table_args__ = (
        UniqueConstraint(
            "category_id", "period", "lexeme", name="uq_wordstat_cat_period_lexeme"
        ),
    )

    category_id: Mapped[int]
    period: Mapped[date] = mapped_column(Date)
    lexeme: Mapped[str]
    word: Mapped[str]
    freq: Mapped[int]
    type: Mapped[Optional[int]] = mapped_column(SmallInteger)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
