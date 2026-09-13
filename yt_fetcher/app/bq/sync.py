"""
Sync Postgres -> BigQuery (PG is master).

Modes (combinable):
  --period YYYY-MM     hard replace rows for that period (DELETE then load)
  --cats 1,3,5         limit to category_ids (via channel.category_id)
  --new-ids            only rows with id > MAX(id) in BQ (append; no DELETE)

Examples:
  poetry run python -m app.bq.sync --period 2026-08
  poetry run python -m app.bq.sync --period 2026-08 --cats 1,7
  poetry run python -m app.bq.sync --tables video_stat --new-ids
  poetry run python -m app.bq.sync --tables channel --cats 1 --new-ids
"""

from __future__ import annotations

from datetime import date
import argparse
import sys
import time
from dataclasses import dataclass

import psycopg2
from google.cloud import bigquery
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from app.bq.client import get_client
from app.bq.copy_tables import (
    _chunk_size,
    _ensure_table,
    _fmt_elapsed,
    _has_id,
    _load_batch,
    _log_progress,
    _max_id,
    _row_to_bq,
)
from app.bq.create_tables import (
    PgTable,
    _pg_connect,
    _pg_type_to_bq,
    bq_target,
    create_bq_tables,
    fetch_pg_tables,
)
from app.period import Period

# Default monthly push: stats + videos for the period
DEFAULT_PERIOD_TABLES = ("video_stat", "channel_stat", "video")


@dataclass(frozen=True)
class TableSyncSpec:
    """How to scope a table for period / category filters."""

    period_col: str | None = None  # e.g. report_period, published_at_period
    # None → no category filter; "category_id" on table; else FK via channel
    category_via: str | None = "channel"  # "channel" | "self" | None


TABLE_SPECS: dict[str, TableSyncSpec] = {
    "video_stat": TableSyncSpec(period_col="report_period", category_via="channel"),
    "channel_stat": TableSyncSpec(period_col="report_period", category_via="channel"),
    "video": TableSyncSpec(period_col="published_at_period", category_via="channel"),
    "playlist_shorts": TableSyncSpec(
        period_col="published_at_period", category_via="channel"
    ),
    "channel": TableSyncSpec(period_col=None, category_via="self"),
    "category": TableSyncSpec(period_col=None, category_via="self"),
}


def _as_period(period: Period | date | str | None) -> date | None:
    if period is None:
        return None
    if isinstance(period, str):
        return Period.parse(period)
    if isinstance(period, Period):
        return period
    return Period(period.month, period.year)


def _parse_cats(s: str | None) -> list[int] | None:
    if not s:
        return None
    out: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    # unique, preserve order
    seen: set[int] = set()
    ordered: list[int] = []
    for i in out:
        if i not in seen:
            seen.add(i)
            ordered.append(i)
    return ordered or None


def _spec(table_name: str) -> TableSyncSpec:
    return TABLE_SPECS.get(table_name, TableSyncSpec())


def _channel_ids_for_cats(pg_conn, category_ids: list[int]) -> list[str]:
    q = sql.SQL("SELECT channel_id FROM channel WHERE category_id = ANY(%s)")
    with pg_conn.cursor() as cur:
        cur.execute(q, (category_ids,))
        return [r[0] for r in cur.fetchall()]


def _build_pg_where(
    table_name: str,
    *,
    period: date | None,
    category_ids: list[int] | None,
    after_id: int | None,
) -> tuple[sql.Composed, list]:
    """WHERE clause + params for SELECT from PG."""
    spec = _spec(table_name)
    parts: list[sql.Composable] = []
    params: list = []

    if period is not None:
        if not spec.period_col:
            raise ValueError(
                f"{table_name}: no period column — cannot filter by --period"
            )
        parts.append(
            sql.SQL("{} = %s").format(sql.Identifier(spec.period_col))
        )
        params.append(period)

    if category_ids:
        via = spec.category_via
        if via is None:
            raise ValueError(f"{table_name}: category filter not supported")
        if via == "self":
            col = "id" if table_name == "category" else "category_id"
            parts.append(sql.SQL("{} = ANY(%s)").format(sql.Identifier(col)))
            params.append(category_ids)
        elif via == "channel":
            parts.append(
                sql.SQL(
                    "channel_id IN (SELECT channel_id FROM channel "
                    "WHERE category_id = ANY(%s))"
                )
            )
            params.append(category_ids)
        else:
            raise ValueError(f"{table_name}: unknown category_via={via}")

    if after_id is not None:
        parts.append(sql.SQL("id > %s"))
        params.append(after_id)

    if not parts:
        return sql.SQL("TRUE"), []

    clause = parts[0]
    for p in parts[1:]:
        clause = sql.SQL("{} AND {}").format(clause, p)
    return clause, params


def _bq_delete(
    client: bigquery.Client,
    table_ref: str,
    table_name: str,
    *,
    period: date | None,
    category_ids: list[int] | None,
    channel_ids: list[str] | None,
) -> int:
    """Hard-delete matching slice in BQ. Returns num_dml_affected_rows."""
    spec = _spec(table_name)
    conditions: list[str] = []
    params: list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter] = []

    if period is not None:
        if not spec.period_col:
            raise ValueError(f"{table_name}: cannot DELETE by period")
        conditions.append(f"`{spec.period_col}` = @period")
        params.append(bigquery.ScalarQueryParameter("period", "DATE", period))

    if category_ids:
        via = spec.category_via
        if via == "self":
            col = "id" if table_name == "category" else "category_id"
            conditions.append(f"`{col}` IN UNNEST(@category_ids)")
            params.append(
                bigquery.ArrayQueryParameter("category_ids", "INT64", category_ids)
            )
        elif via == "channel":
            if not channel_ids:
                return 0
            conditions.append("channel_id IN UNNEST(@channel_ids)")
            params.append(
                bigquery.ArrayQueryParameter("channel_ids", "STRING", channel_ids)
            )
        elif via is None:
            raise ValueError(f"{table_name}: category delete not supported")

    if not conditions:
        raise ValueError("refusing DELETE without period/category scope")

    sql_del = f"DELETE FROM `{table_ref}` WHERE " + " AND ".join(conditions)
    job = client.query(
        sql_del,
        job_config=bigquery.QueryJobConfig(query_parameters=params),
    )
    job.result()
    return int(job.num_dml_affected_rows or 0)


def sync_table(
    pg_conn,
    bq_client: bigquery.Client,
    table: PgTable,
    dataset_id: str,
    *,
    period: date | None = None,
    category_ids: list[int] | None = None,
    new_ids_only: bool = False,
) -> tuple[int, object]:
    """
    Sync one table PG → BQ.

    - period / category_ids (without new_ids): DELETE matching BQ slice, load from PG
    - new_ids_only: append id > MAX(BQ.id), optional period/cats narrow the SELECT
    """
    if period is None and not category_ids and not new_ids_only:
        raise ValueError(
            "specify --period and/or --cats and/or --new-ids "
            "(refusing full-table sync; use copy_tables for that)"
        )

    # Safety: period-scoped tables need --period for hard replace
    # (otherwise --cats alone would wipe all months for those channels)
    if (
        not new_ids_only
        and period is None
        and category_ids
        and _spec(table.name).period_col
    ):
        raise ValueError(
            f"{table.name}: hard replace with --cats requires --period "
            f"(refusing to delete all periods for those channels)"
        )

    dest_ref = f"{bq_client.project}.{dataset_id}.{table.name}"
    schema = [_pg_type_to_bq(c) for c in table.columns]
    chunk = _chunk_size(table.name)
    use_id = _has_id(table)

    _ensure_table(bq_client, dest_ref, schema)

    after_id: int | None = None
    if new_ids_only:
        if not use_id:
            raise ValueError(f"{table.name}: --new-ids requires id column")
        after_id = _max_id(bq_client, dest_ref)
        if after_id is None:
            after_id = 0
        print(f"    {table.name}: new-ids after id > {after_id}")

    channel_ids: list[str] | None = None
    if category_ids and _spec(table.name).category_via == "channel":
        channel_ids = _channel_ids_for_cats(pg_conn, category_ids)
        print(
            f"    {table.name}: category filter -> {len(channel_ids)} channels"
        )

    # Hard replace: delete scoped rows, then reload (skip delete for --new-ids)
    if not new_ids_only:
        deleted = _bq_delete(
            bq_client,
            dest_ref,
            table.name,
            period=period,
            category_ids=category_ids,
            channel_ids=channel_ids,
        )
        print(f"    {table.name}: deleted {deleted} BQ rows in scope")

    where_sql, where_params = _build_pg_where(
        table.name,
        period=period,
        category_ids=category_ids,
        after_id=after_id,
    )

    order = sql.SQL(" ORDER BY id") if use_id else sql.SQL("")
    query = sql.SQL("SELECT * FROM {}.{} WHERE {}{}").format(
        sql.Identifier("public"),
        sql.Identifier(table.name),
        where_sql,
        order,
    )

    started = time.perf_counter()
    copied = 0

    count_q = sql.SQL("SELECT COUNT(*) FROM {}.{} WHERE {}").format(
        sql.Identifier("public"),
        sql.Identifier(table.name),
        where_sql,
    )
    with pg_conn.cursor() as cur:
        cur.execute(count_q, where_params or None)
        pg_total = int(cur.fetchone()[0])

    print(f"    {table.name}: loading {pg_total:,} PG rows -> BQ")

    while True:
        try:
            with pg_conn.cursor(
                name=f"sync_{table.name}_{int(time.time())}",
                cursor_factory=RealDictCursor,
            ) as cur:
                cur.itersize = chunk
                cur.execute(query, where_params or None)
                batch: list[dict] = []
                for row in cur:
                    batch.append(_row_to_bq(dict(row), table))
                    if len(batch) >= chunk:
                        _load_batch(
                            bq_client,
                            dest_ref,
                            schema,
                            batch,
                            truncate=False,
                        )
                        copied += len(batch)
                        _log_progress(table.name, copied, 0, pg_total, started)
                        batch = []
                if batch:
                    _load_batch(
                        bq_client, dest_ref, schema, batch, truncate=False
                    )
                    copied += len(batch)
                    _log_progress(table.name, copied, 0, pg_total, started)
            break
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            print(f"\n    postgres dropped ({exc}); reconnect")
            try:
                pg_conn.close()
            except Exception:
                pass
            time.sleep(3)
            pg_conn = _pg_connect()
            pg_conn.set_session(readonly=True)

    if copied == 0 and pg_total == 0:
        print(f"\n    {table.name}: nothing to load")

    elapsed = time.perf_counter() - started
    rate = copied / elapsed if elapsed else 0
    print()
    print(
        f"  {table.name}: synced {copied:,} rows in {_fmt_elapsed(elapsed)}"
        f" ({rate:,.0f} rows/s)"
    )
    return copied, pg_conn


def sync_to_bq(
    tables: list[str] | None = None,
    *,
    period: Period | date | str | None = None,
    category_ids: list[int] | None = None,
    new_ids_only: bool = False,
) -> dict[str, int]:
    """
    Universal PG → BQ sync.

    period: hard-replace that report/published month in listed tables
    category_ids: limit to those categories
    new_ids_only: append only id > max(BQ)
    """
    period_d = _as_period(period)
    if tables is None:
        tables = list(DEFAULT_PERIOD_TABLES)

    if period_d is None and not category_ids and not new_ids_only:
        raise ValueError("need period and/or category_ids and/or new_ids_only")

    project_id, dataset_id = bq_target()
    all_tables = {t.name: t for t in fetch_pg_tables()}
    missing = [n for n in tables if n not in all_tables]
    if missing:
        raise ValueError(f"not in postgres: {', '.join(missing)}")

    wanted = [all_tables[n] for n in tables]
    create_bq_tables(wanted, project_id=project_id, dataset_id=dataset_id)
    bq_client = get_client(project_id)
    pg_conn = _pg_connect()
    pg_conn.set_session(readonly=True)

    results: dict[str, int] = {}
    try:
        for table in wanted:
            print(f"  sync {table.name}...")
            n, pg_conn = sync_table(
                pg_conn,
                bq_client,
                table,
                dataset_id,
                period=period_d,
                category_ids=category_ids,
                new_ids_only=new_ids_only,
            )
            results[table.name] = n
    finally:
        pg_conn.close()

    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Sync Postgres -> BigQuery (period / category / new-ids)"
    )
    p.add_argument(
        "--tables",
        default=None,
        help=f"comma list (default for --period: {','.join(DEFAULT_PERIOD_TABLES)})",
    )
    p.add_argument("--period", default=None, help="YYYY-MM - hard replace that period")
    p.add_argument("--cats", default=None, help="category ids, e.g. 1,7,8 or 3-6")
    p.add_argument(
        "--new-ids",
        action="store_true",
        help="append only rows with id > MAX(id) in BQ",
    )
    args = p.parse_args(argv)

    if not args.period and not args.cats and not args.new_ids:
        p.error("specify --period and/or --cats and/or --new-ids")

    tables = (
        [t.strip() for t in args.tables.split(",") if t.strip()]
        if args.tables
        else None
    )
    cats = _parse_cats(args.cats)

    print(
        f"sync PG->BQ period={args.period} cats={cats} "
        f"new_ids={args.new_ids} tables={tables or DEFAULT_PERIOD_TABLES}"
    )
    wall = time.perf_counter()
    try:
        results = sync_to_bq(
            tables,
            period=args.period,
            category_ids=cats,
            new_ids_only=args.new_ids,
        )
    except Exception as exc:
        print(f"sync error: {exc}")
        return 1

    for name, n in results.items():
        print(f"  {name}: {n:,}")
    print(f"done in {_fmt_elapsed(time.perf_counter() - wall)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
