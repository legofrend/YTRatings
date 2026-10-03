"""Fill / type-backfill / read for wordstat (title lexeme freqs)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import delete, select, text, update

from app.channel.models import ChannelStatus
from app.database import async_session_maker
from app.logger import logger
from app.period import Period
from app.wordstat.models import Wordstat

STOP_LEXEMES_PATH = Path(__file__).with_name("stop_lexemes.txt")


def load_stop_lexemes(path: Path | str | None = None) -> list[str]:
    p = Path(path) if path else STOP_LEXEMES_PATH
    if not p.is_file():
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = raw.split("#", 1)[0].strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def stop_lexemes_for_category(category_id: int) -> list[str]:
    """Global stops + optional `stop_lexemes_{category_id}.txt` (merged, deduped)."""
    base = load_stop_lexemes()
    extra_path = STOP_LEXEMES_PATH.with_name(f"stop_lexemes_{int(category_id)}.txt")
    extra = load_stop_lexemes(extra_path)
    if not extra:
        return base
    seen = set(base)
    out = list(base)
    for s in extra:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


# type codes (NULL = outside MoM top / not typed)
TYPE_LEAVING = -1
TYPE_CORE = 0
TYPE_NEW = 1
TYPE_BOTH = 2

DEFAULT_TOP_N = 40  # fill buffer (store extra ranks)
DEFAULT_MOM_TOP_N = 20  # MoM type / report color sets


def _as_date(p: date | Period | str) -> date:
    if isinstance(p, Period):
        return date(p.year, p.month, 1)
    if isinstance(p, str):
        return Period.parse(p)
    return date(p.year, p.month, 1)


def _period_range(start: date, end: date) -> list[date]:
    cur = Period(start.month, start.year)
    last = Period(end.month, end.year)
    out: list[date] = []
    while cur <= last:
        out.append(date(cur.year, cur.month, 1))
        cur = cur.next(1)
    return out


class WordstatDAO:
    model = Wordstat

    @classmethod
    async def has_period(
        cls, category_id: int, period: date | Period | str
    ) -> bool:
        """True if wordstat already has any rows for category×period."""
        p = _as_date(period)
        async with async_session_maker() as session:
            row = (
                await session.execute(
                    select(Wordstat.id)
                    .where(
                        Wordstat.category_id == category_id,
                        Wordstat.period == p,
                    )
                    .limit(1)
                )
            ).first()
            return row is not None

    @classmethod
    async def fill(
        cls,
        *,
        category_ids: list[int],
        period_from: date | Period | str,
        period_to: date | Period | str | None = None,
        top_n: int = DEFAULT_TOP_N,
        stop_lexemes: list[str] | None = None,
        stop_path: Path | str | None = None,
    ) -> dict:
        """Compute top-N lexemes per category×period (longs only), type=NULL."""
        if top_n < 1:
            raise ValueError("top_n must be >= 1")
        start = _as_date(period_from)
        end = _as_date(period_to) if period_to else start
        if end < start:
            start, end = end, start
        periods = _period_range(start, end)
        explicit_stops = stop_lexemes
        if explicit_stops is None and stop_path is not None:
            explicit_stops = load_stop_lexemes(stop_path)

        inserted = 0
        deleted = 0
        async with async_session_maker() as session:
            for category_id in category_ids:
                stops = (
                    explicit_stops
                    if explicit_stops is not None
                    else stop_lexemes_for_category(category_id)
                )
                for period in periods:
                    n_del = await session.execute(
                        delete(Wordstat).where(
                            Wordstat.category_id == category_id,
                            Wordstat.period == period,
                        )
                    )
                    deleted += n_del.rowcount or 0

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
                            INSERT INTO wordstat (
                                category_id, period, lexeme, word, freq, type
                            )
                            SELECT
                                :category_id, :period, lexeme, word, freq, NULL
                            FROM agg
                            RETURNING id
                            """
                        ),
                        {
                            "category_id": category_id,
                            "period": period,
                            "stops": stops,
                            "top_n": top_n,
                        },
                    )
                    rows = result.fetchall()
                    inserted += len(rows)
                    logger.info(
                        f"wordstat fill cat={category_id} period={period} "
                        f"rows={len(rows)} stops={len(stops)} top={top_n}"
                    )
            await session.commit()

        return {
            "categories": category_ids,
            "periods": [p.isoformat() for p in periods],
            "top_n": top_n,
            "stops": len(stops),
            "deleted": deleted,
            "inserted": inserted,
        }

    @classmethod
    async def backfill_type(
        cls,
        *,
        category_ids: list[int] | None = None,
        period_from: date | Period | str | None = None,
        period_to: date | Period | str | None = None,
        mom_top_n: int = DEFAULT_MOM_TOP_N,
    ) -> dict:
        """Set type from MoM presence within each category.

        MoM sets = top `mom_top_n` by freq per period (default 20), even if fill
        stored more (e.g. 40). Ranks outside MoM top get type=NULL.

        Loads full period timeline for neighbor sets, but only UPDATEs rows whose
        period is in [period_from, period_to] when those are set (inclusive).
        Omit both → all periods (legacy).
        """
        if mom_top_n < 1:
            raise ValueError("mom_top_n must be >= 1")
        start = _as_date(period_from) if period_from is not None else None
        end = _as_date(period_to) if period_to is not None else start
        if start is not None and end is not None and end < start:
            start, end = end, start

        updated = 0
        async with async_session_maker() as session:
            cat_q = select(Wordstat.category_id).distinct()
            if category_ids:
                cat_q = cat_q.where(Wordstat.category_id.in_(category_ids))
            cats = [r[0] for r in (await session.execute(cat_q)).all()]

            for category_id in cats:
                periods = [
                    r[0]
                    for r in (
                        await session.execute(
                            select(Wordstat.period)
                            .where(Wordstat.category_id == category_id)
                            .distinct()
                            .order_by(Wordstat.period)
                        )
                    ).all()
                ]
                if not periods:
                    continue

                # period → (mom_top set, all lexemes for NULL-clear)
                sets: dict[date, set[str]] = {}
                all_lexemes: dict[date, list[str]] = {}
                for period in periods:
                    rows = (
                        await session.execute(
                            select(Wordstat.lexeme)
                            .where(
                                Wordstat.category_id == category_id,
                                Wordstat.period == period,
                            )
                            .order_by(Wordstat.freq.desc(), Wordstat.lexeme)
                        )
                    ).scalars().all()
                    all_lexemes[period] = list(rows)
                    sets[period] = set(rows[:mom_top_n])

                typed_n = 0
                for i, period in enumerate(periods):
                    if start is not None and (period < start or period > end):
                        continue

                    prev_set = sets[periods[i - 1]] if i > 0 else None
                    next_set = sets[periods[i + 1]] if i + 1 < len(periods) else None
                    cur = sets[period]
                    outside = [
                        lex
                        for lex in all_lexemes[period]
                        if lex not in cur
                    ]

                    by_type: dict[int, list[str]] = {
                        TYPE_LEAVING: [],
                        TYPE_CORE: [],
                        TYPE_NEW: [],
                        TYPE_BOTH: [],
                    }
                    for lexeme in cur:
                        is_new = prev_set is not None and lexeme not in prev_set
                        is_leaving = next_set is not None and lexeme not in next_set
                        if is_new and is_leaving:
                            t = TYPE_BOTH
                        elif is_new:
                            t = TYPE_NEW
                        elif is_leaving:
                            t = TYPE_LEAVING
                        else:
                            t = TYPE_CORE
                        by_type[t].append(lexeme)

                    for t, lexemes in by_type.items():
                        if not lexemes:
                            continue
                        res = await session.execute(
                            update(Wordstat)
                            .where(
                                Wordstat.category_id == category_id,
                                Wordstat.period == period,
                                Wordstat.lexeme.in_(lexemes),
                            )
                            .values(type=t)
                        )
                        updated += res.rowcount or 0

                    if outside:
                        res = await session.execute(
                            update(Wordstat)
                            .where(
                                Wordstat.category_id == category_id,
                                Wordstat.period == period,
                                Wordstat.lexeme.in_(outside),
                            )
                            .values(type=None)
                        )
                        updated += res.rowcount or 0
                    typed_n += 1

                logger.info(
                    f"wordstat type backfill cat={category_id} "
                    f"typed={typed_n}/{len(periods)} periods mom_top={mom_top_n}"
                    + (
                        f" range={start}..{end}"
                        if start is not None
                        else ""
                    )
                )

            await session.commit()

        return {
            "categories": cats,
            "updated": updated,
            "mom_top_n": mom_top_n,
            "period_from": start.isoformat() if start else None,
            "period_to": end.isoformat() if end else None,
        }

    @classmethod
    async def report(
        cls,
        *,
        category_id: int,
        period: date | Period | str,
    ) -> dict:
        """Assemble leaving/core/new for API.

        For period M:
          leaving — type −1/2 from M−1 (dropped out of top after previous month)
          core    — type 0 from M
          new     — type 1/2 from M (entered top this month; 2 = one-month spike)

        So a type=2 word is blue on its month and red on the next.
        Empty lists if no rows.
        """
        period_d = _as_date(period)
        prev_d = Period(period_d.month, period_d.year).next(-1)

        async with async_session_maker() as session:
            cur = (
                await session.execute(
                    select(
                        Wordstat.lexeme,
                        Wordstat.word,
                        Wordstat.freq,
                        Wordstat.type,
                    )
                    .where(
                        Wordstat.category_id == category_id,
                        Wordstat.period == period_d,
                    )
                    .order_by(Wordstat.freq.desc())
                )
            ).mappings().all()

            prev = (
                await session.execute(
                    select(
                        Wordstat.lexeme,
                        Wordstat.word,
                        Wordstat.freq,
                        Wordstat.type,
                    )
                    .where(
                        Wordstat.category_id == category_id,
                        Wordstat.period == prev_d,
                        Wordstat.type.in_([TYPE_LEAVING, TYPE_BOTH]),
                    )
                    .order_by(Wordstat.freq.desc())
                )
            ).mappings().all()

        def item(r) -> dict:
            return {
                "lexeme": r["lexeme"],
                "word": r["word"],
                "freq": r["freq"],
                "type": r["type"],
            }

        leaving = [item(r) for r in prev]
        core: list[dict] = []
        new: list[dict] = []
        for r in cur:
            t = r["type"]
            if t in (TYPE_NEW, TYPE_BOTH):
                new.append(item(r))
            elif t == TYPE_CORE:
                core.append(item(r))
            # NULL = outside MoM top (fill buffer); type −1 of M → leaving on M+1

        return {
            "category_id": category_id,
            "period": period_d.isoformat(),
            "leaving": leaving,
            "core": core,
            "new": new,
        }
