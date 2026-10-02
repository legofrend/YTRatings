"""Probe report.data shape + world channel counts."""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import text

from app.database import async_session_maker


async def main() -> None:
    async with async_session_maker() as s:
        rows = (
            await s.execute(
                text(
                    """
                    SELECT category_id, report_period,
                           jsonb_typeof(data) AS t,
                           CASE
                             WHEN jsonb_typeof(data)='array'
                               THEN jsonb_array_length(data)
                             WHEN jsonb_typeof(data)='object'
                               THEN (SELECT count(*)::int FROM jsonb_object_keys(data))
                           END AS n,
                           left(data::text, 500) AS sample
                    FROM report
                    WHERE category_id <> 19
                    ORDER BY report_period DESC
                    LIMIT 3
                    """
                )
            )
        ).mappings().all()
        for row in rows:
            print(json.dumps({k: (str(v) if k == "report_period" else v) for k, v in dict(row).items()}, ensure_ascii=False))

        w = (
            await s.execute(
                text(
                    """
                    SELECT count(*) AS total,
                           count(*) FILTER (WHERE created_at::date < DATE '2026-09-19') AS before,
                           count(*) FILTER (WHERE created_at::date >= DATE '2026-09-19') AS today
                    FROM channel WHERE category_id = 19
                    """
                )
            )
        ).mappings().one()
        print("world counts", dict(w))

        # sample keys of first array element
        sample = (
            await s.execute(
                text(
                    """
                    SELECT category_id, report_period,
                           jsonb_object_keys(data->0) AS k
                    FROM report
                    WHERE jsonb_typeof(data)='array' AND jsonb_array_length(data)>0
                      AND category_id <> 19
                    ORDER BY report_period DESC
                    LIMIT 30
                    """
                )
            )
        ).mappings().all()
        print("keys sample:", [dict(r) for r in sample])


if __name__ == "__main__":
    asyncio.run(main())
