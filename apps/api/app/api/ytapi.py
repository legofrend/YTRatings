import time

# import nest_asyncio
from typing import Literal
from googleapiclient.discovery import build
from datetime import date, datetime, timedelta
import re

from app.logger import logger
from app.config import settings
from app.api import yt_quota

from googleapiclient.errors import HttpError


class QuotaExceededException(Exception):
    pass


YT_TIME_REGEX = re.compile(
    r"^P(?:\d+D)?(?:T(?:\d+H)?(?:\d+M)?(?:\d+S)?)?$"
)
DATETIME_YT_F = "%Y-%m-%dT%H:%M:%SZ"
DATETIME_YT_F2 = "%Y-%m-%dT%H:%M:%S.%fZ"

IS_QUOTA_EXCEEDED = False

yt_quota.ensure_loaded()

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
# Swap host only — do not replace full _baseUrl or paths double (…/youtube/v3/youtube/v3/…).
_root = (settings.YT_API_ROOT_URL or "").strip()
if _root:
    if not _root.endswith("/"):
        _root += "/"
    _default_root = "https://youtube.googleapis.com/"
    if youtube._baseUrl.startswith(_default_root):
        youtube._baseUrl = _root + youtube._baseUrl[len(_default_root) :]
    elif "://www.googleapis.com/" not in youtube._baseUrl:
        # unexpected discovery shape: force www host, keep path after first /
        _path = youtube._baseUrl.split("/", 3)[-1]  # after https://host/
        youtube._baseUrl = _root + _path


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
            yt_quota.add("search.list")
            d = parse_response(response, type=type)
            data.extend(d)
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                yt_quota.add("search.list")
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
            yt_quota.add("playlistItems.list")

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
                yt_quota.add("playlistItems.list")
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
    ids: list | str | None = None,
    obj_type: Literal["channel_stat", "video_stat", "channel_detail", "video_detail"] = "channel_detail",
    *,
    handles: list[str] | str | None = None,
):
    """
    Fetch channels or videos by id.

    Channel lookups also accept YouTube handles via `handles` / auto-detect in `ids`
    (values not starting with UC… → forHandle, one API call each).
    """
    global IS_QUOTA_EXCEEDED
    if IS_QUOTA_EXCEEDED:
        raise QuotaExceededException("YouTube API quota exceeded")

    if ids is None:
        ids = []
    if isinstance(ids, str):
        ids = [ids]
    if handles is None:
        handles = []
    if isinstance(handles, str):
        handles = [handles]

    id_list: list[str] = []
    handle_list: list[str] = []
    for raw in list(ids) + list(handles):
        if raw is None:
            continue
        s = str(raw).strip()
        if not s:
            continue
        # URL → handle or channel id
        if "youtube.com/" in s or "youtu.be/" in s:
            if "/channel/" in s:
                s = s.split("/channel/", 1)[1].split("/", 1)[0].split("?", 1)[0]
            elif "/@" in s:
                s = s.split("/@", 1)[1].split("/", 1)[0].split("?", 1)[0]
            elif "@" in s:
                s = s.split("@", 1)[1].split("/", 1)[0].split("?", 1)[0]
        if s.startswith("@"):
            s = s[1:]
        if not s:
            continue
        if obj_type.startswith("channel_") and not s.startswith("UC"):
            handle_list.append(s)
        else:
            id_list.append(s)

    # de-dupe preserve order
    def _uniq(seq: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in seq:
            k = x.lower() if not x.startswith("UC") else x
            if k in seen:
                continue
            seen.add(k)
            out.append(x)
        return out

    id_list = _uniq(id_list)
    handle_list = _uniq(handle_list)

    data = []
    response = None

    # --- by channel/video id (batches of 50) ---
    step = 50
    iter_i = 0
    while iter_i < len(id_list):
        try:
            part_ids = ",".join(id_list[iter_i : (iter_i + step)])
            data_dt = datetime.now()
            if obj_type in ("channel_stat", "channel_detail"):
                response = (
                    youtube.channels()
                    .list(id=part_ids, part="snippet,statistics,contentDetails")
                    .execute()
                )
                yt_quota.add("channels.list")
            elif obj_type in ("video_stat", "video_detail"):
                response = (
                    youtube.videos()
                    .list(id=part_ids, part="statistics,contentDetails")
                    .execute()
                )
                yt_quota.add("videos.list")
            response["data_dt"] = data_dt
            data.extend(parse_response(response, type=obj_type))
            iter_i += step
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                op = (
                    "channels.list"
                    if obj_type.startswith("channel_")
                    else "videos.list"
                )
                yt_quota.add(op)
                logger.error(
                    "YouTube API quota exceeded",
                    extra={"obj_type": obj_type, "response": response},
                    exc_info=True,
                )
                IS_QUOTA_EXCEEDED = True
                return data
            logger.error(
                "Can't execute list",
                extra={"obj_type": obj_type, "response": response},
                exc_info=True,
            )
            break
        except Exception:
            logger.error(
                "Can't execute list",
                extra={"obj_type": obj_type, "response": response},
                exc_info=True,
            )
            break

    # --- by handle (API: one forHandle per request) ---
    if handle_list and not obj_type.startswith("channel_"):
        logger.warning("handles ignored for non-channel obj_type=%s", obj_type)
        handle_list = []

    for handle in handle_list:
        if IS_QUOTA_EXCEEDED:
            break
        try:
            data_dt = datetime.now()
            response = (
                youtube.channels()
                .list(forHandle=handle, part="snippet,statistics,contentDetails")
                .execute()
            )
            yt_quota.add("channels.list")
            response["data_dt"] = data_dt
            got = parse_response(response, type=obj_type)
            if not got:
                logger.warning(f"forHandle={handle}: not found")
            data.extend(got)
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                yt_quota.add("channels.list")
                logger.error(
                    "YouTube API quota exceeded",
                    extra={"obj_type": obj_type, "handle": handle},
                    exc_info=True,
                )
                IS_QUOTA_EXCEEDED = True
                break
            logger.error(
                f"Can't execute channels.list forHandle={handle}",
                exc_info=True,
            )
        except Exception:
            logger.error(
                f"Can't execute channels.list forHandle={handle}",
                exc_info=True,
            )

    return data


def channel_list(
    ids: list | str | None = None,
    obj_type: Literal["stat", "detail"] = "detail",
    *,
    handles: list[str] | str | None = None,
):
    return channel_or_video_list(
        ids, obj_type="channel_" + obj_type, handles=handles
    )


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
