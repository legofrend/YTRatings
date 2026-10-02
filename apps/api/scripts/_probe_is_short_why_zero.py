"""Why only_null channels still get set_true=0 set_false=0."""
from __future__ import annotations

import asyncio

import asyncpg

from app.channel.video.dao import VideoDAO
from app.config import settings


async def main() -> None:
    chs = await VideoDAO.list_channels_for_is_short(category_ids=[8], only_null=True)
    print("channels", chs)
    if not chs:
        return
    cid = chs[0]
    conn = await asyncpg.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASS,
        database=settings.DB_NAME,
    )
    try:
        c = await conn.fetchrow(
            "SELECT channel_id, last_shorts_fetch_dt FROM channel WHERE channel_id=$1",
            cid,
        )
        print("channel", dict(c))
        win = await conn.fetchrow(
            """
            SELECT MIN(published_at) AS win_from, COUNT(*) AS ps_n
            FROM playlist_shorts WHERE channel_id=$1
            """,
            cid,
        )
        print("playlist_shorts", dict(win))
        nulls = await conn.fetch(
            """
            SELECT video_id, published_at, status, is_short
            FROM video
            WHERE channel_id=$1 AND is_short IS NULL
            ORDER BY published_at DESC NULLS LAST
            LIMIT 15
            """,
            cid,
        )
        print(f"null videos sample ({len(nulls)} shown):")
        for r in nulls:
            print(" ", dict(r))

        # would set_true match any?
        n_true = await conn.fetchval(
            """
            SELECT count(*)
            FROM video v
            JOIN playlist_shorts ps ON v.video_id = ps.video_id
            JOIN channel c ON c.channel_id = ps.channel_id
            WHERE c.channel_id = $1
              AND c.last_shorts_fetch_dt IS NOT NULL
              AND ps.published_at < c.last_shorts_fetch_dt
              AND v.is_short IS NULL
            """,
            cid,
        )
        print("candidates set_true:", n_true)

        n_false = await conn.fetchval(
            """
            SELECT count(*)
            FROM video v
            JOIN channel c ON v.channel_id = c.channel_id
            JOIN (
                SELECT channel_id, MIN(published_at) AS win_from
                FROM playlist_shorts WHERE channel_id=$1
                GROUP BY channel_id
            ) w ON w.channel_id = c.channel_id
            WHERE c.channel_id = $1
              AND c.last_shorts_fetch_dt IS NOT NULL
              AND w.win_from IS NOT NULL
              AND v.published_at >= w.win_from
              AND v.published_at < c.last_shorts_fetch_dt
              AND v.status = 1
              AND v.is_short IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM playlist_shorts ps WHERE ps.video_id = v.video_id
              )
            """,
            cid,
        )
        print("candidates set_false:", n_false)

        # nulls outside window?
        n_out = await conn.fetchval(
            """
            SELECT count(*)
            FROM video v
            JOIN channel c ON v.channel_id = c.channel_id
            LEFT JOIN (
                SELECT channel_id, MIN(published_at) AS win_from
                FROM playlist_shorts WHERE channel_id=$1
                GROUP BY channel_id
            ) w ON w.channel_id = c.channel_id
            WHERE v.channel_id=$1 AND v.is_short IS NULL
              AND (
                w.win_from IS NULL
                OR v.published_at < w.win_from
                OR v.published_at >= c.last_shorts_fetch_dt
                OR c.last_shorts_fetch_dt IS NULL
              )
            """,
            cid,
        )
        n_null = await conn.fetchval(
            "SELECT count(*) FROM video WHERE channel_id=$1 AND is_short IS NULL",
            cid,
        )
        print(f"null_total={n_null} null_outside_window={n_out}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
