from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    LOG_LEVEL: Literal["INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"]

    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASS: str
    DB_NAME: str

    @property
    def DATABASE_URL(self):
        # return f"postgresql://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # SECRET_AUTH: str

    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    # @property
    # def DATABASE_URL(self):
    #     return f"sqlite:///../data/data.db"

    YT_API_KEY: str
    # Host swap for googleapiclient (discovery paths stay intact). Some VPS
    # can't TLS to youtube.googleapis.com; www.googleapis.com is the same API.
    # Example: https://www.googleapis.com/  (trailing slash ok)
    YT_API_ROOT_URL: str = "https://www.googleapis.com/"
    # Null-duration backfill: DB keyset page size (API still chunks by 50).
    YT_DETAIL_BATCH_SIZE: int = 5000
    # apply-is-short: channels per UPDATE batch (TRUE then FALSE for each chunk).
    # Keep small — set_false does NOT EXISTS vs playlist_shorts (heavy without index).
    APPLY_IS_SHORT_CHANNEL_BATCH: int = 10
    OAI_API_KEY: str
    GOOGLE_SHEETS_API_KEY: str = ""

    # BigQuery (optional until migration; auth via ADC or GOOGLE_APPLICATION_CREDENTIALS)
    BQ_PROJECT_ID: str | None = None
    BQ_DATASET: str | None = None
    # Prefer service-account JSON key for stable scripts (path outside repo).
    # If set, used instead of user ADC from `gcloud auth application-default login`.
    GOOGLE_APPLICATION_CREDENTIALS: str | None = None
    # Where raw ingest (channel/video/stat) is written. report/FastAPI stay on Postgres.
    RAW_DB: Literal["postgres", "bigquery"] = "postgres"

    SECRET_KEY: str
    ALGORITHM: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
