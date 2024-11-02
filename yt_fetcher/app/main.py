import os
import sys
from datetime import date, datetime

sys.path.append(os.getcwd())


from app.period import Period
from app.dao import ChannelDAO, ReportDAO, VideoDAO, VideoStatDAO, ChannelStatDAO


def main():
    category_id = 5
    period = Period(10)
    per_range = [date(2024, 8, 1), date(2024, 10, 31)]

    start_dt = datetime.now()
    print("Start", start_dt)

    # ChannelDAO.search_by_keywords(
    #     "Новости и обзоры нейросетей",
    #     iterations=4,
    #     date_step=30,
    #     type="channel",
    #     max_result=50,
    # )

    # names = """""".split("\n")
    # print(names)

    # ChannelStatDAO.update_stat(report_period=period, category_id=category_id)

    # VideoDAO.search_new_by_category_period(period=period, category_ids=category_id)
    # or
    # VideoDAO.search_new_by_channel_period(period=period, channel_ids=names)

    # VideoDAO.update_detail()

    # VideoStatDAO.update_stat(report_period=period, category_id=category_id)
    for category_id in [1, 5, 6, 7]:
        ReportDAO.build(period, category_id)

    print("Finish after ", datetime.now() - start_dt)

    return True


if __name__ == "__main__":
    main()
