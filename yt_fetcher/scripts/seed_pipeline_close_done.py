"""One-shot: ensure pipeline_run + mark close steps done for previous month."""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.database import async_session_maker
from app.period import Period
from app.pipeline import ensure_schema, load_scenario

MSK = ZoneInfo("Europe/Moscow")


async def main() -> None:
    now = datetime.now(MSK)
    period = Period(now.month, now.year).next(-1)
    period_d = date(period.year, period.month, 1)
    scenario = load_scenario("close")
    await ensure_schema()

    async with async_session_maker() as session:
        for step in scenario.steps:
            await session.execute(
                text(
                    """
                    INSERT INTO pipeline_run
                        (scenario, period, step_ord, step_id, status, error, updated_at)
                    VALUES
                        (:scenario, :period, :step_ord, :step_id, 'done', NULL, now())
                    ON CONFLICT (scenario, period, step_id)
                    DO UPDATE SET
                        step_ord = EXCLUDED.step_ord,
                        status = 'done',
                        error = NULL,
                        updated_at = now()
                    """
                ),
                {
                    "scenario": scenario.id,
                    "period": period_d,
                    "step_ord": step.ord,
                    "step_id": step.id,
                },
            )
        await session.commit()
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, step_ord, step_id, status
                    FROM pipeline_run
                    WHERE scenario = :s AND period = :p
                    ORDER BY step_ord, id
                    """
                ),
                {"s": scenario.id, "p": period_d},
            )
        ).mappings().all()

    print(f"now_msk={now.isoformat()}")
    print(f"seeded scenario={scenario.id} period={period.strf('%p')} n={len(rows)}")
    for r in rows:
        print(f"  id={r['id']}  {r['step_ord']:2d}  {r['step_id']}: {r['status']}")


if __name__ == "__main__":
    asyncio.run(main())
