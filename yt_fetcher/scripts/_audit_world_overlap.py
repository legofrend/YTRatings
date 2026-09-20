"""Find world (cat 19) channels that belonged to another category before import.

Report stores rankings in JSONB `data` arrays; also try materialized `channel_report`.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import text

from app.database import async_session_maker

OUT = Path(__file__).resolve().parents[2] / "data" / "world_category_overlap.json"
WORLD_CAT = 19
IMPORT_DAY = "2026-09-19"


async def main() -> None:
    async with async_session_maker() as s:
        world = (
            await s.execute(
                text(
                    """
                    SELECT channel_id, channel_title, custom_url, priority, status,
                           created_at, updated_at
                    FROM channel
                    WHERE category_id = :cat
                    ORDER BY channel_title
                    """
                ),
                {"cat": WORLD_CAT},
            )
        ).mappings().all()
        world = [dict(r) for r in world]
        ids = [r["channel_id"] for r in world]

        preexisting = [
            r
            for r in world
            if r["created_at"] is not None
            and str(r["created_at"])[:10] < IMPORT_DAY
        ]
        new_today = [
            r
            for r in world
            if r["created_at"] is not None
            and str(r["created_at"])[:10] >= IMPORT_DAY
        ]

        # Latest other-category appearance from report JSONB
        hist = (
            await s.execute(
                text(
                    """
                    WITH elems AS (
                      SELECT r.category_id,
                             r.report_period,
                             (e->>'channel_id') AS channel_id,
                             NULLIF(e->>'rank', '')::int AS rank
                      FROM report r
                      CROSS JOIN LATERAL jsonb_array_elements(r.data) AS e
                      WHERE r.category_id <> :world_cat
                        AND jsonb_typeof(r.data) = 'array'
                        AND (e->>'channel_id') = ANY(:ids)
                    ),
                    latest AS (
                      SELECT DISTINCT ON (channel_id)
                             channel_id, category_id, report_period, rank
                      FROM elems
                      ORDER BY channel_id, report_period DESC
                    )
                    SELECT l.channel_id,
                           l.category_id AS old_category_id,
                           l.report_period,
                           l.rank,
                           c.name AS old_category_name,
                           ch.channel_title,
                           ch.custom_url,
                           ch.created_at,
                           ch.updated_at,
                           ch.priority,
                           ch.status
                    FROM latest l
                    LEFT JOIN category c ON c.id = l.category_id
                    LEFT JOIN channel ch ON ch.channel_id = l.channel_id
                    ORDER BY l.category_id, l.rank NULLS LAST
                    """
                ),
                {"ids": ids, "world_cat": WORLD_CAT},
            )
        ).mappings().all()
        hist = [dict(r) for r in hist]

        ever = (
            await s.execute(
                text(
                    """
                    SELECT (e->>'channel_id') AS channel_id,
                           r.category_id,
                           count(*) AS n,
                           max(r.report_period) AS last_period,
                           min(NULLIF(e->>'rank','')::int) AS best_rank
                    FROM report r
                    CROSS JOIN LATERAL jsonb_array_elements(r.data) AS e
                    WHERE r.category_id <> :world_cat
                      AND jsonb_typeof(r.data) = 'array'
                      AND (e->>'channel_id') = ANY(:ids)
                    GROUP BY (e->>'channel_id'), r.category_id
                    ORDER BY channel_id, category_id
                    """
                ),
                {"ids": ids, "world_cat": WORLD_CAT},
            )
        ).mappings().all()
        ever = [dict(r) for r in ever]

        # channel_report if present
        cr_exists = (
            await s.execute(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM information_schema.tables
                      WHERE table_schema='public' AND table_name='channel_report'
                    ) AS ok
                    """
                )
            )
        ).scalar()
        from_cr: list[dict] = []
        if cr_exists:
            from_cr = (
                await s.execute(
                    text(
                        """
                        WITH latest AS (
                          SELECT DISTINCT ON (channel_id)
                                 channel_id, category_id, report_period, rank
                          FROM channel_report
                          WHERE channel_id = ANY(:ids)
                            AND category_id <> :world_cat
                          ORDER BY channel_id, report_period DESC
                        )
                        SELECT l.*, c.name AS old_category_name,
                               ch.channel_title, ch.custom_url
                        FROM latest l
                        LEFT JOIN category c ON c.id = l.category_id
                        LEFT JOIN channel ch ON ch.channel_id = l.channel_id
                        ORDER BY l.category_id, l.rank NULLS LAST
                        """
                    ),
                    {"ids": ids, "world_cat": WORLD_CAT},
                )
            ).mappings().all()
            from_cr = [dict(r) for r in from_cr]

        # Preexisting world rows with NO history in other cats (edge case)
        hist_ids = {r["channel_id"] for r in hist}
        preexisting_no_hist = [
            r for r in preexisting if r["channel_id"] not in hist_ids
        ]

        def ser(rows: list[dict]) -> list[dict]:
            out = []
            for r in rows:
                d = dict(r)
                for k, v in list(d.items()):
                    if v is not None and k in (
                        "report_period",
                        "created_at",
                        "updated_at",
                        "last_period",
                    ):
                        d[k] = str(v)
                out.append(d)
            return out

        payload = {
            "world_total": len(world),
            "created_before_import_day": len(preexisting),
            "created_on_or_after_import_day": len(new_today),
            "found_in_report_other_cats": len(hist),
            "found_in_channel_report_other_cats": len(from_cr),
            "preexisting_without_report_history": len(preexisting_no_hist),
            "preexisting": ser(preexisting),
            "recoverable_from_report": ser(hist),
            "recoverable_from_channel_report": ser(from_cr),
            "ever_other_cat_rows": ser(ever),
            "preexisting_no_hist": ser(preexisting_no_hist),
        }
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        summary = {
            k: payload[k]
            for k in payload
            if k
            not in (
                "preexisting",
                "recoverable_from_report",
                "recoverable_from_channel_report",
                "ever_other_cat_rows",
                "preexisting_no_hist",
            )
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"wrote {OUT}")
        def _safe(s: object) -> str:
            return str(s).encode("cp1251", "replace").decode("cp1251")

        print("--- preexisting (moved) ---")
        for r in preexisting:
            print(
                _safe(
                    f"  {r.get('custom_url')} | {r.get('channel_title')} | "
                    f"created={r.get('created_at')} updated={r.get('updated_at')}"
                )
            )
        print("--- recoverable (latest other cat from report) ---")
        for r in hist:
            print(
                _safe(
                    f"{r['old_category_id']:>3} {r.get('old_category_name')} | "
                    f"rank={r.get('rank')} period={r.get('report_period')} | "
                    f"{r.get('custom_url')} | {r.get('channel_title')}"
                )
            )


if __name__ == "__main__":
    asyncio.run(main())
