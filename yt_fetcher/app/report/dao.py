from datetime import date

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert


from app.dao.base import BaseDAO
from app.database import async_session_maker
from app.logger import logger, save_errors
from app.period import Period

from app.report.models import Report
from app.report.schemas import SMetaData, SReport
from app.report.tools import render_info_pic

from app.channel import (
    SChannel,
    SChannelStat,
    Category,
    CategoryDAO,
    SVideo,
    SVideoStat,
)


async def select_view(view_name: str, filters: dict = {}, conditions: list[str] = None):
    if not conditions:
        conditions = []
    query = f"select * from {view_name}"
    for key, value in filters.items():
        conditions.append(f"{key} = '{value}'")
    if conditions:
        query += " where " + " and ".join(conditions)

    async with async_session_maker() as session:
        query = text(query)
        result = await session.execute(query)
        data = result.mappings().all()
        data = [dict(item) for item in data]
        return data


class ReportDAO(BaseDAO):
    model = Report

    @classmethod
    # new version of add_update using on conflict
    async def add_or_update(cls, data: dict, do_nothing: bool = False):
        stmt = insert(cls.model).values(**data)

        if do_nothing:
            stmt = stmt.on_conflict_do_nothing(constraint="uq_period_category")
        else:
            stmt = stmt.on_conflict_do_update(
                constraint="uq_period_category",
                set_={"data": data["data"]},
            )
        stmt = stmt.returning(cls.model.id)

        async with async_session_maker() as session:
            result = await session.execute(stmt)
            await session.commit()

        return result.mappings().first()

    @classmethod
    async def _query_top_videos(
        cls, period: Period, category_id: int, top_number: int = 3
    ) -> list[SVideo]:
        data = await select_view(
            "channel_period_top_videos",
            filters={"report_period": period.strf(), "category_id": category_id},
            conditions=["rank <= " + str(top_number)],
        )
        result = {}
        for v in data:
            video_stat = SVideoStat(**v)
            video = SVideo(stat=video_stat, **v)
            if not result.get(v["channel_id"]):
                result[v["channel_id"]] = []
            result[v["channel_id"]].append(video)

        return result

    @classmethod
    async def query_report_view(cls, period: Period, category_id: int) -> dict:
        data = await select_view(
            "report_view",
            filters={"report_period": period.strf(), "category_id": category_id},
        )

        top_videos = await cls._query_top_videos(period, category_id, top_number=5)
        channels = []
        for i in data:
            stat = SChannelStat.model_validate(i)
            top_video = top_videos.get(i["channel_id"]) or []
            channel = SChannel(stat=stat, top_videos=top_video, **i)
            channels.append(channel.model_dump())

        return channels

    @classmethod
    async def build(cls, period: Period, category_id: int):
        data = await cls.query_report_view(period, category_id)
        if not data:
            return None

        res = await cls.add_or_update(
            val={
                "report_period": period.strf(),
                "category_id": category_id,
                "data": data,
            }
        )
        msg = f"report for {period}, category {category_id}: {res}"
        if not res:
            logger.error(f"Cannot add {msg}")
            return None

        logger.info(f"Added {msg}")
        return res

    @classmethod
    async def get(cls, period: Period | date | str, category_id: int) -> SReport:
        if isinstance(period, (str)):
            period = Period.parse(period)

        data = await cls.find_one_or_none(report_period=period, category_id=category_id)
        if not data:
            return None
        id = data["id"]
        data = data["data"]
        # for item in data:
        #     item.video = [SChannel(**i) for i in data]
        scale = data[0]["stat"]["score"] + max(0, -data[0]["stat"]["score_change"])

        category = await CategoryDAO().find_by_id(category_id)

        result = {
            "id": id,
            "period": period.strf(),
            # "display_period": period._date.strftime("%B %Y"),
            "category_id": category_id,
            "category": category,
            "scale": scale,
            "data": data,
        }

        return SReport(**result)

    @classmethod
    async def metadata(cls) -> list[SMetaData]:
        async with async_session_maker() as session:
            query = (
                select(Category.id, Category.name, Report.report_period)
                .join(Category, Category.id == Report.category_id, isouter=True)
                .order_by(Category.id, Report.report_period.asc())
            )
            results = await session.execute(query)
            # results = result.mappings().all()

        data_dict = {}
        for id, name, report_period in results:

            if id not in data_dict:
                data_dict[id] = {"name": name, "periods": []}
            if report_period is not None:  # Проверяем на None, чтобы не добавлять его
                data_dict[id]["periods"].append(report_period)

        # Превращаем данные в список SMetaData
        meta_data_list = [
            SMetaData(id=int(id), name=info["name"], periods=info["periods"])
            for id, info in data_dict.items()
        ]

        return meta_data_list

    @classmethod
    async def generate_info_images(
        cls,
        period: Period,
        category_id: int,
        top_channels: int = 10,
        top_videos_count: int = 1,
    ):
        report = await cls.get(period, category_id)
        data = report.data

        for item in data[:top_channels]:
            render_info_pic(report.period, report.category.name, item, top_videos_count)
