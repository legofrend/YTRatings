import os
import sys
import asyncio
from datetime import date, datetime

sys.path.append(os.getcwd())

from app.period import Period
from app.report.dao import ReportDAO
from app.channel import ChannelDAO, ChannelStatDAO, VideoDAO, VideoStatDAO


# Categories
# 1	Политика
# 2	SC2
# 3	Юмор
# 5	Авто
# 6	Кино
# 7	Нейросети
# 8 AI Eng


async def actions():
    category_id = 5
    period = Period(12)
    per_range = [date(2024, 12, 1), date(2024, 12, 29)]

    start_dt = datetime.now()
    print("Start", start_dt)

    # await ChannelDAO.search_by_keywords(
    #     "новости и обзоры компьютерных игр",
    #     iterations=12,
    #     date_step=30,
    #     date_from=datetime(2024, 11, 1),
    #     type="video",
    #     max_result=50,
    #     # order="viewCount",
    # )

    names = """@syntxai  @ZHUBAN""".split("\n")  #

    # ch_ids = await ChannelDAO.add_channels(names, category_id=category_id)
    # for name in names:
    #     await ChannelDAO.search_channel(name, category_id=category_id)
    # await ChannelDAO.update_detail()
    # await ChannelStatDAO.update_stat(
    #     report_period=period, channel_ids=ch_ids, category_id=category_id
    # )

    # await ChannelStatDAO.update_stat(report_period=period)

    await ChannelDAO.search_new_by_category_period(
        period=per_range, category_ids=category_id
    )
    # or
    ids = """""".split("\n")

    # await VideoDAO.search_new_by_channel_period(period=per_range, channel_ids=ids)
    # await VideoDAO.update_detail()
    # await upload_from_file()
    # await VideoDAO.update_is_short()

    # await VideoStatDAO.update_stat(report_period=period, category_id=None)

    # await VideoDAO.eval_clickbait({"published_at_period": period})

    # for category_id in (4, 8, 11, 12):
    #     await ReportDAO.build(period, category_id)

    # tmpl_path = "../video_gen/2024-11/Нейросети/tmpl.png"
    # for category_id in (1, 5, 6, 7):
    #     await ReportDAO.generate_info_images(
    #         period, category_id, top_channels=20, top_videos_count=0
    #     )

    print("Finish after ", datetime.now() - start_dt)

    return True


async def upload_from_file():
    import csv

    csv_file_path = "logs/2024-12-21-14-01-08video_detail_errors_.csv"

    # Чтение CSV и преобразование в JSON
    with open(csv_file_path, mode="r", encoding="utf-8") as csv_file:
        csv_reader = csv.DictReader(csv_file, delimiter="\t")
        json_data = [row for row in csv_reader]

    njson_data = []
    for item in json_data:
        # item["data_at"] = datetime.strptime(item["data_at"], "%Y-%m-%d %H:%M:%S")
        # item["report_period"] = datetime.strptime(item["report_period"], "%Y-%m-%d")
        # for key in 'view_count like_count comment_count'.split(" "):
        # item[key] = int(item[key])
        item["duration"] = int(item["duration"])
        if item["is_short"] == "":
            item["is_short"] = None
            njson_data.append(item)

        # if item["is_short"] == "True":
        #     item["is_short"] = True
        # elif item["is_short"] == "0":
        #     item["is_short"] = False
        # else:
        #     item["is_short"] = None

        # item["is_short"] = bool(item["is_short"])

    # 'data_at': '2024-12-01 00:05:29.664345', 'view_count': '350724', 'like_count': '15000', 'comment_count': '2113', 'report_period': '2024-11-01'

    print(len(njson_data))

    res = await VideoDAO.update_bulk(njson_data)


def main():
    asyncio.run(actions())


if __name__ == "__main__":
    main()
