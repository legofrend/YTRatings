import os
import sys
import asyncio
from datetime import date, datetime
import pandas as pd

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


async def prepare_monthly_report(
    step: int | float | set[int | float] | frozenset[int | float] = 0,
):
    category_id = 1
    category_ids = list(set(range(4, 19)) - {9})
    # category_ids = [1]
    period = Period(6, 2026)
    per_range = [date(2026, 6, 1), date(2026, 7, 1)]

    # step = {1}
    step = {5}

    ids = """""".split("\n")

    steps = {step} if isinstance(step, (int, float)) else step

    if 0.0 in steps:  # Add new channel
        queries = """""".split("\n")
        # VideoDAO.search_new_by_channel_period(names, period)
        res = await ChannelDAO.search_channel(queries=queries, category_id=category_id)

    if 0.1 in steps:  # Update detail for channels
        await ChannelDAO.update_detail()

    if 0.2 in steps:  # download channel thumbnail
        await ChannelDAO.save_thumbnails(filters={"category_id": category_id})

    if 1 in steps:  # Update stat per channels
        res = await ChannelStatDAO.update_stat(report_period=period, category_id=None)

    if 1.1 in steps:  # Update stat per channels from the file after error
        data = pd.read_csv(
            "logs/2025-06-01-10-48-27_channel_stat_errors_.csv",
            sep="\t",
            encoding="utf-8",
            parse_dates=["data_at", "report_period"],
        )

        data = data.to_dict(orient="records")
        await ChannelStatDAO.add_bulk(data)

    if 2 in steps:  # Fetch new videos
        res = await ChannelDAO.fetch_new_videos(
            category_ids=category_ids,
            # channel_ids=["UC3wtD22NT4D2i-CddPJns4Q"],
            # date_from=datetime(2025, 5, 1, 0, 0, 0, 0),
            date_to=per_range[1],
            priority=100,
        )

    if 3 in steps:  # Update detail for videos without duration and or is_short
        res = await VideoDAO.update_detail()

    if 3.1 in steps:
        res = await VideoDAO.update_is_short()

    if 3.2 in steps:
        files = os.listdir("logs")
        for i, file in enumerate(files, start=1):
            if "2025-10-01" in file:
                data = pd.read_csv(
                    f"logs/{file}",
                    sep="\t",
                    encoding="utf-8",
                )

                # Конвертируем is_short в boolean
                data["is_short"] = data["is_short"].apply(
                    lambda x: bool(x) if pd.notna(x) else None
                )

                data = data.to_dict(orient="records")
                await VideoDAO.update_bulk(data)
                print(f"{i}/{len(files)}: Updated {len(data)} records")

    if 4 in steps:  # Update stat for videos
        res = await VideoStatDAO.update_stat(
            report_period=period, category_ids=category_ids
        )

    if 4.1 in steps:  # Update stat for videos from the file after error
        data = pd.read_csv(
            "logs/2025-06-01-22-11-26_video_stat_errors_.csv",
            sep="\t",
            encoding="utf-8",
            parse_dates=["data_at", "report_period"],
        )

        data = data.to_dict(orient="records")
        await VideoStatDAO.add_bulk(data)

    if 5 in steps:  # Build reports
        await ReportDAO.build(period, category_ids)

    return True


def main():
    start_dt = datetime.now()
    print("Start", start_dt)

    asyncio.run(prepare_monthly_report())

    print("Finish after ", datetime.now() - start_dt)
    print("\a")  # Beep sound


if __name__ == "__main__":
    main()
