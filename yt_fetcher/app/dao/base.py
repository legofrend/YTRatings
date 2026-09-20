from sqlalchemy import delete, select, text, update, literal_column, Boolean
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from datetime import date, datetime, timedelta

from app.database import async_session_maker
from app.logger import logger, save_errors

# Оптимальный размер батча для PostgreSQL
LIMIT = 1000  # Было 500


def _format_sql_literal(value, sa_type=None) -> str:
    """Format a Python value as a SQL literal; cast NULLs when sa_type is known (PG VALUES)."""
    if value is None:
        if sa_type is not None:
            from sqlalchemy import (
                Boolean,
                Date,
                DateTime,
                Float,
                Integer,
                BigInteger,
                SmallInteger,
                String,
                Text,
            )

            if isinstance(sa_type, Boolean):
                return "NULL::boolean"
            if isinstance(sa_type, (Integer, SmallInteger)):
                return "NULL::integer"
            if isinstance(sa_type, BigInteger):
                return "NULL::bigint"
            if isinstance(sa_type, Float):
                return "NULL::double precision"
            if isinstance(sa_type, DateTime):
                return "NULL::timestamp"
            if isinstance(sa_type, Date):
                return "NULL::date"
            if isinstance(sa_type, (String, Text)):
                return "NULL::text"
        return "NULL"
    # bool before int — bool is a subclass of int in Python
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return f"'{value.isoformat()}'"
    if isinstance(value, date):
        return f"'{value.isoformat()}'"
    s = str(value).replace("'", "''")
    return f"'{s}'"


def _dedupe_by_gid(data: list[dict], gid: str) -> list[dict]:
    """Keep last row per gid — PG ON CONFLICT DO UPDATE rejects duplicate keys in one INSERT."""
    if not data:
        return data
    by_id: dict = {}
    order: list = []
    for row in data:
        key = row.get(gid)
        if key is None:
            continue
        if key not in by_id:
            order.append(key)
        by_id[key] = row
    if len(by_id) < len(data):
        logger.warning(
            f"dedupe_by_gid: {len(data)} → {len(by_id)} rows (dropped {len(data) - len(by_id)} dupes on {gid})"
        )
    return [by_id[k] for k in order]


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
        if not data:
            return False

        data = _dedupe_by_gid(data, cls.gid)
        if not data:
            return False

        total_inserted = 0
        total_updated = 0
        total_skipped = 0
        any_ok = False

        for i in range(0, len(data), LIMIT):
            part = data[i : i + LIMIT]
            try:
                stmt = insert(cls.model).values(part)

                if do_nothing:
                    stmt = stmt.on_conflict_do_nothing(index_elements=[cls.gid])
                    stmt = stmt.returning(cls.model.id)
                else:
                    pk_names = {c.name for c in cls.model.__table__.primary_key.columns}
                    update_cols = [
                        c.name
                        for c in cls.model.__table__.columns
                        if c.name != cls.gid and c.name not in pk_names
                    ]
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[cls.gid],
                        set_={k: getattr(stmt.excluded, k) for k in update_cols},
                    )
                    stmt = stmt.returning(
                        cls.model.id,
                        literal_column("(xmax = 0)", type_=Boolean).label("inserted"),
                    )

                async with async_session_maker() as session:
                    result = await session.execute(stmt)
                    await session.commit()

                    if do_nothing:
                        inserted = [row.id for row in result]
                        total_inserted += len(inserted)
                        total_skipped += len(part) - len(inserted)
                    else:
                        for row in result.mappings():
                            if row["inserted"]:
                                total_inserted += 1
                            else:
                                total_updated += 1
                    any_ok = True

            except Exception as e:
                logger.error(
                    f"Error in bulk update batch {i}-{i + len(part)}/{len(data)}: {e}",
                    extra={"table": cls.model.__tablename__},
                    exc_info=True,
                )
                # Cap dump — full 5k batches froze disk/terminals last time
                save_errors(part[:50], cls.model.__tablename__)
                return False

        if do_nothing:
            msg = (
                f"Added {total_inserted} records in {cls.model.__tablename__}"
            )
            if total_skipped:
                msg += f", {total_skipped} skipped"
        else:
            msg = (
                f"Added {total_inserted} and updated {total_updated} records "
                f"in {cls.model.__tablename__}"
            )
        logger.info(msg)
        return any_ok

    @classmethod
    async def add_bulk(cls, data: list[dict]) -> list:
        total_result = []
        start_time = None
        avg_time_per_batch = None

        for i in range(0, len(data), LIMIT):
            batch_start = datetime.now()
            if start_time is None:
                start_time = batch_start

            part_data = data[i : (i + LIMIT)]

            # Calculate time estimation
            if avg_time_per_batch is not None:
                remaining_batches = (len(data) - i) / LIMIT
                est_remaining_time = avg_time_per_batch * remaining_batches
                est_end_time = datetime.now() + timedelta(seconds=est_remaining_time)
                time_info = f" | Est. remaining: {est_remaining_time:.0f}s | End: {est_end_time.strftime('%H:%M:%S')}"
            else:
                time_info = ""

            print(
                f"\rProcessing {i}/{len(data)} records...{time_info}",
                end="",
                flush=True,
            )

            try:
                async with async_session_maker() as session:
                    query = insert(cls.model).values(part_data).returning(cls.model.id)
                    result = await session.execute(query)
                    await session.commit()
                    total_result.extend(result.mappings().all())

                    # Update average time
                    batch_time = (datetime.now() - batch_start).total_seconds()
                    if avg_time_per_batch is None:
                        avg_time_per_batch = batch_time
                    else:
                        avg_time_per_batch = (avg_time_per_batch + batch_time) / 2

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
                return False
        return total_result

    @classmethod
    async def update_bulk(cls, data: list[dict], identifier: str = None) -> bool:
        if not data:
            return True

        identifier = identifier or cls.gid
        result = True

        for i in range(0, len(data), LIMIT):
            part_data = data[i : (i + LIMIT)]
            print(f"\rProcessing {i}/{len(data)} records...", end="", flush=True)
            try:
                async with async_session_maker() as session:
                    # Получаем колонки для обновления (все кроме identifier)
                    update_cols = [
                        col for col in part_data[0].keys() if col != identifier
                    ]

                    # Создаем VALUES конструкцию для временной таблицы
                    # Нужны все колонки, включая identifier, так как они используются в FROM
                    cols = list(part_data[0].keys())
                    table_cols = cls.model.__table__.columns
                    values = []
                    for record in part_data:
                        formatted_values = [
                            _format_sql_literal(
                                record.get(k),
                                table_cols[k].type if k in table_cols else None,
                            )
                            for k in cols
                        ]
                        values.append(f"({', '.join(formatted_values)})")

                    # Формируем SQL запрос
                    query = text(
                        f"""
                        UPDATE {cls.model.__tablename__} t
                        SET {', '.join(f"{col} = v.{col}" for col in update_cols)}
                        FROM (VALUES {', '.join(values)}) AS v({', '.join(cols)})
                        WHERE t.{identifier} = v.{identifier}
                    """
                    )

                    await session.execute(query)
                    await session.commit()

            except Exception as e:
                logger.error(
                    f"Error in bulk update: {str(e)}",
                    extra={"table": cls.model.__tablename__},
                    exc_info=True,
                )
                save_errors(part_data, cls.model.__tablename__)
                result = False

            # print("\n")

        return result

    @classmethod
    async def delete(cls, **filter_by):
        async with async_session_maker() as session:
            query = delete(cls.model).filter_by(**filter_by).returning(cls.model.id)
            result = await session.execute(query)
            await session.commit()
            return result.mappings().all()


# print("ok")
