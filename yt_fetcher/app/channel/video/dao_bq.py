"""
BigQuery writers for video / video_stat (raw ingest).

Used when settings.RAW_DB == "bigquery". Postgres VideoDAO stays default.
"""

from __future__ import annotations

from datetime import timedelta

from app.bq import write as bq_write
from app.logger import logger
from app.period import Period


class VideoBqDAO:
    table = "video"
    keys = ["video_id"]

    @classmethod
    async def get_ids(cls, filters: dict | None = None) -> list[str]:
        filters = filters or {}
        video = bq_write.table_fqn(cls.table)
        clauses: list[str] = []
        params: dict = {}
        for i, (k, v) in enumerate(filters.items()):
            if v is None:
                clauses.append(f"`{k}` IS NULL")
            else:
                pname = f"p{i}"
                clauses.append(f"`{k}` = @{pname}")
                params[pname] = v
        sql = f"SELECT video_id FROM `{video}`"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        rows = bq_write.query_rows(sql, params or None)
        return [r["video_id"] for r in rows]

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
    async def update_bulk(cls, data: list[dict], identifier: str = "video_id") -> bool:
        if not data:
            return True
        bq_write.merge_rows(cls.table, data, [identifier], update_on_match=True)
        return True

    @classmethod
    async def get_ids_missing_duration(cls) -> list[str]:
        video = bq_write.table_fqn("video")
        sql = f"""
            SELECT video_id
            FROM `{video}`
            WHERE duration IS NULL AND status = 1
        """
        rows = bq_write.query_rows(sql)
        return [r["video_id"] for r in rows]

    @classmethod
    async def get_ids_wo_is_short(cls, category_id: int | None = None) -> list[dict]:
        video = bq_write.table_fqn("video")
        sql = f"""
            SELECT v.video_id
            FROM `{video}` AS v
            WHERE v.status = 1
              AND v.is_short IS NULL
              AND v.published_at_period >= '2025-05-01'
        """
        # category filter needs channel join — kept simple like PG (PG version had a bug with c.)
        rows = bq_write.query_rows(sql)
        return [{"video_id": r["video_id"], "is_short": None} for r in rows]


class VideoStatBqDAO:
    table = "video_stat"
    keys = ["video_id", "report_period"]

    @classmethod
    def _enrich(cls, data: list[dict]) -> list[dict]:
        out = []
        for row in data:
            item = dict(row)
            rp = item.get("report_period")
            if rp is not None and item.get("prev_period") is None:
                if hasattr(rp, "next"):
                    item["prev_period"] = rp.next(-1)
                else:
                    item["prev_period"] = (
                        rp.replace(day=1) - timedelta(days=1)
                    ).replace(day=1)
            out.append(item)
        return out

    @classmethod
    async def add_bulk(cls, data: list[dict]) -> list | bool:
        if not data:
            return []
        n = bq_write.merge_rows(cls.table, cls._enrich(data), cls.keys)
        return [{"ok": True}] * n if n else []

    @classmethod
    async def get_ids_for_stat(
        cls,
        report_period: Period,
        published_at_period: Period | None = None,
        category_id: int | None = None,
    ) -> list[str]:
        if not published_at_period:
            published_at_period = report_period.next(-3)

        video = bq_write.table_fqn("video")
        channel = bq_write.table_fqn("channel")
        sql = f"""
            SELECT DISTINCT v.video_id
            FROM `{video}` AS v
            LEFT JOIN `{channel}` AS c ON c.channel_id = v.channel_id
            WHERE v.published_at_period >= @published_at_period
              AND c.status = 1 AND v.status = 1
        """
        params: dict = {"published_at_period": published_at_period}
        if category_id is not None:
            sql += " AND c.category_id = @category_id"
            params["category_id"] = category_id
        rows = bq_write.query_rows(sql, params)
        ids = [r["video_id"] for r in rows]
        logger.info(f"BQ get_ids_for_stat videos: {len(ids)}")
        return ids

    @classmethod
    async def get_ids_wo_stat(
        cls,
        report_period: Period,
        published_at_period: Period | None = None,
        category_id: int | None = None,
    ) -> list[str]:
        if not published_at_period:
            published_at_period = report_period.next(-3)

        video = bq_write.table_fqn("video")
        channel = bq_write.table_fqn("channel")
        video_stat = bq_write.table_fqn("video_stat")
        sql = f"""
            SELECT DISTINCT v.video_id
            FROM `{video}` AS v
            LEFT JOIN `{channel}` AS c ON c.channel_id = v.channel_id
            LEFT JOIN `{video_stat}` AS vs
              ON v.video_id = vs.video_id AND vs.report_period = @report_period
            WHERE vs.id IS NULL
              AND v.published_at_period >= @published_at_period
              AND c.status = 1 AND v.status = 1
        """
        params: dict = {
            "report_period": report_period,
            "published_at_period": published_at_period,
        }
        if category_id is not None:
            sql += " AND c.category_id = @category_id"
            params["category_id"] = category_id
        rows = bq_write.query_rows(sql, params)
        ids = [r["video_id"] for r in rows]
        logger.info(f"BQ get_ids_wo_stat videos: {len(ids)}")
        return ids
