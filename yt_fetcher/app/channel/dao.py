from datetime import date, datetime, timedelta


from sqlalchemy import text, select, or_

# from sqlalchemy.exc import SQLAlchemyError

from app.dao.base import BaseDAO
from app.database import async_session_maker
from app.logger import logger, save_errors
from app.channel.models import Channel, ChannelStat
from app.channel.video.dao import VideoDAO
from app.period import Period

import app.api.ytapi as yt


class ChannelDAO(BaseDAO):
    model = Channel
    gid = "channel_id"

    @classmethod
    async def get_ids(cls, filters: dict = {}):
        # if not "status" in filters.keys():
        #     filters["status"] = 1
        data = await cls.find_all(**filters)
        ids = [d.channel_id for d in data]
        return ids

    @classmethod
    async def get_ids_wo_stat(
        cls,
        report_period: Period,
        category_id: int = None,
    ):
        # TODO replace with alchemy query
        query = f"""select distinct c.channel_id
                    from channel as c
                    left join channel_stat cs on cs.channel_id = c.channel_id and cs.report_period = '{report_period.strf()}'
                    where cs.id is null and (c.status = 1)
                """
        if category_id:
            query += f" and c.category_id={category_id}"
        query += " limit 1000"
        query = text(query)
        async with async_session_maker() as session:
            result = await session.execute(query)
            data = result.mappings().all()
            data = [item["channel_id"] for item in data]
            return data

    @classmethod
    async def get_ids_wo_video(
        cls,
        report_period: Period,
        category_id: int = None,
    ):
        # TODO replace with alchemy query
        query = f"""select c.channel_id
                    from channel as c
                    left join video v on v.channel_id = c.channel_id and v.published_at_period = '{report_period.strf()}'
                    where c.status = 1 and v.id is null"""
        query += f" and c.category_id={category_id}" if category_id else ""
        # query += " group by c.channel_id having count(v.id) = 0"
        query = text(query)
        async with async_session_maker() as session:
            result = await session.execute(query)
            data = result.mappings().all()
            data = [item["channel_id"] for item in data]
            return data

    @classmethod
    async def search_channel(
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
                    item["status"] = 1
            await cls.add_update_bulk(data, do_nothing=True)
        return data

    @classmethod
    async def find_by_name(cls, name: str) -> str:
        channel = cls.find_one_or_none(custom_url=name)
        if not channel:
            [channel] = await cls.search_channel(name)
        if not channel:
            return None
        return channel.get("channel_id")

    @classmethod
    async def add_channels(cls, names: list[str], category_id: int = None):
        channel_ids = []
        for name in names:
            res = await cls.search_channel(name, category_id=category_id)
            if res:
                channel_ids.append(res[0].get("channel_id"))
        if channel_ids:
            await cls.update_detail(channel_ids=channel_ids)
        return channel_ids

    @classmethod
    async def update_detail(
        cls,
        channel_ids: list[str] | str = None,
        category_id: int = None,
        do_nothing: bool = False,
    ):
        if not channel_ids:
            if category_id:
                filters = {
                    "category_id": category_id,
                    "status": 1,
                }
            else:
                filters = {
                    "published_at": None,
                    "status": 1,
                }

            channel_ids = await cls.get_ids(filters=filters)

        data = yt.channel_list(channel_ids, obj_type="detail")
        if data:
            await cls.add_update_bulk(data, do_nothing=do_nothing)
        return data

    @classmethod
    async def search_by_keywords(
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

        return await cls.update_detail(unique_channel_ids, do_nothing=True)

    @classmethod
    async def get_channels_to_fetch_videos(
        cls,
        category_id: int = None,
        date_to: date = date.today(),
    ):
        query = select(Channel.channel_id, Channel.last_video_fetch_dt).where(
            Channel.status == 1,
            or_(
                Channel.last_video_fetch_dt.is_(None),
                Channel.last_video_fetch_dt < date_to,
            ),
        )
        if category_id:
            query = query.where(Channel.category_id == category_id)
        query = query.limit(1000).order_by(Channel.last_video_fetch_dt.desc())

        query = f"""select
    ch.channel_id, ch.last_video_fetch_dt
    
from channel_stat_change as csc
left join channel ch on csc.channel_id = ch.channel_id
left join category as c on ch.category_id = c.id
where total_view_count_change is not null
and (ch.last_video_fetch_dt  is null or ch.last_video_fetch_dt < '{date_to}') 
and category_id={category_id} and csc.report_period='2025-03-01'
order by csc.report_period desc, c.category, total_view_count_change desc
"""
        query = text(query)

        async with async_session_maker() as session:
            result = await session.execute(query)
            data = result.mappings().all()
            # data = [item["channel_id"] for item in data]
            return data

    @classmethod
    async def fetch_new_videos(
        cls,
        category_ids: list[int] | int,
        date_from: date = None,
        date_to: date = date.today(),
        # period: Period | tuple[datetime, datetime] = Period(),
    ):

        if isinstance(category_ids, int):
            category_ids = [category_ids]
        # if isinstance(period, Period):
        #     period = period.as_range()
        # date_from = period

        for i, category_id in enumerate(category_ids, start=1):
            channels = await cls.get_channels_to_fetch_videos(
                date_to=date_to,
                category_id=category_id,
            )
            for index, channel in enumerate(channels, start=1):
                channel_id = channel["channel_id"]
                date_from = channel["last_video_fetch_dt"] or date_from
                logger.info(f"{index}/{len(channels)}: {channel_id}")
                res = await VideoDAO.get_from_playlist(
                    channel_id, date_from=date_from, max_result=50
                )
                # ToDo различать ситуации, когда видео нет из-за ошибки или их просто нет
                await cls.update(
                    {"channel_id": channel_id},
                    {"last_video_fetch_dt": date_to},
                )

            logger.info(
                f"Category {i}/{len(category_ids)}: Updated {len(channels)} channels"
            )

        return True

    @classmethod
    async def save_thumbnails(cls, filters: dict = {}):
        from app.report.tools import save_thumbnails

        if "status" not in filters.keys():
            filters["status"] = 1
        channels = await cls.find_all(**filters)
        return save_thumbnails(channels)


class ChannelStatDAO(BaseDAO):
    model = ChannelStat

    @classmethod
    async def update_stat(
        cls,
        report_period: Period,
        channel_ids: list[str] | str = None,
        category_id: int = None,
    ):
        if not channel_ids:
            channel_ids = await ChannelDAO.get_ids_wo_stat(
                report_period=report_period, category_id=category_id
            )
            logger.info(f"Found {len(channel_ids)} channels wo stat")

        data = yt.channel_list(channel_ids, obj_type="stat")

        if data:
            for item in data:
                item["report_period"] = report_period
            await cls.add_bulk(data)
        return data
