from datetime import date, datetime
from sqlalchemy import text

from app.dao.base import BaseDAO
from app.database import async_session_maker
from app.logger import logger, save_errors
from app.period.period import Period
import app.api.ytapi as yt
import app.api.openaiapi as oai

from app.channel.video.models import Video, VideoStat


class VideoDAO(BaseDAO):
    model = Video
    gid = "video_id"

    @classmethod
    async def get_ids(cls, filters: dict = {}):
        data = await cls.find_all(**filters)
        ids = [d.video_id for d in data]
        return ids

    @classmethod
    async def get_ids_wo_stat(
        cls,
        report_period: Period,
        published_at_period: Period = None,
        category_id: int = None,
    ):
        if not published_at_period:
            published_at_period = report_period.next(-1)

        async with async_session_maker() as session:
            query = f"""select distinct v.video_id
                        from video as v
                        left join channel as c on c.channel_id = v.channel_id
                        left join video_stat vs on v.video_id = vs.video_id and vs.report_period = '{report_period.strf()}'
                        where vs.id is null and v.published_at_period >= '{published_at_period.strf()}'
                        ;
                    """
            if category_id:
                query += f" and c.category_id={category_id}"
            query = text(query)
            result = await session.execute(query)
            data = result.mappings().all()
            data = [item["video_id"] for item in data]
            return data

    @classmethod
    async def update_detail(cls, video_ids: list[str] | str = None):
        if not video_ids:
            video_ids = await cls.get_ids(
                filters={
                    "duration": None,
                }
            )
            if not video_ids:
                return None
        try:
            data = yt.video_list(video_ids, obj_type="detail")
            if not data:
                return None
            await yt.check_shorts(data)
            await cls.update_bulk(data)
        except:
            logger.error("Can't update video detail", exc_info=True)
            save_errors(data, "video_detail")

        return data

    @classmethod
    async def update_is_short(
        cls, video_ids: list[str] | str = None, do_nothing: bool = False
    ):
        if not video_ids:
            res = await cls.find_all(is_short=None)
            video_ids = [item["video_id"] for item in res]

        data = yt.check_shorts(video_ids)
        if data:
            await cls.add_update_bulk(data, do_nothing=do_nothing)
        return data

    @classmethod
    async def search_new_by_channel_period(
        cls,
        channel_ids: list[str] | str,
        period: Period | tuple[datetime, datetime] = Period(),
    ):
        if isinstance(channel_ids, str):
            channel_ids = [channel_ids]

        if isinstance(period, Period):
            period = period.as_range()

        if isinstance(period, tuple) and len(period) != 2:
            raise Exception("Invalid period")

        data = []

        for index in range(0, len(channel_ids)):
            channel_id = channel_ids[index]
            logger.info(f"{index+1}/{len(channel_ids)}: {channel_id}")
            try:
                videos = yt.search_list(
                    "",
                    published=period,
                    type="video",
                    channel_id=channel_id,
                    order="date",
                    max_result=500,
                )
                if videos:
                    await cls.add_update_bulk(videos, do_nothing=True)
                    data.extend(videos)

            except Exception as e:
                logger.error(
                    f"Can't get videos for channel id {index}: {channel_id}",
                    exc_info=True,
                )

        return data

    @classmethod
    async def get_thumbnails(
        cls, channel_ids: list[str] = None, category_id: int = None
    ) -> None:
        from app.report.tools import download_file
        import os

        # workdir = r'C:\Users\eremi\Documents\4. Projects\2024-07 YTRatings\video_gen\channel_logo'
        workdir = r"..\video_gen\channel_logo" + os.sep + str(category_id)
        os.makedirs(workdir, exist_ok=True)
        # if not channel_ids:
        channels = await cls.find_all(category_id=category_id, status=1)

        for channel in channels:
            file_url = channel["thumbnail_url"]
            file_name = channel.get("custom_url") or channel["channel_id"]
            full_path = os.path.join(workdir, file_name)
            if not os.path.exists(full_path):
                download_file(file_url, full_path)

    @classmethod
    async def eval_clickbait(cls, filters: dict = {}):
        LIMIT = 50
        instructions = """Ты на вход получишь данные с video_id и заголовком видео, разделенных табом. Для каждого заголовка тебе нужно определить, является ли он кликбейт и почему (clickbait_comment). Кликбейт — это термин, описывающий веб-контент, целью которого является получение дохода от онлайн-рекламы, особенно в ущерб качеству или точности информации. Пожалуйста, выведи только массив объектов в JSON формате:

[ { "video_id": <>, "is_clickbait": 1 or 0, "clickbait_comment": <> }, ... ]

Не добавляй в ответ никаких дополнительных слов, символов или переносов строк. Вот входные данные:"""

        if "is_clickbait" not in filters.keys():
            filters["is_clickbait"] = None
        if "is_short" not in filters.keys():
            filters["is_short"] = False
        videos = await cls.find_all(**filters)

        for i in range(0, len(videos), LIMIT):
            data = [
                (item["video_id"] + "\t" + item["title"])
                for item in videos[i : (i + LIMIT)]
            ]

            prompt = instructions + "\n".join(data) + "\n"
            response = oai.chat_with_gpt(prompt, is_json=True, temperature=0.5)
            if response:
                await cls.update_bulk(response)
            logger.info(f"Progress: {i+LIMIT}/{len(videos)}")


class VideoStatDAO(BaseDAO):
    model = VideoStat

    @classmethod
    async def update_stat(
        cls,
        report_period: Period,
        video_ids: list[str] | str = None,
        category_id: int = None,
    ):
        if not video_ids:
            video_ids = await VideoDAO.get_ids_wo_stat(
                report_period=report_period, category_id=category_id
            )

        data = yt.video_list(video_ids, obj_type="stat")

        if data:
            for item in data:
                item["report_period"] = report_period
            await cls.add_bulk(data)
        return data


# print("OK")
