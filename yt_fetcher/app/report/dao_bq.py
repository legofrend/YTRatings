"""
BigQuery report build + sync helpers.

1) build_in_bq  — MERGE nested JSON into BQ `report` via sql/build_report_bq.sql
2) sync_from_bq — copy selected (period, category_id) rows BQ → Postgres `report`
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.bq import write as bq_write
from app.bq.create_tables import bq_target
from app.logger import logger
from app.period import Period

_SQL_PATH = Path(__file__).resolve().parents[2] / "sql" / "build_report_bq.sql"


def _as_periods(report_periods: Period | date | str | list) -> list[date]:
    if not isinstance(report_periods, list):
        report_periods = [report_periods]
    out: list[date] = []
    for p in report_periods:
        if isinstance(p, str):
            out.append(Period.parse(p))
        elif isinstance(p, Period):
            out.append(p)
        elif isinstance(p, date):
            out.append(Period(p.month, p.year))
        else:
            raise TypeError(f"unsupported report_period: {type(p)}")
    return out


def _as_category_ids(category_ids: int | list[int]) -> list[int]:
    if isinstance(category_ids, int):
        return [category_ids]
    return list(category_ids)


def _load_build_sql() -> str:
    project, dataset = bq_target()
    return (
        _SQL_PATH.read_text(encoding="utf-8")
        .replace("{project}", project)
        .replace("{dataset}", dataset)
    )


def _parse_data(raw) -> list | dict:
    if raw is None:
        return []
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    # google.cloud.bigquery row JSON / DbApiType
    if hasattr(raw, "to_py"):
        return raw.to_py()
    return json.loads(str(raw))


class ReportBqDAO:
    table = "report"

    @classmethod
    async def build_in_bq(
        cls,
        report_period: Period | date | str,
        category_ids: int | list[int],
        *,
        top_n: int = 5,
        rank_limit: int = 100,
    ) -> bool:
        periods = _as_periods(report_period)
        cats = _as_category_ids(category_ids)
        if not cats:
            logger.warning("build_in_bq: empty category_ids")
            return False

        sql = _load_build_sql()
        for period in periods:
            logger.info(
                f"BQ build report period={period} categories={cats} "
                f"top_n={top_n} rank_limit={rank_limit}"
            )
            bq_write.run_sql(
                sql,
                {
                    "report_period": period,
                    "category_ids": cats,
                    "top_n": top_n,
                    "rank_limit": rank_limit,
                },
            )
        return True

    @classmethod
    async def fetch_reports(
        cls,
        report_periods: Period | date | str | list,
        category_ids: int | list[int],
    ) -> list[dict]:
        periods = _as_periods(report_periods)
        cats = _as_category_ids(category_ids)
        report = bq_write.table_fqn(cls.table)
        # BQ has no DATE array param helper for mixed Period — pass as strings
        sql = f"""
            SELECT report_period, category_id, data
            FROM `{report}`
            WHERE report_period IN UNNEST(@report_periods)
              AND category_id IN UNNEST(@category_ids)
            ORDER BY report_period, category_id
        """
        rows = bq_write.query_rows(
            sql,
            {
                "report_periods": [p.isoformat() for p in periods],
                "category_ids": cats,
            },
        )
        out = []
        for r in rows:
            out.append(
                {
                    "report_period": r["report_period"],
                    "category_id": r["category_id"],
                    "data": _parse_data(r["data"]),
                }
            )
        return out

    @classmethod
    async def sync_from_bq(
        cls,
        report_periods: Period | date | str | list,
        category_ids: int | list[int],
    ) -> int:
        """Pull BQ report rows and upsert into Postgres report."""
        from app.report.dao import ReportDAO

        rows = await cls.fetch_reports(report_periods, category_ids)
        if not rows:
            logger.warning("sync_from_bq: no rows in BQ for given filters")
            return 0

        n = 0
        for row in rows:
            res = await ReportDAO.add_or_update(
                {
                    "report_period": row["report_period"],
                    "category_id": row["category_id"],
                    "data": row["data"],
                },
                do_nothing=False,
            )
            if res:
                n += 1
                logger.info(
                    f"synced report {row['report_period']} "
                    f"category={row['category_id']}"
                )
            else:
                logger.error(
                    f"failed sync report {row['report_period']} "
                    f"category={row['category_id']}"
                )
        return n
