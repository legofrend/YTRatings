import asyncio
import time
import nest_asyncio
import aiohttp
from typing import Literal
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import re

from app.logger import logger
from app.config import settings

nest_asyncio.apply()


YT_TIME_REGEX = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
DATETIME_YT_F = "%Y-%m-%dT%H:%M:%SZ"
DATETIME_YT_F2 = "%Y-%m-%dT%H:%M:%S.%fZ"

OrderType = Literal["date", "rating", "relevance", "title", "videoCount", "viewCount"]
# videoCount – Channels are sorted in descending order of their number of uploaded videos.
# viewCount – Resources are sorted from highest to lowest number of views. For live broadcasts, videos are sorted by number of concurrent viewers while the broadcasts are ongoing.
ResourseType = Literal["video", "channel", "playlist"]
TableType = Literal[
    "channel", "video", "channel_stat", "video_stat", "video_detail", "channel_detail"
]

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


def search_list(
    query: str,
    max_result: int = 50,
    published: tuple[datetime, datetime] = None,
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
        # "relevanceLanguage": "en",  # en ru
    }
    if published:
        after, before = published
        if after:
            params["publishedAfter"] = dt2ytfmt(after)
        if before:
            params["publishedBefore"] = dt2ytfmt(before)

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
            return data

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


def channel_or_video_list(
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


def channel_list(
    ids: list | str,
    obj_type: Literal["stat", "detail"],
):
    return channel_or_video_list(ids, obj_type="channel_" + obj_type)


def video_list(
    ids: list | str,
    obj_type: Literal["stat", "detail"],
):
    return channel_or_video_list(ids, obj_type="video_" + obj_type)


def parse_response(response, type: TableType) -> list[dict]:
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
                # TODO: check
            published_period_dt = published_dt.replace(day=1)

        if type == "video":
            url = "https://www.youtube.com/watch?v=" + item["id"]["videoId"]
            val = {
                "video_id": item["id"]["videoId"],
                "channel_id": item["snippet"]["channelId"],
                "title": item["snippet"]["title"],
                "description": item["snippet"]["description"],
                "published_at": published_dt,
                "published_at_period": published_period_dt,
                # shorts/item["id"]["videoId"]
                "video_url": url,
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
            is_short = (
                0 if duration > 65 else None
            )  # Если больше 1 минуты, то точно не short

            val = {
                "video_id": video_id,
                "duration": duration,
                "is_short": is_short,
                "video_url": f"https://www.youtube.com/watch?v={video_id}",
            }

        data.append(val)

    return data


async def check_short(video: dict):
    video_id = video["video_id"]
    url = f"https://www.youtube.com/shorts/{video_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                video["is_short"] = True  # Это шорт
            elif response.status == 303:
                video["is_short"] = False  # Это обычное видео
                url = f"https://www.youtube.com/watch?v={video_id}"
            else:
                logger.error(f"{video_id=}, status={response.status}")
                video["is_short"] = None  # Не удалось определить
    # video["is_short"] = is_short
    video["video_url"] = url
    return video["is_short"]


async def limited_gather(sem, tasks):
    async with sem:
        time.sleep(0.5)
        return await asyncio.gather(*tasks)


async def check_shorts(data: list[dict]):
    tasks = []
    limit = 50
    for item in data:
        if item.get("is_short") is None or item.get("is_short") == "":
            tasks.append(check_short(item))

    # ограничиваем до limit одновременно выполняемых задач
    sem = asyncio.Semaphore(limit)
    results = await asyncio.gather(
        *(
            limited_gather(sem, tasks[i : i + limit])
            for i in range(0, len(tasks), limit)
        )
    )

    return results


async def check_short_old(video_id: str):
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
            url = (
                "https://www.youtube.com/"
                + ("shorts/" if is_short else "watch?v=")
                + video_id
            )
            # val = {"video_id": video_id, "is_short": is_short, "video_url": url}
            return is_short, url


def check_shorts_sync(video_ids: list[str]):

    import time

    async def main(video_ids):
        tasks = [check_short(video_id) for video_id in video_ids]
        return await asyncio.gather(*tasks)

    step = 100
    total = len(video_ids)
    data = []
    i = 0
    while i < total:
        results = asyncio.run(main(video_ids[i : (i + step)]))
        data.extend(results)

        i += step
        logger.info(f"Checking shorts {i}/{total}")
        time.sleep(1)

    return data


# check_is_short()
# print("OK")
