from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_dotenv() -> str:
    """Walk up from this file to find the repo root .env (directory containing .git)."""
    current = Path(__file__).resolve().parent
    for ancestor in (current, *current.parents):
        candidate = ancestor / ".env"
        if (ancestor / ".git").is_dir() and candidate.is_file():
            return str(candidate)
    return ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_find_dotenv(), extra="ignore")

    database_url: str = "postgresql+psycopg://contentlab:contentlab@localhost:5432/contentlab"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "http://localhost:9000"
    minio_bucket: str = "content-lab"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"

    runway_api_key: str = "changeme"
