import os
import sys
import asyncio
from datetime import date, datetime

sys.path.append(os.getcwd())


from app.period.period import Period
from app.report.dao import ReportDAO
from app.video.dao import VideoDAO, VideoStatDAO
from app.channel.dao import ChannelDAO, ChannelStatDAO


# Categories
# 1	Политика
# 2	SC2
# 3	Юмор
# 5	Авто
# 6	Кино
# 7	Нейросети


async def actions():
    category_id = 6
    period = Period(10)
    per_range = [date(2024, 8, 1), date(2024, 10, 31)]

    start_dt = datetime.now()
    print("Start", start_dt)

    # await ChannelDAO.search_by_keywords(
    #     "нейросети",
    #     iterations=1,
    #     date_step=300,
    #     type="channel",
    #     max_result=150,
    # )

    # names = "@BoxOfficeRU".split(" ")
    # for name in names:
    #     await ChannelDAO.search_channel(name, category_id=category_id)

    # print(names)
    # await ChannelDAO.update_detail()

    await ChannelStatDAO.update_stat(report_period=period, category_id=category_id)

    # await VideoDAO.search_new_by_category_period(period=period, category_ids=category_id)
    # or
    #     ids = """""".split(
    #         "\n"
    #     )
    # await VideoDAO.search_new_by_channel_period(period=period, channel_ids=ids)

    # await VideoDAO.add_update_bulk(data, skip_if_exist=False)

    # await VideoDAO.update_detail()

    # await VideoStatDAO.update_stat(report_period=period, category_id=category_id)

    # await ReportDAO.build(period, category_id)

    # for category_id in [1, 5]:
    #     await ReportDAO.build(period, category_id)

    print("Finish after ", datetime.now() - start_dt)

    return True


def main():
    asyncio.run(actions())


if __name__ == "__main__":
    main()
