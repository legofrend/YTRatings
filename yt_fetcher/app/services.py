import os
import requests


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
