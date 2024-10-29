from typing import Literal
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import re
import functools

import asyncio
import aiohttp

from app.logger import logger
from app.config import settings
from app.period import Period
from app.dao import VideoDAO, VideoStatDAO, ChannelStatDAO, ChannelDAO


YT_TIME_REGEX = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
DATETIME_YT_F = "%Y-%m-%dT%H:%M:%SZ"
DATETIME_YT_F2 = "%Y-%m-%dT%H:%M:%S.%fZ"

youtube = build(
    "youtube", "v3", developerKey=settings.YT_API_KEY, cache_discovery=False
)


def dt2ytfmt(dt: datetime):
    return dt.strftime(DATETIME_YT_F)


def parse_yt_time(s):
    if not s:
        return 0
    if not isinstance(s, str):
        return int(s)

    m = YT_TIME_REGEX.match(s)
    if not m:
        logger.error("invalid string " + s)
        return 0
    hour, min, sec = (int(g) if g is not None else 0 for g in m.groups())
    secs = hour * 60 * 60 + min * 60 + sec
    return secs


OrderType = Literal["date", "rating", "relevance", "title", "videoCount", "viewCount"]
# videoCount – Channels are sorted in descending order of their number of uploaded videos.
# viewCount – Resources are sorted from highest to lowest number of views. For live broadcasts, videos are sorted by number of concurrent viewers while the broadcasts are ongoing.
ResourseType = Literal["video", "channel", "playlist"]
TableType = Literal[
    "channel", "video", "channel_stat", "video_stat", "video_detail", "channel_detail"
]


def store_db(dao_class, mode: Literal["add_update", "add_skip", "add"] = "add_update"):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Получаем результат выполнения функции
            data = func(*args, **kwargs)
            if data:
                if mode == "add":
                    dao_class.add_bulk(data)
                else:
                    dao_class.add_update_bulk(data, skip_if_exist=(mode == "add_skip"))
            return data

        return wrapper

    return decorator


def get_search_list(
    query: str,
    max_result: int = 50,
    published: list | datetime = [],
    order: OrderType = "",
    type: ResourseType = "video",
    channel_id: str = None,
    page_token: str = None,
):

    params = {
        # "q": query,
        "part": "snippet",
        "type": type,
        "maxResults": min(max_result, 50),
    }
    if published:
        published_after = (
            dt2ytfmt(published)
            if isinstance(published, datetime)
            else dt2ytfmt(published[0])
        )
        published_before = (
            dt2ytfmt(published[1])
            if not isinstance(published, datetime) and len(published) > 1
            else None
        )
        if published_after:
            params["publishedAfter"] = published_after
        if published_before:
            params["publishedBefore"] = published_before

    if order:
        params["order"] = order
    if channel_id:
        params["channelId"] = channel_id
    if page_token:
        params["pageToken"] = page_token

    data = []
    next_page_token = None

    while True:
        try:
            response = youtube.search().list(q=query, **params).execute()
            d = parse_response(response, type=type)
            data.extend(d)
        except Exception as e:
            logger.error(
                "Can't execute search list",
                extra={"query": query, "params": params, "response": response},
                exc_info=True,
            )
            break

        # Получение следующей страницы
        next_page_token = response.get("nextPageToken")
        # Если нет следующей страницы, выходим из цикла
        if (not next_page_token) or len(data) >= max_result:
            break

        params["pageToken"] = next_page_token

    total_results = response["pageInfo"].get("totalResults", 0)
    if total_results > len(data):
        logger.debug(
            "Seems we didn't fetch all data",
            extra={
                "totalResults": total_results,
                "fetchedResults": len(data),
                "nextPageToken": response.get("nextPageToken"),
            },
        )

    return data


@store_db(ChannelDAO, mode="add_skip")
def find_channel(query: str, max_result: int = 1, order: OrderType = "relevance"):
    data = get_search_list(
        query=query, type="channel", max_result=max_result, order=order
    )
    return data


def find_channels(names: list):
    data = [find_channel(name) for name in names]
    return data


def get_stat(
    ids: list | str,
    obj_type: Literal["channel_stat", "video_stat", "channel_detail", "video_detail"],
):
    if isinstance(ids, str):
        ids = [ids]

    data = []
    iter = 0
    step = 50
    while iter < len(ids):
        try:
            part_ids = ",".join(ids[iter : (iter + step)])

            data_dt = datetime.now()
            if obj_type in ("channel_stat", "channel_detail"):
                response = (
                    youtube.channels()
                    .list(id=part_ids, part="snippet,statistics")
                    .execute()
                )
            elif obj_type in ("video_stat", "video_detail"):
                response = (
                    youtube.videos()
                    .list(id=part_ids, part="statistics,contentDetails")
                    .execute()
                )

            logger.debug("Get stat", extra={"obj_type": obj_type, "response": response})
            response["data_dt"] = data_dt
            d = parse_response(response, type=obj_type)
            data.extend(d)

            iter += step
        except Exception as e:
            logger.error(
                "Can't execute list",
                extra={"obj_type": obj_type, "response": response},
                exc_info=True,
            )
            break

    return data


@store_db(VideoStatDAO, mode="add")
def get_video_stat(video_ids: list | str):
    return get_stat(video_ids, "video_stat")


@store_db(VideoDAO, mode="add_update")
def get_video_detail(video_ids: list | str):
    return get_stat(video_ids, "video_detail")


@store_db(ChannelStatDAO, mode="add")
def get_channel_stat(channel_ids: list | str):
    return get_stat(channel_ids, "channel_stat")


@store_db(ChannelDAO, mode="add_update")
def get_channel_detail(channel_ids: list | str):
    return get_stat(channel_ids, "channel_detail")


def parse_response(response, type: TableType):
    data = []
    for item in response.get("items"):
        info = item.get("snippet")
        stat = item.get("statistics")
        if info and info.get("publishedAt"):
            try:
                published_dt = datetime.strptime(info.get("publishedAt"), DATETIME_YT_F)
            except Exception as e:
                published_dt = datetime.strptime(
                    info.get("publishedAt"), DATETIME_YT_F2
                )

        if type == "video":
            # TODO добавить is_short
            is_short = 0
            url = "https://www.youtube.com/" + ("watch?v=" if is_short else "shorts/")
            val = {
                "video_id": item["id"]["videoId"],
                "channel_id": item["snippet"]["channelId"],
                "title": item["snippet"]["title"],
                "description": item["snippet"]["description"],
                "published_at": published_dt,
                # shorts/item["id"]["videoId"]
                "video_url": url + item["id"]["videoId"],
                "thumbnail_url": item["snippet"]["thumbnails"]["high"]["url"],
            }
        elif type == "channel":
            val = {
                "channel_id": item["id"]["channelId"],
                "channel_title": item["snippet"]["channelTitle"],
                "description": item["snippet"].get("description", ""),
            }
        elif type == "channel_detail":

            val = {
                "channel_id": item.get("id"),
                "channel_title": info.get("title"),
                "description": info.get("description", ""),
                "published_at": published_dt,
                "custom_url": info.get("customUrl", ""),
                "thumbnail_url": info.get("thumbnails", {})["medium"]["url"],
            }
        elif type == "channel_stat":
            val = {
                "channel_id": item.get("id"),
                "data_at": response.get("data_dt", datetime.now()),
                "channel_view_count": int(stat.get("viewCount", 0)),
                "subscriber_count": int(stat.get("subscriberCount", 0)),
                "video_count": int(stat.get("videoCount", 0)),
            }

        elif type == "video_stat":
            val = {
                "video_id": item.get("id"),
                "data_at": response.get("data_dt", datetime.now()),
                "view_count": int(stat.get("viewCount", 0)),
                "like_count": int(stat.get("likeCount", 0)),
                "comment_count": int(stat.get("commentCount", 0)),
            }
        elif type == "video_detail":
            # Определение типа видео (short или обычное)
            video_id = item.get("id")
            duration = parse_yt_time(item["contentDetails"].get("duration", ""))
            is_short = 0 if duration > 65 else None  # Если меньше 1 минуты

            val = {
                "video_id": video_id,
                "duration": duration,
                "is_short": is_short,
            }

        data.append(val)

    return data


@store_db(VideoDAO, mode="add_skip")
def get_videos_by_period(channel_ids: list | str, period: Period | list[datetime]):
    if isinstance(channel_ids, str):
        channel_ids = [channel_ids]

    if isinstance(period, Period):
        period = period.as_range()

    if isinstance(period, list) and len(period) != 2:
        raise Exception("Invalid period")

    data = []
    for index in range(0, len(channel_ids)):
        channel_id = channel_ids[index]
        logger.info(f"{round(index / len(channel_ids)*100)}%")
        try:
            videos = get_search_list(
                "",
                published=period,
                type="video",
                channel_id=channel_id,
                order="viewCount",
                max_result=1000,
            )
            data.extend(videos)
            logger.info(f"Fetched {len(videos)} videos from channel {channel_id}")

        except Exception as e:
            logger.error(
                f"Can't get videos for channel id {index}: {channel_id}", exc_info=True
            )

    return data


def get_channels_by_keywords(
    query: str,
    date_from: datetime = datetime.now(),
    iterations: int = 8,
    date_step: int = 7,
    order: OrderType = "relevance",
    type: ResourseType = "video",
):

    data = []
    for _ in range(0, iterations):
        try:
            published_range = [date_from, date_from - timedelta(days=date_step)]
            videos = get_search_list(
                query,
                published=published_range,
                type=type,
                order=order,
                max_result=50,
            )
            data.extend(videos)
            logger.info(f"Fetched {len(videos)} videos")

        except Exception as e:
            logger.error(f"Can't get videos", exc_info=True)

        date_from -= timedelta(days=date_step)

    unique_channel_ids = set(video["channel_id"] for video in data)
    unique_channel_ids = list(unique_channel_ids)
    logger.info(f"Get {len(unique_channel_ids)} unique channels")

    return get_channel_detail(unique_channel_ids)


async def check_short(video_id):
    url = f"https://www.youtube.com/shorts/{video_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                is_short = 1  # Это шорт
            elif response.status == 303:
                is_short = 0  # Это обычное видео
            else:
                logger.error(f"{video_id=}, status={response.status}")
                is_short = None  # Не удалось определить
            return video_id, is_short


async def main(video_ids):
    tasks = [check_short(video_id) for video_id in video_ids]
    return await asyncio.gather(*tasks)


def check_is_short():
    import time

    res = VideoDAO.find_all(is_short=None)
    step = 100
    video_ids = [item["video_id"] for item in res]
    total = len(video_ids)

    i = 0
    while i < total:
        results = asyncio.run(main(video_ids[i : (i + step)]))
        for video_id, is_short in results:
            url = (
                "https://www.youtube.com/"
                + ("shorts/" if is_short else "watch?v=")
                + video_id
            )
            VideoDAO.update(video_id, "video_id", is_short=is_short, video_url=url)
        i += step
        logger.info(f"Checking shorts {i}/{total}")
        time.sleep(1)


check_is_short()
# print("OK")
