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
    value: int,
    is_change: bool = False,
):
    text = display_value(value)
    color = "black" if not is_change else color_value(value)
    font = ImageFont.truetype("arial.ttf", font_size)

    bbox = draw.textbbox((0, 0), text, font=font)
    xy = get_abs_xy(xy, align, bbox)
    if is_change and value:
        r = font_size // 3
        xy_sign = (xy[0] - r // 2, xy[1] + 2 * r - (r // 2 if value < 0 else 0))
        rot = 180 if value < 0 else 0
        draw.regular_polygon((xy_sign, r), 3, rotation=rot, fill=color)
        xy[0] += r // 2

    draw.text(xy, text, fill=color, font=font)


def render_info_pic(period: date, category_name: str, channel: SChannel):

    # Prepare variables
    parent_dir = r"..\video_gen\\"
    work_dir = os.path.join(parent_dir, "templates")
    tmpl_path = os.path.join(work_dir, "tmpl.png")
    star_path = os.path.join(work_dir, "star.png")
    output_dir = os.path.join(parent_dir, period.strftime("%Y-%m"), category_name)
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
    for index, video in enumerate(channel.top_videos[:3], start=1):
        video_file = os.path.join(output_dir, f"{channel.rank}_{index}.jpg")
        if not os.path.exists(video_file):
            download_file(video.thumbnail_url, video_file)

    # Load template
    image = Image.open(tmpl_path)

    # Load and paste logo
    logo = Image.open(logo_file)
    logo = logo.resize((320, 320), Image.LANCZOS)
    logo_position = (140, 140)
    image.paste(logo, logo_position)

    # Load and paste 10x star in the top-left corner
    star = Image.open(star_path)
    image.paste(star, (0, 0), star)

    # Render values into template
    draw = ImageDraw.Draw(image)
    draw_value(draw, (100, 100), "cc", 96, channel.rank)
    draw_value(draw, (500, 100), "cc", 45, channel.rank_change, True)
    draw_value(draw, (170, 480), "tl", 24, channel.stat.score)
    draw_value(draw, (460, 480), "tr", 24, channel.stat.score_change, True)

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


def gen_script(data: list[SChannel]):
    tmpl_file = "../video_gen/templates/script_tmpl_ai_first.txt"
    output_file = "../video_gen/2024-10/Нейросети/script.txt"
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
