"""Restore channels moved to world (19) back to their previous category; fix priorities if needed."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import text

from app.database import async_session_maker

OVERLAP = Path(__file__).resolve().parents[2] / "data" / "world_category_overlap.json"


async def main() -> None:
    data = json.loads(OVERLAP.read_text(encoding="utf-8"))
    rows = data["recoverable_from_report"]
    if not rows:
        print("nothing to restore")
        return

    async with async_session_maker() as s:
        # peer priorities in old cats (for sanity)
        for r in rows:
            peer = (
                await s.execute(
                    text(
                        """
                        SELECT priority, count(*) AS n
                        FROM channel
                        WHERE category_id = :cat AND status = 1 AND priority <= 100
                        GROUP BY priority
                        ORDER BY priority
                        LIMIT 15
                        """
                    ),
                    {"cat": r["old_category_id"]},
                )
            ).mappings().all()
            print(
                f"peer priorities cat {r['old_category_id']}: "
                + ", ".join(f"p={p['priority']}:{p['n']}" for p in peer)
            )

        for r in rows:
            await s.execute(
                text(
                    """
                    UPDATE channel
                    SET category_id = :cat,
                        updated_at = now()
                    WHERE channel_id = :cid
                      AND category_id = 19
                    """
                ),
                {"cat": r["old_category_id"], "cid": r["channel_id"]},
            )
            print(
                f"RESTORE {r['custom_url']} -> cat {r['old_category_id']} "
                f"({r['old_category_name']})"
            )

        # verify
        ids = [r["channel_id"] for r in rows]
        check = (
            await s.execute(
                text(
                    """
                    SELECT channel_id, custom_url, category_id, priority, status
                    FROM channel WHERE channel_id = ANY(:ids)
                    ORDER BY custom_url
                    """
                ),
                {"ids": ids},
            )
        ).mappings().all()
        await s.commit()
        print("after:", [dict(c) for c in check])

        world_left = (
            await s.execute(
                text("SELECT count(*) FROM channel WHERE category_id = 19")
            )
        ).scalar()
        print(f"world remaining: {world_left}")


if __name__ == "__main__":
    asyncio.run(main())
