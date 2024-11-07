import os
import requests
from app.logger import logger


def download_file(from_url: str, to_file: str):

    # Загружаем изображение
    response = requests.get(from_url)

    if response.status_code == 200:
        # Сохраняем изображение
        with open(to_file, "wb") as f:
            f.write(response.content)
            return True
    else:
        logger.error(
            f"Не удалось загрузить файл по линку {from_url}: статус {response.status_code}"
        )
        return False


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


def get_thumbnails(data: list[dict], path: str = None):
    # TODO rewrite to general
    key = "thumbnail_url"
    thmbs = [
        {
            key: item["top_videos"][0][key],
            "filename": f"{data['period']}_{data['category_id']}_{item['rank']}",
        }
        for item in data["data"][:20]
    ]
    download_thumbnails(thmbs, "video_gen/2024-10/img")
