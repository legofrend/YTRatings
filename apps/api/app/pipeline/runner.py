"""Orchestrate close (YAML) + harvest (inline) for `python -m app.main auto`."""

from __future__ import annotations

from calendar import monthrange
from datetime import UTC, datetime
from typing import Any, Literal

from app import ntfy
from app.api import yt_quota
from app.logger import logger
from app.period import Period
from app.pipeline import (
    Scenario,
    ScenarioStep,
    ensure_run_rows,
    ensure_schema,
    has_incomplete,
    in_calendar_window,
    load_scenario,
    next_pending_step,
    resolve_period,
    set_step_status,
)

_QUOTA_STOPS = frozenset({"quota_warn", "quota_exceeded"})
RunStatus = Literal["done", "paused", "skipped"]


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _step_priority_kwargs(params: dict[str, Any]) -> dict[str, Any]:
    """Map YAML priority_lte / priority_gt → cmd kwargs."""
    out: dict[str, Any] = {}
    if "priority_lte" in params:
        out["priority"] = params["priority_lte"]
    if "priority_gt" in params:
        out["priority_gt"] = params["priority_gt"]
        if "priority_lte" not in params:
            out["priority"] = None
    return out


def _step_category_ids(
    params: dict[str, Any],
    all_category_ids: list[int],
) -> list[int]:
    """Per-step cats / cats_exclude over the auto-resolved active list."""
    cats = params.get("cats")
    exclude = params.get("cats_exclude")
    if cats is not None:
        if isinstance(cats, int):
            ids = [cats]
        else:
            ids = [int(c) for c in cats]
        allowed = set(all_category_ids)
        return [i for i in ids if i in allowed] or ids
    if exclude is not None:
        if isinstance(exclude, int):
            ex = {exclude}
        else:
            ex = {int(c) for c in exclude}
        return [i for i in all_category_ids if i not in ex]
    return list(all_category_ids)


async def _dispatch_cmd(
    name: str,
    *,
    period: Period,
    category_ids: list[int],
    step: ScenarioStep,
) -> str | None:
    """Run one CLI command. Returns quota stop reason or None."""
    from app.main import (
        cmd_build_rating,
        cmd_denorm,
        cmd_fetch_channel_stats,
        cmd_fetch_video_stats,
        cmd_fetch_videos,
    )

    p = step.params
    cats = _step_category_ids(p, category_ids)
    prio = _step_priority_kwargs(p)
    # Explicit null priority_lte → all priorities; omit → default 100
    priority = prio["priority"] if "priority" in prio else 100
    # YAML: prefer skip_duration; accept legacy skip_detail as alias in params only
    skip_duration = bool(p.get("skip_duration", p.get("skip_detail", False)))

    if name == "fetch-channel-stats":
        await cmd_fetch_channel_stats(period, cats, force=bool(p.get("force")))
    elif name == "fetch-video-stats":
        await cmd_fetch_video_stats(period, cats, force=bool(p.get("force")))
    elif name == "fetch-videos":
        return await cmd_fetch_videos(
            period,
            cats,
            priority=priority,
            priority_gt=prio.get("priority_gt"),
            skip_shorts=bool(p.get("skip_shorts", False)),
            skip_duration=skip_duration,
            skip_apply=bool(p.get("skip_apply", False)),
            only_duration=bool(p.get("only_duration", False)),
            only_shorts=bool(p.get("only_shorts", False)),
            only_missing=bool(p.get("only_missing", False)),
        )
    elif name == "denorm":
        await cmd_denorm(
            period,
            None,
            batch_size=int(p.get("batch_size", 10_000)),
        )
    elif name == "build-rating":
        await cmd_build_rating(period, None)
    else:
        raise SystemExit(f"auto: unsupported cmd {name!r} in step {step.id}")
    return None


def _quota_stop_after_cmd() -> str | None:
    import app.api.ytapi as yt

    if yt.IS_QUOTA_EXCEEDED:
        return "quota_exceeded"
    if yt_quota.is_at_warn():
        return "quota_warn"
    return None


async def _run_close_steps(
    scenario: Scenario,
    period: Period,
    category_ids: list[int],
) -> RunStatus:
    """Close only: resume via pipeline_run until done or soft-stop."""
    await ensure_run_rows(scenario, period)
    ntfy.info(
        f"auto close start period={period.strf('%p')}",
        title="ytr · auto close",
    )

    while True:
        step = await next_pending_step(scenario, period)
        if step is None:
            logger.info(f"auto: close DONE period={period.strf('%p')}")
            ntfy.info(
                f"auto close DONE period={period.strf('%p')}",
                title="ytr · auto close done",
            )
            return "done"

        logger.info(
            f"auto: === close / {step.id} cmds={step.cmds} "
            f"params={step.params} ==="
        )
        await set_step_status(scenario.id, period, step.id, "running")
        try:
            stop: str | None = None
            for cmd_name in step.cmds:
                logger.info(f"auto: run {cmd_name}")
                stop = await _dispatch_cmd(
                    cmd_name,
                    period=period,
                    category_ids=category_ids,
                    step=step,
                )
                if stop in _QUOTA_STOPS:
                    break
                stop = _quota_stop_after_cmd()
                if stop:
                    break
                yt_quota.flush(reason=f"auto-after-{cmd_name}")
                logger.info(yt_quota.format_status())

            if stop in _QUOTA_STOPS:
                await set_step_status(
                    scenario.id, period, step.id, "pending", error=stop
                )
                logger.warning(
                    f"auto: soft-stop at close/{step.id} reason={stop}; "
                    "exit (resume next cron)"
                )
                ntfy.info(
                    f"auto soft-stop {stop} at close/{step.id} "
                    f"period={period.strf('%p')}",
                    title="ytr · auto pause",
                )
                return "paused"

            await set_step_status(scenario.id, period, step.id, "done")
            logger.info(f"auto: close/{step.id} done")
        except BaseException as e:
            await set_step_status(
                scenario.id, period, step.id, "failed", error=str(e)[:500]
            )
            ntfy.error(
                f"auto FAILED close/{step.id}: {e}",
                title="ytr · auto FAILED",
            )
            raise


async def _run_close(
    *,
    category_ids: list[int],
    force: bool,
    now: datetime,
) -> RunStatus:
    scenario = load_scenario("close")
    period = resolve_period(scenario, now)
    in_window = in_calendar_window(scenario, now)
    incomplete = await has_incomplete(scenario.id, period)

    # auto: only days 1..N. After that holes are manual CLI / --force.
    if not in_window and not force:
        logger.info(
            f"auto: skip close (outside day window"
            f"{', unfinished left for manual' if incomplete else ''}) "
            f"period={period.strf('%p')} when={scenario.when}"
        )
        return "skipped"

    if force and not in_window:
        logger.warning(
            f"auto: --force close outside window "
            f"period={period.strf('%p')} incomplete={incomplete}"
        )

    logger.info(
        f"auto: close period={period.strf('%p')} "
        f"in_window={in_window} incomplete={incomplete} force={force}"
    )
    return await _run_close_steps(scenario, period, category_ids)


def _harvest_priority(now: datetime) -> int | None | Literal[False]:
    """False = idle. None = all priorities. int = priority ceiling.

    Calendar is UTC. Near month-end (last 3 days) prefer top channels first;
    last day after 08:00 UTC → idle (close starts 00:01 UTC on the 1st).
    """
    last = monthrange(now.year, now.month)[1]
    if now.day == last and (now.hour, now.minute, now.second) >= (8, 0, 0):
        return False
    if now.day >= last - 2:
        return 100
    return None


async def _run_harvest(
    *,
    period: Period,
    category_ids: list[int],
    priority: int | None,
) -> RunStatus:
    """Full fetch-videos chain (duration + shorts + is_short). Resume via DB cursors."""
    from app.main import cmd_fetch_videos

    label = "harvest_top" if priority is not None else "harvest_all"
    logger.info(
        f"auto: {label} period={period.strf('%p')} priority={priority}"
    )
    ntfy.info(
        f"auto {label} start period={period.strf('%p')}",
        title=f"ytr · auto {label}",
    )

    stop = await cmd_fetch_videos(period, category_ids, priority=priority)
    if stop not in _QUOTA_STOPS:
        stop = _quota_stop_after_cmd()
    yt_quota.flush(reason=f"auto-after-{label}")
    logger.info(yt_quota.format_status())

    if stop in _QUOTA_STOPS:
        logger.warning(f"auto: soft-stop at {label} reason={stop}")
        ntfy.info(
            f"auto soft-stop {stop} at {label} period={period.strf('%p')}",
            title="ytr · auto pause",
        )
        return "paused"

    logger.info(f"auto: {label} DONE period={period.strf('%p')}")
    ntfy.info(
        f"auto {label} DONE period={period.strf('%p')}",
        title=f"ytr · auto {label} done",
    )
    return "done"


async def run_auto(
    *,
    category_ids: list[int],
    force: bool = False,
) -> None:
    """
    Mutually exclusive phases (never chain close → harvest in one run).
    All calendar decisions use UTC (month boundary = 00:00 UTC).

    1) days 1..5 UTC (or --force): close only — YAML + pipeline_run
    2) outside close window:
       - last day >= 08:00 UTC — idle
       - last 3 days (before idle) — harvest priority<=100
       - else — harvest all priorities

    Unfinished close after day 5 is not auto-resumed; use manual commands.
    No sleeping for quota; timer re-invokes later.
    """
    now = _now_utc()
    await ensure_schema()
    logger.info(f"auto: now={now.isoformat()} force={force}")

    close_status = await _run_close(
        category_ids=category_ids, force=force, now=now
    )
    # Close stage (in window / --force): never fall through to harvest.
    if close_status != "skipped":
        return

    priority = _harvest_priority(now)
    if priority is False:
        logger.info(
            "auto: idle — last day of month after 08:00 UTC; "
            "wait for next month"
        )
        return

    period = Period(now.month, now.year)
    await _run_harvest(
        period=period, category_ids=category_ids, priority=priority
    )


async def run_close_auto(
    *,
    category_ids: list[int],
    force: bool = False,
) -> None:
    await run_auto(category_ids=category_ids, force=force)
