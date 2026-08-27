"""
BigQuery writers for channel / channel_stat (raw ingest).

Used when settings.RAW_DB == "bigquery". Postgres ChannelDAO stays default.
"""

from __future__ import annotations

from datetime import date

from app.bq import write as bq_write
from app.logger import logger
from app.period import Period


class ChannelBqDAO:
    table = "channel"
    keys = ["channel_id"]

    @classmethod
    async def get_ids(cls, filters: dict | None = None) -> list[str]:
        filters = filters or {}
        channel = bq_write.table_fqn(cls.table)
        clauses: list[str] = []
        params: dict = {}
        for i, (k, v) in enumerate(filters.items()):
            if v is None:
                clauses.append(f"`{k}` IS NULL")
            else:
                pname = f"p{i}"
                clauses.append(f"`{k}` = @{pname}")
                params[pname] = v
        sql = f"SELECT channel_id FROM `{channel}`"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        rows = bq_write.query_rows(sql, params or None)
        return [r["channel_id"] for r in rows]

    @classmethod
    async def add_update_bulk(
        cls, data: list[dict], do_nothing: bool = False
    ) -> bool:
        if not data:
            return False
        bq_write.merge_rows(
            cls.table, data, cls.keys, update_on_match=not do_nothing
        )
        return True

    @classmethod
    async def update(cls, filter: dict, data: dict) -> bool:
        row = {**filter, **data}
        bq_write.merge_rows(cls.table, [row], cls.keys, update_on_match=True)
        return True

    @classmethod
    async def get_channels_to_fetch_videos(
        cls,
        category_id: int | None = None,
        date_to: date | None = None,
        priority: int = 100,
    ) -> list[dict]:
        date_to = date_to or date.today()
        # last_video_fetch_dt is TIMESTAMP — compare as DATE
        channel = bq_write.table_fqn("channel")
        sql = f"""
            SELECT c.channel_id, c.last_video_fetch_dt
            FROM `{channel}` AS c
            WHERE c.status = 1
              AND (c.last_video_fetch_dt IS NULL
                   OR DATE(c.last_video_fetch_dt) < @date_to)
              AND c.priority <= @priority
        """
        params: dict = {"date_to": date_to, "priority": priority}
        if category_id is not None:
            sql += " AND c.category_id = @category_id"
            params["category_id"] = category_id
        sql += " ORDER BY c.last_video_fetch_dt DESC LIMIT 1000"
        rows = bq_write.query_rows(sql, params)
        logger.info(f"BQ get_channels_to_fetch_videos: {len(rows)}")
        return rows

    @classmethod
    async def get_ids_wo_video(
        cls,
        report_period: Period,
        category_id: int | None = None,
    ) -> list[str]:
        channel = bq_write.table_fqn("channel")
        video = bq_write.table_fqn("video")
        sql = f"""
            SELECT c.channel_id
            FROM `{channel}` AS c
            LEFT JOIN `{video}` AS v
              ON v.channel_id = c.channel_id
             AND v.published_at_period = @report_period
            WHERE c.status = 1 AND v.id IS NULL
        """
        params: dict = {"report_period": report_period}
        if category_id is not None:
            sql += " AND c.category_id = @category_id"
            params["category_id"] = category_id
        rows = bq_write.query_rows(sql, params)
        return [r["channel_id"] for r in rows]


class ChannelStatBqDAO:
    table = "channel_stat"
    keys = ["channel_id", "report_period"]

    @classmethod
    async def add_bulk(cls, data: list[dict]) -> list | bool:
        if not data:
            return []
        n = bq_write.merge_rows(cls.table, data, cls.keys)
        return [{"ok": True}] * n if n else []

    @classmethod
    async def get_ids_wo_stat(
        cls,
        report_period: Period,
        category_id: int | None = None,
    ) -> list[str]:
        channel = bq_write.table_fqn("channel")
        channel_stat = bq_write.table_fqn("channel_stat")
        sql = f"""
            SELECT DISTINCT c.channel_id
            FROM `{channel}` AS c
            LEFT JOIN `{channel_stat}` AS cs
              ON c.channel_id = cs.channel_id
             AND cs.report_period = @report_period
            WHERE cs.id IS NULL AND c.status = 1
        """
        params: dict = {"report_period": report_period}
        if category_id is not None:
            sql += " AND c.category_id = @category_id"
            params["category_id"] = category_id
        rows = bq_write.query_rows(sql, params)
        ids = [r["channel_id"] for r in rows]
        logger.info(f"BQ get_ids_wo_stat channels: {len(ids)}")
        return ids
