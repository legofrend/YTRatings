from datetime import date, datetime, timedelta

# import locale
from sqlalchemy import delete, insert, select, text, update


from app.dao import BaseDAO
from app.database import session_maker, engine
from app.logger import logger, save_errors
from app.video.models import Video, VideoStat
from app.period.period import Period

import app.ytapi as yt


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

    @classmethod
    def get_thumbnails(
        cls, channel_ids: list[str] = None, category_id: int = None
    ) -> None:
        from app.report.tools import download_file
        import os

        # workdir = r'C:\Users\eremi\Documents\4. Projects\2024-07 YTRatings\video_gen\channel_logo'
        workdir = r"..\video_gen\channel_logo" + os.sep + str(category_id)
        os.makedirs(workdir, exist_ok=True)
        # if not channel_ids:
        channels = cls.find_all(category_id=category_id, status=1)

        for channel in channels:
            file_url = channel["thumbnail_url"]
            file_name = channel.get("custom_url") or channel["channel_id"]
            full_path = os.path.join(workdir, file_name)
            if not os.path.exists(full_path):
                download_file(file_url, full_path)


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
