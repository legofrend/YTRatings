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

# Игры и гейминг
# Лайфстайл и влоги
# Здоровье и фитнес
# Научно-популярные каналы
# Финансовая грамотность и инвестиции
# Кулинария и рецепты
# Путешествия и туризм
# Технологии и гаджеты
# Красота и мода
# Образование и саморазвитие


async def actions():
    category_id = 1
    period = Period(11)
    per_range = [date(2024, 11, 1), date(2024, 11, 27)]

    start_dt = datetime.now()
    print("Start", start_dt)

    # await ChannelDAO.search_by_keywords(
    #     "нейросети",
    #     iterations=1,
    #     date_step=300,
    #     type="channel",
    #     max_result=150,
    # )

    names = "@MarvelDCRU @lebovsky".split(" ")  #

    # ch_ids = await ChannelDAO.add_channels(names, category_id=category_id)
    # for name in names:
    #     await ChannelDAO.search_channel(name, category_id=category_id)
    # await ChannelDAO.update_detail()
    # await ChannelStatDAO.update_stat(
    #     report_period=period, channel_ids=ch_ids, category_id=category_id
    # )

    # await ChannelStatDAO.update_stat(report_period=period)

    await ChannelDAO.search_new_by_category_period(
        period=period, category_ids=category_id
    )
    # or
    # ids = """UCrp2It0yWUC7XcrWyBIQeKw""".split("\n")

    # await VideoDAO.search_new_by_channel_period(period=per_range, channel_ids=ids)
    # await VideoDAO.update_detail()

    # await VideoStatDAO.update_stat(report_period=period, category_id=None)

    # await ReportDAO.build(period, category_id)

    # for category_id in [1, 5]:
    #     await ReportDAO.build(period, category_id)

    # tmpl_path = "../video_gen/2024-10/Политика/tmpl.png"
    # await ReportDAO.generate_info_images(
    #     tmpl_path, period, category_id, top_channels=20, top_videos_count=0
    # )

    await VideoDAO.eval_clickbait({"published_at_period": period})

    print("Finish after ", datetime.now() - start_dt)

    return True


def main():
    asyncio.run(actions())


if __name__ == "__main__":
    main()
