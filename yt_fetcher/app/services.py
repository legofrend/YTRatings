from datetime import datetime, timedelta, date
import os
import requests

from app.period import Period
from app.logger import logger, save_json
from app.dao import ChannelDAO, ReportDAO, VideoDAO, VideoStatDAO, ChannelStatDAO


def update_data_for_period(
    category_id: int,
    period: Period = Period(),
):
    # ChannelStatDAO.update_stat(report_period=period, category_id=category_id)
    # VideoDAO.search_new_by_category_period(period=period, category_ids=category_id)
    # VideoDAO.update_detail()
    # VideoDAO.update_is_short()
    VideoStatDAO.update_stat(report_period=period, category_id=category_id)
    ReportDAO.build(period, category_id)


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
