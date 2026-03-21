from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_MARKERS = (".git", "pyproject.toml", "pnpm-workspace.yaml")


def _find_dotenv() -> str | None:
    """Walk up from this file to find the repo-root .env.

    Looks for common repo-root markers (.git, pyproject.toml,
    pnpm-workspace.yaml) so the lookup works both in a normal checkout
    (where .git exists) and inside Docker images (where .git is excluded
    but pyproject.toml / pnpm-workspace.yaml are present).
    Returns *None* when no .env is found so pydantic-settings still reads
    real environment variables without error.
    """
    current = Path(__file__).resolve().parent
    for ancestor in (current, *current.parents):
        if any((ancestor / m).exists() for m in _REPO_MARKERS):
            candidate = ancestor / ".env"
            if candidate.is_file():
                return str(candidate)
            return None
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_find_dotenv(), extra="ignore")

    # -- Infrastructure --
    database_url: str = "postgresql+psycopg://contentlab:contentlab@localhost:5433/contentlab"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "http://localhost:9000"
    minio_bucket: str = "content-lab"
    minio_root_user: str = "minioadmin"
    minio_root_password: SecretStr = SecretStr("minioadmin")

    # -- Provider keys --
    runway_api_key: SecretStr = SecretStr("changeme")

    # -- Security --
    api_key_salt: SecretStr = SecretStr("changeme-salt")
    jwt_secret: SecretStr | None = None

    # -- Object-storage prefixes --
    package_storage_prefix: str = "packages/"
    asset_storage_prefix: str = "assets/"

    # -- Budget --
    monthly_budget_usd: float = 100.0
    budget_alert_threshold_pct: float = 80.0

    # -- Runtime --
    environment: str = "local"
    log_level: str = "INFO"
