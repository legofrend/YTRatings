import asyncio
from datetime import UTC, date, datetime, timedelta
import time

from sqlalchemy import text, select, or_, and_, func, case

# from sqlalchemy.exc import SQLAlchemyError

from app.dao.base import BaseDAO
from app.database import async_session_maker
from app.logger import logger, save_errors
from app.channel.models import (
    Channel,
    ChannelRating,
    ChannelStat,
    ChannelStatus,
)
from app.channel.category.models import Category
from app.channel.video.dao import VideoDAO
from app.period import Period

# ytapi is imported lazily inside YouTube-calling methods (FastAPI image has no ingest deps)


def _naive_utc(dt: datetime) -> datetime:
    """Normalize tz-aware datetimes to naive UTC (PG/YouTube store naive UTC)."""
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


class ChannelDAO(BaseDAO):
    model = Channel
    gid = "channel_id"

    @classmethod
    async def get_ids(cls, filters: dict = {}):
        # if not "status" in filters.keys():
        #     filters["status"] = ChannelStatus.ACTIVE
        data = await cls.find_all(**filters)
        ids = [d.channel_id for d in data]
        return ids

    @classmethod
    async def add_update_bulk(cls, data, do_nothing: bool = False):
        return await super().add_update_bulk(data, do_nothing=do_nothing)

    @classmethod
    async def update(cls, filter: dict, data: dict):
        return await super().update(filter, data)

    @classmethod
    async def get_ids_wo_stat(
        cls,
        report_period: Period,
        category_id: int = None,
    ):
        async with async_session_maker() as session:
            query = (
                select(Channel.channel_id)
                .outerjoin(
                    ChannelStat,
                    and_(
                        Channel.channel_id == ChannelStat.channel_id,
                        ChannelStat.report_period == report_period,
                    ),
                )
                .where(and_(ChannelStat.id.is_(None), Channel.status == ChannelStatus.ACTIVE))
                .distinct()
            )

            if category_id:
                query = query.where(Channel.category_id == category_id)

            result = await session.execute(query)
            data = result.scalars().all()
            return data

    @classmethod
    async def get_ids_wo_video(
        cls,
        report_period: Period,
        category_id: int = None,
    ):
        # TODO replace with alchemy query
        query = f"""select c.channel_id
                    from channel as c
                    left join video v on v.channel_id = c.channel_id and v.published_at_period = '{report_period.strf()}'
                    where c.status = {ChannelStatus.ACTIVE} and v.id is null"""
        query += f" and c.category_id={category_id}" if category_id else ""
        # query += " group by c.channel_id having count(v.id) = 0"
        query = text(query)
        async with async_session_maker() as session:
            result = await session.execute(query)
            data = result.mappings().all()
            data = [item["channel_id"] for item in data]
            return data

    @classmethod
    async def search_channel(
        cls,
        queries: str | list[str],
        max_result: int = 1,
        order: str = "relevance",
        category_id: int = None,
    ):
        import app.api.ytapi as yt

        if isinstance(queries, str):
            queries = [queries]
        for i, query in enumerate(queries, start=1):

            data = yt.search_list(
                query=query, type="channel", max_result=max_result, order=order
            )
            if data:
                check = "OK" if query == data[0]["channel_title"] else "CHECK"
                logger.info(
                    f"{i}/{len(queries)} {query}:{data[0]['channel_title']} {check }"
                )
                if category_id:
                    for item in data:
                        item["category_id"] = category_id
                        item["status"] = ChannelStatus.ACTIVE
                await cls.add_update_bulk(data, do_nothing=True)
            else:
                logger.warning(f"{i}/{len(queries)} {query}: NOT FOUND")

        return True

    @classmethod
    async def find_by_name(cls, name: str) -> str:
        channel = cls.find_one_or_none(custom_url=name)
        if not channel:
            [channel] = await cls.search_channel(name)
        if not channel:
            return None
        return channel.get("channel_id")

    @classmethod
    async def add_by_handles(
        cls,
        handles: list[str],
        *,
        category_id: int,
        priority: int = 100,
        status: int = ChannelStatus.ACTIVE,
    ) -> dict:
        """
        Resolve YouTube handles via channels.list(forHandle=…) and upsert into channel.

        On INSERT: sets category_id / status / priority.
        On CONFLICT: refreshes YT detail fields only — never overwrites category_id,
        status, or priority (a channel belongs to one category; world/import must not
        steal existing Russian-category placements).
        Fetch timestamps are omitted from the payload and stay untouched.
        """
        import app.api.ytapi as yt

        if not handles:
            return {
                "requested": 0,
                "fetched": 0,
                "upserted": 0,
                "inserted": 0,
                "updated": 0,
                "skipped_existing": 0,
                "channel_ids": [],
            }

        details = yt.channel_list(handles=handles, obj_type="detail")
        if not details:
            logger.warning("add_by_handles: no channels returned from API")
            return {
                "requested": len(handles),
                "fetched": 0,
                "upserted": 0,
                "inserted": 0,
                "updated": 0,
                "skipped_existing": 0,
                "channel_ids": [],
            }

        rows = []
        for d in details:
            cid = d.get("channel_id")
            if not cid:
                continue
            rows.append(
                {
                    "channel_id": cid,
                    "channel_title": d.get("channel_title") or "",
                    "description": d.get("description"),
                    "custom_url": d.get("custom_url"),
                    "thumbnail_url": d.get("thumbnail_url"),
                    "published_at": d.get("published_at"),
                    "category_id": category_id,
                    "status": status,
                    "priority": priority,
                }
            )

        if not rows:
            return {
                "requested": len(handles),
                "fetched": len(details),
                "upserted": 0,
                "inserted": 0,
                "updated": 0,
                "skipped_existing": 0,
                "channel_ids": [],
            }

        from app.api import yt_pending

        ok = await yt_pending.commit_rows(
            "channel_detail_handles",
            rows,
            scope=f"cat{category_id}",
        )
        channel_ids = [r["channel_id"] for r in rows] if ok else []
        logger.info(
            f"add_by_handles: requested={len(handles)} fetched={len(details)} "
            f"upserted={len(channel_ids)} ok={ok} "
            f"category_id={category_id}(new only) priority={priority}(new only)"
        )
        return {
            "requested": len(handles),
            "fetched": len(details),
            "upserted": len(channel_ids),
            "inserted": 0,
            "updated": 0,
            "skipped_existing": 0,
            "channel_ids": channel_ids,
        }

    @classmethod
    async def upsert_yt_handle_rows(cls, rows: list[dict]) -> bool:
        """
        Insert new channels with category/status/priority; on conflict refresh
        YT detail fields only (never steal category ownership).
        """
        if not rows:
            return True

        from sqlalchemy.dialects.postgresql import insert as pg_insert

        detail_cols = [
            "channel_title",
            "description",
            "custom_url",
            "thumbnail_url",
            "published_at",
        ]
        stmt = pg_insert(Channel).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["channel_id"],
            set_={c: getattr(stmt.excluded, c) for c in detail_cols},
        ).returning(Channel.channel_id)
        async with async_session_maker() as session:
            result = await session.execute(stmt)
            await session.commit()
            channel_ids = [r[0] for r in result.all()]
        logger.info(f"upsert_yt_handle_rows: upserted={len(channel_ids)}")
        return True

    @classmethod
    async def update_detail(
        cls,
        channel_ids: list[str] | str = None,
        category_id: int = None,
        do_nothing: bool = False,
    ):
        import app.api.ytapi as yt
        from app.api import yt_pending

        if not channel_ids:
            if category_id:
                filters = {
                    "category_id": category_id,
                    "status": ChannelStatus.ACTIVE,
                }
            else:
                filters = {
                    "published_at": None,
                    "status": ChannelStatus.ACTIVE,
                }

            channel_ids = await cls.get_ids(filters=filters)

        data = yt.channel_list(channel_ids, obj_type="detail")
        if data:
            # Only touch detail fields — add_update_bulk would NULL out
            # category_id/status/priority/fetch dts via excluded defaults.
            op = "channel_detail_upsert" if do_nothing else "channel_detail_update"
            scope = f"cat{category_id}" if category_id else "default"
            await yt_pending.commit_rows(
                op, data, scope=scope, meta={"do_nothing": do_nothing}
            )
        return data

    @classmethod
    async def refresh_broken_thumbnails(
        cls,
        *,
        category_id: int | None = None,
        concurrency: int = 20,
        timeout_s: float = 10.0,
    ) -> dict:
        """
        Check channel.thumbnail_url reachability; refresh detail via YT API for broken ones.

        category_id: only that category (ACTIVE); None = all active channels.
        """
        import aiohttp

        async with async_session_maker() as session:
            q = select(
                Channel.channel_id,
                Channel.channel_title,
                Channel.custom_url,
                Channel.thumbnail_url,
            ).where(Channel.status == ChannelStatus.ACTIVE)
            if category_id is not None:
                q = q.where(Channel.category_id == category_id)
            rows = (await session.execute(q)).mappings().all()

        channels = [dict(r) for r in rows]
        logger.info(
            f"refresh_broken_thumbnails: checking {len(channels)} channels "
            f"category_id={category_id}"
        )

        sem = asyncio.Semaphore(concurrency)
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        broken: list[dict] = []

        async def _check(ch: dict, session: aiohttp.ClientSession) -> None:
            url = (ch.get("thumbnail_url") or "").strip()
            if not url:
                broken.append({**ch, "reason": "empty_url"})
                return
            async with sem:
                try:
                    async with session.head(url, allow_redirects=True) as resp:
                        if resp.status == 405:
                            async with session.get(url, allow_redirects=True) as g:
                                ok = 200 <= g.status < 400
                                status = g.status
                        else:
                            ok = 200 <= resp.status < 400
                            status = resp.status
                    if not ok:
                        broken.append({**ch, "reason": f"http_{status}"})
                except Exception as e:
                    broken.append({**ch, "reason": type(e).__name__})

        async with aiohttp.ClientSession(timeout=timeout) as http:
            await asyncio.gather(*[_check(ch, http) for ch in channels])

        broken_ids = [c["channel_id"] for c in broken]
        logger.info(
            f"refresh_broken_thumbnails: broken={len(broken_ids)}/{len(channels)}"
        )
        for c in broken[:20]:
            logger.info(
                f"  broken {c.get('custom_url') or c['channel_id']}: {c.get('reason')}"
            )
        if len(broken) > 20:
            logger.info(f"  ... and {len(broken) - 20} more")

        updated = []
        if broken_ids:
            updated = await cls.update_detail(channel_ids=broken_ids) or []
            logger.info(
                f"refresh_broken_thumbnails: refreshed detail for {len(updated)} channels"
            )

        return {
            "checked": len(channels),
            "broken": len(broken_ids),
            "broken_ids": broken_ids,
            "broken_detail": broken,
            "updated": len(updated) if updated else 0,
        }

    @classmethod
    async def search_by_keywords(
        cls,
        query: str,
        date_from: datetime = datetime.now(),
        iterations: int = 8,
        date_step: int = 7,
        order: str = "relevance",
        type: str = "video",
        max_result: int = 50,
    ):
        import app.api.ytapi as yt

        data = []
        for _ in range(0, iterations):
            try:
                published_range = [date_from, date_from - timedelta(days=date_step)]
                videos = yt.search_list(
                    query,
                    published=published_range,
                    type=type,
                    order=order,
                    max_result=max_result,
                )
                data.extend(videos)
                logger.debug(f"Fetched {len(videos)} videos")

            except Exception as e:
                logger.error(f"Can't get videos {published_range=}", exc_info=True)
                return data

            date_from -= timedelta(days=date_step)

        unique_channel_ids = list(set(video["channel_id"] for video in data))
        logger.info(f"Find {len(unique_channel_ids)} unique channels")

        return await cls.update_detail(unique_channel_ids, do_nothing=True)

    @classmethod
    async def get_channels_to_fetch_videos(
        cls,
        category_id: int = None,
        date_to: date = date.today(),
        priority: int | None = 100,
        priority_gt: int | None = None,
    ):
        """Active channels with last_video_fetch_dt < date_to.

        priority: ceiling (priority <= N). None = no upper bound.
        priority_gt: floor exclusive (priority > N OR priority IS NULL).
        Oldest / never-fetched first so fresh top channels don't burn quota
        before the long tail.
        """
        query = select(Channel.channel_id, Channel.last_video_fetch_dt).where(
            Channel.status == ChannelStatus.ACTIVE,
            or_(
                Channel.last_video_fetch_dt.is_(None),
                Channel.last_video_fetch_dt < date_to,
            ),
        )
        if priority is not None:
            query = query.where(Channel.priority <= priority)
        if priority_gt is not None:
            query = query.where(
                or_(Channel.priority.is_(None), Channel.priority > priority_gt)
            )
        if category_id:
            query = query.where(Channel.category_id == category_id)
        query = query.limit(1000).order_by(
            Channel.last_video_fetch_dt.asc().nullsfirst()
        )

        async with async_session_maker() as session:
            result = await session.execute(query)
            data = result.mappings().all()
            return data

    @classmethod
    async def get_channels_to_fetch_shorts(
        cls,
        category_id: int = None,
        date_to: date = date.today(),
        priority: int | None = 100,
        priority_gt: int | None = None,
        *,
        only_missing: bool = False,
    ):
        """Channels needing UUSH sync.

        Default: last_shorts_fetch_dt IS NULL or < date_to (incremental).
        only_missing=True: never synced only (backfill).
        Oldest / never-synced first (same rationale as videos).
        """
        fetch_filter = (
            Channel.last_shorts_fetch_dt.is_(None)
            if only_missing
            else or_(
                Channel.last_shorts_fetch_dt.is_(None),
                Channel.last_shorts_fetch_dt < date_to,
            )
        )
        query = select(Channel.channel_id, Channel.last_shorts_fetch_dt).where(
            Channel.status == ChannelStatus.ACTIVE,
            fetch_filter,
        )
        if priority is not None:
            query = query.where(Channel.priority <= priority)
        if priority_gt is not None:
            query = query.where(
                or_(Channel.priority.is_(None), Channel.priority > priority_gt)
            )
        if category_id:
            query = query.where(Channel.category_id == category_id)
        query = query.limit(1000).order_by(
            Channel.last_shorts_fetch_dt.asc().nullsfirst()
        )

        async with async_session_maker() as session:
            result = await session.execute(query)
            return result.mappings().all()

    @classmethod
    async def fetch_new_videos(
        cls,
        category_ids: list[int] | int = None,
        channel_ids: list[str] | str = None,
        date_from: date = None,
        date_to: date = None,
        priority: int | None = 100,
        priority_gt: int | None = None,
        # period: Period | tuple[datetime, datetime] = Period(),
    ) -> str:
        """Fetch new uploads. Returns 'ok' | 'quota_warn' | 'quota_exceeded'."""
        import app.api.ytapi as yt
        from app.api import yt_quota

        if isinstance(category_ids, int):
            category_ids = [category_ids]
        if channel_ids and category_ids:
            logger.warning("channel_ids and category_ids can't be used together")
        if channel_ids:
            category_ids = [0]

        # Exclusive end of report window (1st of next month). Channels / videos
        # beyond this belong to the next period.
        date_to = date_to or date.today()
        period_end = datetime.combine(date_to, datetime.min.time())
        stop_reason: str | None = None

        for i, category_id in enumerate(category_ids, start=1):
            if stop_reason:
                break
            if channel_ids:
                channels = [
                    {"channel_id": channel_id, "last_video_fetch_dt": None}
                    for channel_id in channel_ids
                ]
            else:
                channels = await cls.get_channels_to_fetch_videos(
                    date_to=date_to,
                    category_id=category_id,
                    priority=priority,
                    priority_gt=priority_gt,
                )
            logger.info(
                f"Category {i}/{len(category_ids)}: {category_id=} {len(channels)} channels"
            )
            for index, channel in enumerate(channels, start=1):
                if yt_quota.is_at_warn() or yt.IS_QUOTA_EXCEEDED:
                    stop_reason = (
                        "quota_exceeded" if yt.IS_QUOTA_EXCEEDED else "quota_warn"
                    )
                    logger.warning(
                        f"fetch_new_videos: soft-stop ({stop_reason}) "
                        f"at channel {index}/{len(channels)} cat={category_id}"
                    )
                    break

                channel_id = channel["channel_id"]
                last_fetched = channel["last_video_fetch_dt"]
                is_cold = last_fetched is None

                if not is_cold:
                    date_from = last_fetched
                    if isinstance(date_from, datetime):
                        date_from = _naive_utc(date_from)
                    if isinstance(date_from, datetime) and date_from >= period_end:
                        logger.info(
                            f"{index}/{len(channels)}: {channel_id} - skipped (up to date)"
                        )
                        continue
                    if isinstance(date_from, date) and not isinstance(
                        date_from, datetime
                    ) and date_from >= date_to:
                        logger.info(
                            f"{index}/{len(channels)}: {channel_id} - skipped (up to date)"
                        )
                        continue
                else:
                    date_from = None

                # Watermark in naive UTC (same as YouTube published_at). Cap at
                # period_end so close after month-end does not claim next month.
                fetch_marker = min(
                    datetime.now(UTC).replace(tzinfo=None), period_end
                )

                try:
                    if is_cold:
                        # First ingest: last 3 calendar months ending at date_to;
                        # if channel is dormant in that window → latest 100 uploads.
                        to_d = date_to if isinstance(date_to, date) else date_to.date()
                        cold_from = datetime.combine(
                            Period(to_d.month, to_d.year).next(-3), datetime.min.time()
                        )
                        logger.info(
                            f"{index}/{len(channels)}: {channel_id} cold-start "
                            f"window=[{cold_from.date()} .. {to_d})"
                        )
                        res = await VideoDAO.get_from_playlist(
                            channel_id,
                            date_from=cold_from,
                            date_to=date_to,
                            max_result=1000,
                        )
                        if not res and not yt.IS_QUOTA_EXCEEDED:
                            logger.info(
                                f"{index}/{len(channels)}: {channel_id} "
                                f"no videos in 3mo window → last 100"
                            )
                            res = await VideoDAO.get_from_playlist(
                                channel_id,
                                date_from=None,
                                date_to=date_to,
                                max_result=100,
                            )
                    else:
                        logger.info(
                            f"{index}/{len(channels)}: {channel_id}, last fetched {date_from}"
                        )
                        res = await VideoDAO.get_from_playlist(
                            channel_id,
                            date_from=date_from,
                            date_to=date_to,
                            max_result=1000,
                        )
                except yt.QuotaExceededException:
                    yt.IS_QUOTA_EXCEEDED = True
                    stop_reason = "quota_exceeded"
                    logger.warning(
                        f"{channel_id}: quota exceeded before fetch; "
                        "not advancing last_video_fetch_dt"
                    )
                    break

                if yt.IS_QUOTA_EXCEEDED:
                    stop_reason = "quota_exceeded"
                    logger.warning(
                        f"{channel_id}: quota exceeded during fetch; "
                        "not advancing last_video_fetch_dt"
                    )
                    break

                # ToDo различать ситуации, когда видео нет из-за ошибки или их просто нет
                await cls.update(
                    {"channel_id": channel_id},
                    {"last_video_fetch_dt": fetch_marker},
                )

            logger.info(
                f"Category {i}/{len(category_ids)}: {category_id=}, updated {len(channels)} channels"
            )

        return stop_reason or "ok"

    @classmethod
    async def save_thumbnails(cls, filters: dict = {}):
        async def get_channels():
            date_from = date(2025, 4, 10)
            async with async_session_maker() as session:
                query = select(
                    Channel.channel_id, Channel.custom_url, Channel.thumbnail_url
                ).where(and_(Channel.status == ChannelStatus.ACTIVE, Channel.category_id == 7))
                # Channel.created_at > date_from,

                result = await session.execute(query)
                data = result.mappings().all()
                return data

        from app.utils.download import save_thumbnails

        channels = await get_channels()
        logger.info(f"Found {len(channels)} channels")
        # channels = await cls.find_all(**filters)

        return save_thumbnails(channels)

    @classmethod
    async def get_channels_with_top_videos(cls, category_id: int, priority: int = 100):
        query = text(
            f"""
            with top_videos as (
                SELECT
                    sub.channel_id,
                    string_agg(title, E'\n' ORDER BY title) AS title_list
                FROM (
                    SELECT
                        channel_id,
                        title,
                        ROW_NUMBER() OVER (PARTITION BY channel_id ORDER BY rank DESC) AS rn
                    FROM video
                ) sub
                WHERE rn <= 10
                GROUP BY channel_id
            )
            select
                c.channel_id, channel_title, description, priority, title_list
            from channel as c
            left join top_videos as tv on tv.channel_id = c.channel_id
            where category_id=:category_id and status={ChannelStatus.ACTIVE} and priority <= :priority
            order by priority
        """
        )

        async with async_session_maker() as session:
            result = await session.execute(
                query, {"category_id": category_id, "priority": priority}
            )
            return result.mappings().all()

    @classmethod
    async def sync_priority(
        cls,
        *,
        months: int = 12,
        category_ids: list[int] | int | None = None,
        default_priority: int = 1000,
    ) -> dict:
        """
        Set channel.priority = best (MIN) pv_score_rank over the last `months`
        report periods. Channels with no ranks in the window keep/get default_priority.

        Matches operational meaning: ever in top-10 recently → priority 10 (fetch ceiling).
        """
        if isinstance(category_ids, int):
            category_ids = [category_ids]
        if months < 1:
            raise ValueError("months must be >= 1")

        # Inclusive window of `months` calendar months ending at current month (PT not needed)
        today = date.today().replace(day=1)
        # months=12 → oldest = today - 11 months
        y, m = today.year, today.month - (months - 1)
        while m <= 0:
            m += 12
            y -= 1
        oldest = date(y, m, 1)

        params: dict = {
            "oldest": oldest,
            "default_priority": default_priority,
        }
        cat_sql = ""
        if category_ids:
            cat_sql = "AND c.category_id = ANY(:cats)"
            params["cats"] = category_ids

        # Best rank in window; channels with no ranked rows → default
        sql = f"""
        WITH best AS (
            SELECT
                cr.channel_id,
                MIN(cr.rank) AS priority
            FROM channel_rating AS cr
            WHERE cr.report_period >= :oldest
              AND cr.rank IS NOT NULL
            GROUP BY cr.channel_id
        ),
        target AS (
            SELECT c.channel_id
            FROM channel AS c
            WHERE c.status = {ChannelStatus.ACTIVE}
              {cat_sql}
        ),
        updates AS (
            SELECT
                t.channel_id,
                COALESCE(b.priority, :default_priority) AS priority
            FROM target AS t
            LEFT JOIN best AS b ON b.channel_id = t.channel_id
        )
        UPDATE channel AS c
        SET priority = u.priority
        FROM updates AS u
        WHERE c.channel_id = u.channel_id
          AND c.priority IS DISTINCT FROM u.priority
        """

        async with async_session_maker() as session:
            before = await session.execute(
                text(
                    f"""
                    SELECT
                      count(*) FILTER (WHERE priority <= 20) AS p20,
                      count(*) FILTER (WHERE priority <= 100) AS p100,
                      count(*) AS total
                    FROM channel c
                    WHERE status = {ChannelStatus.ACTIVE} {cat_sql}
                    """
                ),
                params,
            )
            before_row = before.mappings().one()

            result = await session.execute(text(sql), params)
            await session.commit()
            updated = result.rowcount

            after = await session.execute(
                text(
                    f"""
                    SELECT
                      count(*) FILTER (WHERE priority <= 20) AS p20,
                      count(*) FILTER (WHERE priority <= 100) AS p100,
                      count(*) AS total,
                      min(priority) AS min_p,
                      max(priority) AS max_p
                    FROM channel c
                    WHERE status = {ChannelStatus.ACTIVE} {cat_sql}
                    """
                ),
                params,
            )
            after_row = after.mappings().one()

        stats = {
            "months": months,
            "oldest": oldest.isoformat(),
            "category_ids": category_ids,
            "updated": updated,
            "before": dict(before_row),
            "after": dict(after_row),
        }
        logger.info(
            f"channel.sync_priority: months={months} oldest={oldest} "
            f"cats={category_ids} updated={updated} "
            f"after min/max={after_row['min_p']}/{after_row['max_p']} "
            f"p<=20={after_row['p20']} p<=100={after_row['p100']}"
        )
        return stats


class ChannelStatDAO(BaseDAO):
    model = ChannelStat

    @classmethod
    async def add_bulk(cls, data: list[dict]) -> list | bool:
        return await super().add_bulk(data)

    @classmethod
    async def periods_for_category(cls, category_id: int) -> list[date]:
        """Distinct report_periods with ranked channel_rating in category."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(ChannelRating.report_period)
                .where(
                    ChannelRating.category_id == category_id,
                    ChannelRating.report_period.is_not(None),
                    ChannelRating.rank.is_not(None),
                )
                .distinct()
                .order_by(ChannelRating.report_period.desc())
            )
            return [row[0] for row in result.all()]

    @classmethod
    async def latest_period(cls, category_id: int) -> date | None:
        periods = await cls.periods_for_category(category_id)
        return periods[0] if periods else None

    @classmethod
    async def latest_period_any(cls) -> date | None:
        """Newest report_period that has any ranked channel_rating."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(func.max(ChannelRating.report_period)).where(
                    ChannelRating.rank.is_not(None)
                )
            )
            return result.scalar_one_or_none()

    @staticmethod
    def _ilike_contains(q: str) -> str:
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{esc}%"

    @staticmethod
    def _zero_channel_stats(item: dict, report_period: date) -> dict:
        """Fill missing channel_stat fields with 0; keep report_period."""
        zeros = {
            "rank": 0,
            "rank_mom": 0,
            "score": 0,
            "score_mom": 0,
            "video_views": 0,
            "views_new_long": 0,
            "views_new_short": 0,
            "views_old_long": 0,
            "views_old_short": 0,
            "video_likes": 0,
            "video_comments": 0,
            "new_longs": 0,
            "new_shorts": 0,
            "duration_sec": 0,
            "channel_subscribers": 0,
            "channel_subscribers_mom": 0,
            "channel_views_mom": 0,
            "channel_views": 0,
            "channel_videos": 0,
        }
        for k, v in zeros.items():
            if item.get(k) is None:
                item[k] = v
        item["report_period"] = report_period.isoformat()
        return item

    @classmethod
    async def search_channels(
        cls,
        *,
        query: str,
        report_period: date | Period,
        limit: int = 20,
        category_id: int | None = None,
    ) -> list[dict]:
        """Search active channels by title / custom_url; attach stats for period (0 if missing)."""
        if isinstance(report_period, Period):
            report_period = date(report_period.year, report_period.month, 1)

        q = (query or "").strip()
        if not q:
            return []

        pat = cls._ilike_contains(q)
        pat_handle = cls._ilike_contains(q.lstrip("@"))

        async with async_session_maker() as session:
            where = [
                Channel.status == ChannelStatus.ACTIVE,
                or_(
                    Channel.channel_title.ilike(pat, escape="\\"),
                    Channel.custom_url.ilike(pat, escape="\\"),
                    Channel.custom_url.ilike(pat_handle, escape="\\"),
                ),
            ]
            if category_id is not None:
                where.append(Channel.category_id == category_id)

            title_hit = Channel.channel_title.ilike(pat, escape="\\")
            result = await session.execute(
                select(
                    Channel.channel_id,
                    func.coalesce(
                        ChannelRating.channel_title, Channel.channel_title
                    ).label("channel_title"),
                    func.coalesce(
                        ChannelRating.description, Channel.description
                    ).label("description"),
                    func.coalesce(
                        ChannelRating.custom_url, Channel.custom_url
                    ).label("custom_url"),
                    func.coalesce(
                        ChannelRating.thumbnail_url, Channel.thumbnail_url
                    ).label("thumbnail_url"),
                    func.coalesce(
                        ChannelRating.category_id, Channel.category_id
                    ).label("category_id"),
                    Category.name.label("category_name"),
                    ChannelRating.report_period,
                    ChannelRating.rank,
                    ChannelRating.rank_mom,
                    ChannelRating.score,
                    ChannelRating.score_mom,
                    ChannelRating.video_views,
                    ChannelRating.views_new_long,
                    ChannelRating.views_new_short,
                    ChannelRating.views_old_long,
                    ChannelRating.views_old_short,
                    ChannelRating.video_likes,
                    ChannelRating.video_comments,
                    ChannelRating.new_longs,
                    ChannelRating.new_shorts,
                    ChannelRating.duration_sec,
                    ChannelRating.channel_subscribers,
                    ChannelRating.channel_subscribers_mom,
                    ChannelRating.channel_views_mom,
                    ChannelRating.channel_views,
                    ChannelRating.channel_videos,
                )
                .outerjoin(Category, Category.id == Channel.category_id)
                .outerjoin(
                    ChannelRating,
                    and_(
                        ChannelRating.channel_id == Channel.channel_id,
                        ChannelRating.report_period == report_period,
                    ),
                )
                .where(*where)
                .order_by(
                    case((title_hit, 0), else_=1),
                    ChannelRating.score.desc().nullslast(),
                    Channel.channel_title.asc(),
                )
                .limit(limit)
            )
            rows = []
            for row in result.mappings().all():
                rows.append(cls._zero_channel_stats(dict(row), report_period))
            return rows

    @classmethod
    async def count_ranked_channels(
        cls,
        *,
        category_id: int,
        report_period: date | Period,
    ) -> int:
        if isinstance(report_period, Period):
            report_period = date(report_period.year, report_period.month, 1)

        async with async_session_maker() as session:
            result = await session.execute(
                select(func.count())
                .select_from(ChannelRating)
                .where(
                    ChannelRating.category_id == category_id,
                    ChannelRating.report_period == report_period,
                    ChannelRating.rank.is_not(None),
                )
            )
            return int(result.scalar_one() or 0)

    @classmethod
    async def top_channels(
        cls,
        *,
        category_id: int,
        report_period: date | Period,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        if isinstance(report_period, Period):
            report_period = date(report_period.year, report_period.month, 1)

        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))

        async with async_session_maker() as session:
            result = await session.execute(
                select(
                    ChannelRating.channel_id,
                    ChannelRating.channel_title,
                    ChannelRating.description,
                    ChannelRating.custom_url,
                    ChannelRating.thumbnail_url,
                    ChannelRating.category_id,
                    ChannelRating.report_period,
                    ChannelRating.rank,
                    ChannelRating.rank_mom,
                    ChannelRating.score,
                    ChannelRating.score_mom,
                    ChannelRating.video_views,
                    ChannelRating.views_new_long,
                    ChannelRating.views_new_short,
                    ChannelRating.views_old_long,
                    ChannelRating.views_old_short,
                    ChannelRating.video_likes,
                    ChannelRating.video_comments,
                    ChannelRating.new_longs,
                    ChannelRating.new_shorts,
                    ChannelRating.duration_sec,
                    ChannelRating.channel_subscribers,
                    ChannelRating.channel_subscribers_mom,
                    ChannelRating.channel_views_mom,
                    ChannelRating.channel_views,
                    ChannelRating.channel_videos,
                )
                .where(
                    ChannelRating.category_id == category_id,
                    ChannelRating.report_period == report_period,
                    ChannelRating.rank.is_not(None),
                )
                .order_by(ChannelRating.rank.asc())
                .offset(offset)
                .limit(limit)
            )
            rows = []
            for row in result.mappings().all():
                item = dict(row)
                if item.get("report_period") is not None:
                    item["report_period"] = item["report_period"].isoformat()
                rows.append(item)
            return rows

    @classmethod
    async def channel_dynamics(
        cls,
        *,
        channel_id: str,
        months: int = 12,
    ) -> dict | None:
        """Rank + pv_score over the last `months` periods (from latest available)."""
        async with async_session_maker() as session:
            ch = await session.execute(
                select(
                    Channel.channel_id,
                    Channel.channel_title,
                    Channel.description,
                    Channel.custom_url,
                    Channel.thumbnail_url,
                    Channel.category_id,
                ).where(Channel.channel_id == channel_id)
            )
            channel = ch.mappings().one_or_none()
            if not channel:
                return None

            result = await session.execute(
                select(
                    ChannelRating.report_period,
                    ChannelRating.rank,
                    ChannelRating.rank_mom,
                    ChannelRating.score,
                    ChannelRating.score_mom,
                    ChannelRating.video_views,
                    ChannelRating.views_new_long,
                    ChannelRating.views_old_long,
                    ChannelRating.views_new_short,
                    ChannelRating.views_old_short,
                    ChannelRating.channel_views,
                    ChannelRating.channel_views_mom,
                    ChannelRating.channel_subscribers,
                    ChannelRating.channel_subscribers_mom,
                )
                .where(
                    ChannelRating.channel_id == channel_id,
                    ChannelRating.report_period.is_not(None),
                )
                .order_by(ChannelRating.report_period.desc())
                .limit(months)
            )
            points = []
            for row in result.mappings().all():
                p = dict(row)
                p["report_period"] = p["report_period"].isoformat()
                points.append(p)

            points.reverse()  # chronological
            return {
                "channel": dict(channel),
                "points": points,
            }

    @classmethod
    async def category_dynamics(
        cls,
        *,
        category_id: int,
        limit: int = 20,
        months: int = 12,
    ) -> dict | None:
        """
        Per month: sum score / view buckets of top-`limit` channels
        (by pv_score_rank) in the category. Last `months` periods.
        """
        limit = max(1, min(int(limit), 100))
        months = max(1, min(int(months), 60))

        periods = await cls.periods_for_category(category_id)
        if not periods:
            return None
        window = periods[:months]
        oldest = window[-1]

        async with async_session_maker() as session:
            result = await session.execute(
                select(
                    ChannelRating.report_period,
                    ChannelRating.score,
                    ChannelRating.views_new_long,
                    ChannelRating.views_old_long,
                    ChannelRating.views_new_short,
                    ChannelRating.views_old_short,
                    ChannelRating.video_views,
                )
                .where(
                    ChannelRating.category_id == category_id,
                    ChannelRating.report_period >= oldest,
                    ChannelRating.report_period.is_not(None),
                    ChannelRating.rank.is_not(None),
                    ChannelRating.rank <= limit,
                )
            )
            buckets: dict[date, dict] = {}
            for row in result.mappings().all():
                rp = row["report_period"]
                b = buckets.setdefault(
                    rp,
                    {
                        "report_period": rp,
                        "score": 0.0,
                        "views_new_long": 0.0,
                        "views_old_long": 0.0,
                        "views_new_short": 0.0,
                        "views_old_short": 0.0,
                        "video_views": 0.0,
                    },
                )
                b["score"] += float(row["score"] or 0)
                b["views_new_long"] += float(row["views_new_long"] or 0)
                b["views_old_long"] += float(row["views_old_long"] or 0)
                b["views_new_short"] += float(row["views_new_short"] or 0)
                b["views_old_short"] += float(row["views_old_short"] or 0)
                b["video_views"] += float(row["video_views"] or 0)

            points = []
            for rp in sorted(window):
                b = buckets.get(rp)
                if not b:
                    continue
                p = dict(b)
                p["report_period"] = rp.isoformat()
                points.append(p)

            return {
                "category_id": category_id,
                "limit": limit,
                "months": months,
                "points": points,
            }

    @classmethod
    async def update_stat(
        cls,
        report_period: Period,
        channel_ids: list[str] | str = None,
        category_ids: list[int] | int | None = None,
        *,
        force: bool = False,
    ):
        if isinstance(category_ids, int):
            category_ids = [category_ids]

        if channel_ids:
            category_ids = [None]

        if not category_ids:
            category_ids = [None]

        total_updated = 0
        for i, category_id in enumerate(category_ids, start=1):
            if category_id is not None:
                logger.info(
                    f"Processing category {category_id} {i}/{len(category_ids)}"
                )
            current_channel_ids = (
                channel_ids
                if channel_ids
                else await (
                    ChannelDAO.get_ids(
                        {"status": ChannelStatus.ACTIVE, **({"category_id": category_id} if category_id is not None else {})}
                    )
                    if force
                    else ChannelDAO.get_ids_wo_stat(
                        report_period=report_period, category_id=category_id
                    )
                )
            )
            label = "channels" if force else "channels wo stat"
            logger.info(f"Found {len(current_channel_ids)} {label}")
            if not current_channel_ids:
                continue

            import app.api.ytapi as yt
            from app.api import yt_pending

            data = yt.channel_list(current_channel_ids, obj_type="stat")

            if data:
                for item in data:
                    item["report_period"] = report_period
                period_key = (
                    report_period.strf("%p")
                    if hasattr(report_period, "strf")
                    else str(report_period)[:7]
                )
                scope = f"cat{category_id}_{period_key}"
                ok = await yt_pending.commit_rows("channel_stat", data, scope=scope)
                if ok:
                    total_updated += len(data)
                    if category_id is not None:
                        logger.info(
                            f"{i}: Updated {len(data)} records for category {category_id}"
                        )
                    else:
                        logger.info(f"Updated {len(data)} records")

        logger.info(f"Total updated channels: {total_updated}")
        return total_updated


class ChannelRatingDAO(BaseDAO):
    model = ChannelRating

    @classmethod
    async def build_rating(
        cls,
        *,
        report_period: date | Period,
    ) -> dict[str, int]:
        """
        Rebuild channel_rating for one report_period — full API product row.

        Snapshots channel dims + channel_stat counts, computes channel_*_mom from
        prev channel_stat, aggregates video_stat, ranks by category, MoM vs prev
        channel_rating. Self-contained: API reads only this table.
        """
        if isinstance(report_period, Period):
            report_period = date(report_period.year, report_period.month, 1)
        params = {"report_period": report_period}
        t_all = time.monotonic()

        sql = f"""
            WITH cur AS (
                SELECT
                    cs.channel_id,
                    cs.report_period,
                    cs.data_at AS stats_at,
                    cs.channel_view_count AS channel_views,
                    cs.subscriber_count AS channel_subscribers,
                    cs.video_count AS channel_videos,
                    ch.channel_title,
                    ch.description,
                    ch.custom_url,
                    ch.thumbnail_url,
                    ch.category_id
                FROM channel_stat AS cs
                JOIN channel AS ch ON ch.channel_id = cs.channel_id
                WHERE cs.report_period = :report_period
                  AND ch.status = {ChannelStatus.ACTIVE}
            ),
            prev_cs AS (
                SELECT DISTINCT ON (channel_id)
                    channel_id,
                    channel_view_count AS channel_views,
                    subscriber_count AS channel_subscribers,
                    video_count AS channel_videos
                FROM channel_stat
                WHERE report_period = (:report_period::date - INTERVAL '1 month')
                ORDER BY channel_id, id DESC
            ),
            video_stats AS (
                SELECT
                    c.channel_id,
                    c.report_period,
                    SUM(CASE WHEN vs.is_new AND vs.is_short IS FALSE THEN 1 ELSE 0 END)
                        AS new_longs,
                    SUM(CASE WHEN vs.is_new AND vs.is_short THEN 1 ELSE 0 END)
                        AS new_shorts,
                    COALESCE(SUM(vs.period_view_count), 0) AS video_views,
                    SUM(CASE
                        WHEN vs.is_new AND vs.is_short IS FALSE
                        THEN vs.period_view_count ELSE 0 END) AS views_new_long,
                    SUM(CASE
                        WHEN vs.is_new AND vs.is_short
                        THEN vs.period_view_count ELSE 0 END) AS views_new_short,
                    SUM(CASE
                        WHEN vs.is_new IS FALSE AND vs.is_short IS FALSE
                        THEN vs.period_view_count ELSE 0 END) AS views_old_long,
                    SUM(CASE
                        WHEN vs.is_new IS FALSE AND vs.is_short
                        THEN vs.period_view_count ELSE 0 END) AS views_old_short,
                    SUM(CASE
                        WHEN vs.is_short THEN vs.period_view_count / 10
                        WHEN vs.is_short IS FALSE THEN vs.period_view_count
                        ELSE NULL
                    END) AS score,
                    COALESCE(SUM(vs.period_like_count), 0) AS video_likes,
                    COALESCE(SUM(vs.period_comment_count), 0) AS video_comments
                FROM cur AS c
                LEFT JOIN video_stat AS vs
                    ON vs.channel_id = c.channel_id
                   AND vs.report_period = c.report_period
                GROUP BY c.channel_id, c.report_period
            ),
            ranked AS (
                SELECT
                    c.*,
                    vs.new_longs,
                    vs.new_shorts,
                    vs.video_views,
                    vs.views_new_long,
                    vs.views_new_short,
                    vs.views_old_long,
                    vs.views_old_short,
                    vs.score,
                    vs.video_likes,
                    vs.video_comments,
                    RANK() OVER (
                        PARTITION BY c.category_id, c.report_period
                        ORDER BY COALESCE(vs.score, 0) DESC
                    ) AS rank
                FROM cur AS c
                LEFT JOIN video_stats AS vs
                    ON vs.channel_id = c.channel_id
                   AND vs.report_period = c.report_period
            ),
            duration AS (
                SELECT
                    channel_id,
                    published_at_period AS report_period,
                    SUM(duration) AS duration_sec
                FROM video
                WHERE published_at_period = :report_period
                GROUP BY channel_id, published_at_period
            ),
            built AS (
                SELECT
                    r.channel_id,
                    r.report_period,
                    r.channel_title,
                    r.description,
                    r.custom_url,
                    r.thumbnail_url,
                    r.category_id,
                    r.stats_at,
                    r.channel_views,
                    r.channel_subscribers,
                    r.channel_videos,
                    COALESCE(r.channel_views, 0)
                        - COALESCE(pcs.channel_views, 0) AS channel_views_mom,
                    COALESCE(r.channel_subscribers, 0)
                        - COALESCE(pcs.channel_subscribers, 0) AS channel_subscribers_mom,
                    COALESCE(r.channel_videos, 0)
                        - COALESCE(pcs.channel_videos, 0) AS channel_videos_mom,
                    r.new_longs,
                    r.new_shorts,
                    d.duration_sec,
                    r.video_views,
                    r.views_new_long,
                    r.views_new_short,
                    r.views_old_long,
                    r.views_old_short,
                    r.video_likes,
                    r.video_comments,
                    r.score,
                    COALESCE(r.score - prev.score, 0) AS score_mom,
                    r.rank,
                    COALESCE(r.rank - prev.rank, 0) AS rank_mom
                FROM ranked AS r
                LEFT JOIN prev_cs AS pcs ON pcs.channel_id = r.channel_id
                LEFT JOIN duration AS d
                    ON d.channel_id = r.channel_id
                   AND d.report_period = r.report_period
                LEFT JOIN channel_rating AS prev
                    ON prev.channel_id = r.channel_id
                   AND prev.report_period = r.report_period - INTERVAL '1 month'
            ),
            deleted AS (
                DELETE FROM channel_rating
                WHERE report_period = :report_period
                RETURNING 1
            )
            INSERT INTO channel_rating (
                channel_id, report_period,
                channel_title, description, custom_url, thumbnail_url, category_id,
                stats_at, channel_views, channel_subscribers, channel_videos,
                channel_views_mom, channel_subscribers_mom, channel_videos_mom,
                new_longs, new_shorts, duration_sec,
                video_views, views_new_long, views_new_short,
                views_old_long, views_old_short,
                video_likes, video_comments,
                score, score_mom, rank, rank_mom
            )
            SELECT
                channel_id, report_period,
                channel_title, description, custom_url, thumbnail_url, category_id,
                stats_at, channel_views, channel_subscribers, channel_videos,
                channel_views_mom, channel_subscribers_mom, channel_videos_mom,
                new_longs, new_shorts, duration_sec,
                video_views, views_new_long, views_new_short,
                views_old_long, views_old_short,
                video_likes, video_comments,
                score, score_mom, rank, rank_mom
            FROM built
        """

        async with async_session_maker() as session:
            result = await session.execute(text(sql), params)
            await session.commit()
            n = result.rowcount

        total_s = time.monotonic() - t_all
        stats = {"rows": n}
        logger.info(
            f"channel_rating.build: period={report_period} "
            f"rows={n} in {total_s:.1f}s"
        )
        return stats
