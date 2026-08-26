"""
Copy Postgres tables into BigQuery.

Default: category + channel (smoke test).
All tables:  python -m app.bq.copy_tables --all
Subset:      python -m app.bq.copy_tables report

Loads into {table}__load, then atomically replaces the dest table.
If the process dies, dest stays as the last successful copy.
Rerun the same table: continues from MAX(id) in __load unless --fresh.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, time as dt_time
from decimal import Decimal
from uuid import UUID

import psycopg2
from google.api_core import exceptions as gcp_exceptions
from google.cloud import bigquery
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from app.bq.client import get_client
from app.bq.create_tables import (
    PgTable,
    _pg_connect,
    _pg_type_to_bq,
    bq_target,
    create_bq_tables,
    fetch_pg_tables,
)

CHUNK = 5_000
CHUNK_JSON_HEAVY = 200
JSON_HEAVY_TABLES = {"report"}
STAGING_SUFFIX = "__load"
LOAD_RETRIES = 3


def _fmt_elapsed(seconds: float) -> str:
    s = int(seconds)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def _convert(value, udt_name: str):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dt_time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, memoryview):
        return bytes(value).hex()
    if isinstance(value, bytes):
        return value.hex()
    if udt_name in {"json", "jsonb"} and isinstance(value, str):
        return json.loads(value)
    return value


def _row_to_bq(row: dict, table: PgTable) -> dict:
    types = {c.name: c.udt_name for c in table.columns}
    return {k: _convert(v, types.get(k, "")) for k, v in row.items()}


def _chunk_size(table_name: str) -> int:
    return CHUNK_JSON_HEAVY if table_name in JSON_HEAVY_TABLES else CHUNK


def _has_id(table: PgTable) -> bool:
    return any(c.name == "id" for c in table.columns)


def _ensure_table(
    client: bigquery.Client, table_ref: str, schema: list[bigquery.SchemaField]
) -> None:
    try:
        client.get_table(table_ref)
    except gcp_exceptions.NotFound:
        client.create_table(bigquery.Table(table_ref, schema=schema))


def _max_id(client: bigquery.Client, table_ref: str) -> int | None:
    try:
        row = next(iter(client.query(f"SELECT MAX(id) AS m FROM `{table_ref}`").result()))
    except gcp_exceptions.NotFound:
        return None
    return int(row.m) if row.m is not None else None


def _pg_count(pg_conn, table_name: str) -> int:
    q = sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
        sql.Identifier("public"),
        sql.Identifier(table_name),
    )
    with pg_conn.cursor() as cur:
        cur.execute(q)
        return int(cur.fetchone()[0])


def _load_batch(
    client: bigquery.Client,
    table_ref: str,
    schema: list[bigquery.SchemaField],
    rows: list[dict],
    truncate: bool,
) -> None:
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=(
            bigquery.WriteDisposition.WRITE_TRUNCATE
            if truncate
            else bigquery.WriteDisposition.WRITE_APPEND
        ),
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )
    last_exc: Exception | None = None
    for attempt in range(1, LOAD_RETRIES + 1):
        try:
            client.load_table_from_json(rows, table_ref, job_config=job_config).result()
            return
        except Exception as exc:
            last_exc = exc
            print(f"\n    load retry {attempt}/{LOAD_RETRIES}: {exc}")
            time.sleep(2 * attempt)
    raise last_exc  # type: ignore[misc]


def _promote_staging(
    client: bigquery.Client, staging_ref: str, dest_ref: str
) -> None:
    job_config = bigquery.CopyJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    client.copy_table(staging_ref, dest_ref, job_config=job_config).result()
    client.delete_table(staging_ref, not_found_ok=True)


def copy_table(
    pg_conn,
    bq_client: bigquery.Client,
    table: PgTable,
    dataset_id: str,
    *,
    fresh: bool = False,
) -> tuple[int, object]:
    dest_ref = f"{bq_client.project}.{dataset_id}.{table.name}"
    staging_ref = f"{bq_client.project}.{dataset_id}.{table.name}{STAGING_SUFFIX}"
    schema = [_pg_type_to_bq(c) for c in table.columns]
    chunk = _chunk_size(table.name)
    use_id = _has_id(table)

    if fresh:
        bq_client.delete_table(staging_ref, not_found_ok=True)

    _ensure_table(bq_client, dest_ref, schema)
    _ensure_table(bq_client, staging_ref, schema)

    after_id: int | None = None
    if use_id and not fresh:
        after_id = _max_id(bq_client, staging_ref)
        if after_id is not None:
            print(f"    resume {table.name} from id > {after_id}")

    pg_total = _pg_count(pg_conn, table.name)
    already = 0
    if after_id is not None:
        q_done = sql.SQL("SELECT COUNT(*) FROM {}.{} WHERE id <= %s").format(
            sql.Identifier("public"),
            sql.Identifier(table.name),
        )
        with pg_conn.cursor() as cur:
            cur.execute(q_done, (after_id,))
            already = int(cur.fetchone()[0])

    started = time.perf_counter()
    copied = 0
    first_batch = after_id is None
    last_id = after_id

    while True:
        if use_id and last_id is not None:
            query = sql.SQL(
                "SELECT * FROM {}.{} WHERE id > %s ORDER BY id"
            ).format(sql.Identifier("public"), sql.Identifier(table.name))
            params = (last_id,)
        elif use_id:
            query = sql.SQL("SELECT * FROM {}.{} ORDER BY id").format(
                sql.Identifier("public"), sql.Identifier(table.name)
            )
            params = None
        else:
            query = sql.SQL("SELECT * FROM {}.{}").format(
                sql.Identifier("public"), sql.Identifier(table.name)
            )
            params = None

        try:
            with pg_conn.cursor(
                name=f"copy_{table.name}_{int(time.time())}",
                cursor_factory=RealDictCursor,
            ) as cur:
                cur.itersize = chunk
                cur.execute(query, params)
                batch: list[dict] = []
                for row in cur:
                    row = dict(row)
                    batch.append(_row_to_bq(row, table))
                    if use_id:
                        last_id = int(row["id"])
                    if len(batch) >= chunk:
                        _load_batch(
                            bq_client, staging_ref, schema, batch, truncate=first_batch
                        )
                        copied += len(batch)
                        first_batch = False
                        _log_progress(table.name, copied, already, pg_total, started)
                        batch = []
                if batch:
                    _load_batch(
                        bq_client, staging_ref, schema, batch, truncate=first_batch
                    )
                    copied += len(batch)
                    first_batch = False
                    _log_progress(table.name, copied, already, pg_total, started)
            break
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            print(f"\n    postgres dropped ({exc}); reconnect, resume id={last_id}")
            try:
                pg_conn.close()
            except Exception:
                pass
            time.sleep(3)
            pg_conn = _pg_connect()
            pg_conn.set_session(readonly=True)
            first_batch = False

    total = already + copied
    if total == 0 and first_batch:
        bq_client.query(f"DELETE FROM `{staging_ref}` WHERE TRUE").result()

    _promote_staging(bq_client, staging_ref, dest_ref)
    elapsed = time.perf_counter() - started
    rate = copied / elapsed if elapsed else 0
    print()
    print(
        f"  {table.name}: {total} rows in {_fmt_elapsed(elapsed)}"
        f" ({rate:,.0f} rows/s this run)"
    )
    return total, pg_conn


def _log_progress(
    name: str, copied: int, already: int, total: int, started: float
) -> None:
    elapsed = time.perf_counter() - started
    done = already + copied
    rate = copied / elapsed if elapsed else 0
    extra = ""
    if total and rate:
        remain = max(total - done, 0) / rate
        end_at = datetime.now() + timedelta(seconds=remain)
        extra = f", eta {_fmt_elapsed(remain)}, end {end_at.strftime('%H:%M:%S')}"
    pct = f" {done / total * 100:.1f}%" if total else ""
    line = (
        f"    {name}: {done:,}/{total:,}{pct}  "
        f"{_fmt_elapsed(elapsed)}  {rate:,.0f} rows/s{extra}"
    )
    print(f"\r{line:<120}", end="", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy Postgres tables to BigQuery")
    parser.add_argument("tables", nargs="*", help="table names (default: category channel)")
    parser.add_argument("--all", action="store_true", help="copy every public base table")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="ignore {table}__load progress and recopy from scratch",
    )
    args = parser.parse_args(argv)

    project_id, dataset_id = bq_target()

    try:
        tables = fetch_pg_tables()
    except psycopg2.Error as exc:
        print(f"postgres error: {exc}")
        return 1

    if not tables:
        print("no postgres tables")
        return 1

    wanted = {t.lower() for t in args.tables} if args.tables else None
    if not args.all:
        wanted = wanted or {"category", "channel"}
        missing = wanted - {t.name for t in tables}
        if missing:
            print(f"not in postgres: {', '.join(sorted(missing))}")
            print("available:", ", ".join(t.name for t in tables))
            return 1
        tables = [t for t in tables if t.name in wanted]

    wall = time.perf_counter()
    try:
        create_bq_tables(tables, project_id=project_id, dataset_id=dataset_id)
        bq_client = get_client(project_id)
        pg_conn = _pg_connect()
        pg_conn.set_session(readonly=True)
        print("copying data")
        for table in tables:
            print(f"  {table.name}...")
            t0 = time.perf_counter()
            n, pg_conn = copy_table(
                pg_conn, bq_client, table, dataset_id, fresh=args.fresh
            )
            print(f"  {table.name} wall {_fmt_elapsed(time.perf_counter() - t0)} ({n:,} rows)")
        pg_conn.close()
    except Exception as exc:
        print(f"copy error: {exc}")
        return 1

    print(f"done in {_fmt_elapsed(time.perf_counter() - wall)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
