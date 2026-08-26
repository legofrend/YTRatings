"""
Create BigQuery tables matching the live Postgres schema on the VPS.

Reads connection and BQ target from app.config (.env):
  DB_*, BQ_PROJECT_ID, BQ_DATASET

Run (dev deps):
    poetry run python -m app.bq.create_tables
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import psycopg2
from google.api_core import exceptions as gcp_exceptions
from google.cloud import bigquery

from app.bq.client import get_client
from app.config import settings

PG_SCHEMA = "public"


def bq_target() -> tuple[str, str]:
    project_id = settings.BQ_PROJECT_ID
    dataset_id = settings.BQ_DATASET
    if not project_id or not dataset_id:
        raise ValueError("Set BQ_PROJECT_ID and BQ_DATASET in .env")
    return project_id, dataset_id

# Postgres udt_name / data_type → BigQuery
_UDT_MAP = {
    "int2": "INTEGER",
    "int4": "INTEGER",
    "int8": "INTEGER",
    "serial": "INTEGER",
    "bigserial": "INTEGER",
    "float4": "FLOAT",
    "float8": "FLOAT",
    "numeric": "NUMERIC",
    "decimal": "NUMERIC",
    "money": "NUMERIC",
    "bool": "BOOLEAN",
    "date": "DATE",
    "time": "TIME",
    "timetz": "TIME",
    "timestamp": "TIMESTAMP",
    "timestamptz": "TIMESTAMP",
    "json": "JSON",
    "jsonb": "JSON",
    "bytea": "BYTES",
    "uuid": "STRING",
    "text": "STRING",
    "varchar": "STRING",
    "bpchar": "STRING",
    "citext": "STRING",
    "name": "STRING",
    "interval": "STRING",
}


@dataclass
class PgColumn:
    name: str
    udt_name: str
    data_type: str
    is_nullable: bool
    ordinal: int


@dataclass
class PgTable:
    name: str
    columns: list[PgColumn]


def _pg_connect():
    return psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASS,
        connect_timeout=15,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )


def _pg_type_to_bq(col: PgColumn) -> bigquery.SchemaField:
    udt = col.udt_name.lstrip("_")
    bq_type = _UDT_MAP.get(udt, "STRING")
    mode = "NULLABLE" if col.is_nullable else "REQUIRED"
    if col.data_type == "ARRAY" or col.udt_name.startswith("_"):
        return bigquery.SchemaField(col.name, bq_type, mode="REPEATED")
    return bigquery.SchemaField(col.name, bq_type, mode=mode)


def fetch_pg_tables() -> list[PgTable]:
    sql = """
        SELECT c.table_name, c.column_name, c.udt_name, c.data_type,
               c.is_nullable, c.ordinal_position
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.table_schema = %s
          AND t.table_type = 'BASE TABLE'
        ORDER BY c.table_name, c.ordinal_position
    """
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (PG_SCHEMA,))
            rows = cur.fetchall()

    tables: dict[str, PgTable] = {}
    for table_name, col_name, udt, data_type, is_nullable, ordinal in rows:
        table = tables.setdefault(table_name, PgTable(name=table_name, columns=[]))
        table.columns.append(
            PgColumn(
                name=col_name,
                udt_name=udt,
                data_type=data_type,
                is_nullable=is_nullable == "YES",
                ordinal=ordinal,
            )
        )
    return list(tables.values())


def ensure_dataset(client: bigquery.Client, dataset_id: str) -> bigquery.Dataset:
    ref = bigquery.Dataset(f"{client.project}.{dataset_id}")
    try:
        return client.get_dataset(ref)
    except gcp_exceptions.NotFound:
        ref.location = "US"
        created = client.create_dataset(ref, exists_ok=True)
        print(f"created dataset {created.full_dataset_id}")
        return created


def create_bq_tables(
    tables: list[PgTable],
    project_id: str | None = None,
    dataset_id: str | None = None,
) -> None:
    default_project, default_dataset = bq_target()
    project_id = project_id or default_project
    dataset_id = dataset_id or default_dataset
    client = get_client(project_id)
    ensure_dataset(client, dataset_id)

    print(f"postgres {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
    print(f"bigquery {client.project}.{dataset_id}")
    print(f"tables to create: {len(tables)}")

    for table in tables:
        schema = [_pg_type_to_bq(c) for c in table.columns]
        table_ref = f"{client.project}.{dataset_id}.{table.name}"
        bq_table = bigquery.Table(table_ref, schema=schema)
        try:
            client.get_table(table_ref)
            print(f"  exists  {table.name} ({len(schema)} cols)")
        except gcp_exceptions.NotFound:
            client.create_table(bq_table)
            cols = ", ".join(f"{c.name}:{f.field_type}" for c, f in zip(table.columns, schema))
            print(f"  created {table.name} ({len(schema)} cols): {cols}")


def main() -> int:
    try:
        tables = fetch_pg_tables()
    except psycopg2.Error as exc:
        print(f"postgres error: {exc}")
        return 1

    if not tables:
        print(f"no base tables in schema {PG_SCHEMA}")
        return 1

    try:
        create_bq_tables(tables)
    except Exception as exc:
        print(f"bigquery error: {exc}")
        return 1

    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
