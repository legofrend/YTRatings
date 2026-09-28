"""Quick probe: how many channels still have is_short NULL."""
from __future__ import annotations

import asyncio
import time

import asyncpg

from app.channel.video.dao import VideoDAO
from app.config import settings


async def main() -> None:
    print(f"DB {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                user=settings.DB_USER,
                password=settings.DB_PASS,
                database=settings.DB_NAME,
            ),
            timeout=15,
        )
    except Exception as e:
        print(f"connect FAIL: {type(e).__name__}: {e}")
        return

    try:
        n = await asyncio.wait_for(conn.fetchval("SELECT 1"), timeout=10)
        print(f"ping={n}")
        t0 = time.time()
        eligible = await asyncio.wait_for(
            conn.fetchval(
                "SELECT count(*) FROM channel "
                "WHERE status = 1 AND last_shorts_fetch_dt IS NOT NULL"
            ),
            timeout=60,
        )
        print(f"eligible_channels={eligible} in {time.time() - t0:.1f}s")
        t0 = time.time()
        # Approximate via channel EXISTS — same idea as list filter
        with_null = await asyncio.wait_for(
            conn.fetchval(
                """
                SELECT count(*) FROM channel c
                WHERE c.status = 1
                  AND c.last_shorts_fetch_dt IS NOT NULL
                  AND EXISTS (
                    SELECT 1 FROM video v
                    WHERE v.channel_id = c.channel_id AND v.is_short IS NULL
                  )
                """
            ),
            timeout=300,
        )
        print(f"eligible_with_null={with_null} in {time.time() - t0:.1f}s")
    except Exception as e:
        print(f"query FAIL: {type(e).__name__}: {e}")
    finally:
        await conn.close()

    t0 = time.time()
    ch = await VideoDAO.list_channels_for_is_short(only_null=True)
    print(f"DAO list only_null={len(ch)} in {time.time() - t0:.1f}s")
    t0 = time.time()
    ch8 = await VideoDAO.list_channels_for_is_short(
        category_ids=[8], only_null=True
    )
    print(f"DAO cat8 only_null={len(ch8)} in {time.time() - t0:.1f}s sample={ch8[:5]}")


if __name__ == "__main__":
    asyncio.run(main())
