from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.database import async_session_maker
from app.logger import logger, save_errors


class BaseDAO:
    model = None

    # Метод было решено скрестить с find_one_or_none, т.к. они выполняют одну и ту же функцию
    @classmethod
    async def find_by_id(cls, model_id: int):
        return await cls.find_one_or_none(id=model_id)

    @classmethod
    async def find_one_or_none(cls, **filter_by):
        async with async_session_maker() as session:
            query = select(cls.model.__table__.columns).filter_by(**filter_by)
            result = await session.execute(query)
            return result.mappings().one_or_none()

    @classmethod
    async def find_all(cls, **filter_by):
        async with async_session_maker() as session:
            query = select(cls.model.__table__.columns).filter_by(**filter_by)
            result = await session.execute(query)
            return result.mappings().all()

    @classmethod
    async def add(cls, **data):
        try:
            query = insert(cls.model).values(**data).returning(cls.model.id)
            async with async_session_maker() as session:
                # logger.warning(query.compile(compile_kwargs={"literal_binds": True}))
                result = await session.execute(query)
                await session.commit()
                return result.mappings().first()
                # return True
        except (SQLAlchemyError, Exception) as e:
            if isinstance(e, SQLAlchemyError):
                msg = f"Database Exc: Cannot insert data into table"
            elif isinstance(e, Exception):
                msg = "Unknown Exc: Cannot insert data into table"

            logger.error(msg, extra={"table": cls.model.__tablename__}, exc_info=True)
            return None

    @classmethod
    async def add_update_bulk(cls, data, index: str = "", skip_if_exist: bool = False):
        if not index:
            index = str(cls.model.__tablename__) + "_id"
        errors = []
        stored = []
        updated = []
        # print(len(data))
        for d in data:
            obj = await cls.find_one_or_none(**{index: d[index]})
            if not obj:
                stored.append(d) if await cls.add(**d) else errors.append(d)
            elif skip_if_exist:
                continue
            else:
                (
                    updated.append(d)
                    if await cls.update(obj.get("id"), **d)
                    else errors.append(d)
                )

        msg = f"Added to {cls.model.__tablename__} {len(stored)} records, updated {len(updated)}"
        if errors:
            save_errors(errors, cls.model.__tablename__)
            msg += f", {len(errors)} errors"
            logger.error(msg)
        else:
            logger.info(msg)

        return (stored, updated, errors)

    @classmethod
    async def add_bulk(cls, data: list):
        errors = []
        stored = []
        for d in data:
            stored.append(d) if await cls.add(**d) else errors.append(d)

        msg = f"Added to {cls.model.__tablename__} {len(stored)} records"
        if errors:
            save_errors(errors, cls.model.__tablename__)
            msg += f", {len(errors)} errors"
            logger.error(msg)
        else:
            logger.info(msg)

        return (stored, errors)

    @classmethod
    async def add_bulk_old(cls, *data):
        # Функция не работает как надо
        # Для загрузки массива данных [{"id": 1}, {"id": 2}]
        # мы должны обрабатывать его через позиционные аргументы *args.
        try:
            query = insert(cls.model).values(*data).returning(cls.model.id)
            async with async_session_maker() as session:
                result = await session.execute(query)
                await session.commit()
                return result.mappings().first()
                # return True
        except (SQLAlchemyError, Exception) as e:
            if isinstance(e, SQLAlchemyError):
                msg = "Database Exc"
            elif isinstance(e, Exception):
                msg = "Unknown Exc"
            msg += ": Cannot bulk insert data into table"

            logger.error(msg, extra={"table": cls.model.__tablename__}, exc_info=True)
            return None

    @classmethod
    async def update(cls, model_id: int, id_name: str = "id", **data):
        try:
            query = (
                update(cls.model)
                .values(**data)
                .filter_by(**{id_name: model_id})
                .returning(cls.model.id)
            )
            async with async_session_maker() as session:
                result = await session.execute(query)
                await session.commit()
                return result.mappings().first()
                # return True

        except (SQLAlchemyError, Exception) as e:
            if isinstance(e, SQLAlchemyError):
                msg = "Database Exc: Cannot update data into table"
            elif isinstance(e, Exception):
                msg = "Unknown Exc: Cannot update data into table"

            logger.error(msg, extra={"table": cls.model.__tablename__}, exc_info=True)
            return None

    @classmethod
    async def delete(cls, **filter_by):
        async with async_session_maker() as session:
            query = delete(cls.model).filter_by(**filter_by).returning(cls.model.id)
            result = await session.execute(query)
            await session.commit()
            return result.mappings().all()


# print("ok")
