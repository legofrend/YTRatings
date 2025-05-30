from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.database import async_session_maker
from app.logger import logger, save_errors

LIMIT = 500


class BaseDAO:
    model = None
    gid = "id"  # general id for yuotube object,  e.g. video_id or channel_id

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
            query = (
                select(cls.model.__table__.columns).filter_by(**filter_by).limit(3000)
            )
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
    async def update(cls, filter: dict, data: dict) -> list:
        try:
            query = (
                update(cls.model)
                .values(**data)
                .filter_by(**filter)
                .returning(cls.model.id)
            )
            async with async_session_maker() as session:
                result = await session.execute(query)
                await session.commit()
                return result.mappings().all()
                # return True

        except (SQLAlchemyError, Exception) as e:
            if isinstance(e, SQLAlchemyError):
                msg = "Database Exc: Cannot update data into table"
            elif isinstance(e, Exception):
                msg = "Unknown Exc: Cannot update data into table"

            logger.error(msg, extra={"table": cls.model.__tablename__}, exc_info=True)
            return None

    @classmethod
    async def add_or_update(cls, data: dict, do_nothing: bool = False):
        id = data.get(cls.gid, None)

        stmt = insert(cls.model).values(**data)

        if id:
            if do_nothing:
                stmt = stmt.on_conflict_do_nothing(index_elements=[cls.gid])
            else:
                stmt = stmt.on_conflict_do_update(
                    index_elements=[cls.gid],
                    set_={key: val for key, val in data.items() if key != cls.gid},
                )
        stmt = stmt.returning(cls.model.id)

        try:
            async with async_session_maker() as session:
                result = await session.execute(stmt)
                await session.commit()
            # TODO: fix, if do_nothing is True returns empty list as in case of error
            return result.mappings().first()
        except Exception as e:
            msg = "Add_or_update failed"
            logger.error(msg, extra={"table": cls.model.__tablename__}, exc_info=True)
            return None

    @classmethod
    async def add_update_bulk(cls, data, do_nothing: bool = False):
        errors = []
        add_update = []
        # print(len(data))
        for d in data:
            result = await cls.add_or_update(d, do_nothing)
            errors.append(d) if result is None else add_update.append(d)

        msg = f"Added or updated to {cls.model.__tablename__} {len(add_update)} records"
        if errors:
            save_errors(errors, cls.model.__tablename__)
            msg += f", {len(errors)} errors"
            logger.error(msg)
        else:
            logger.info(msg)

        return (add_update, errors)

    @classmethod
    async def add_bulk(cls, data: list[dict]) -> list:
        total_result = []
        for i in range(0, len(data), LIMIT):
            part_data = data[i : (i + LIMIT)]
            try:
                async with async_session_maker() as session:
                    query = insert(cls.model).values(part_data).returning(cls.model.id)
                    result = await session.execute(query)
                    await session.commit()
                    total_result.extend(result.mappings().all())
            except (SQLAlchemyError, Exception) as e:
                if isinstance(e, SQLAlchemyError):
                    msg = "Database Exc"
                elif isinstance(e, Exception):
                    msg = "Unknown Exc"
                msg += ": Cannot bulk insert data into table"

                logger.error(
                    msg, extra={"table": cls.model.__tablename__}, exc_info=True
                )
                save_errors(data, cls.model.__tablename__)
                # await session.rollback()
                # return None
        return total_result

    @classmethod
    async def update_bulk(cls, data: list[dict], identifier: str = None) -> list:
        identifier = identifier or cls.gid
        # TODO rewrite without cycle to speed up, it was not easy when id is not in data
        result = True
        for i in range(0, len(data), LIMIT):
            part_data = data[i : (i + LIMIT)]
            try:
                async with async_session_maker() as session:
                    for record in part_data:
                        # Получаем channel_id для обновления
                        id = record.pop(identifier, None)
                        if not id:
                            raise Exception(f"{identifier} is not in data")
                        query = (
                            update(cls.model)
                            .filter_by(**{identifier: id})
                            .values(record)
                            .returning(cls.model.id)
                        )
                        await session.execute(query)
                        # result = await session.execute(query)
                    await session.commit()
                    # return result.mappings().all()
                    # return True

            except (SQLAlchemyError, Exception) as e:
                if isinstance(e, SQLAlchemyError):
                    msg = "Database Exc: Cannot update data into table"
                elif isinstance(e, Exception):
                    msg = "Unknown Exc: Cannot update data into table"
                logger.error(
                    msg, extra={"table": cls.model.__tablename__}, exc_info=True
                )
                save_errors(part_data, cls.model.__tablename__)
                # return None
                result = False

        return result

    @classmethod
    async def delete(cls, **filter_by):
        async with async_session_maker() as session:
            query = delete(cls.model).filter_by(**filter_by).returning(cls.model.id)
            result = await session.execute(query)
            await session.commit()
            return result.mappings().all()


# print("ok")
