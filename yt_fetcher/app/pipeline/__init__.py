"""Scenario loader + runner for `python -m app.main auto`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import text

from app.database import async_session_maker
from app.period import Period

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"

# Fresh installs
_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_run (
    id         bigserial   PRIMARY KEY,
    scenario   text        NOT NULL,
    period     date        NOT NULL,
    step_ord   int         NOT NULL,
    step_id    text        NOT NULL,
    status     text        NOT NULL DEFAULT 'pending',
    error      text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (scenario, period, step_id)
)
"""

# Existing installs (created before id/step_ord)
_MIGRATE_SQL = [
    "ALTER TABLE pipeline_run ADD COLUMN IF NOT EXISTS id bigserial",
    "ALTER TABLE pipeline_run ADD COLUMN IF NOT EXISTS step_ord int",
]


@dataclass
class ScenarioStep:
    id: str
    ord: int  # 1-based position in YAML
    cmds: list[str]
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scenario:
    id: str
    when: dict[str, Any]
    period_mode: str
    steps: list[ScenarioStep]
    path: Path


def load_scenario(name: str = "close") -> Scenario:
    path = SCENARIOS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"scenario not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"scenario root must be mapping: {path}")

    steps: list[ScenarioStep] = []
    for i, item in enumerate(raw.get("steps") or [], start=1):
        if not isinstance(item, dict) or not item.get("id"):
            raise ValueError(f"step[{i}] needs id: {path}")
        cmd = item.get("cmd")
        if isinstance(cmd, str):
            cmds = [cmd]
        elif isinstance(cmd, list) and cmd:
            cmds = [str(c) for c in cmd]
        else:
            raise ValueError(f"step {item.get('id')}: cmd required")
        params = {
            k: v
            for k, v in item.items()
            if k not in ("id", "cmd")
        }
        steps.append(
            ScenarioStep(
                id=str(item["id"]),
                ord=i,
                cmds=cmds,
                params=params,
            )
        )

    return Scenario(
        id=str(raw.get("id") or name),
        when=dict(raw.get("when") or {}),
        period_mode=str(raw.get("period") or "previous_month"),
        steps=steps,
        path=path,
    )


def resolve_period(scenario: Scenario, now: datetime | None = None) -> Period:
    tz_name = scenario.when.get("timezone") or "Europe/Moscow"
    now = now or datetime.now(ZoneInfo(tz_name))
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo(tz_name))
    else:
        now = now.astimezone(ZoneInfo(tz_name))
    cur = Period(now.month, now.year)
    mode = scenario.period_mode
    if mode == "previous_month":
        return cur.next(-1)
    if mode == "current_month":
        return cur
    return Period.parse(mode)


def in_calendar_window(scenario: Scenario, now: datetime | None = None) -> bool:
    tz_name = scenario.when.get("timezone") or "Europe/Moscow"
    now = now or datetime.now(ZoneInfo(tz_name))
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo(tz_name))
    else:
        now = now.astimezone(ZoneInfo(tz_name))
    day_lte = scenario.when.get("day_of_month_lte")
    if day_lte is None:
        return True
    return now.day <= int(day_lte)


async def ensure_schema() -> None:
    async with async_session_maker() as session:
        await session.execute(text(_CREATE_SQL))
        for stmt in _MIGRATE_SQL:
            await session.execute(text(stmt))
        await session.commit()


async def ensure_run_rows(scenario: Scenario, period: Period) -> None:
    """Insert missing step rows; always refresh step_ord from YAML order."""
    period_d = date(period.year, period.month, 1)
    async with async_session_maker() as session:
        for step in scenario.steps:
            await session.execute(
                text(
                    """
                    INSERT INTO pipeline_run
                        (scenario, period, step_ord, step_id, status)
                    VALUES
                        (:scenario, :period, :step_ord, :step_id, 'pending')
                    ON CONFLICT (scenario, period, step_id)
                    DO UPDATE SET step_ord = EXCLUDED.step_ord
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


async def has_incomplete(scenario_id: str, period: Period) -> bool:
    period_d = date(period.year, period.month, 1)
    async with async_session_maker() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT 1
                    FROM pipeline_run
                    WHERE scenario = :scenario
                      AND period = :period
                      AND status <> 'done'
                    LIMIT 1
                    """
                ),
                {"scenario": scenario_id, "period": period_d},
            )
        ).first()
        return row is not None


async def next_pending_step(
    scenario: Scenario, period: Period
) -> ScenarioStep | None:
    period_d = date(period.year, period.month, 1)
    async with async_session_maker() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT step_id, status
                    FROM pipeline_run
                    WHERE scenario = :scenario AND period = :period
                    ORDER BY step_ord NULLS LAST, step_id
                    """
                ),
                {"scenario": scenario.id, "period": period_d},
            )
        ).mappings().all()
    by_id = {r["step_id"]: r["status"] for r in rows}
    for step in scenario.steps:
        st = by_id.get(step.id, "pending")
        if st != "done":
            return step
    return None


async def set_step_status(
    scenario_id: str,
    period: Period,
    step_id: str,
    status: str,
    error: str | None = None,
) -> None:
    period_d = date(period.year, period.month, 1)
    async with async_session_maker() as session:
        await session.execute(
            text(
                """
                UPDATE pipeline_run
                SET status = :status,
                    error = :error,
                    updated_at = now()
                WHERE scenario = :scenario
                  AND period = :period
                  AND step_id = :step_id
                """
            ),
            {
                "scenario": scenario_id,
                "period": period_d,
                "step_id": step_id,
                "status": status,
                "error": error,
            },
        )
        await session.commit()
