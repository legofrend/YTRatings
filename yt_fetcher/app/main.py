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


async def actions():
    category_id = 7
    period = Period(11)
    per_range = [date(2024, 8, 1), date(2024, 10, 31)]

    start_dt = datetime.now()
    print("Start", start_dt)

    # async with async_session_maker() as session:
    #     print(type(data))
    #     query = insert(Category).values(data)  # .returning(cls.model.id)
    #     result = await session.execute(query)
    #     await session.commit()
    #     # return result.mappings().first()
    #     return True

    # await ChannelDAO.search_by_keywords(
    #     "нейросети",
    #     iterations=1,
    #     date_step=300,
    #     type="channel",
    #     max_result=150,
    # )

    names = "".split(" ")
    # ch_ids = await ChannelDAO.add_channels(names, category_id=category_id)
    # await ChannelStatDAO.update_stat(report_period=period, channel_ids=ch_ids, category_id=category_id)

    # await ChannelStatDAO.update_stat(report_period=period, category_id=category_id)

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
