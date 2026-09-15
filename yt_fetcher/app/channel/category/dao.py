from sqlalchemy import select

from app.dao.base import BaseDAO
from app.database import async_session_maker
from app.channel.category.models import Category


class CategoryDAO(BaseDAO):
    model = Category

    @classmethod
    async def list_active(cls) -> list[dict]:
        """Active categories ordered by sort_order, then id."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(
                    Category.id,
                    Category.name,
                    Category.title,
                    Category.description,
                    Category.sys_name,
                    Category.sort_order,
                )
                .where(Category.active == 1)
                .order_by(Category.sort_order, Category.id)
            )
            return [dict(row) for row in result.mappings().all()]
