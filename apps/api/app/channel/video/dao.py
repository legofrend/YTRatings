import asyncio
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

# ytapi / openaiapi imported lazily inside methods that need them (FastAPI image stays slim)

from app.channel.video.models import Video, VideoStat
from app.channel.models import ChannelStatus
import csv
import json
import pickle


def _raw_is_bq() -> bool:
    return settings.RAW_DB == "bigquery"


def _is_connection_error(exc: BaseException) -> bool:
    """True if exc (or its cause chain) is a dropped/failed DB connection, not a timeout."""
    seen = set()
    e: BaseException | None = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        if isinstance(e, (ConnectionError, TimeoutError)):
            return isinstance(e, ConnectionError)
        if type(e).__name__ in (
            "ConnectionDoesNotExistError",
            "ConnectionFailureError",
            "InterfaceError",
        ):
            return True
        if getattr(e, "connection_invalidated", False):
            return True
        e = e.__cause__ or e.__context__
    return False


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
            query = f"""
                SELECT video_id FROM (
                    SELECT DISTINCT
                        v.video_id,
                        c.priority,
                        v.published_at_period
                    FROM video AS v
                    LEFT JOIN channel AS c ON c.channel_id = v.channel_id
                    WHERE v.published_at_period >= '{published_at_period.strf()}'
                      AND c.status = {ChannelStatus.ACTIVE}
                      AND v.status = 1
            """
            if category_id:
                query += f" AND c.category_id = {category_id}"
            query += """
                ) AS sub
                ORDER BY
                    priority ASC NULLS LAST,
                    published_at_period DESC NULLS LAST,
                    video_id
            """
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
            query = f"""
                SELECT video_id FROM (
                    SELECT DISTINCT
                        v.video_id,
                        c.priority,
                        v.published_at_period
                    FROM video AS v
                    LEFT JOIN channel AS c ON c.channel_id = v.channel_id
                    LEFT JOIN video_stat AS vs
                        ON v.video_id = vs.video_id
                       AND vs.report_period = '{report_period.strf()}'
                    WHERE vs.id IS NULL
                      AND v.published_at_period >= '{published_at_period.strf()}'
                      AND c.status = {ChannelStatus.ACTIVE}
                      AND v.status = 1
            """
            if category_id:
                query += f" AND c.category_id = {category_id}"
            query += """
                ) AS sub
                ORDER BY
                    priority ASC NULLS LAST,
                    published_at_period DESC NULLS LAST,
                    video_id
            """
            query = text(query)
            result = await session.execute(query)
            data = result.mappings().all()
            data = [item["video_id"] for item in data]
            return data

    @classmethod
    async def get_ids_wo_duration(
        cls,
        *,
        category_ids: list[int] | int | None = None,
        limit: int | None = None,
        after_id: str | None = None,
    ) -> list[str]:
        """video_id with duration IS NULL (status=1), optional category filter via channel.

        Keyset pagination: after_id + limit for stable batched backfills.
        """
        if isinstance(category_ids, int):
            category_ids = [category_ids]

        if _raw_is_bq():
            # BQ path: fall back to generic null-duration ids (no cat filter yet)
            ids = await cls.get_ids(filters={"duration": None, "status": 1})
            if after_id:
                ids = [i for i in ids if i > after_id]
            ids.sort()
            if limit is not None:
                ids = ids[: max(0, int(limit))]
            return ids

        params: dict = {}
        where = ["v.status = 1", "v.duration IS NULL"]
        join = ""
        if category_ids:
            join = "JOIN channel c ON c.channel_id = v.channel_id"
            where.append("c.category_id = ANY(:cats)")
            params["cats"] = category_ids
        if after_id:
            where.append("v.video_id > :after_id")
            params["after_id"] = after_id
        lim = ""
        if limit is not None:
            lim = "LIMIT :limit"
            params["limit"] = int(limit)

        q = text(
            f"""
            SELECT v.video_id
            FROM video v
            {join}
            WHERE {" AND ".join(where)}
            ORDER BY v.video_id
            {lim}
            """
        )
        async with async_session_maker() as session:
            result = await session.execute(q, params)
            return list(result.scalars().all())

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
    async def update_detail(
        cls,
        video_ids: list[str] | str = None,
        *,
        category_ids: list[int] | int | None = None,
        skip_shorts: bool = True,
        batch_size: int | None = None,
    ):
        """
        Fill duration (and related detail) via videos.list.
        skip_shorts kept for API compat; HTTP is_short is disabled — use apply-is-short.

        When video_ids omitted: keyset-scan null-duration rows in batches of
        YT_DETAIL_BATCH_SIZE (commit after each batch). Cursor advances even if YT
        omits deleted ids — no infinite loop; leftover NULLs need a later run.
        """
        import app.api.ytapi as yt
        from app.api import yt_pending
        from app.config import settings

        _ = skip_shorts
        if batch_size is None:
            batch_size = settings.YT_DETAIL_BATCH_SIZE

        if isinstance(video_ids, str):
            video_ids = [video_ids]

        if isinstance(category_ids, int):
            scope = f"cat{category_ids}"
            cat_list: list[int] | None = [category_ids]
        elif category_ids:
            scope = "cat" + "_".join(str(c) for c in category_ids[:8])
            cat_list = list(category_ids)
        else:
            scope = "default"
            cat_list = None

        async def _commit_batch(rows: list, *, batch_no: int) -> bool:
            batch_scope = f"{scope}_b{batch_no}" if batch_no else scope
            ok = await yt_pending.commit_rows("video_detail", rows, scope=batch_scope)
            if ok:
                logger.info(f"Updated videos: {len(rows)} (batch={batch_no or 'all'})")
                return True
            logger.error(
                f"Partial/failed bulk update for {len(rows)} videos; "
                f"pending kept in logs/yt_pending/"
            )
            return False

        # Explicit id list: one shot (API still chunks by 50 inside video_list).
        if video_ids:
            data = None
            try:
                data = yt.video_list(video_ids, obj_type="detail")
                logger.info(f"Fetched videos: {len(data) if data else 0}")
                if not data:
                    return [] if yt.IS_QUOTA_EXCEEDED else None
                if not await _commit_batch(data, batch_no=0):
                    return None
                return data
            except Exception:
                logger.error("Can't update video detail", exc_info=True)
                try:
                    if data:
                        yt_pending._save_pending(
                            yt_pending.pending_path("video_detail", scope),
                            {
                                "op": "video_detail",
                                "scope": scope,
                                "meta": {},
                                "rows": yt_pending._normalize_rows(data),
                            },
                        )
                except Exception:
                    pass
                return None

        batch_size = max(50, int(batch_size or 5000))
        after_id: str | None = None
        batch_no = 0
        total_updated = 0

        while True:
            ids = await cls.get_ids_wo_duration(
                category_ids=cat_list,
                limit=batch_size,
                after_id=after_id,
            )
            if not ids:
                if batch_no == 0:
                    logger.info(
                        f"Found videos without duration: 0 cats={cat_list}"
                    )
                break

            batch_no += 1
            after_id = ids[-1]
            logger.info(
                f"video-detail batch {batch_no}: {len(ids)} ids "
                f"(through {after_id}) cats={cat_list}"
            )

            data = None
            try:
                data = yt.video_list(ids, obj_type="detail")
            except Exception:
                logger.error(
                    f"Can't update video detail batch {batch_no}", exc_info=True
                )
                try:
                    if data:
                        yt_pending._save_pending(
                            yt_pending.pending_path(
                                "video_detail", f"{scope}_b{batch_no}"
                            ),
                            {
                                "op": "video_detail",
                                "scope": f"{scope}_b{batch_no}",
                                "meta": {},
                                "rows": yt_pending._normalize_rows(data),
                            },
                        )
                except Exception:
                    pass
                return None if total_updated == 0 else []

            logger.info(
                f"Fetched videos: {len(data) if data else 0}/{len(ids)} "
                f"(batch={batch_no})"
            )

            if data:
                if not await _commit_batch(data, batch_no=batch_no):
                    return None if total_updated == 0 else []
                total_updated += len(data)

            if yt.IS_QUOTA_EXCEEDED:
                logger.warning(
                    f"yt quota exceeded during video-detail "
                    f"(batch={batch_no}, updated={total_updated}); stopping"
                )
                break

            # YT omitted some ids (deleted) — cursor already advanced; continue.

        logger.info(
            f"video-detail done: updated={total_updated} batches={batch_no} "
            f"cats={cat_list}"
        )
        # Empty list = success (possibly partial); None = hard failure.
        # Do not keep all rows in RAM across hundreds of thousands of videos.
        return []


    @classmethod
    async def _list_video_ids_for_is_short(
        cls,
        *,
        after_id: str,
        limit: int,
        category_ids: list[int] | None = None,
        channel_ids: list[str] | None = None,
        only_null: bool = True,
    ) -> list[str]:
        """Keyset page of videos eligible for apply-is-short."""
        filters = [
            f"c.status = {ChannelStatus.ACTIVE}",
            "c.last_shorts_fetch_dt IS NOT NULL",
            "v.published_at < c.last_shorts_fetch_dt",
            "v.video_id > :after_id",
        ]
        params: dict = {"after_id": after_id or "", "limit": limit}
        if only_null:
            filters.append("v.is_short IS NULL")
        if channel_ids:
            filters.append("c.channel_id IN :channel_ids")
            params["channel_ids"] = list(channel_ids)
        if category_ids:
            filters.append("c.category_id IN :category_ids")
            params["category_ids"] = list(category_ids)
        q = text(
            f"""
            SELECT v.video_id
            FROM video v
            JOIN channel c ON c.channel_id = v.channel_id
            WHERE {" AND ".join(filters)}
            ORDER BY v.video_id
            LIMIT :limit
            """
        )
        if channel_ids:
            q = q.bindparams(bindparam("channel_ids", expanding=True))
        if category_ids:
            q = q.bindparams(bindparam("category_ids", expanding=True))
        async with async_session_maker() as session:
            rows = (await session.execute(q, params)).scalars().all()
        return list(rows)

    @classmethod
    async def _update_is_short_for_videos(
        cls,
        video_ids: list[str],
        *,
        only_null: bool = True,
    ) -> dict:
        """One UPDATE: is_short = (video in playlist_shorts). updated_at via trigger."""
        if not video_ids:
            return {"set_true": 0, "set_false": 0, "updated": 0}

        null_sql = " AND v.is_short IS NULL" if only_null else ""
        # In UUSH → TRUE (any status). Not in UUSH → FALSE only for status=1.
        # updated_at: trigger_set_updated_at_video
        q = text(
            f"""
            UPDATE video v
            SET is_short = EXISTS (
                SELECT 1 FROM playlist_shorts ps WHERE ps.video_id = v.video_id
            )
            FROM channel c
            WHERE v.video_id IN :video_ids
              AND v.channel_id = c.channel_id
              AND c.last_shorts_fetch_dt IS NOT NULL
              AND v.published_at < c.last_shorts_fetch_dt
              AND (
                EXISTS (
                    SELECT 1 FROM playlist_shorts ps WHERE ps.video_id = v.video_id
                )
                OR v.status = 1
              )
              AND v.is_short IS DISTINCT FROM EXISTS (
                  SELECT 1 FROM playlist_shorts ps WHERE ps.video_id = v.video_id
              )
              {null_sql}
            RETURNING v.is_short
            """
        ).bindparams(bindparam("video_ids", expanding=True))

        async with async_session_maker() as session:
            rows = (
                await session.execute(q, {"video_ids": list(video_ids)})
            ).scalars().all()
            await session.commit()

        n_true = sum(1 for x in rows if x is True)
        n_false = sum(1 for x in rows if x is False)
        return {"set_true": n_true, "set_false": n_false, "updated": len(rows)}

    @classmethod
    async def update_is_short_new(
        cls,
        *,
        category_ids: list[int] | None = None,
        channel_ids: list[str] | None = None,
        only_null: bool = True,
        batch_size: int | None = None,
    ) -> dict:
        """
        Apply is_short from playlist_shorts (UUSH mirror). No YouTube API.

        Scope: optional category_ids / channel_ids; omit both → all synced channels.
        One UPDATE per video batch: TRUE if in UUSH else FALSE
        (published_at < last_shorts_fetch_dt; updated_at via DB trigger).
        """
        from app.config import settings

        batch_size = max(
            1, int(batch_size or settings.APPLY_IS_SHORT_VIDEO_BATCH or 5000)
        )
        total_true = 0
        total_false = 0
        total_updated = 0
        batches = 0
        skipped = 0
        after_id = ""

        while True:
            ids = await cls._list_video_ids_for_is_short(
                after_id=after_id,
                limit=batch_size,
                category_ids=category_ids,
                channel_ids=channel_ids,
                only_null=only_null,
            )
            if not ids:
                break

            batches += 1
            part = None
            for attempt in range(1, 4):
                try:
                    part = await cls._update_is_short_for_videos(
                        ids, only_null=only_null
                    )
                    break
                except Exception as e:
                    if attempt < 3 and _is_connection_error(e):
                        wait_s = 30 * attempt
                        logger.warning(
                            f"update_is_short_new batch {batches}: "
                            f"connection lost ({type(e).__name__}), "
                            f"retry {attempt}/2 in {wait_s}s"
                        )
                        await asyncio.sleep(wait_s)
                        continue
                    logger.error(
                        f"update_is_short_new batch {batches} FAILED "
                        f"(videos={len(ids)} first={ids[0]}); continuing",
                        exc_info=True,
                    )
                    break

            after_id = ids[-1]
            if part is None:
                skipped += 1
                continue

            total_true += part["set_true"]
            total_false += part["set_false"]
            total_updated += part["updated"]
            logger.info(
                f"update_is_short_new batch {batches}: "
                f"videos={len(ids)} updated={part['updated']} "
                f"set_true={part['set_true']} set_false={part['set_false']} "
                f"after={after_id}"
            )

        if batches == 0:
            logger.info(
                f"update_is_short_new: no eligible videos "
                f"cats={category_ids} channels={channel_ids} only_null={only_null}"
            )

        logger.info(
            f"update_is_short_new: cats={category_ids} "
            f"batches={batches} skipped={skipped} only_null={only_null} "
            f"updated={total_updated} set_true={total_true} set_false={total_false}"
        )
        return {
            "set_true": total_true,
            "set_false": total_false,
            "updated": total_updated,
            "batches": batches,
            "skipped": skipped,
        }

    @classmethod
    async def update_is_short_http_old(
        cls, video_list: list[str] = None, from_file: str = None
    ):
        """LEGACY HTTP is_short. Do not use — prefer update_is_short_new / apply-is-short."""
        import app.api.ytapi as yt

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
            await yt.check_shorts_http_old(video_list)
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
        except Exception:
            logger.error("Can't update video is_short (HTTP legacy)", exc_info=True)
            save_errors(video_list, "video_detail")

        return video_list

    @classmethod
    async def update_is_short(cls, *args, **kwargs):
        raise RuntimeError(
            "VideoDAO.update_is_short (HTTP) is disabled; use update_is_short_new "
            "or `python -m app.main apply-is-short`. Legacy: update_is_short_http_old"
        )

    @classmethod
    async def get_from_playlist(
        cls,
        id: str,
        date_from: datetime = None,
        date_to: date | datetime = None,
        max_result: int = 500,
    ):
        import app.api.ytapi as yt
        from app.api import yt_pending

        videos = yt.playlistitem_list(
            id, date_from=date_from, date_to=date_to, max_result=max_result
        )
        if videos:
            ok = await yt_pending.commit_rows(
                "video_insert", videos, scope=str(id)[:64]
            )
            return videos if ok else None
        return None

    @classmethod
    async def search_new_by_channel_period(
        cls,
        channel_id: str,
        period: Period | tuple[datetime, datetime] = Period(),
    ):
        import app.api.ytapi as yt
        from app.api import yt_pending

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
                ok = await yt_pending.commit_rows(
                    "video_insert", videos, scope=channel_id
                )
                return videos if ok else None

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
        from app.media_paths import video_gen_dir
        from app.report.tools import download_file
        import os

        workdir = str(video_gen_dir() / "channel_logo" / str(category_id))
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
        import app.api.openaiapi as oai

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
    async def top_for_category(
        cls,
        *,
        category_id: int,
        report_period: date | Period,
        limit: int = 5,
    ) -> list[dict]:
        """Top new long-form videos across a category for period (excludes shorts)."""
        if isinstance(report_period, Period):
            report_period = date(report_period.year, report_period.month, 1)

        async with async_session_maker() as session:
            result = await session.execute(
                text(
                    f"""
                    SELECT
                        v.video_id,
                        v.channel_id,
                        ch.channel_title,
                        ch.custom_url,
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
                        COALESCE(vs.period_view_count, 0) AS score
                    FROM video_stat AS vs
                    JOIN video AS v ON v.video_id = vs.video_id
                    JOIN channel AS ch ON ch.channel_id = vs.channel_id
                    WHERE ch.category_id = :category_id
                      AND ch.status = {ChannelStatus.ACTIVE}
                      AND vs.report_period = :report_period
                      AND vs.is_new IS TRUE
                      AND COALESCE(v.status, 1) > 0
                      AND COALESCE(vs.is_short, v.is_short, false) = false
                    ORDER BY score DESC
                    LIMIT :limit
                    """
                ),
                {
                    "category_id": int(category_id),
                    "report_period": report_period,
                    "limit": int(limit),
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

    @staticmethod
    def _ilike_contains(q: str) -> str:
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{esc}%"

    @classmethod
    async def search_by_title(
        cls,
        *,
        query: str,
        report_period: date | Period,
        limit: int = 20,
        category_id: int | None = None,
        channel_id: str | None = None,
        period_from: date | Period | None = None,
        period_to: date | Period | None = None,
    ) -> list[dict]:
        """FTS search videos by title (title_tsv); attach video_stat for report_period."""
        if isinstance(report_period, Period):
            report_period = date(report_period.year, report_period.month, 1)
        if isinstance(period_from, Period):
            period_from = date(period_from.year, period_from.month, 1)
        if isinstance(period_to, Period):
            period_to = date(period_to.year, period_to.month, 1)

        q = (query or "").strip()
        if not q:
            return []

        where = [
            "COALESCE(v.status, 1) > 0",
            f"ch.status = {ChannelStatus.ACTIVE}",
            # Must use bare title_tsv (not COALESCE/to_tsvector) so GIN can match
            "v.title_tsv @@ plainto_tsquery('russian', :q)",
        ]
        params: dict = {
            "q": q,
            "report_period": report_period,
            "limit": int(limit),
        }
        if category_id is not None:
            where.append("ch.category_id = :category_id")
            params["category_id"] = int(category_id)
        if channel_id:
            where.append("v.channel_id = :channel_id")
            params["channel_id"] = channel_id
        if period_from is not None:
            # bare column → can use idx on published_at_period
            where.append("v.published_at_period >= :period_from")
            params["period_from"] = period_from
        if period_to is not None:
            # exclusive end: [from, to)
            where.append("v.published_at_period < :period_to")
            params["period_to"] = period_to

        sql = f"""
            SELECT
                v.video_id,
                v.channel_id,
                ch.channel_title,
                ch.custom_url,
                v.title,
                v.description,
                v.video_url,
                v.thumbnail_url,
                v.duration,
                v.published_at,
                v.is_clickbait,
                v.clickbait_comment,
                COALESCE(vs.report_period, :report_period) AS report_period,
                COALESCE(vs.is_short, v.is_short) AS is_short,
                vs.is_new,
                COALESCE(vs.period_view_count, 0) AS period_view_count,
                COALESCE(vs.period_like_count, 0) AS period_like_count,
                COALESCE(vs.period_comment_count, 0) AS period_comment_count,
                COALESCE(vs.view_count, 0) AS view_count,
                COALESCE(vs.like_count, 0) AS like_count,
                COALESCE(vs.comment_count, 0) AS comment_count,
                CASE
                    WHEN COALESCE(vs.is_short, v.is_short) IS TRUE
                    THEN COALESCE(vs.period_view_count, 0) / 10.0
                    ELSE COALESCE(vs.period_view_count, 0)
                END AS score,
                ts_rank(v.title_tsv, plainto_tsquery('russian', :q)) AS fts_rank
            FROM video AS v
            JOIN channel AS ch ON ch.channel_id = v.channel_id
            LEFT JOIN video_stat AS vs
              ON vs.video_id = v.video_id
             AND vs.report_period = :report_period
            WHERE {" AND ".join(where)}
            ORDER BY
                fts_rank DESC,
                score DESC NULLS LAST,
                v.published_at DESC NULLS LAST
            LIMIT :limit
        """

        async with async_session_maker() as session:
            result = await session.execute(text(sql), params)
            rows = []
            for row in result.mappings().all():
                item = dict(row)
                item.pop("fts_rank", None)
                if item.get("report_period") is not None:
                    item["report_period"] = item["report_period"].isoformat()
                if item.get("published_at") is not None:
                    item["published_at"] = item["published_at"].isoformat()
                if item.get("score") is not None:
                    item["score"] = int(round(float(item["score"])))
                else:
                    item["score"] = 0
                rows.append(item)
            return rows

    @classmethod
    async def top_for_channels(
        cls,
        *,
        channel_ids: list[str],
        report_period: date | Period,
        limit: int = 5,
    ) -> dict[str, list[dict]]:
        """Top `limit` new videos per channel for period. Returns {channel_id: [videos]}."""
        if not channel_ids:
            return {}
        if isinstance(report_period, Period):
            report_period = date(report_period.year, report_period.month, 1)

        async with async_session_maker() as session:
            result = await session.execute(
                text(
                    """
                    WITH scored AS (
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
                            END AS score,
                            ROW_NUMBER() OVER (
                                PARTITION BY v.channel_id
                                ORDER BY
                                    vs.is_short ASC NULLS FIRST,
                                    CASE
                                        WHEN vs.is_short
                                        THEN COALESCE(vs.period_view_count, 0) / 10.0
                                        ELSE COALESCE(vs.period_view_count, 0)
                                    END DESC
                            ) AS rn
                        FROM video_stat AS vs
                        JOIN video AS v ON v.video_id = vs.video_id
                        WHERE vs.channel_id IN :channel_ids
                          AND vs.report_period = :report_period
                          AND vs.is_new IS TRUE
                          AND COALESCE(v.status, 1) > 0
                    )
                    SELECT *
                    FROM scored
                    WHERE rn <= :limit
                    ORDER BY channel_id, rn
                    """
                ).bindparams(bindparam("channel_ids", expanding=True)),
                {
                    "channel_ids": list(channel_ids),
                    "report_period": report_period,
                    "limit": int(limit),
                },
            )
            out: dict[str, list[dict]] = {cid: [] for cid in channel_ids}
            for row in result.mappings().all():
                item = dict(row)
                item.pop("rn", None)
                if item.get("report_period") is not None:
                    item["report_period"] = item["report_period"].isoformat()
                if item.get("published_at") is not None:
                    item["published_at"] = item["published_at"].isoformat()
                if item.get("score") is not None:
                    item["score"] = int(round(float(item["score"])))
                cid = item.get("channel_id")
                if cid in out:
                    out[cid].append(item)
            return out

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
        Only rows with video.channel_id NOT NULL and channel.status != DELETED.
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
              AND c.status > {ChannelStatus.DELETED}
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

            import app.api.ytapi as yt
            from app.api import yt_pending

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
                    await yt_pending.commit_rows(
                        "video_status",
                        missing_payload,
                        scope=f"missing_cat{category_id}",
                    )

                for item in data:
                    item["report_period"] = report_period
                period_key = (
                    report_period.strftime("%Y-%m")
                    if hasattr(report_period, "strftime")
                    else str(report_period)[:7]
                )
                ok = await yt_pending.commit_rows(
                    "video_stat",
                    data,
                    scope=f"cat{category_id}_{period_key}",
                )
                if ok:
                    total_updated += len(data)
                    if category_id != 0:  # Don't print for single video_ids case
                        logger.info(
                            f"{i}: Updated {len(data)} records for category {category_id}"
                        )

        logger.info(f"Total updated videos: {total_updated}")
        return total_updated


# print("OK")

# save_data_dump({"a": 1, "test": 2}, "video_list_dump")
