from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field
from typing import TYPE_CHECKING, List, Dict, Optional
from app.channel.schemas import SChannel, SCategory

if TYPE_CHECKING:
    # Убирает предупреждения отсутствия импорта и неприятные подчеркивания в PyCharm и VSCode
    from app.channel.schemas import SChannel, SCategory


class SReport(BaseModel):
    id: Optional[int] = None
    period: date
    display_period: Optional[str] = None
    category_id: int
    category: SCategory
    scale: int
    data: List[SChannel]

    model_config = ConfigDict(from_attributes=True)


class SMetaData(BaseModel):
    id: int
    name: str
    periods: List[date]

    model_config = ConfigDict(from_attributes=True)
