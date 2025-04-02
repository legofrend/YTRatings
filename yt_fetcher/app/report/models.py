from typing import Optional
from unicodedata import digit
from sqlalchemy.orm import mapped_column, Mapped, relationship
from sqlalchemy import (
    UniqueConstraint,
    ForeignKey,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from datetime import date, datetime

from app.database import Base


# if TYPE_CHECKING:
# Убирает предупреждения отсутствия импорта и неприятные подчеркивания в PyCharm и VSCode


class Report(Base):
    __tablename__ = "report"
    report_period: Mapped[date]
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"))
    data: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("report_period", "category_id", name="uq_period_category"),
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


# print("ok")
