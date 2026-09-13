from datetime import date, datetime, UTC
from pathlib import Path
import sys
import time
from sqlalchemy import text, select, or_, and_, bindparam

from app.dao.base import BaseDAO
from app.database import async_session_maker
from app.logger import logger, save_errors, save_json_csv
from app.period.period import Period
from app.config import settings
import app.api.ytapi as yt
import app.api.openaiapi as oai

from app.channel.video.models import Video, VideoStat
import csv
import json
import pickle


def _raw_is_bq() -> bool:
    return settings.RAW_DB == "bigquery"


def save_data_dump(data: dict, filename_prefix: str = "youtube_data_dump") -> str:
    """Сохраняет данные в файл для последующего использования"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Создаем папку для дампов если её нет
    dump_dir = Path("data_dumps")
    dump_dir.mkdir(exist_ok=True)

    # Сохраняем в JSON (читаемо) и pickle (полная структура)
    json_filename = dump_dir / f"{filename_prefix}_{timestamp}.json"
    pickle_filename = dump_dir / f"{filename_prefix}_{timestamp}.pkl"

    # JSON для читаемости
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    # Pickle для полной структуры данных
    with open(pickle_filename, "wb") as f:
        pickle.dump(data, f)

    logger.info(f"✅ Данные сохранены в: {json_filename} и {pickle_filename}")

    return str(pickle_filename)


def load_data_dump(filename: str) -> dict:
    """Загружает данные из дампа"""
    try:
        with open(filename, "rb") as f:
            data = pickle.load(f)
        logger.info(f"✅ Данные загружены из {filename}")
        return data
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки дампа: {e}")
        return None


def get_latest_dump(dump_prefix: str = "video_list_dump") -> str:
    """Находит последний дамп по префиксу"""
    dump_dir = Path("data_dumps")
    if not dump_dir.exists():
        return None

    dump_files = list(dump_dir.glob(f"{dump_prefix}_*.pkl"))
    if not dump_files:
        return None

    latest_dump = max(dump_files, key=lambda x: x.stat().st_mtime)
    return str(latest_dump)


class VideoDAO(BaseDAO):
    model = Video
    gid = "video_id"

    @classmethod
    async def get_ids(cls, filters: dict = {}):
        if _raw_is_bq():
            from app.channel.video.dao_bq import VideoBqDAO

            return await VideoBqDAO.get_ids(filters)

        async with async_session_maker() as session:
            query = select(cls.model.video_id).filter_by(**filters)
            result = await session.execute(query)
            return result.scalars().all()

    @classmethod
    async def add_update_bulk(cls, data, do_nothing: bool = False):
        if _raw_is_bq():
            from app.channel.video.dao_bq import VideoBqDAO

            return await VideoBqDAO.add_update_bulk(data, do_nothing=do_nothing)
        return await super().add_update_bulk(data, do_nothing=do_nothing)

    @classmethod
    async def update_bulk(cls, data: list[dict], identifier: str = None) -> bool:
        if _raw_is_bq():
            from app.channel.video.dao_bq import VideoBqDAO

            return await VideoBqDAO.update_bulk(
                data, identifier=identifier or cls.gid
            )
        return await super().update_bulk(data, identifier=identifier)

    @classmethod
    async def get_ids_for_stat(
        cls,
        report_period: Period,
        published_at_period: Period = None,
        category_id: int = None,
    ):
        if _raw_is_bq():
            from app.channel.video.dao_bq import VideoStatBqDAO

            return await VideoStatBqDAO.get_ids_for_stat(
                report_period=report_period,
                published_at_period=published_at_period,
                category_id=category_id,
            )

        if not published_at_period:
            published_at_period = report_period.next(-3)

        async with async_session_maker() as session:
            query = f"""select distinct v.video_id
                        from video as v
                        left join channel as c on c.channel_id = v.channel_id
                        where v.published_at_period >= '{published_at_period.strf()}'
                        and c.status=1 and v.status=1
                    """
            if category_id:
                query += f" and c.category_id={category_id}"
            query = text(query)
            result = await session.execute(query)
            data = result.mappings().all()
            return [item["video_id"] for item in data]

    @classmethod
    async def get_ids_wo_stat(
        cls,
        report_period: Period,
        published_at_period: Period = None,
        category_id: int = None,
    ):
        if _raw_is_bq():
            from app.channel.video.dao_bq import VideoStatBqDAO

            return await VideoStatBqDAO.get_ids_wo_stat(
                report_period=report_period,
                published_at_period=published_at_period,
                category_id=category_id,
            )

        if not published_at_period:
            published_at_period = report_period.next(-3)

        async with async_session_maker() as session:
            query = f"""select distinct v.video_id
                        from video as v
                        left join channel as c on c.channel_id = v.channel_id
                        left join video_stat vs on v.video_id = vs.video_id and vs.report_period = '{report_period.strf()}'
                        where vs.id is null and v.published_at_period >= '{published_at_period.strf()}'
                        and c.status=1 and v.status=1
                    """
            if category_id:
                query += f" and c.category_id={category_id}"
            query = text(query)
            result = await session.execute(query)
            data = result.mappings().all()
            data = [item["video_id"] for item in data]
            return data

    @classmethod
    async def get_ids_wo_is_short(
        cls,
        category_id: int = None,
    ):
        if _raw_is_bq():
            from app.channel.video.dao_bq import VideoBqDAO

            return await VideoBqDAO.get_ids_wo_is_short(category_id=category_id)

        async with async_session_maker() as session:
            query = f"""select v.video_id
                        from video as v
                        where v.status=1 and is_short is null and v.published_at_period >= '2025-05-01'
                    """
            # and duration between 60 and 180
            if category_id:
                query += f" and c.category_id={category_id}"
            query = text(query)
            result = await session.execute(query)
            data = result.mappings().all()
            data = [dict(video_id=item.video_id, is_short=None) for item in data]
            return data

    @classmethod
    async def update_detail(cls, video_ids: list[str] | str = None, *, skip_shorts: bool = False):
        if not video_ids:
            video_ids = await cls.get_ids(
                filters={
                    "duration": None,
                    "status": 1,
                    # "published_at_period": date(2025, 3, 1),
                }
            )
            logger.info(f"Found videos without duration: {len(video_ids)}")
            if not video_ids:
                return None
        try:
            data = yt.video_list(video_ids, obj_type="detail")
            logger.info(f"Fetched videos: {len(video_ids)}")
            if not data:
                return None
            if not skip_shorts:
                await yt.check_shorts(data)
            ok = await cls.update_bulk(data)
            if ok:
                logger.info(f"Updated videos: {len(data)}")
            else:
                logger.error(
                    f"Partial/failed bulk update for {len(data)} videos; see logs/*_video_errors_.csv"
                )
        except:
            logger.error("Can't update video detail", exc_info=True)
            dump_file = save_data_dump(data, "video_list_dump")
            logger.info(f"Data dump saved: {dump_file}")

            save_errors(data, "video_detail")

        return data

    @classmethod
    async def update_is_short_new(
        cls,
        *,
        category_ids: list[int] | None = None,
        channel_ids: list[str] | None = None,
        only_null: bool = True,
    ) -> dict:
        """
        Apply is_short from playlist_shorts (UUSH mirror). No YouTube API.

        Scope: optional category_ids / channel_ids; omit both → all synced channels.
        Default window per channel: MIN(playlist_shorts.published_at) .. last_shorts_fetch_dt.
        FALSE only inside that window (and only if channel has shorts rows + fetch marker).
        """
        filters: list[str] = []
        params: dict = {}

        if channel_ids:
            filters.append("c.channel_id IN :channel_ids")
            params["channel_ids"] = channel_ids
        if category_ids:
            filters.append("c.category_id IN :category_ids")
            params["category_ids"] = category_ids

        filter_sql = (" AND " + " AND ".join(filters)) if filters else ""
        null_sql = " AND v.is_short IS NULL" if only_null else ""

        set_true = text(
            f"""
            UPDATE video v
            SET is_short = TRUE,
                updated_at = CURRENT_TIMESTAMP
            FROM playlist_shorts ps
            JOIN channel c ON c.channel_id = ps.channel_id
            WHERE v.video_id = ps.video_id
              AND c.last_shorts_fetch_dt IS NOT NULL
              AND ps.published_at < c.last_shorts_fetch_dt
              AND (v.is_short IS DISTINCT FROM TRUE)
              {null_sql}
              {filter_sql}
            """
        )
        set_false = text(
            f"""
            UPDATE video v
            SET is_short = FALSE,
                updated_at = CURRENT_TIMESTAMP
            FROM channel c
            JOIN (
                SELECT channel_id, MIN(published_at) AS win_from
                FROM playlist_shorts
                GROUP BY channel_id
            ) w ON w.channel_id = c.channel_id
            WHERE v.channel_id = c.channel_id
              AND c.last_shorts_fetch_dt IS NOT NULL
              AND w.win_from IS NOT NULL
              AND v.published_at >= w.win_from
              AND v.published_at < c.last_shorts_fetch_dt
              AND v.status = 1
              AND NOT EXISTS (
                  SELECT 1 FROM playlist_shorts ps
                  WHERE ps.video_id = v.video_id
              )
              AND (v.is_short IS DISTINCT FROM FALSE)
              {null_sql}
              {filter_sql}
            """
        )

        if channel_ids:
            set_true = set_true.bindparams(bindparam("channel_ids", expanding=True))
            set_false = set_false.bindparams(bindparam("channel_ids", expanding=True))
        if category_ids:
            set_true = set_true.bindparams(bindparam("category_ids", expanding=True))
            set_false = set_false.bindparams(bindparam("category_ids", expanding=True))

        async with async_session_maker() as session:
            r_true = await session.execute(set_true, params)
            r_false = await session.execute(set_false, params)
            await session.commit()
            n_true = r_true.rowcount
            n_false = r_false.rowcount

        logger.info(
            f"update_is_short_new: cats={category_ids} channels={channel_ids} "
            f"only_null={only_null} set_true={n_true} set_false={n_false}"
        )
        return {"set_true": n_true, "set_false": n_false}

    @classmethod
    async def update_is_short(cls, video_list: list[str] = None, from_file: str = None):

        if not video_list:
            if from_file:
                with open(from_file, mode="r", encoding="utf-8") as file:
                    csv_reader = csv.DictReader(
                        file, delimiter="\t"
                    )  # используем табуляцию как разделитель
                    video_list = [
                        {
                            "video_id": row["video_id"],
                            "is_short": (
                                row["is_short"].strip().lower() == "true"
                                if row.get("is_short") and str(row["is_short"]).strip()
                                else None
                            ),
                        }
                        for row in csv_reader
                    ]
            else:
                video_list = await cls.get_ids_wo_is_short()
                # res = await cls.find_all(is_short=None, status=1)
                if not video_list:
                    return None
            logger.info(f"Found videos without is_short: {len(video_list)}")

        try:
            await yt.check_shorts(video_list)
            logger.info(f"Fetched info about videos: {len(video_list)}")
            try:
                filename = "logs/list_filled.csv"
                save_json_csv(video_list, filename)
            except Exception as e:
                with open(filename, "w", encoding="utf-8") as file:
                    file.write(str(video_list))

            ok = await cls.update_bulk(video_list)
            if not ok:
                logger.error(
                    f"Partial/failed is_short bulk update for {len(video_list)} videos"
                )
        except:
            logger.error("Can't update video detail", exc_info=True)
            save_errors(video_list, "video_detail")

        return video_list

    @classmethod
    async def get_from_playlist(
        cls,
        id: str,
        date_from: datetime = None,
        date_to: date | datetime = None,
        max_result: int = 500,
    ):

        videos = yt.playlistitem_list(
            id, date_from=date_from, date_to=date_to, max_result=max_result
        )
        if videos:
            await cls.add_update_bulk(videos, do_nothing=True)
            return videos
        return None

    @classmethod
    async def search_new_by_channel_period(
        cls,
        channel_id: str,
        period: Period | tuple[datetime, datetime] = Period(),
    ):
        if isinstance(period, Period):
            period = period.as_range()

        if isinstance(period, tuple) and len(period) != 2:
            raise Exception("Invalid period")

        try:
            videos = yt.search_list(
                "",
                published=period,
                type="video",
                channel_id=channel_id,
                order="date",
                max_result=500,
            )
            if videos:
                await cls.add_update_bulk(videos, do_nothing=True)
                return videos

        except Exception as e:
            logger.error(
                f"Can't get videos for {channel_id=}",
                exc_info=True,
            )
            return None

    @classmethod
    async def get_thumbnails(
        cls, channel_ids: list[str] = None, category_id: int = None
    ) -> None:
        from app.report.tools import download_file
        import os

        # workdir = r'C:\Users\eremi\Documents\4. Projects\2024-07 YTRatings\video_gen\channel_logo'
        workdir = r"..\video_gen\channel_logo" + os.sep + str(category_id)
        os.makedirs(workdir, exist_ok=True)
        # if not channel_ids:
        channels = await cls.find_all(category_id=category_id, status=1)

        for channel in channels:
            file_url = channel["thumbnail_url"]
            file_name = channel.get("custom_url") or channel["channel_id"]
            full_path = os.path.join(workdir, file_name)
            if not os.path.exists(full_path):
                download_file(file_url, full_path)

    @classmethod
    async def eval_clickbait(cls, filters: dict = {}):
        LIMIT = 50
        instructions = """Ты на вход получишь данные с video_id и заголовком видео, разделенных табом. Для каждого заголовка тебе нужно определить, является ли он кликбейт и почему (clickbait_comment). Кликбейт — это термин, описывающий веб-контент, целью которого является получение дохода от онлайн-рекламы, особенно в ущерб качеству или точности информации. Пожалуйста, выведи только массив объектов в JSON формате:

[ { "video_id": <>, "is_clickbait": 1 or 0, "clickbait_comment": <> }, ... ]

Не добавляй в ответ никаких дополнительных слов, символов или переносов строк. Вот входные данные:"""

        if "is_clickbait" not in filters.keys():
            filters["is_clickbait"] = None
        if "is_short" not in filters.keys():
            filters["is_short"] = False
        videos = await cls.find_all(**filters)
        responses = []
        for i in range(0, len(videos), LIMIT):
            data = [
                (item["video_id"] + "\t" + item["title"])
                for item in videos[i : (i + LIMIT)]
            ]

            prompt = instructions + "\n".join(data) + "\n"
            response = oai.chat_with_gpt(prompt, is_json=True, temperature=0.5)
            if response:
                responses.extend(response)
                # await cls.update_bulk(response)
            logger.info(f"Progress: {i+LIMIT}/{len(videos)}")

        # Save responses to file
        filename = f"logs/gpt_out_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(responses, f, ensure_ascii=False, indent=2)

        save_errors(responses, "clickbait")
        await cls.update_bulk(responses)


class VideoStatDAO(BaseDAO):
    model = VideoStat

    @classmethod
    async def add_bulk(cls, data: list[dict]) -> list | bool:
        if _raw_is_bq():
            from app.channel.video.dao_bq import VideoStatBqDAO

            return await VideoStatBqDAO.add_bulk(data)
        return await super().add_bulk(data)

    @classmethod
    async def top_for_channel(
        cls,
        *,
        channel_id: str,
        report_period: date | Period,
        limit: int = 10,
    ) -> list[dict]:
        """Top videos for channel in period (new uploads by score; longs before shorts)."""
        if isinstance(report_period, Period):
            report_period = date(report_period.year, report_period.month, 1)

        async with async_session_maker() as session:
            result = await session.execute(
                text(
                    """
                    SELECT
                        v.video_id,
                        v.channel_id,
                        v.title,
                        v.description,
                        v.video_url,
                        v.thumbnail_url,
                        v.duration,
                        v.published_at,
                        v.is_clickbait,
                        v.clickbait_comment,
                        vs.report_period,
                        vs.is_short,
                        vs.is_new,
                        vs.period_view_count,
                        vs.period_like_count,
                        vs.period_comment_count,
                        vs.view_count,
                        vs.like_count,
                        vs.comment_count,
                        CASE
                            WHEN vs.is_short
                            THEN COALESCE(vs.period_view_count, 0) / 10.0
                            ELSE COALESCE(vs.period_view_count, 0)
                        END AS score
                    FROM video_stat AS vs
                    JOIN video AS v ON v.video_id = vs.video_id
                    WHERE vs.channel_id = :channel_id
                      AND vs.report_period = :report_period
                      AND vs.is_new IS TRUE
                      AND COALESCE(v.status, 1) > 0
                    ORDER BY
                        vs.is_short ASC NULLS FIRST,
                        score DESC
                    LIMIT :limit
                    """
                ),
                {
                    "channel_id": channel_id,
                    "report_period": report_period,
                    "limit": limit,
                },
            )
            rows = []
            for row in result.mappings().all():
                item = dict(row)
                if item.get("report_period") is not None:
                    item["report_period"] = item["report_period"].isoformat()
                if item.get("published_at") is not None:
                    item["published_at"] = item["published_at"].isoformat()
                if item.get("score") is not None:
                    item["score"] = int(round(float(item["score"])))
                rows.append(item)
            return rows

    @classmethod
    async def backfill_denorm(
        cls,
        *,
        report_period: date | Period | None = None,
        batch_size: int = 10_000,
    ) -> int:
        """
        Fill NULL denorm cols on video_stat: build staging → UPDATE in batches.

        MoM / is_new / is_short match video_stat_change (sql/views.sql), joins
        inlined + scoped (no view). Staging is UNLOGGED (not TEMP) so rebuild
        survives connection drops; UPDATE commits every batch_size rows.

        report_period: optional YYYY-MM-01 (or Period); None = all periods.
        Only rows with video.channel_id NOT NULL and channel.status > 0.
        """
        period_sql = ""
        params: dict = {}
        if report_period is not None:
            if isinstance(report_period, Period):
                report_period = date(report_period.year, report_period.month, 1)
            period_sql = "AND cur.report_period = :report_period"
            params["report_period"] = report_period

        # Same filters/CASE as video_stat_change; no ORDER BY
        create_stg = f"""
            CREATE UNLOGGED TABLE _vs_denorm_stg AS
            SELECT
                cur.id,
                v.channel_id,
                (cur.report_period = v.published_at_period) AS is_new,
                (CASE WHEN v.is_short THEN TRUE ELSE FALSE END) AS is_short,
                CASE
                    WHEN prev.video_id IS NOT NULL
                        THEN cur.view_count - prev.view_count
                    WHEN cur.report_period = v.published_at_period
                        THEN cur.view_count
                    ELSE 0
                END AS period_view_count,
                CASE
                    WHEN prev.video_id IS NOT NULL
                        THEN cur.like_count - prev.like_count
                    WHEN cur.report_period = v.published_at_period
                        THEN cur.like_count
                    ELSE 0
                END AS period_like_count,
                CASE
                    WHEN prev.video_id IS NOT NULL
                        THEN cur.comment_count - prev.comment_count
                    WHEN cur.report_period = v.published_at_period
                        THEN cur.comment_count
                    ELSE 0
                END AS period_comment_count
            FROM video_stat AS cur
            JOIN video AS v ON v.video_id = cur.video_id
            LEFT JOIN video_stat AS prev
                ON prev.report_period = cur.prev_period
               AND prev.video_id = cur.video_id
            JOIN channel AS c ON c.channel_id = v.channel_id
            WHERE v.channel_id IS NOT NULL
              AND c.status > 0
              AND (
                  cur.channel_id IS NULL
                  OR cur.is_short IS NULL
                  OR cur.is_new IS NULL
                  OR cur.period_view_count IS NULL
                  OR cur.period_like_count IS NULL
                  OR cur.period_comment_count IS NULL
              )
              {period_sql}
        """
        apply_batch = """
            WITH batch AS (
                SELECT id FROM _vs_denorm_stg
                ORDER BY id
                LIMIT :batch_size
            ),
            upd AS (
                UPDATE video_stat AS vs
                SET
                    channel_id = s.channel_id,
                    is_short = s.is_short,
                    is_new = s.is_new,
                    period_view_count = s.period_view_count,
                    period_like_count = s.period_like_count,
                    period_comment_count = s.period_comment_count,
                    updated_at = CURRENT_TIMESTAMP
                FROM _vs_denorm_stg AS s
                JOIN batch b ON b.id = s.id
                WHERE vs.id = s.id
                RETURNING s.id
            )
            DELETE FROM _vs_denorm_stg s
            USING upd
            WHERE s.id = upd.id
        """
        total = 0
        t_all = time.monotonic()
        async with async_session_maker() as session:
            await session.execute(text("DROP TABLE IF EXISTS _vs_denorm_stg"))
            await session.execute(text(create_stg), params)
            await session.execute(text("CREATE INDEX ON _vs_denorm_stg (id)"))
            cnt = await session.execute(text("SELECT count(*) FROM _vs_denorm_stg"))
            stg_n = cnt.scalar_one()
            await session.commit()
            stg_s = time.monotonic() - t_all
            logger.info(
                f"video_stat.backfill_denorm: staging rows={stg_n} "
                f"in {stg_s:.1f}s"
            )

            t0 = time.monotonic()
            period_label = (
                report_period.isoformat() if report_period else "all"
            )
            while True:
                result = await session.execute(
                    text(apply_batch), {"batch_size": batch_size}
                )
                # DELETE rowcount == updated ids
                n = result.rowcount
                await session.commit()
                if not n:
                    break
                total += n
                elapsed = time.monotonic() - t0
                rate = total / elapsed if elapsed > 0 else 0
                left = max(stg_n - total, 0)
                eta_s = left / rate if rate > 0 else 0
                pct = (100.0 * total / stg_n) if stg_n else 100.0
                msg = (
                    f"\rbackfill {period_label}: {total}/{stg_n} "
                    f"({pct:5.1f}%) ETA {eta_s:6.0f}s   "
                )
                sys.stdout.write(msg)
                sys.stdout.flush()

            apply_s = time.monotonic() - t0
            if stg_n:
                sys.stdout.write("\n")
                sys.stdout.flush()

            await session.execute(text("DROP TABLE IF EXISTS _vs_denorm_stg"))
            await session.commit()

        total_s = time.monotonic() - t_all
        logger.info(
            f"video_stat.backfill_denorm: updated {total} rows "
            f"period={report_period} in {total_s:.1f}s "
            f"(staging {stg_s:.1f}s, apply {apply_s:.1f}s)"
        )
        return total

    @classmethod
    async def update_stat(
        cls,
        report_period: Period,
        video_ids: list[str] | str = None,
        category_ids: list[int] | int = None,
        *,
        force: bool = False,
    ):
        if isinstance(category_ids, int):
            category_ids = [category_ids]

        # If video_ids provided, use single category_id=0 to skip category filtering
        if video_ids:
            category_ids = [0]

        total_updated = 0
        for i, category_id in enumerate(category_ids, start=1):
            logger.info(f"Processing category {category_id} {i}/{len(category_ids)}")
            current_video_ids = (
                video_ids
                if video_ids
                else await (
                    VideoDAO.get_ids_for_stat(
                        report_period=report_period, category_id=category_id
                    )
                    if force
                    else VideoDAO.get_ids_wo_stat(
                        report_period=report_period, category_id=category_id
                    )
                )
            )
            label = "videos" if force else "videos without stat"
            logger.info(f"Found {len(current_video_ids)} {label}")
            if not current_video_ids:
                continue

            data = yt.video_list(current_video_ids, obj_type="stat")
            # data = []
            logger.info(f"Fetched video stats: {len(data)}")

            if data:
                # Check for missing videos
                returned_ids = {item["video_id"] for item in data}
                missing_ids = set(current_video_ids) - returned_ids
                if missing_ids:
                    logger.warning(f"Missing stats for {len(missing_ids)} videos")
                    missing_payload = [
                        {"video_id": vid, "status": 0} for vid in missing_ids
                    ]
                    if _raw_is_bq():
                        from app.channel.video.dao_bq import VideoBqDAO

                        await VideoBqDAO.update_bulk(missing_payload)
                    else:
                        await VideoDAO.update_bulk(missing_payload)

                for item in data:
                    item["report_period"] = report_period
                if _raw_is_bq():
                    from app.channel.video.dao_bq import VideoStatBqDAO

                    await VideoStatBqDAO.add_bulk(data)
                else:
                    await cls.add_bulk(data)
                total_updated += len(data)
                if category_id != 0:  # Don't print for single video_ids case
                    logger.info(
                        f"{i}: Updated {len(data)} records for category {category_id}"
                    )

        logger.info(f"Total updated videos: {total_updated}")
        return total_updated


# print("OK")

# save_data_dump({"a": 1, "test": 2}, "video_list_dump")
