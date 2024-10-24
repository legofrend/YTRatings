from services import *


def main():
    rebuild_reports()

    # videos_ids = VideoDAO.get_videos_wo_stat()
    # res = VideoDAO.find_all(duration=None)
    # videos_ids = [item["video_id"] for item in res]
    # print(len(videos_ids))

    # ytapi.get_video_stat(videos_ids)

    # ytapi.get_video_detail(videos_ids)

    # ytapi.get_channel_detail(["UCcX5TJjQsRN4Bg-EVc5Dcfg"])
    # res = ytapi.get_channels_by_keywords("юмор сатира шутки")
    # save_json(res, "out.json")

    # update_info_for_period(filter={"status": 1, "category_id": 3})

    # ytapi.check_is_short()


if __name__ == "__main__":
    main()
