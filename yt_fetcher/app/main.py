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
    category_id = 4
    period = Period(4)
    per_range = [date(2025, 4, 1), date(2025, 5, 1)]

    step = step or 0.1

    ids = """""".split("\n")

    match step:

        case 0.0:  # Add new channel
            queries = """""".split("\n")
            # VideoDAO.search_new_by_channel_period(names, period)
            res = await ChannelDAO.search_channel(
                queries=queries, category_id=category_id
            )

        case 0.1:  # Update detail for channels
            await ChannelDAO.update_detail()

        case 0.2:  # download channel thumbnail
            await ChannelDAO.save_thumbnails(filters={"category_id": 4})

        case 1:  # Update stat per channels
            res = await ChannelStatDAO.update_stat(
                report_period=period, category_id=None
            )
            print(f"Updated {len(res)} records")

        case 2:  # Fetch new videos
            res = await ChannelDAO.fetch_new_videos(
                category_ids=list(range(10, 19)), date_from=None, date_to=per_range[1]
            )

        case 3:  # Update detail for videos without duration and or is_short
            max_count = 100
            for _ in range(0, max_count):
                print(f"{_} out of {max_count}")
                res = await VideoDAO.update_detail()
            if res:
                print(f"Updated details for {len(res)} records")

        case 3.1:
            res = await VideoDAO.update_is_short()

        # case 3.2:
        # await upload_from_csv_file(
        #     filename="logs/2025-05-01-21-28-14_video_detail_errors_.csv"
        # )

        case 4:  # Update stat for videos
            for i, category_id in enumerate(range(10, 19), start=1):
                res = await VideoStatDAO.update_stat(
                    report_period=period, category_id=category_id
                )
                print(f"{i}: Updated {len(res)} records")

        case 5:  # Build reports
            await ReportDAO.build(period, list(range(10, 19)))

    return True


def main():
    start_dt = datetime.now()
    print("Start", start_dt)

    asyncio.run(prepare_monthly_report())

    print("Finish after ", datetime.now() - start_dt)
    print("\a")  # Beep sound


if __name__ == "__main__":
    main()
