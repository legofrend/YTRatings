from datetime import date, datetime

from sqlalchemy import bindparam, text

import app.api.ytapi as yt
from app.channel.playlist_shorts.models import PlaylistShorts
from app.dao.base import BaseDAO
from app.database import async_session_maker
from app.logger import logger


class PlaylistShortsDAO(BaseDAO):
    model = PlaylistShorts
    gid = "video_id"

    @classmethod
    async def find_orphans_not_in_video(
        cls,
        *,
        category_ids: list[int] | None = None,
        channel_ids: list[str] | None = None,
        limit: int = 50,
    ) -> dict:
        """Shorts in playlist_shorts missing from video (within synced window per channel)."""
        filters: list[str] = []
        params: dict = {"limit": limit}

        if channel_ids:
            filters.append("ps.channel_id IN :channel_ids")
            params["channel_ids"] = channel_ids
        if category_ids:
            filters.append("c.category_id IN :category_ids")
            params["category_ids"] = category_ids

        filter_sql = (" AND " + " AND ".join(filters)) if filters else ""

        count_sql = f"""
            SELECT COUNT(*) AS cnt
            FROM playlist_shorts ps
            JOIN channel c ON c.channel_id = ps.channel_id
            LEFT JOIN video v ON v.video_id = ps.video_id
            WHERE v.video_id IS NULL
              AND c.last_shorts_fetch_dt IS NOT NULL
              AND ps.published_at < c.last_shorts_fetch_dt
              {filter_sql}
        """
        sample_sql = f"""
            SELECT ps.video_id, ps.channel_id, ps.title, ps.published_at
            FROM playlist_shorts ps
            JOIN channel c ON c.channel_id = ps.channel_id
            LEFT JOIN video v ON v.video_id = ps.video_id
            WHERE v.video_id IS NULL
              AND c.last_shorts_fetch_dt IS NOT NULL
              AND ps.published_at < c.last_shorts_fetch_dt
              {filter_sql}
            ORDER BY ps.published_at DESC
            LIMIT :limit
        """
        count_q = text(count_sql)
        sample_q = text(sample_sql)
        if channel_ids:
            count_q = count_q.bindparams(bindparam("channel_ids", expanding=True))
            sample_q = sample_q.bindparams(bindparam("channel_ids", expanding=True))
        if category_ids:
            count_q = count_q.bindparams(bindparam("category_ids", expanding=True))
            sample_q = sample_q.bindparams(bindparam("category_ids", expanding=True))

        async with async_session_maker() as session:
            total = (await session.execute(count_q, params)).scalar() or 0
            sample = (await session.execute(sample_q, params)).mappings().all()

        logger.info(
            f"orphans playlist_shorts∉video: {total} "
            f"cats={category_ids} channels={channel_ids or 'ALL'}"
        )
        return {"count": total, "sample": [dict(r) for r in sample]}

    @classmethod
    def _to_rows(cls, items: list[dict]) -> list[dict]:
        return [
            {
                "video_id": row["video_id"],
                "channel_id": row["channel_id"],
                "title": row.get("title"),
                "published_at": row["published_at"],
                "published_at_period": row.get("published_at_period"),
            }
            for row in items
        ]

    @classmethod
    async def sync_from_playlist(
        cls,
        channel_id: str,
        date_from: datetime | date | None = None,
        date_to: datetime | date | None = None,
        max_result: int = 5000,
    ) -> int | None:
        """Fetch UUSH playlist into playlist_shorts. Returns row count, 0 if empty, None on DB error."""
        from app.api import yt_pending

        items = yt.playlistitem_list(
            channel_id,
            date_from=date_from,
            date_to=date_to,
            max_result=max_result,
            playlist_kind="shorts",
        )
        if not items:
            logger.info(f"No shorts in UUSH for {channel_id} in window")
            return 0

        rows = cls._to_rows(items)
        ok = await yt_pending.commit_rows(
            "playlist_shorts", rows, scope=channel_id
        )
        if not ok:
            logger.error(f"Failed to upsert {len(rows)} shorts for {channel_id}")
            return None

        logger.info(f"Upserted {len(rows)} shorts for {channel_id}")
        return len(rows)

    @classmethod
    async def sync_channels(
        cls,
        category_ids: list[int],
        date_from: datetime,
        date_to: datetime,
        *,
        channel_ids: list[str] | None = None,
        priority: int = 100,
        max_result: int = 5000,
    ) -> None:
        from app.channel.dao import ChannelDAO

        if channel_ids:
            channels = [{"channel_id": cid} for cid in channel_ids]
        else:
            channels = []
            for category_id in category_ids:
                part = await ChannelDAO.get_channels_to_fetch_shorts(
                    category_id=category_id,
                    date_to=date_to.date(),
                    priority=priority,
                )
                channels.extend(part)

        if not channels:
            logger.warning("No channels to sync shorts")
            return

        fetch_marker = min(datetime.now(), date_to)
        total = len(channels)
        logger.info(
            f"shorts-sync: {total} channels, window [{date_from} .. {date_to})"
        )

        for index, channel in enumerate(channels, start=1):
            channel_id = channel["channel_id"]
            last = channel.get("last_shorts_fetch_dt")
            # Cold channel: pull same 3-mo window as video cold-start.
            # Incremental: resume from last marker (still capped by date_to).
            if last is None:
                to_d = date_to.date() if isinstance(date_to, datetime) else date_to
                from app.period import Period

                ch_from = datetime.combine(
                    Period(to_d.month, to_d.year).next(-3), datetime.min.time()
                )
            else:
                ch_from = last if isinstance(last, datetime) else datetime.combine(
                    last, datetime.min.time()
                )
            if ch_from >= date_to:
                logger.info(f"{index}/{total}: {channel_id} - skipped (up to date)")
                continue

            logger.info(
                f"{index}/{total}: {channel_id} window=[{ch_from} .. {date_to})"
            )
            count = await cls.sync_from_playlist(
                channel_id,
                date_from=ch_from,
                date_to=date_to,
                max_result=max_result,
            )
            if count is None:
                logger.error(f"{channel_id}: skipped last_shorts_fetch_dt (upsert failed)")
                continue

            await ChannelDAO.update(
                {"channel_id": channel_id},
                {"last_shorts_fetch_dt": fetch_marker},
            )
