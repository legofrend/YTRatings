from datetime import date, datetime, timedelta

# import locale
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.dao import BaseDAO
from app.database import session_maker, engine
from app.logger import logger, save_errors
from app.channel.models import Channel, ChannelStat, Category
from app.period.period import Period

import app.ytapi as yt

class CategoryDAO(BaseDAO):
    model = Category

class ChannelDAO(BaseDAO):
    model = Channel

    @classmethod
    def get_ids(cls, filters: dict = {}):
        # if not "status" in filters.keys():
        #     filters["status"] = 1
        data = cls.find_all(**filters)
        ids = [d.channel_id for d in data]
        return ids

    @classmethod
    def get_ids_wo_stat(
        cls,
        report_period: Period,
        category_id: int = None,
    ):
        # TODO replace with alchemy query
        query = f"""select distinct c.channel_id
                    from channel as c
                    left join channel_stat cs on cs.channel_id = c.channel_id and cs.report_period = '{report_period.strf()}'
                    where cs.id is null and (c.status > 0 or c.status is null)
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
    def get_ids_wo_video(
        cls,
        report_period: Period,
        category_id: int = None,
    ):
        # TODO replace with alchemy query
        query = f"""select c.channel_id, count(*)
                    from channel as c
                    left join video v on v.channel_id = c.channel_id and v.published_at_period = '{report_period.strf()}'
                    where c.status = 1"""
        query += f" and c.category_id={category_id}" if category_id else ""
        query += " group by c.channel_id having count(*) = 0"
        query = text(query)
        with session_maker() as session:
            result = session.execute(query)
            data = result.mappings().all()
            data = [item["channel_id"] for item in data]
            return data

    @classmethod
    def search_channel(
        cls,
        query: str,
        max_result: int = 1,
        order: yt.OrderType = "relevance",
        category_id: int = None,
    ):
        data = yt.search_list(
            query=query, type="channel", max_result=max_result, order=order
        )
        if data:
            if category_id:
                for item in data:
                    item["category_id"] = category_id
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
        max_result: int = 50,
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
                    max_result=max_result,
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
