import os
import sys
import asyncio
from datetime import date, datetime

sys.path.append(os.getcwd())

from app.period import Period
from app.report.dao import ReportDAO
from app.channel import ChannelDAO, ChannelStatDAO, VideoDAO, VideoStatDAO


# Categories
# 1	Политика 1
# 2	SC2
# 3	Юмор
# 4	Финансы 1 23/30
# 5	Авто
# 6	Кино
# 7	Нейросети 1
# 8 AI Eng 1
# 11 Мода
# 12 Игры


async def prepare_monthly_report(step: int = 0):
    category_id = 10
    period = Period(3)
    per_range = [date(2025, 3, 1), date(2025, 4, 1)]

    step = step or 3

    ids = """""".split("\n")
    # Step 1. Update stat per channels
    if step == 1:
        res = await ChannelStatDAO.update_stat(report_period=period)
        print(f"Updated {len(res)} records")

    # Step 2. Fetch new videos
    if step == 2:
        res = await ChannelDAO.fetch_new_videos(
            category_ids=list(range(14, 19)), date_from=None, date_to=per_range[1]
        )
        # print(f"Fetched {len(res)} records")

    # Step 3. Update detail for videos without duration and or is_short
    if step == 3:
        for _ in range(0, 100):
            print(f"{_} out of 100")
            res = await VideoDAO.update_detail()
            # if res:
            #     print(f"Updated details for {len(res)} records")
        # res =await VideoDAO.update_is_short()
        # await upload_from_json_file()
        # res = await VideoDAO.eval_clickbait({"published_at_period": period})

    # Step 4. Update stat for videos
    if step == 4:
        res = await VideoStatDAO.update_stat(
            report_period=period, category_id=category_id
        )
        print(f"Updated {len(res)} records")

    # Step 5. Build reports
    if step == 5:
        for i in (1,):
            for category_id in (5, 7, 8):
                await ReportDAO.build(period, category_id)

    return True


def prepare_materials():
    pass

    # names = """""".split(" ")  #
    ids = """""".split("\n")

    # ch_ids = await ChannelDAO.add_channels(names, category_id=category_id)
    # for name in names:
    #     await ChannelDAO.search_channel(name, category_id=category_id)
    # await ChannelDAO.update_detail()
    # await ChannelStatDAO.update_stat(
    #     report_period=period, channel_ids=ch_ids, category_id=category_id
    # )

    # await ChannelDAO.search_by_keywords(
    #     "новости и обзоры компьютерных игр",
    #     iterations=12,
    #     date_step=30,
    #     date_from=datetime(2024, 11, 1),
    #     type="video",
    #     max_result=50,
    #     # order="viewCount",
    # )

    # errors = []
    # for category_id in range(13, 19):
    #     print(f"Category {category_id}")
    #     err = await ChannelDAO.save_thumbnails(filters={"category_id": category_id})
    #     errors.extend(err)
    # print(f"Errors: {len(errors)}")
    # await ChannelDAO.update_detail(channel_ids=errors)

    # tmpl_path = "../video_gen/2024-11/Нейросети/tmpl.png"
    # for category_id in (1, 5, 6, 7):
    #     await ReportDAO.generate_info_images(
    #         period, category_id, top_channels=20, top_videos_count=0
    #     )


async def upload_from_csv_file():
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


async def upload_from_json_file():
    import json

    csv_file_path = "logs/2025-02-01-21-59-44_video_errors_.csv"

    # Чтение CSV и преобразование в JSON
    with open(csv_file_path, mode="r", encoding="utf-8") as file:
        json_data = json.load(file)

    print(len(json_data))

    res = await VideoDAO.update_bulk(json_data)


def main():
    start_dt = datetime.now()
    print("Start", start_dt)

    asyncio.run(prepare_monthly_report())

    print("Finish after ", datetime.now() - start_dt)


if __name__ == "__main__":
    main()
