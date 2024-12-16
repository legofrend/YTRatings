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
    category_id = 8
    period = Period(11)
    per_range = [date(2024, 11, 27), date(2024, 12, 1)]

    start_dt = datetime.now()
    print("Start", start_dt)

    await ChannelDAO.search_by_keywords(
        "AI news|News and reviews of neural networks",
        iterations=8,
        date_step=7,
        type="video",
        max_result=50,
        # order="viewCount",
    )

    names = "@LesnarAI".split(" ")  #

    # ch_ids = await ChannelDAO.add_channels(names, category_id=category_id)
    # for name in names:
    #     await ChannelDAO.search_channel(name, category_id=category_id)
    # await ChannelDAO.update_detail()
    # await ChannelStatDAO.update_stat(
    #     report_period=period, channel_ids=ch_ids, category_id=category_id
    # )

    # await ChannelStatDAO.update_stat(report_period=period)

    # await ChannelDAO.search_new_by_category_period(
    #     period=per_range, category_ids=category_id
    # )
    # or
    ids = """""".split("\n")

    # await VideoDAO.search_new_by_channel_period(period=per_range, channel_ids=ids)
    # await VideoDAO.update_detail()

    # await VideoStatDAO.update_stat(report_period=period, category_id=None)

    # await VideoDAO.eval_clickbait({"published_at_period": period})

    # for category_id in (1, 5, 6, 7):
    #     await ReportDAO.build(period, category_id)

    # tmpl_path = "../video_gen/2024-11/Нейросети/tmpl.png"
    # for category_id in (1, 5, 6, 7):
    #     await ReportDAO.generate_info_images(
    #         period, category_id, top_channels=20, top_videos_count=0
    #     )

    print("Finish after ", datetime.now() - start_dt)

    return True


def main():
    asyncio.run(actions())


if __name__ == "__main__":
    main()
