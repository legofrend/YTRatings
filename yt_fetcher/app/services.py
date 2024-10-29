from datetime import datetime, timedelta, date
import os
import requests

import app.ytapi as ytapi
from app.period import Period
from app.logger import logger, save_json
from app.dao import ChannelDAO, ReportDAO, VideoDAO, VideoStatDAO, ChannelStatDAO


def find_channels_by_keywords(
    cls,
    keywords: str,
    category: int = None,
    category_name: str = None,
    max_results: int = 50,
):
    if not channel:
        return None
    return channel.get("channel_id")


def find_by_title(title: str) -> str:
    channel = ChannelDAO.find_one_or_none(channel_title=title)
    if not channel:
        [channel] = ytapi.find_channel(title)
    if not channel:
        return None
    return channel.get("channel_id")


def update_info_for_period(
    titles: list[str] = None,
    channel_ids: list[str] = None,
    filter: dict = {"status": 1},
    period: Period = Period().next(-1),
):
    # TODO: refactor
    # 0. For each channel
    # 1.    get statistics from YT
    # 2.    get videos from YT for period
    # 3.    get videos from DB for previous period
    # 3. For each video get statistics from YT

    # if titles:
    #     channel_ids = ChannelDAO.get(titles)
    if not channel_ids:
        channel_ids = ChannelDAO.get_ids(filter=filter)

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


def rebuild_reports():
    return ReportDAO.build_reports([Period(i) for i in range(6, 10)], [5])


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
