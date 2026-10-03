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
    # Local YT Data API quota estimate (logs/yt_quota/). Soft-stop harvest at WARN_AT.
    YT_QUOTA_LIMIT: int = 10_000
    YT_QUOTA_WARN_AT: int = 9500
    # apply-is-short: video rows per UPDATE batch (one statement: TRUE/FALSE via LEFT JOIN).
    APPLY_IS_SHORT_VIDEO_BATCH: int = 5000
    OAI_API_KEY: str
    GOOGLE_SHEETS_API_KEY: str = ""

    # BigQuery analytical warehouse sync only (PG → BQ via app.bq.sync).
    # Auth via ADC or GOOGLE_APPLICATION_CREDENTIALS.
    BQ_PROJECT_ID: str | None = None
    BQ_DATASET: str | None = None
    # Prefer service-account JSON key for stable scripts (path outside repo).
    # If set, used instead of user ADC from `gcloud auth application-default login`.
    GOOGLE_APPLICATION_CREDENTIALS: str | None = None

    SECRET_KEY: str
    ALGORITHM: str

    # ntfy.sh (or self-hosted): phone/push alerts for pipeline runs.
    # LEVEL: off = silent; error = failures only; info = start/stop steps + errors.
    # Override per run: python -m app.main ... --ntfy info
    NTFY_SERVER: str = "https://ntfy.sh"
    NTFY_TOPIC: str = ""
    NTFY_LEVEL: Literal["off", "error", "info"] = "off"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
