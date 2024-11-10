from app.dao.base import BaseDAO
from app.channel.category.models import Category


class CategoryDAO(BaseDAO):
    model = Category
