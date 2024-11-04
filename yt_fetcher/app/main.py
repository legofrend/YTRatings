import os
import sys
from datetime import date, datetime

sys.path.append(os.getcwd())


from app.period import Period
from app.dao_report import ReportDAO
from app.dao_yt import ChannelDAO, VideoDAO, VideoStatDAO, ChannelStatDAO


def main():
    category_id = 7
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

    ids = """UC_GgOplL884a5epC_tLmZ5g
UCvrc5UdweQwmrDVSeWruCLQ
UCY8x6xRApsKTneT3FSlcoFg
UC_jJJRp6yZTvWvtLIK6a4Rg
UCZiWrEnhyCpkT8aE-vkC1VA
UCFYiDR-Ecy3G_mflvNv8ceQ
UC_lquTU9KW6qvVwXxpFt3Og
UC7Cct_zb6oG2FK1d2nrFpGA
UCgNCgZf8M28zx6BYIrnfBng
UCtvSwlo9m_a9zX7DBuyZXIA
UCX2O3YjU2B7Ez7OcRNJCC4Q
UC4OcySZ8uQ6xt1fh4qhUN8g
UCZ6Fos-CqOFKdAUXXkbZ_fw
UCEV4Gi5cTLmYTTIctI7O4IA
UCaC5Ds-cUDAHi6CfjzG5NMw
UCZxYHMdHS0QfD6l9wn2yzOw
UC9q-B7BLekxjrDyOXDtImVQ
UCZcfRX8LbGqFOW06Nf0tHnQ
UCL9qmgOJwczxpMmtgKwDDeA
UCTU7JOKrjXOiN0ifL5BGSRA
""".split(
        "\n"
    )
    # print(names)
    # ChannelDAO.update_detail()

    # ChannelStatDAO.update_stat(report_period=period, category_id=category_id)

    # VideoDAO.search_new_by_category_period(period=period, category_ids=category_id)
    # or
    # VideoDAO.search_new_by_channel_period(period=period, channel_ids=ids)

    # VideoDAO.add_update_bulk(data, skip_if_exist=False)

    # VideoDAO.update_detail()

    # VideoStatDAO.update_stat(report_period=period, category_id=category_id)

    ReportDAO.build(period, category_id)

    # for category_id in [1, 5, 6, 7]:
    #     ReportDAO.build(period, category_id)

    print("Finish after ", datetime.now() - start_dt)

    return True


if __name__ == "__main__":
    main()
