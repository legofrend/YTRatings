from datetime import date, datetime, timedelta

# import locale
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.dao_base import BaseDAO
from app.database import session_maker, engine
from app.logger import logger, save_errors
from app.models import Channel, ChannelStat, Video, VideoStat
from app.period import Period

import app.ytapi as yt


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
        # TODO replace with alchemy query
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
        if not data:
            return None
        video_ids = [item["video_id"] for item in data if item.get("is_short") is None]
        data_shorts = yt.check_shorts(video_ids)
        data_shorts = {item["video_id"]: item["is_short"] for item in data_shorts}
        for item in data:
            is_short = data_shorts.get(item["video_id"])
            if item.get("is_short") is None and is_short:
                item["is_short"] = is_short
                item["video_url"] = (
                    "https://www.youtube.com/"
                    + ("shorts/" if is_short else "watch?v=")
                    + item["video_id"]
                )

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
            logger.info(f"{index+1}/{len(channel_ids)}: {channel_id}")
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
            # TODO finish method wo_videos
            # channel_ids = ChannelDAO.get_ids_wo_video(
            #     filters={"category_id": category_id, "report_period": period}
            # )
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
