from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import func

from app.config import settings

DATABASE_URL = settings.DATABASE_URL
# if settings.MODE == "TEST":
#     DATABASE_URL = settings.TEST_DATABASE_URL
#     DATABASE_PARAMS = {"poolclass": NullPool, "echo": True}
# else:
#     DATABASE_URL = settings.DATABASE_URL
#     DATABASE_PARAMS = {"echo": False}

# sync version
# engine = create_engine(DATABASE_URL)
# session_maker = sessionmaker(engine, expire_on_commit=False)

# async version
async_engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(async_engine, expire_on_commit=False)

# this is for testing
# async_session_maker_nullpool = async_sessionmaker(engine_nullpool, expire_on_commit=False)
# async_session_maker_nullpool = async_sessionmaker(engine_nullpool, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


# def get_session():
#     with session_maker() as session:
#         yield session


class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)


async def init_database(drop_db: bool):
    print("Recreating DB")
    async with async_engine.begin() as conn:
        if drop_db:
            # Удаление всех заданных нами таблиц из БД
            await conn.run_sync(Base.metadata.drop_all)
            # Добавление всех заданных нами таблиц из БД
            await conn.run_sync(Base.metadata.create_all)
