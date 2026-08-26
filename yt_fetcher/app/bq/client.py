"""
BigQuery client and connectivity smoke test.

Auth is NOT login/password. Google Cloud uses credentials (identity + permissions):

1. Local dev (recommended first step):
   - Install gcloud: https://cloud.google.com/sdk/docs/install
   - gcloud auth application-default login
   - ADC is picked up automatically; no key file needed.

2. Scripts / VPS / CI (production-style):
   - GCP Console -> IAM -> Service Accounts -> Keys -> JSON key
   - Save outside the repo, e.g. ../secrets/ytratings-bq-key.json
   - Set env var:
       GOOGLE_APPLICATION_CREDENTIALS=C:/path/to/key.json
   - Service account needs at least:
       roles/bigquery.user          (run queries)
       roles/bigquery.dataEditor    (load/write tables later)

3. Optional env vars (see app.config.Settings):
       BQ_PROJECT_ID=my-gcp-project
       BQ_DATASET=ytratings

Run (requires dev deps: poetry install --with dev):
    poetry run python -m app.bq.client
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from google.api_core import exceptions as gcp_exceptions
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery
from google.oauth2 import service_account

from app.config import settings


@dataclass
class BqAuthInfo:
    method: str
    project_id: str | None
    credentials_path: str | None
    service_account_email: str | None


@dataclass
class BqTestResult:
    ok: bool
    auth: BqAuthInfo
    ping_query: str | None = None
    ping_value: int | None = None
    datasets: list[str] | None = None
    dataset_tables: dict[str, list[str]] | None = None
    error: str | None = None
    hint: str | None = None


def _resolve_project_id(explicit: str | None = None) -> str | None:
    return (
        explicit
        or settings.BQ_PROJECT_ID
        or os.environ.get("BQ_PROJECT_ID")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCLOUD_PROJECT")
    )


def describe_auth(project_id: str | None = None) -> BqAuthInfo:
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    resolved_project = _resolve_project_id(project_id)

    if creds_path:
        if not os.path.isfile(creds_path):
            return BqAuthInfo(
                method="service_account_file_missing",
                project_id=resolved_project,
                credentials_path=creds_path,
                service_account_email=None,
            )
        creds = service_account.Credentials.from_service_account_file(creds_path)
        return BqAuthInfo(
            method="service_account_json",
            project_id=resolved_project or creds.project_id,
            credentials_path=os.path.abspath(creds_path),
            service_account_email=getattr(creds, "service_account_email", None),
        )

    return BqAuthInfo(
        method="application_default_credentials",
        project_id=resolved_project,
        credentials_path=None,
        service_account_email=None,
    )


def get_client(project_id: str | None = None) -> bigquery.Client:
    resolved_project = _resolve_project_id(project_id)
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if creds_path:
        if not os.path.isfile(creds_path):
            raise FileNotFoundError(
                f"GOOGLE_APPLICATION_CREDENTIALS points to missing file: {creds_path}"
            )
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return bigquery.Client(
            project=resolved_project or credentials.project_id,
            credentials=credentials,
        )

    if not resolved_project:
        raise DefaultCredentialsError(
            "Set BQ_PROJECT_ID in .env or run: gcloud config set project YOUR_PROJECT"
        )

    return bigquery.Client(project=resolved_project)


def test_connection(
    project_id: str | None = None,
    dataset_id: str | None = None,
    list_datasets: bool = True,
    max_datasets: int = 20,
) -> BqTestResult:
    """
    Smoke test: create client, run SELECT 1, optionally list datasets/tables.
    """
    auth = describe_auth(project_id)
    dataset_id = dataset_id or settings.BQ_DATASET

    try:
        client = get_client(project_id)
    except DefaultCredentialsError as exc:
        return BqTestResult(
            ok=False,
            auth=auth,
            error=str(exc),
            hint=(
                "Local: run `gcloud auth application-default login` "
                "or set GOOGLE_APPLICATION_CREDENTIALS to a service account JSON key."
            ),
        )
    except FileNotFoundError as exc:
        return BqTestResult(
            ok=False,
            auth=auth,
            error=str(exc),
            hint="Download a JSON key for a service account and fix the path in .env.",
        )

    auth.project_id = auth.project_id or client.project

    try:
        ping_job = client.query("SELECT 1 AS ok")
        ping_row = next(iter(ping_job.result()))
        ping_value = int(ping_row["ok"])
    except gcp_exceptions.GoogleAPICallError as exc:
        return BqTestResult(
            ok=False,
            auth=auth,
            error=f"Query failed: {exc}",
            hint=(
                "Check that BigQuery API is enabled and the identity has "
                "roles/bigquery.user (and dataViewer/dataEditor as needed)."
            ),
        )

    datasets: list[str] = []
    dataset_tables: dict[str, list[str]] = {}

    if list_datasets:
        try:
            for i, ds in enumerate(client.list_datasets()):
                if i >= max_datasets:
                    break
                datasets.append(ds.dataset_id)
        except gcp_exceptions.GoogleAPICallError as exc:
            return BqTestResult(
                ok=False,
                auth=auth,
                ping_query="SELECT 1 AS ok",
                ping_value=ping_value,
                error=f"list_datasets failed: {exc}",
                hint="Query works, but listing datasets may need bigquery.datasets.list permission.",
            )

        if dataset_id and dataset_id in datasets:
            tables = list(client.list_tables(f"{client.project}.{dataset_id}"))
            dataset_tables[dataset_id] = [table.table_id for table in tables[:50]]

    return BqTestResult(
        ok=True,
        auth=auth,
        ping_query="SELECT 1 AS ok",
        ping_value=ping_value,
        datasets=datasets,
        dataset_tables=dataset_tables or None,
    )


def _print_result(result: BqTestResult) -> None:
    print("=== BigQuery connectivity test ===")
    print(f"ok: {result.ok}")
    print(f"auth.method: {result.auth.method}")
    print(f"auth.project_id: {result.auth.project_id}")
    if result.auth.credentials_path:
        print(f"auth.credentials_path: {result.auth.credentials_path}")
    if result.auth.service_account_email:
        print(f"auth.service_account_email: {result.auth.service_account_email}")

    if result.ping_value is not None:
        print(f"ping: {result.ping_query} -> {result.ping_value}")

    if result.datasets is not None:
        print(f"datasets ({len(result.datasets)}): {', '.join(result.datasets) or '(none)'}")

    if result.dataset_tables:
        for ds, tables in result.dataset_tables.items():
            print(f"tables in {ds} ({len(tables)}): {', '.join(tables) or '(none)'}")

    if result.error:
        print(f"error: {result.error}")
    if result.hint:
        print(f"hint: {result.hint}")


def main() -> int:
    result = test_connection()
    _print_result(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
