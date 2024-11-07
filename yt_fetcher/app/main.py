import os
import sys
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


def main():
    category_id = 1
    period = Period(10)
    per_range = [date(2024, 8, 1), date(2024, 10, 31)]

    start_dt = datetime.now()
    print("Start", start_dt)

    # ChannelDAO.search_by_keywords(
    #     "нейросети",
    #     iterations=1,
    #     date_step=300,
    #     type="channel",
    #     max_result=150,
    # )

    ids = """UCWAIvx2yYLK_xTYD4F2mUNw
UC0lT9K8Wfuc1KPqm6YjRf1A
UCG4yz4wtp2E5S62L06yqC9w""".split(
        "\n"
    )
    names = "@zhivoygvozd @ildarauto @AcademeG".split(" ")  # @zhivoygvozd
    # for name in names[:1]:
    #     ChannelDAO.search_channel(name, category_id=category_id)

    # print(names)
    # ChannelDAO.update_detail()

    # ChannelStatDAO.update_stat(report_period=period, category_id=category_id)

    # VideoDAO.search_new_by_category_period(period=period, category_ids=category_id)
    # or
    # VideoDAO.search_new_by_channel_period(period=period, channel_ids=ids)

    # VideoDAO.add_update_bulk(data, skip_if_exist=False)

    # VideoDAO.update_detail()

    # VideoStatDAO.update_stat(report_period=period, category_id=category_id)

    # ReportDAO.build(period, category_id)

    # for category_id in [1, 5]:
    #     ReportDAO.build(period, category_id)

    print("Finish after ", datetime.now() - start_dt)

    return True


if __name__ == "__main__":
    main()
