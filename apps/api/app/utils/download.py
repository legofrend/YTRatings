"""Small HTTP/file helpers (logos, thumbnails)."""

from __future__ import annotations

import os

import requests

from app.channel.schemas import SChannel
from app.logger import logger
from app.media_paths import channel_logo_dir


def download_file(from_url: str, to_file: str) -> bool:
    response = requests.get(from_url)

    if response.status_code == 200:
        with open(to_file, "wb") as f:
            f.write(response.content)
        return True

    logger.error(
        f"Не удалось загрузить файл по линку {from_url}: статус {response.status_code}"
    )
    return False


def save_thumbnails(channels: list[SChannel], output_dir: str | None = None):
    main_dir = output_dir or str(channel_logo_dir())
    out = main_dir + os.sep + "new"
    os.makedirs(out, exist_ok=True)
    errors = []
    downloaded = 0
    for channel in channels:
        logo_file = channel.custom_url or channel.channel_id
        logo_file_check = os.path.join(main_dir, logo_file + ".jpg")
        logo_path = os.path.join(out, logo_file + ".jpg")
        if not os.path.exists(logo_file_check):
            if not download_file(channel.thumbnail_url, logo_path):
                logger.error(
                    f"Can't download logo for channel {channel.custom_url}: "
                    f"{channel.thumbnail_url}"
                )
                errors.append(channel.channel_id)
            else:
                downloaded += 1

    logger.info(f"Downloaded {downloaded} of {len(channels)} thumbnails")
    if errors:
        logger.error(f"Can't download {len(errors)} thumbnails")
    return errors
