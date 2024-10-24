from datetime import datetime, timedelta, date
import os
import requests

import ytapi
from period import Period
from yt_fetcher.app.logger import logger, save_json
from dao import ChannelDAO, ReportDAO, VideoDAO, VideoStatDAO, ChannelStatDAO


def get_channel_ids_from_db(filter: dict = {"status": 1}):
    data = ChannelDAO.find_all(**filter)
    ids = [d.channel_id for d in data]
    return ids


def find_channels_by_title(ch_titles: list[str]) -> list[tuple[str, str]]:
    # Result is list of tuple with channel_id and channel_title
    ch_titles = [ch_titles] if not isinstance(ch_titles, list) else ch_titles
    res = []
    for title in ch_titles:
        channel = ChannelDAO.find_one_or_none(channel_title=title)
        if not channel:
            [channel] = ytapi.find_channels(title)
            ytapi.get_channel_detail([channel])

        res.append((channel.get("channel_id"), channel.get("channel_title")))
    return res


def get_video_ids_from_db(filters: dict = {}):
    data = VideoDAO.find_all(**filters)
    ids = [d.video_id for d in data]
    return ids


def update_info_for_period(
    titles: list[str] = None,
    channel_ids: list[str] = None,
    filter: dict = {"status": 1},
    period: Period = Period().next(-1),
):
    # 0. For each channel
    # 1.    get statistics from YT
    # 2.    get videos from YT for period
    # 3.    get videos from DB for previous period
    # 3. For each video get statistics from YT

    if titles:
        channel_ids = find_channels_by_title(titles)
    elif not channel_ids:
        channel_ids = get_channel_ids_from_db(filter=filter)

    prev_period = period.next(-1)
    # ytapi.get_channel_stat(channel_ids)

    # for channel_id in channel_ids:
    #     videos = ytapi.get_videos_by_period(channel_id, period)

    # return
    videos = []
    for channel_id in channel_ids:
        # TODO: check function
        videos_db = VideoDAO.find_all(
            channel_id=channel_id, published_at_period=prev_period._date
        )
        videos.extend(videos_db) if videos_db else None

        video_ids = [v["video_id"] for v in videos]
        ytapi.get_video_stat(video_ids)


def download_thumbnails(data: list[dict], path: str = None):

    if not path:
        path = "video_gen/video_img"

    # Создаем папку img, если она не существует
    os.makedirs(path, exist_ok=True)

    for item in data:
        filename = item.get("filename") or item.get("channel_title")

        thumbnail_url = item["thumbnail_url"]

        # Загружаем изображение
        response = requests.get(thumbnail_url)

        if response.status_code == 200:
            # Сохраняем изображение
            with open(f"{path}/{filename}.jpg", "wb") as f:
                f.write(response.content)
        else:
            print(
                f"Не удалось загрузить изображение для {channel_id}: статус {response.status_code}"
            )


def rebuild_reports():
    return ReportDAO.build_reports([Period(i) for i in range(6, 10)], [1, 2, 3])
