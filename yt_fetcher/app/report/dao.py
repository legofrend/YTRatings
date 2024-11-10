from datetime import date

from sqlalchemy import select, text


from app.dao.base import BaseDAO
from app.database import async_session_maker
from app.logger import logger, save_errors
from app.report.models import Report
from app.report.schemas import SMetaData, SReport
from app.channel.schemas import SChannel, SChannelStat
from app.channel.models import Category
from app.channel.dao import CategoryDAO
from app.video.schemas import SVideo, SVideoStat
from app.period.period import Period
from app.report.tools import render_info_pic


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
    async def add_update(cls, val: dict, skip_if_exist: bool = False):
        obj = await cls.find_one_or_none(
            category_id=val["category_id"], report_period=val["report_period"]
        )
        if not obj:
            return await cls.add(**val)
        elif skip_if_exist:
            return None
        else:
            return await cls.update(obj.get("id"), **val)

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
        # TODO replace with add_update
        res = await cls.add_update(
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
        if isinstance(period, (str, date)):
            period = Period.parse(period)

        data = await cls.find_one_or_none(
            report_period=period.strf(), category_id=category_id
        )
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
        cls, period: Period, category_id: int, top_channels: int = 10
    ):
        report = await cls.get(period, category_id)
        data = report.data

        for item in data[:top_channels]:
            render_info_pic(report.period, report.category.name, item)
