"""One-shot: time old ts_debug fill vs new ts_stat+top-N debug. Not for import."""
from __future__ import annotations

import asyncio
import time
from datetime import date

from sqlalchemy import text

from app.channel.models import ChannelStatus
from app.database import async_session_maker
from app.wordstat.dao import WordstatDAO, stop_lexemes_for_category

CAT = 1
PERIOD = date(2026, 10, 1)
TOP_N = 40


async def _count_titles(session) -> int:
    row = (
        await session.execute(
            text(
                f"""
                SELECT count(*)::int
                FROM video v
                JOIN channel c ON c.channel_id = v.channel_id
                WHERE c.category_id = :category_id
                  AND c.status = {ChannelStatus.ACTIVE}
                  AND v.published_at_period = :period
                  AND COALESCE(v.is_short, false) = false
                  AND v.title IS NOT NULL
                  AND length(btrim(v.title)) > 0
                """
            ),
            {"category_id": CAT, "period": PERIOD},
        )
    ).scalar()
    return int(row or 0)


async def _run_old(session, stops: list[str]) -> tuple[float, int]:
    t0 = time.perf_counter()
    result = await session.execute(
        text(
            f"""
            WITH titles AS (
                SELECT v.title
                FROM video v
                JOIN channel c ON c.channel_id = v.channel_id
                WHERE c.category_id = :category_id
                  AND c.status = {ChannelStatus.ACTIVE}
                  AND v.published_at_period = :period
                  AND COALESCE(v.is_short, false) = false
                  AND v.title IS NOT NULL
                  AND length(btrim(v.title)) > 0
            ),
            tok AS (
                SELECT
                    d.token AS surface,
                    d.lexemes[1] AS lexeme
                FROM titles t
                CROSS JOIN LATERAL ts_debug('russian', t.title) AS d
                WHERE d.lexemes IS NOT NULL
                  AND cardinality(d.lexemes) >= 1
                  AND d.alias IN (
                      'word', 'asciiword', 'hword',
                      'hword_part', 'numhword'
                  )
                  AND (
                      CAST(:stops AS text[]) IS NULL
                      OR cardinality(CAST(:stops AS text[])) = 0
                      OR NOT (d.lexemes[1] = ANY (CAST(:stops AS text[])))
                  )
            ),
            agg AS (
                SELECT
                    lexeme,
                    mode() WITHIN GROUP (ORDER BY surface) AS word,
                    count(*)::int AS freq
                FROM tok
                GROUP BY lexeme
                ORDER BY freq DESC
                LIMIT :top_n
            )
            SELECT lexeme, word, freq FROM agg
            """
        ),
        {
            "category_id": CAT,
            "period": PERIOD,
            "stops": stops,
            "top_n": TOP_N,
        },
    )
    rows = result.fetchall()
    return time.perf_counter() - t0, len(rows)


async def _run_new(session, stops: list[str]) -> tuple[float, int]:
    t0 = time.perf_counter()
    await session.execute(text("DROP TABLE IF EXISTS tmp_ws_titles"))
    await session.execute(
        text(
            f"""
            CREATE TEMP TABLE tmp_ws_titles AS
            SELECT v.title, v.title_tsv
            FROM video v
            JOIN channel c ON c.channel_id = v.channel_id
            WHERE c.category_id = :category_id
              AND c.status = {ChannelStatus.ACTIVE}
              AND v.published_at_period = :period
              AND COALESCE(v.is_short, false) = false
              AND v.title_tsv IS NOT NULL
              AND v.title IS NOT NULL
              AND length(btrim(v.title)) > 0
            """
        ),
        {"category_id": CAT, "period": PERIOD},
    )
    result = await session.execute(
        text(
            """
            WITH top AS (
                SELECT
                    s.word AS lexeme,
                    s.nentry::int AS freq
                FROM ts_stat('SELECT title_tsv FROM tmp_ws_titles') AS s
                WHERE CAST(:stops AS text[]) IS NULL
                   OR cardinality(CAST(:stops AS text[])) = 0
                   OR NOT (s.word = ANY (CAST(:stops AS text[])))
                ORDER BY s.nentry DESC
                LIMIT :top_n
            ),
            surf AS (
                SELECT
                    d.lexemes[1] AS lexeme,
                    d.token AS surface
                FROM tmp_ws_titles t
                CROSS JOIN LATERAL ts_debug('russian', t.title) AS d
                WHERE d.lexemes IS NOT NULL
                  AND cardinality(d.lexemes) >= 1
                  AND d.alias IN (
                      'word', 'asciiword', 'hword',
                      'hword_part', 'numhword'
                  )
                  AND d.lexemes[1] IN (SELECT lexeme FROM top)
            ),
            surf_mode AS (
                SELECT
                    lexeme,
                    mode() WITHIN GROUP (ORDER BY surface) AS word
                FROM surf
                GROUP BY lexeme
            ),
            picked AS (
                SELECT
                    t.lexeme,
                    t.freq,
                    COALESCE(m.word, t.lexeme) AS word
                FROM top t
                LEFT JOIN surf_mode m ON m.lexeme = t.lexeme
            )
            SELECT lexeme, word, freq FROM picked
            """
        ),
        {
            "category_id": CAT,
            "period": PERIOD,
            "stops": stops,
            "top_n": TOP_N,
        },
    )
    rows = result.fetchall()
    return time.perf_counter() - t0, len(rows)


async def main() -> None:
    stops = stop_lexemes_for_category(CAT)
    async with async_session_maker() as session:
        n_titles = await _count_titles(session)
        print(f"cat={CAT} period={PERIOD} titles={n_titles} top={TOP_N} stops={len(stops)}")

        # warmup / connect
        await session.execute(text("SELECT 1"))

        old_s, old_n = await _run_old(session, stops)
        print(f"OLD ts_debug-all: {old_s:.2f}s rows={old_n}")

        new_s, new_n = await _run_new(session, stops)
        print(f"NEW ts_stat+top debug: {new_s:.2f}s rows={new_n}")

        if old_s > 0:
            print(f"speedup: {old_s / new_s:.1f}x")

        # also time DAO.fill path once (writes)
        t0 = time.perf_counter()
        stats = await WordstatDAO.fill(
            category_ids=[CAT],
            period_from=PERIOD,
            top_n=TOP_N,
        )
        print(f"DAO.fill (write): {time.perf_counter() - t0:.2f}s {stats}")

        await session.rollback()


if __name__ == "__main__":
    asyncio.run(main())
