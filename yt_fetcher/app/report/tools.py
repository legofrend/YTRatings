import os
import requests
from datetime import date
from PIL import Image, ImageDraw, ImageFont

from app.logger import logger

# from app.report.dao import ReportDAO
from app.period.period import Period
from app.report.schemas import SChannel


def download_file(from_url: str, to_file: str):
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


def display_value(value):
    if value == 0:
        return "-"
    if abs(value) >= 10**6:
        return str(round(abs(value) / 10**6, 1)) + "M"
    if abs(value) >= 10**3:
        return str(round(abs(value) / 10**3)) + "K"
    return str(abs(value))


def color_value(value):
    if value == 0:
        return "black"
    return "green" if value > 0 else "red"


def get_abs_xy(xy: tuple, align: str, bbox: tuple) -> tuple:
    match align:
        case "cc":
            nxy = (xy[0] - bbox[2] // 2, xy[1] - (bbox[1] + bbox[3]) // 2)
        case "tc":
            nxy = (xy[0] - bbox[2] // 2, xy[1])
        case "tl":
            nxy = xy
        case "tr":
            nxy = (xy[0] - bbox[2], xy[1])
        case "bl":
            nxy = (xy[0], xy[1] - bbox[3])
        case "br":
            nxy = (xy[0] - bbox[2], xy[1] - bbox[3])
    return nxy


def draw_value(
    draw: ImageDraw,
    xy: tuple,
    align: str,
    font_size: int,
    value: int | str,
    is_change: bool = False,
):
    text = display_value(value) if isinstance(value, int) else value
    color = "black" if not is_change else color_value(value)
    font = ImageFont.truetype("arial.ttf", font_size)

    bbox = draw.textbbox((0, 0), text, font=font)
    xy = get_abs_xy(xy, align, bbox)
    if is_change and value:
        r = font_size // 3
        xy_sign = (xy[0] - r // 2, xy[1] + 2 * r - (r // 2 if value < 0 else 0))
        rot = 180 if value < 0 else 0
        draw.regular_polygon((xy_sign, r), 3, rotation=rot, fill=color)
        xy = (xy[0] + r // 2, xy[1])

    align_dict = {
        "c": "center",
        "l": "left",
        "r": "right",
    }
    align_text = align_dict[align[1]]
    draw.multiline_text(xy, text, fill=color, font=font, align=align_text)


def split_text(text: str, limit: int):
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        # Проверяем, помещается ли слово в текущую строку
        if len(current_line) + len(word) + 1 <= limit:
            if current_line:
                current_line += " "  # Добавляем пробел перед словом
            current_line += word
        else:
            # Если текущее слово не помещается, добавляем текущую строку в вывод
            if current_line:
                lines.append(current_line)
            # Проверяем, помещается ли слово с переносом
            while len(word) > limit:
                lines.append(word[:limit] + "-")
                word = word[limit:]
            current_line = word  # Начинаем новую строку с текущего слова

    if current_line:
        lines.append(current_line)  # Добавляем последнюю строку

    return "\n".join(lines)


def render_info_pic(
    tmpl_path: str,
    period: date,
    category_name: str,
    channel: SChannel,
    top_videos_count: int = 1,
    output_dir: str = None,
):

    # Prepare variables
    parent_dir = r"..\video_gen\\"
    # work_dir = os.path.join(parent_dir, "templates")
    # tmpl_path = os.path.join(work_dir, "tmpl_movie.png")
    # star_path = os.path.join(work_dir, "star.png")
    output_dir = output_dir or os.path.join(
        parent_dir, period.strftime("%Y-%m"), category_name
    )
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, str(channel.rank) + ".png")
    logo_file = channel.custom_url or channel.channel_id
    logo_file = os.path.join(
        parent_dir, "channel_logo", category_name, logo_file + ".jpg"
    )
    if not os.path.exists(logo_file):
        if not download_file(channel.thumbnail_url, logo_file):
            return False

    # download thumbnails for top videos
    if top_videos_count > 0:
        for index, video in enumerate(channel.top_videos[:top_videos_count], start=1):
            video_file = os.path.join(output_dir, f"v_{channel.rank}_{index}.jpg")
            if not os.path.exists(video_file):
                download_file(video.thumbnail_url, video_file)

    # Load template
    image = Image.open(tmpl_path)

    # Load and paste logo
    logo = Image.open(logo_file)
    logo = logo.resize((320, 320), Image.LANCZOS)
    image.paste(logo, (128, 330))

    # Load and paste 10x star in the top-left corner
    # star = Image.open(star_path)
    # image.paste(star, (0, 0), star)

    # Render values into template
    draw = ImageDraw.Draw(image)

    draw_value(draw, (100, 100), "cc", 96, channel.rank)
    if channel.rank_change:
        draw_value(draw, (500, 100), "cc", 45, channel.rank_change, True)

    title = split_text(channel.channel_title, 20)
    draw_value(draw, (56 + 463 // 2, 194 + 137 // 2), "cc", 36, title)

    draw_value(draw, (260, 668), "tl", 24, channel.stat.score)
    if channel.stat.score_change:
        draw_value(draw, (347, 668), "tl", 24, channel.stat.score_change, True)

    draw_value(draw, (260, 705), "tl", 24, channel.stat.subscriber_count)
    if channel.stat.subscriber_count_change:
        draw_value(
            draw, (347, 705), "tl", 24, channel.stat.subscriber_count_change, True
        )

    video_count = channel.stat.videos - channel.stat.shorts
    draw_value(draw, (260, 740), "tl", 24, video_count)
    draw_value(draw, (380, 740), "tl", 24, channel.stat.shorts)

    if len(channel.top_videos) > 0:
        video_title = split_text(channel.top_videos[0].title, 40)
        # draw_value(draw, (100 + 387 // 2, 824 + 80 // 2), "cc", 12, video_title)
        draw_value(draw, (100, 830), "tl", 12, video_title)
        video_view = channel.top_videos[0].stat.view_count
        draw_value(draw, (332, 804), "tl", 20, video_view)

    image.save(output_file)
    return True


def text_value(value):
    if value == 0:
        return "без изменений"
    if abs(value) >= 10**6:
        return str(round(abs(value) / 10**6, 1)) + " миллионов"
    if abs(value) >= 10**3:
        return str(round(abs(value) / 10**3)) + " тысяч"
    return str(abs(value))


def gen_script(data: list[SChannel], tmpl_file: str, output_file: str):
    with open(tmpl_file, "r", encoding="utf-8") as f:
        tmlp = f.read()

    rdata = []
    for item in data:
        val = {
            "score_display": text_value(item.stat.score),
            "score_change_display": text_value(item.stat.score_change),
            "score_video_display": text_value(item.top_videos[0].stat.score),
            "channel_title": item.channel_title,
            "video_title": item.top_videos[0].title,
            "rank_change": item.rank_change,
        }

        rdata.append(val)

    # print(rdata[0])
    res = tmlp.format(data=rdata)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(res)


# def get_thumbnails(channel_ids: list[str] = None, category_id: int = None) -> None:

#     # workdir = r'C:\Users\eremi\Documents\4. Projects\2024-07 YTRatings\video_gen\channel_logo'
#     workdir = r"..\video_gen\channel_logo" + os.sep + str(category_id)
#     downloaded = 0
#     os.makedirs(workdir, exist_ok=True)
#     # if not channel_ids:
#     channels = ChannelDAO.find_all(category_id=category_id, status=1)

#     for channel in channels:
#         file_url = channel["thumbnail_url"]
#         file_name = channel.get("custom_url") or channel["channel_id"]
#         file_name += ".jpg"
#         full_path = os.path.join(workdir, file_name)
#         if not os.path.exists(full_path):
#             if download_file(file_url, full_path):
#                 downloaded += 1

#     return downloaded


def save_thumbnails(channels: list[SChannel], output_dir: str = None):

    output_dir = (
        output_dir
        or r"C:\Users\eremi\Documents\4. Projects\2024-07 YTRatings\frontend\public\channel_logo"
    )
    os.makedirs(output_dir, exist_ok=True)
    errors = []
    downloaded = 0
    for channel in channels:
        logo_file = channel.custom_url or channel.channel_id
        logo_file = os.path.join(output_dir, logo_file + ".jpg")
        if not os.path.exists(logo_file):
            if not download_file(channel.thumbnail_url, logo_file):
                logger.error(
                    f"Can't download logo for channel {channel.custom_url}: {channel.thumbnail_url}"
                )
                errors.append(channel.channel_id)
            else:
                downloaded += 1

    logger.info(f"Downloaded {downloaded} of {len(channels)} thumbnails")
    if errors:
        logger.error(f"Can't download {len(errors)} thumbnails")
    return errors
