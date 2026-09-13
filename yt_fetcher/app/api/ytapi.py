import asyncio
import random
import sys
import time

# import nest_asyncio
import aiohttp
from typing import Literal
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from datetime import date, datetime, timedelta
import re

import requests

from app.logger import logger
from app.config import settings

from googleapiclient.errors import HttpError


class QuotaExceededException(Exception):
    pass


YT_TIME_REGEX = re.compile(
    r"^P(?:\d+D)?(?:T(?:\d+H)?(?:\d+M)?(?:\d+S)?)?$"
)
DATETIME_YT_F = "%Y-%m-%dT%H:%M:%SZ"
DATETIME_YT_F2 = "%Y-%m-%dT%H:%M:%S.%fZ"

IS_QUOTA_EXCEEDED = False

OrderType = Literal["date", "rating", "relevance", "title", "videoCount", "viewCount"]
PlaylistKind = Literal["uploads", "shorts"]
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


def ytfmt2dt(dt_str: str) -> datetime | None:
    format = DATETIME_YT_F if "." not in dt_str else DATETIME_YT_F2
    try:
        dt = datetime.strptime(dt_str, format)
    except ValueError:
        logger.error(f"Invalid datetime string: {dt_str}")
        return None
    return dt


def channel_to_playlist_id(channel_id: str, playlist_kind: PlaylistKind = "uploads") -> str:
    """UC… → UU… (uploads) or UUSH… (shorts). Pass-through if already a playlist id."""
    if channel_id.startswith("UC"):
        prefix = "UUSH" if playlist_kind == "shorts" else "UU"
        return prefix + channel_id[2:]
    return channel_id


def parse_yt_time(s):
    if not s:
        return 0
    if not isinstance(s, str):
        return int(s)
    if s in ("P0D", "PT0S"):
        return 0
    if not YT_TIME_REGEX.match(s):
        logger.error("invalid string " + s)
        return 0

    def _n(unit: str) -> int:
        m = re.search(rf"(\d+){unit}", s)
        return int(m.group(1)) if m else 0

    days, hour, min, sec = _n("D"), _n("H"), _n("M"), _n("S")
    return days * 86400 + hour * 3600 + min * 60 + sec


def search_list(
    query: str,
    max_result: int = 50,
    published: tuple[datetime, datetime] = None,
    order: OrderType = "",
    type: ResourseType = "video",
    channel_id: str = None,
    page_token: str = None,
):
    global IS_QUOTA_EXCEEDED
    if IS_QUOTA_EXCEEDED:
        raise QuotaExceededException("YouTube API quota exceeded")
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
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                logger.error(
                    "YouTube API quota exceeded",
                    extra={"query": query, "params": params, "response": response},
                    exc_info=True,
                )
                IS_QUOTA_EXCEEDED = True
                return data
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


def playlistitem_list(
    playlist_id: str,
    date_from: datetime = None,
    date_to: datetime | date | None = None,
    max_result: int = 500,
    playlist_kind: PlaylistKind = "uploads",
) -> list[dict]:
    """
    Get videos from playlist with published_at in [date_from, date_to).
    Playlist is newest-first; stop when items fall below date_from.
    playlist_kind: uploads (UU…) or shorts (UUSH…) when playlist_id is a channel id (UC…).
    """
    global IS_QUOTA_EXCEEDED
    if IS_QUOTA_EXCEEDED:
        raise QuotaExceededException("YouTube API quota exceeded")

    if playlist_id.startswith("UC"):
        playlist_id = channel_to_playlist_id(playlist_id, playlist_kind)

    if isinstance(date_to, date) and not isinstance(date_to, datetime):
        date_to = datetime.combine(date_to, datetime.min.time())

    params = {
        "part": "snippet,contentDetails",
        "playlistId": playlist_id,
        "maxResults": 50,
    }

    data = []
    next_page_token = None
    continue_cycle = True

    while continue_cycle:
        try:
            if next_page_token:
                params["pageToken"] = next_page_token

            response = youtube.playlistItems().list(**params).execute()

            # Parse items
            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                content = item.get("contentDetails", {})

                published_dt = ytfmt2dt(snippet.get("publishedAt"))

                if date_to and published_dt >= date_to:
                    # Too new for this report window — skip, keep paging
                    continue

                if date_from and published_dt < date_from:
                    # Reached older-than-window; rest of playlist is older
                    continue_cycle = False
                    # break
                    # continue
                else:
                    published_period_dt = published_dt.replace(day=1).date()
                    url = "https://www.youtube.com/watch?v=" + content.get("videoId")
                    video = {
                        "video_id": content.get("videoId"),
                        "channel_id": snippet.get("channelId"),
                        "title": snippet.get("title"),
                        "description": snippet.get("description"),
                        "published_at": published_dt,
                        "published_at_period": published_period_dt,
                        "video_url": url,
                        "thumbnail_url": snippet.get("thumbnails", {})
                        .get("high", {})
                        .get("url"),
                        #     "channel_title": snippet.get("channelTitle"),
                        #     "position": snippet.get("position"),
                    }

                    data.append(video)

            next_page_token = response.get("nextPageToken")
            if not next_page_token or len(data) >= max_result:
                break

        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(
                    "Playlist not found (empty or missing)",
                    extra={"playlist_id": playlist_id, "playlist_kind": playlist_kind},
                )
                return data
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                logger.error(
                    "YouTube API quota exceeded",
                    extra={"playlist_id": playlist_id, "error": str(e)},
                    exc_info=True,
                )
                IS_QUOTA_EXCEEDED = True
                return data

            logger.error(
                "Can't execute playlist items list",
                extra={"playlist_id": playlist_id, "error": str(e)},
                exc_info=True,
            )
            break
        except Exception as e:
            logger.error(
                "Can't execute playlist items list",
                extra={"playlist_id": playlist_id, "error": str(e)},
                exc_info=True,
            )
            break

    return data


def channel_or_video_list(
    ids: list | str,
    obj_type: Literal["channel_stat", "video_stat", "channel_detail", "video_detail"],
):
    global IS_QUOTA_EXCEEDED
    if IS_QUOTA_EXCEEDED:
        raise QuotaExceededException("YouTube API quota exceeded")

    if isinstance(ids, str):
        ids = [ids]

    data = []
    iter = 0
    step = 50
    response = None  # Initialize response variable

    while iter < len(ids):
        try:
            part_ids = ",".join(ids[iter : (iter + step)])

            data_dt = datetime.now()
            if obj_type in ("channel_stat", "channel_detail"):
                response = (
                    youtube.channels()
                    .list(id=part_ids, part="snippet,statistics,contentDetails")
                    .execute()
                )
            elif obj_type in ("video_stat", "video_detail"):
                response = (
                    youtube.videos()
                    .list(id=part_ids, part="statistics,contentDetails")
                    .execute()
                )

            # logger.debug("Get stat", extra={"obj_type": obj_type, "response": response})
            response["data_dt"] = data_dt
            d = parse_response(response, type=obj_type)
            data.extend(d)

            iter += step
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                logger.error(
                    "YouTube API quota exceeded",
                    extra={"obj_type": obj_type, "response": response},
                    exc_info=True,
                )
                IS_QUOTA_EXCEEDED = True
                return data
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
        snippet = item.get("snippet")
        stat = item.get("statistics")
        if snippet and snippet.get("publishedAt"):
            published_dt = ytfmt2dt(snippet.get("publishedAt"))
            published_period_dt = published_dt.replace(day=1).date()

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
                "channel_title": snippet.get("title"),
                "description": snippet.get("description", ""),
                "published_at": published_dt,
                "custom_url": snippet.get("customUrl", ""),
                "thumbnail_url": snippet.get("thumbnails", {})["medium"]["url"],
                # "uploads_playlist_id": item.get("contentDetails", {})
                # .get("relatedPlaylists", {})
                # .get("uploads"),
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
            # >3 min → definitely not a Short; ≤3 min left NULL → fill from playlist_shorts
            video_id = item.get("id")
            duration = parse_yt_time(item["contentDetails"].get("duration", ""))
            is_short = False if duration > 3 * 60 else None

            val = {
                "video_id": video_id,
                "duration": duration,
                "is_short": is_short,
                "video_url": f"https://www.youtube.com/watch?v={video_id}",
            }

        data.append(val)

    return data


# working with YT through direct requests, to get info about shorts


# result in the list of proxies like ['http://127.0.0.1:9050', 'http://127.0.0.1:9051']
def find_proxies() -> list[str]:
    url = "https://free-proxy-list.net/"
    try:
        response = requests.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", {"class": "table table-striped table-bordered"})
        proxies = []

        for row in table.find_all("tr")[1:]:
            columns = row.find_all("td")
            if len(columns) > 0:
                ip = columns[0].text.strip()
                port = columns[1].text.strip()
                proxy = f"http://{ip}:{port}"
                proxies.append(proxy)

        logger.info(f"Successfully found {len(proxies)} proxies")
        return proxies
    except Exception as e:
        logger.error(f"Failed to fetch proxies: {str(e)}")
        return []


# Функция для выполнения запросов с п/овторными попытками
def retry_request(url, params=None, retries=5, delay=5):
    for attempt in range(retries):
        proxy = {"http": random.choice(find_proxies())}

        try:
            response = requests.get(url, params=params, proxies=proxy)
            response.raise_for_status()
            logger.debug(f"Request successful with proxy {proxy}")
            return response
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed with proxy {proxy}: {str(e)}")
            if attempt < retries - 1:
                logger.info(
                    f"Attempt {attempt + 1} of {retries}. Retrying in {delay} seconds..."
                )
                time.sleep(delay)
            else:
                logger.error("Maximum retry attempts reached. Giving up.")
                return None


# Функция для выполнения запросов с п/овторными попытками
def choose_proxy(
    url: str = None, params: dict = None, retries: int = 5, delay: int = 5
):
    if not url:
        url = "https://www.youtube.com"
    proxies = find_proxies()
    for attempt in range(retries):
        choice = random.choice(proxies)
        proxy = {"http": choice}

        try:
            response = requests.get(url, params=params, proxies=proxy)
            response.raise_for_status()
            logger.debug(f"Request successful with proxy {proxy}")
            return "http://" + choice
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed with proxy {proxy}: {str(e)}")
            if attempt < retries - 1:
                logger.info(
                    f"Attempt {attempt + 1} of {retries}. Retrying in {delay} seconds..."
                )
                time.sleep(delay)
            else:
                logger.error("Maximum retry attempts reached. Giving up.")
                return None


async def check_short(video: dict, proxy: str = None):
    video_id = video["video_id"]
    url = f"https://www.youtube.com/shorts/{video_id}"

    timeout = aiohttp.ClientTimeout(total=30, connect=10)
    connector = aiohttp.TCPConnector(limit=100, limit_per_host=5)

    try:
        async with aiohttp.ClientSession(
            timeout=timeout, connector=connector
        ) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    video["is_short"] = True  # Это шорт
                elif response.status == 303:
                    video["is_short"] = False  # Это обычное видео
                    url = f"https://www.youtube.com/watch?v={video_id}"
                else:
                    logger.error(f"{video_id=}, status={response.status}")
                    video["is_short"] = None  # Не удалось определить
    except (
        aiohttp.ClientConnectorError,
        aiohttp.ClientTimeout,
        asyncio.TimeoutError,
    ) as e:
        logger.warning(f"Connection error for {video_id}: {e}")
        video["is_short"] = None
    except Exception as e:
        logger.error(f"Unexpected error for {video_id}: {e}")
        video["is_short"] = None

    video["video_url"] = url
    return video["is_short"]


async def limited_gather(sem, tasks):
    async with sem:
        await asyncio.sleep(0.5)  # Заменили time.sleep на asyncio.sleep
        return await asyncio.gather(*tasks, return_exceptions=True)


def _fmt_eta(seconds: float) -> str:
    if seconds <= 0:
        return "?"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _print_shorts_progress(done: int, total: int, start: float) -> None:
    elapsed = time.monotonic() - start
    pct = 100.0 * done / total if total else 100.0
    eta = (elapsed / done * (total - done)) if done > 0 else 0
    msg = f"Checking shorts: {done}/{total} ({pct:.1f}%) ETA {_fmt_eta(eta)}"
    sys.stdout.write(f"\r{msg:<72}")
    sys.stdout.flush()


async def check_shorts(data: list[dict]):
    tasks = []
    limit = 3  # Уменьшили с 10 до 3 для снижения нагрузки
    proxy = None
    # proxy = choose_proxy()
    # if not proxy:
    #     logger.warning(f"No proxy available")

    for item in data:
        if item.get("is_short") is None or item.get("is_short") == "":
            tasks.append(check_short(item, proxy))

    if not tasks:
        return []

    total = len(tasks)
    logger.info(f"Checking shorts: {total}")

    sem = asyncio.Semaphore(limit)
    chunk_size = limit * 10  # progress every ~30 videos
    results: list = []
    start = time.monotonic()
    for chunk_start in range(0, total, chunk_size):
        chunk = tasks[chunk_start : chunk_start + chunk_size]
        chunk_results = await asyncio.gather(
            *(
                limited_gather(sem, chunk[i : i + limit])
                for i in range(0, len(chunk), limit)
            ),
            return_exceptions=True,
        )
        results.extend(chunk_results)
        done = min(chunk_start + chunk_size, total)
        _print_shorts_progress(done, total, start)

    if total:
        _print_shorts_progress(total, total, start)
        sys.stdout.write("\n")
        sys.stdout.flush()
        logger.info(
            f"Checking shorts done: {total} in {_fmt_eta(time.monotonic() - start)}"
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


# playlist_id = contentDetails.relatedPlaylists.uploads
# check_is_short()
# print("OK")
