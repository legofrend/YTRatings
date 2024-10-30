from datetime import date, datetime, timedelta

# import locale
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError
import functools

import asyncio

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

import app.ytapi as yt


# def store_db(dao_class, mode: Literal["add_update", "add_skip", "add"] = "add_update"):
#     def decorator(func):
#         @functools.wraps(func)
#         def wrapper(*args, **kwargs):
#             # Получаем результат выполнения функции
#             data = func(*args, **kwargs)
#             if data:
#                 if mode == "add":
#                     dao_class.add_bulk(data)
#                 else:
#                     dao_class.add_update_bulk(data, skip_if_exist=(mode == "add_skip"))
#             return data

#         return wrapper

#     return decorator


class CategoryDAO(BaseDAO):
    model = Category


class ChannelDAO(BaseDAO):
    model = Channel

    @classmethod
    def get_ids(cls, filters: dict = {}):
        if not "status" in filters.keys():
            filters["status"] = 1
        data = cls.find_all(**filters)
        ids = [d.channel_id for d in data]
        return ids

    @classmethod
    def get_ids_wo_stat(
        cls,
        report_period: Period,
        category_id: int = None,
    ):
        query = f"""select distinct c.channel_id
                    from channel as c
                    left join channel_stat cs on cs.channel_id = c.channel_id and cs.report_period = '{report_period.strf()}'
                    where cs.id is null 
                """
        if category_id:
            query += f" and c.category_id={category_id}"
        query = text(query)
        with session_maker() as session:
            result = session.execute(query)
            data = result.mappings().all()
            data = [item["channel_id"] for item in data]
            return data

    @classmethod
    def search_channel(
        cls, query: str, max_result: int = 1, order: yt.OrderType = "relevance"
    ):
        data = yt.search_list(
            query=query, type="channel", max_result=max_result, order=order
        )
        if data:
            cls.add_update_bulk(data, skip_if_exist=True)
        return data

    @classmethod
    def find_by_title(cls, title: str) -> str:
        channel = cls.find_one_or_none(channel_title=title)
        if not channel:
            [channel] = cls.search_channel(title)
        if not channel:
            return None
        return channel.get("channel_id")

    @classmethod
    def update_detail(
        cls, channel_ids: list[str] | str = None, skip_if_exist: bool = False
    ):
        if not channel_ids:
            channel_ids = cls.get_ids(
                filters={
                    "published_at": None,
                }
            )
        data = yt.channel_list(channel_ids, obj_type="detail")
        if data:
            cls.add_update_bulk(data, skip_if_exist=skip_if_exist)
        return data

    @classmethod
    def search_by_keywords(
        cls,
        query: str,
        date_from: datetime = datetime.now(),
        iterations: int = 8,
        date_step: int = 7,
        order: yt.OrderType = "relevance",
        type: yt.ResourseType = "video",
    ):

        data = []
        for _ in range(0, iterations):
            try:
                published_range = [date_from, date_from - timedelta(days=date_step)]
                videos = yt.search_list(
                    query,
                    published=published_range,
                    type=type,
                    order=order,
                    max_result=50,
                )
                data.extend(videos)
                logger.debug(f"Fetched {len(videos)} videos")

            except Exception as e:
                logger.error(f"Can't get videos {published_range=}", exc_info=True)
                return data

            date_from -= timedelta(days=date_step)

        unique_channel_ids = list(set(video["channel_id"] for video in data))
        logger.info(f"Find {len(unique_channel_ids)} unique channels")

        return cls.update_detail(unique_channel_ids, skip_if_exist=True)


class VideoDAO(BaseDAO):
    model = Video

    @classmethod
    def get_ids(cls, filters: dict = {}):
        data = cls.find_all(**filters)
        ids = [d.video_id for d in data]
        return ids

    @classmethod
    def get_ids_wo_stat(
        cls,
        report_period: Period,
        published_at_period: Period = None,
        category_id: int = None,
    ):
        if not published_at_period:
            published_at_period = report_period.next(-1)

        with session_maker() as session:
            query = f"""select distinct v.video_id
                        from video as v
                        left join channel as c on c.channel_id = v.channel_id
                        left join video_stat vs on v.video_id = vs.video_id and vs.report_period = '{report_period.strf()}'
                        where c.category_id={category_id} and vs.id is null and v.published_at_period >= '{published_at_period.strf()}'
                        ;
                    """
            query = text(query)
            result = session.execute(query)
            data = result.mappings().all()
            data = [item["video_id"] for item in data]
            return data

    @classmethod
    def update_detail(
        cls, video_ids: list[str] | str = None, skip_if_exist: bool = False
    ):
        if not video_ids:
            video_ids = cls.get_ids(
                filters={
                    "duration": None,
                }
            )
        data = yt.video_list(video_ids, obj_type="detail")
        if data:
            cls.add_update_bulk(data, skip_if_exist=skip_if_exist)
        return data

    @classmethod
    def update_is_short(
        cls, video_ids: list[str] | str = None, skip_if_exist: bool = False
    ):
        if not video_ids:
            res = cls.find_all(is_short=None)
            video_ids = [item["video_id"] for item in res]

        data = yt.check_shorts(video_ids)
        if data:
            cls.add_update_bulk(data, skip_if_exist=skip_if_exist)
        return data

    @classmethod
    def search_new_by_channel_period(
        cls, channel_ids: list[str] | str, period: Period | list[datetime] = Period()
    ):
        if isinstance(channel_ids, str):
            channel_ids = [channel_ids]

        if isinstance(period, Period):
            period = period.as_range()

        if isinstance(period, list) and len(period) != 2:
            raise Exception("Invalid period")

        data = []
        # TODO: check multiple channels query
        for index in range(0, len(channel_ids)):
            channel_id = channel_ids[index]
            try:
                videos = yt.search_list(
                    "",
                    published=period,
                    type="video",
                    channel_id=channel_id,
                    order="viewCount",
                    max_result=1000,
                )
                if videos:
                    cls.add_update_bulk(videos, skip_if_exist=True)
                    data.extend(videos)
                logger.info(
                    f"{index}/{len(channel_ids)}: fetched {len(videos)} videos from channel {channel_id}"
                )

            except Exception as e:
                logger.error(
                    f"Can't get videos for channel id {index}: {channel_id}",
                    exc_info=True,
                )

        return data

    @classmethod
    def search_new_by_category_period(
        cls, category_ids: list[int] | int, period: Period | list[datetime] = Period()
    ):
        if isinstance(category_ids, int):
            category_ids = [category_ids]
        for category_id in category_ids:
            channel_ids = ChannelDAO.get_ids(filters={"category_id": category_id})
            cls.search_new_by_channel_period(channel_ids, period)
            logger.info(
                f"Updated {len(channel_ids)} channels for category {category_id}"
            )

        return True


class VideoStatDAO(BaseDAO):
    model = VideoStat

    @classmethod
    def update_stat(
        cls,
        report_period: Period,
        video_ids: list[str] | str = None,
        category_id: int = None,
    ):
        if not video_ids:
            video_ids = VideoDAO.get_ids_wo_stat(
                report_period=report_period, category_id=category_id
            )

        data = yt.video_list(video_ids, obj_type="stat")

        if data:
            for item in data:
                item["report_period"] = report_period.strf()
            cls.add_bulk(data)
        return data


class ChannelStatDAO(BaseDAO):
    model = ChannelStat

    @classmethod
    def update_stat(
        cls,
        report_period: Period,
        channel_ids: list[str] | str = None,
        category_id: int = None,
    ):
        if not channel_ids:
            channel_ids = ChannelDAO.get_ids_wo_stat(
                report_period=report_period, category_id=category_id
            )

        data = yt.channel_list(channel_ids, obj_type="stat")

        if data:
            for item in data:
                item["report_period"] = report_period.strf()
            cls.add_bulk(data)
        return data


def select_view(view_name: str, filters: dict = {}, conditions: list[str] = None):
    if not conditions:
        conditions = []
    query = f"select * from {view_name}"
    for key, value in filters.items():
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
    def query_report_view(cls, period: Period, category_id: int) -> dict:
        data = select_view(
            "report_view",
            filters={"report_period": period.strf(), "category_id": category_id},
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
    def build(cls, period: Period, category_id: int):
        data = cls.query_report_view(period, category_id)
        if not data:
            return None
        # TODO replace with add_update
        res = cls.add(
            report_period=period.strf(),
            category_id=category_id,
            data=data,
        )
        msg = f"report for {period}, category {category_id}: {res}"
        if not res:
            logger.error(f"Cannot add {msg}")
            return None

        logger.info(f"Added {msg}")
        return res

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
