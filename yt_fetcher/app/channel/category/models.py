from typing import Optional
from sqlalchemy.orm import mapped_column, Mapped

from app.database import Base


# if TYPE_CHECKING:
# Убирает предупреждения отсутствия импорта и неприятные подчеркивания в PyCharm и VSCode


class Category(Base):
    __tablename__ = "category"
    active: Mapped[int] = mapped_column(default=1)
    # status: Mapped[int] = mapped_column(default=1)
    name: Mapped[str | None]
    title: Mapped[str | None]
    description: Mapped[str | None]
    sys_name: Mapped[str | None]
    sort_order: Mapped[int] = mapped_column(default=1000, server_default="1000")
