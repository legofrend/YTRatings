"""Count playlist_shorts for world cat 19 vs last_shorts_fetch_dt."""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.database import async_session_maker


async def main() -> None:
    async with async_session_maker() as s:
        r = (
            await s.execute(
                text(
                    """
                    SELECT
                      count(*) FILTER (WHERE last_shorts_fetch_dt IS NOT NULL) AS marked,
                      count(*) FILTER (WHERE last_shorts_fetch_dt IS NULL) AS unmarked,
                      count(*) AS channels
                    FROM channel
                    WHERE category_id = 19 AND status = 1
                    """
                )
            )
        ).mappings().one()
        print("channels", dict(r))

        r2 = (
            await s.execute(
                text(
                    """
                    SELECT
                      count(*) AS short_rows,
                      count(DISTINCT ps.channel_id) AS channels_with_shorts
                    FROM playlist_shorts ps
                    JOIN channel c ON c.channel_id = ps.channel_id
                    WHERE c.category_id = 19
                    """
                )
            )
        ).mappings().one()
        print("playlist_shorts", dict(r2))

        # channels marked but zero shorts rows (empty UUSH ok)
        r3 = (
            await s.execute(
                text(
                    """
                    SELECT c.channel_id, c.custom_url, c.last_shorts_fetch_dt,
                           coalesce(n.cnt, 0) AS n_shorts
                    FROM channel c
                    LEFT JOIN (
                      SELECT channel_id, count(*) AS cnt
                      FROM playlist_shorts
                      GROUP BY channel_id
                    ) n ON n.channel_id = c.channel_id
                    WHERE c.category_id = 19 AND c.status = 1
                      AND c.last_shorts_fetch_dt IS NOT NULL
                    ORDER BY n_shorts DESC
                    LIMIT 10
                    """
                )
            )
        ).mappings().all()
        print("top marked by shorts count:")
        for row in r3:
            print(dict(row))


if __name__ == "__main__":
    asyncio.run(main())
