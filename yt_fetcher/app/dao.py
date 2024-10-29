from datetime import date

# import locale
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.dao_base import BaseDAO
from app.database import session_maker, engine
from app.logger import logger, save_errors
from app.models import Category, Channel, ChannelStat, Video, VideoStat, Report
from app.schemas import (
    SChannelStat,
    SMetaData,
    SVideoStat,
    SVideo,
    SReport,
    SChannel,
)
from app.period import Period

# import app.ytapi as ytapi


class CategoryDAO(BaseDAO):
    model = Category


class ChannelDAO(BaseDAO):
    model = Channel

    @classmethod
    def get_ids(cls, filter: dict = {}):
        if not "status" in filter.keys():
            filter["status"] = 1
        data = cls.find_all(**filter)
        ids = [d.channel_id for d in data]
        return ids

    # @classmethod
    # def find_by_title(cls, title: str) -> str:
    #     channel = cls.find_one_or_none(channel_title=title)
    #     if not channel:
    #         [channel] = ytapi.find_channel(title)
    #     if not channel:
    #         return None
    #     return channel.get("channel_id")

    # @classmethod
    # def find_by_keywords(cls, keywords: str) -> list[tuple[str, str]]:
    #     [channel] = ytapi.find_channel(keywords)
    #     if not channel:
    #         return None
    #     return channel.get("channel_id")


class VideoDAO(BaseDAO):
    model = Video

    @classmethod
    def get_videos_wo_stat(cls, category_id: int):
        # TODO: add filter by report_period and category_id
        with session_maker() as session:
            query = f"""select distinct v.video_id
                        from video as v
                        left join channel as c on c.channel_id = v.channel_id
                        left join video_stat vs on v.video_id = vs.video_id and vs.report_period = '2024-10-01'
                        where c.category_id={category_id} and vs.id is null and v.published_at_period >= '2024-08-01'
                        ;
                    """
            query = text(query)
            result = session.execute(query)
            data = result.mappings().all()
            data = [item["video_id"] for item in data]
            return data

    @classmethod
    def get_ids(cls, filters: dict = {}):
        data = cls.find_all(**filters)
        ids = [d.video_id for d in data]
        return ids


class VideoStatDAO(BaseDAO):
    model = VideoStat


class ChannelStatDAO(BaseDAO):
    model = ChannelStat


def select_view(view_name: str, filter: dict = {}, conditions: list[str] = None):
    if not conditions:
        conditions = []
    query = f"select * from {view_name}"
    for key, value in filter.items():
        conditions.append(f"{key} = '{value}'")
    if conditions:
        query += " where " + " and ".join(conditions)

    with session_maker() as session:
        query = text(query)
        result = session.execute(query)
        data = result.mappings().all()
        data = [dict(item) for item in data]
        return data


class ReportDAO(BaseDAO):
    model = Report

    @classmethod
    def _query_top_videos(
        cls, period: Period, category_id: int, top_number: int = 3
    ) -> list[SVideo]:
        data = select_view(
            "channel_period_top_videos",
            filter={"report_period": period.strf(), "category_id": category_id},
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
    def query_report_view(cls, period: Period, category_id: int) -> dict:
        data = select_view(
            "report_view",
            filter={"report_period": period.strf(), "category_id": category_id},
        )

        top_videos = cls._query_top_videos(period, category_id, top_number=5)
        channels = []
        for i in data:
            stat = SChannelStat.model_validate(i)
            top_video = top_videos.get(i["channel_id"]) or []
            channel = SChannel(stat=stat, top_videos=top_video, **i)
            channels.append(channel.model_dump())

        return channels

    @classmethod
    def build(cls, periods: list[Period], category_ids: list[int]):
        for period in periods:
            for category_id in category_ids:
                data = cls.query_report_view(period, category_id)
                if not data:
                    continue
                res = cls.add(
                    report_period=period.strf(),
                    category_id=category_id,
                    # data=json.dumps(data, indent=4, ensure_ascii=False),
                    data=data,
                )
                if res:
                    logger.info(
                        f"Added report for {period}, category {category_id}: {res}"
                    )
                else:
                    logger.error(
                        f"Cannot add report for {period}, category {category_id}"
                    )
        return True

    @classmethod
    def get(cls, period: Period | date | str, category_id: int) -> SReport:
        if isinstance(period, (str, date)):
            period = Period.parse(period)

        data = cls.find_one_or_none(
            report_period=period.strf(), category_id=category_id
        )
        if not data:
            return None
        id = data["id"]
        data = data["data"]
        scale = data[0]["stat"]["score"] + max(0, -data[0]["stat"]["score_change"])

        category = CategoryDAO().find_by_id(category_id)

        # locale.setlocale(locale.LC_ALL, "Russian")
        # display_period = period._date.strftime("%B %Y")
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
    def metadata(cls) -> list[SMetaData]:
        with session_maker() as session:
            query = (
                select(Category.id, Category.name, Report.report_period)
                .join(Category, Category.id == Report.category_id, isouter=True)
                .order_by(Category.id, Report.report_period.asc())
            )
            results = session.execute(query)
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


def init_database(drop_db: bool):
    print("Recreating DB")
    with engine.begin() as conn:
        if drop_db:
            Base.metadata.drop_all(conn)
            Base.metadata.create_all(conn)


# res = ReportDAO.metadata()
# print(res)

# init_database(drop_db=True)

# from logger import print_json, save_json

# res = ReportDAO.get(Period(9), 3)
# save_json(res)
