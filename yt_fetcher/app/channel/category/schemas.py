from pydantic import BaseModel
from typing import TYPE_CHECKING, Optional

# Убирает предупреждения отсутствия импорта и неприятные подчеркивания в PyCharm и VSCode
# if TYPE_CHECKING:
#     from app.video.schemas import SVideo


class SCategory(BaseModel):
    id: int
    name: str
    title: str
    description: Optional[str] = ""


# print("ok")
