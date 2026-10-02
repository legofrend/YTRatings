"""
BigQuery batch writer for raw tables (channel_stat, video_stat, …).

Postgres DAOs stay intact; call these when settings.RAW_DB == "bigquery".

Write safety: dump rows to logs/bq_pending/ BEFORE BQ I/O; delete dump only after
success. On restart, flush_pending_writes() / next merge|append replays dumps.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, TypeVar
from uuid import UUID

from google.api_core import exceptions as gcp_exceptions
from google.cloud import bigquery

from app.bq.client import get_client
from app.bq.create_tables import bq_target
from app.logger import logger

STAGING_SUFFIX = "__ingest"
CHUNK = 5_000

# Transient Google front-door HTML 403 (not real IAM/billing JSON errors).
BQ_RETRY_ATTEMPTS = 3
BQ_RETRY_SLEEP_SEC = 60

PENDING_DIR = Path("logs/bq_pending")

T = TypeVar("T")


def _is_transient_html_403(exc: BaseException) -> bool:
    if not isinstance(exc, gcp_exceptions.Forbidden):
        return False
    msg = str(exc)
    return (
        "<!DOCTYPE html>" in msg
        or "That’s an error" in msg
        or "That's an error" in msg
    )


def _with_bq_retry(label: str, fn: Callable[[], T]) -> T:
    last: BaseException | None = None
    for attempt in range(1, BQ_RETRY_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if not _is_transient_html_403(exc) or attempt >= BQ_RETRY_ATTEMPTS:
                raise
            logger.warning(
                f"BQ transient 403 on {label}: attempt {attempt}/{BQ_RETRY_ATTEMPTS}, "
                f"sleep {BQ_RETRY_SLEEP_SEC}s then retry"
            )
            time.sleep(BQ_RETRY_SLEEP_SEC)
    assert last is not None
    raise last


def _table_ref(table_name: str) -> str:
    project_id, dataset_id = bq_target()
    return f"{project_id}.{dataset_id}.{table_name}"


def _convert(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return bytes(value).hex()
    if isinstance(value, dict):
        return json.loads(json.dumps(value, default=str))
    return value


def _normalize_rows(rows: list[dict]) -> list[dict]:
    return [{k: _convert(v) for k, v in row.items()} for row in rows]


def _pending_path(table_name: str, op: str) -> Path:
    safe = table_name.replace("/", "_")
    return PENDING_DIR / f"{safe}__{op}.json"


def _save_pending(path: Path, payload: dict) -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)
    logger.debug(f"BQ pending dump written: {path} ({len(payload.get('rows', []))} rows)")


def _clear_pending(path: Path) -> None:
    if path.exists():
        path.unlink()
        logger.debug(f"BQ pending dump removed: {path}")


def _load_pending(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_table(client: bigquery.Client, table_ref: str) -> bigquery.Table:
    try:
        return client.get_table(table_ref)
    except gcp_exceptions.NotFound as exc:
        raise RuntimeError(
            f"BQ table missing: {table_ref}. Run create_tables / copy first."
        ) from exc


def _schema_field_names(table: bigquery.Table) -> set[str]:
    return {f.name for f in table.schema}


def _coerce_for_field(field: bigquery.SchemaField, value: Any) -> Any:
    if value is None:
        return None
    ft = field.field_type
    if ft == "DATE":
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            return value.split("T")[0][:10]
    if ft in ("TIMESTAMP", "DATETIME"):
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time()).isoformat()
        return value
    if ft in ("INTEGER", "INT64") and isinstance(value, bool):
        return int(value)
    return _convert(value)


def _clean_rows_for_schema(
    rows: list[dict], schema: list[bigquery.SchemaField]
) -> list[dict]:
    by_name = {f.name: f for f in schema}
    allowed = set(by_name)
    out = []
    for row in rows:
        out.append(
            {
                k: _coerce_for_field(by_name[k], v)
                for k, v in row.items()
                if k in allowed
            }
        )
    return out


def _load_json(
    client: bigquery.Client,
    table_ref: str,
    rows: list[dict],
    *,
    truncate: bool,
) -> None:
    dest = _ensure_table(client, table_ref)
    cleaned = _clean_rows_for_schema(rows, dest.schema)
    job_config = bigquery.LoadJobConfig(
        schema=dest.schema,
        write_disposition=(
            bigquery.WriteDisposition.WRITE_TRUNCATE
            if truncate
            else bigquery.WriteDisposition.WRITE_APPEND
        ),
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )

    def _do() -> None:
        client.load_table_from_json(
            cleaned, table_ref, job_config=job_config
        ).result()

    _with_bq_retry(f"load {table_ref}", _do)


def _append_rows_impl(table_name: str, rows: list[dict]) -> int:
    """Actual WRITE_APPEND (no pending dump)."""
    if not rows:
        return 0
    client = get_client()
    table_ref = _table_ref(table_name)
    dest = _ensure_table(client, table_ref)
    allowed = _schema_field_names(dest)
    rows = _normalize_rows(rows)

    need_id = "id" in allowed and any(row.get("id") is None for row in rows)
    if need_id:
        max_id = _max_id(client, table_ref)
        next_id = (max_id or 0) + 1
        for row in rows:
            if row.get("id") is None:
                row["id"] = next_id
                next_id += 1

    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        _load_json(client, table_ref, chunk, truncate=False)
        logger.debug(f"BQ append {table_name}: {i + len(chunk)}/{len(rows)}")
    return len(rows)


def _merge_rows_impl(
    table_name: str,
    rows: list[dict],
    key_columns: list[str],
    *,
    update_on_match: bool = True,
) -> int:
    """Actual staging+MERGE (no pending dump)."""
    if not rows:
        return 0
    if not key_columns:
        raise ValueError("key_columns required for merge")

    client = get_client()
    dest_ref = _table_ref(table_name)
    staging_ref = _table_ref(f"{table_name}{STAGING_SUFFIX}")
    dest = _ensure_table(client, dest_ref)
    allowed = _schema_field_names(dest)
    rows = _normalize_rows(rows)

    payload_cols = set()
    for row in rows:
        payload_cols.update(row.keys())
    payload_cols &= allowed
    if not payload_cols.issuperset(key_columns):
        missing = set(key_columns) - payload_cols
        raise ValueError(f"merge rows missing key columns: {missing}")

    def _delete_staging() -> None:
        client.delete_table(staging_ref, not_found_ok=True)

    try:
        _with_bq_retry(f"delete staging {table_name}", _delete_staging)
    except Exception:
        pass

    staging_schema = [f for f in dest.schema if f.name in payload_cols]
    staging = bigquery.Table(staging_ref, schema=staging_schema)

    def _create_staging() -> None:
        client.create_table(staging)

    _with_bq_retry(f"create staging {table_name}", _create_staging)

    cleaned = _clean_rows_for_schema(rows, staging_schema)
    for i in range(0, len(cleaned), CHUNK):
        job_config = bigquery.LoadJobConfig(
            schema=staging_schema,
            write_disposition=(
                bigquery.WriteDisposition.WRITE_TRUNCATE
                if i == 0
                else bigquery.WriteDisposition.WRITE_APPEND
            ),
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        )
        chunk = cleaned[i : i + CHUNK]

        def _load_chunk(_chunk=chunk, _cfg=job_config) -> None:
            client.load_table_from_json(
                _chunk, staging_ref, job_config=_cfg
            ).result()

        _with_bq_retry(f"load staging {table_name} chunk={i}", _load_chunk)

    update_cols = sorted(payload_cols - set(key_columns) - {"id"})
    on_clause = " AND ".join(f"T.`{k}` = S.`{k}`" for k in key_columns)

    has_id = "id" in allowed
    insert_cols = [f.name for f in dest.schema]

    using_select = [f"S.`{c}`" for c in sorted(payload_cols)]
    if has_id:
        if "id" in payload_cols:
            using_select.append(
                "COALESCE(S.`id`, m.max_id + ROW_NUMBER() OVER()) AS `_alloc_id`"
            )
        else:
            using_select.append("m.max_id + ROW_NUMBER() OVER() AS `_alloc_id`")

    using_sql = f"""(
      SELECT {", ".join(using_select)}
      FROM `{staging_ref}` AS S
      CROSS JOIN (SELECT COALESCE(MAX(id), 0) AS max_id FROM `{dest_ref}`) AS m
    )"""

    merge_parts = [
        f"MERGE `{dest_ref}` AS T",
        f"USING {using_sql} AS S",
        f"ON {on_clause}",
    ]
    if update_on_match and update_cols:
        set_clause = ", ".join(f"T.`{c}` = S.`{c}`" for c in update_cols)
        merge_parts.append(f"WHEN MATCHED THEN UPDATE SET {set_clause}")

    insert_vals = []
    for col in insert_cols:
        if col == "id" and has_id:
            insert_vals.append("S.`_alloc_id`")
        elif col in payload_cols:
            insert_vals.append(f"S.`{col}`")
        else:
            insert_vals.append("NULL")

    insert_col_sql = ", ".join(f"`{c}`" for c in insert_cols)
    insert_val_sql = ", ".join(insert_vals)
    merge_parts.append(
        f"WHEN NOT MATCHED THEN INSERT ({insert_col_sql}) VALUES ({insert_val_sql})"
    )
    merge_sql = "\n".join(merge_parts)

    def _merge() -> None:
        client.query(merge_sql).result()

    _with_bq_retry(f"merge {table_name}", _merge)

    def _drop_staging() -> None:
        client.delete_table(staging_ref, not_found_ok=True)

    _with_bq_retry(f"drop staging {table_name}", _drop_staging)

    mode = "upsert" if update_on_match else "insert_only"
    logger.debug(f"BQ merge {table_name} ({mode}): {len(rows)} rows keys={key_columns}")
    return len(rows)


def _replay_pending(path: Path) -> int:
    payload = _load_pending(path)
    if not payload:
        return 0
    op = payload.get("op")
    table = payload["table"]
    rows = payload.get("rows") or []
    logger.info(f"BQ replaying pending dump {path} op={op} rows={len(rows)}")
    if op == "merge":
        n = _merge_rows_impl(
            table,
            rows,
            payload["key_columns"],
            update_on_match=bool(payload.get("update_on_match", True)),
        )
    elif op == "append":
        n = _append_rows_impl(table, rows)
    else:
        raise ValueError(f"unknown pending op in {path}: {op}")
    _clear_pending(path)
    return n


def flush_pending_writes() -> int:
    """Replay all dumps in logs/bq_pending/. Call at pipeline start."""
    if not PENDING_DIR.exists():
        return 0
    total = 0
    for path in sorted(PENDING_DIR.glob("*.json")):
        total += _replay_pending(path)
    if total:
        logger.info(f"BQ flushed pending dumps: {total} rows")
    return total


def append_rows(table_name: str, rows: list[dict]) -> int:
    """WRITE_APPEND; dump-first, delete dump on success."""
    path = _pending_path(table_name, "append")
    if path.exists():
        _replay_pending(path)

    if not rows:
        return 0

    rows = _normalize_rows(rows)
    _save_pending(
        path,
        {"op": "append", "table": table_name, "rows": rows},
    )
    try:
        n = _append_rows_impl(table_name, rows)
        _clear_pending(path)
        return n
    except Exception:
        logger.error(f"BQ append failed; pending kept at {path}")
        raise


def merge_rows(
    table_name: str,
    rows: list[dict],
    key_columns: list[str],
    *,
    update_on_match: bool = True,
) -> int:
    """
    Upsert by key_columns via staging + MERGE.
    Dump-first to logs/bq_pending/; delete only after success.
    """
    path = _pending_path(table_name, "merge")
    if path.exists():
        _replay_pending(path)

    if not rows:
        return 0
    if not key_columns:
        raise ValueError("key_columns required for merge")

    rows = _normalize_rows(rows)
    _save_pending(
        path,
        {
            "op": "merge",
            "table": table_name,
            "key_columns": list(key_columns),
            "update_on_match": update_on_match,
            "rows": rows,
        },
    )
    try:
        n = _merge_rows_impl(
            table_name, rows, key_columns, update_on_match=update_on_match
        )
        _clear_pending(path)
        return n
    except Exception:
        logger.error(f"BQ merge failed; pending kept at {path}")
        raise


def _max_id(client: bigquery.Client, table_ref: str) -> int | None:
    def _q() -> int | None:
        row = next(
            iter(client.query(f"SELECT MAX(id) AS m FROM `{table_ref}`").result())
        )
        return int(row.m) if row.m is not None else None

    return _with_bq_retry(f"max_id {table_ref}", _q)


def query_rows(sql: str, params: dict | None = None) -> list[dict]:
    client = get_client()

    def _q() -> list[dict]:
        result = client.query(sql, job_config=_job_config(params)).result()
        return [dict(row.items()) for row in result]

    return _with_bq_retry("query_rows", _q)


def run_sql(sql: str, params: dict | None = None) -> None:
    """Run DML/DDL (MERGE, CREATE, …) and wait."""
    client = get_client()

    def _q() -> None:
        client.query(sql, job_config=_job_config(params)).result()

    _with_bq_retry("run_sql", _q)


def _job_config(params: dict | None) -> bigquery.QueryJobConfig | None:
    if not params:
        return None
    qparams = []
    for k, v in params.items():
        if isinstance(v, list):
            if not v:
                qparams.append(bigquery.ArrayQueryParameter(k, "STRING", []))
            elif isinstance(v[0], bool):
                qparams.append(bigquery.ArrayQueryParameter(k, "BOOL", v))
            elif isinstance(v[0], int) and not isinstance(v[0], bool):
                qparams.append(bigquery.ArrayQueryParameter(k, "INT64", v))
            elif isinstance(v[0], date) and not isinstance(v[0], datetime):
                qparams.append(bigquery.ArrayQueryParameter(k, "DATE", v))
            else:
                if all(isinstance(x, str) and len(x) == 10 and x[4] == "-" for x in v):
                    qparams.append(
                        bigquery.ArrayQueryParameter(
                            k, "DATE", [date.fromisoformat(x) for x in v]
                        )
                    )
                else:
                    qparams.append(
                        bigquery.ArrayQueryParameter(k, "STRING", [str(x) for x in v])
                    )
        elif isinstance(v, bool):
            qparams.append(bigquery.ScalarQueryParameter(k, "BOOL", v))
        elif isinstance(v, date) and not isinstance(v, datetime):
            qparams.append(bigquery.ScalarQueryParameter(k, "DATE", v))
        elif isinstance(v, int) and not isinstance(v, bool):
            qparams.append(bigquery.ScalarQueryParameter(k, "INT64", v))
        else:
            qparams.append(bigquery.ScalarQueryParameter(k, "STRING", str(v)))
    return bigquery.QueryJobConfig(query_parameters=qparams)


def table_fqn(table_name: str) -> str:
    return _table_ref(table_name)
