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
            # Nested package has a marker (e.g. pyproject) but no .env — keep walking to monorepo root.
            continue
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_find_dotenv(), extra="ignore")

    # -- Infrastructure --
    database_url: str = "postgresql+psycopg://contentlab:contentlab@localhost:5433/contentlab"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "http://localhost:9000"
    # Endpoint browsers use for presigned download links; defaults to minio_endpoint.
    minio_public_endpoint: str | None = None
    minio_bucket: str = "content-lab"
    minio_root_user: str = "minioadmin"
    minio_root_password: SecretStr = SecretStr("minioadmin")

    # -- Provider keys --
    runway_api_key: SecretStr = SecretStr("changeme")
    # Must match the Runway key (dev vs prod); see Runway API docs for your account.
    runway_api_base_url: str = "https://api.dev.runwayml.com"
    runway_api_version: str = "2024-11-06"
    runway_api_mode: str = "live"
    # Cost cap: provider clips (5-10 s each) generated per reel. Longer reels loop these clips
    # (with dissolves) instead of paying for more; 3 covers 30 s of unique footage.
    runway_max_clips_per_reel: int = 3

    # -- Voiceover (text-to-speech) --
    # "" = auto: mock when RUNWAY_API_MODE=mock, elevenlabs when a key is set, else none.
    # Explicit values: mock | elevenlabs | none.
    tts_provider: str = ""
    elevenlabs_api_key: SecretStr = SecretStr("")
    # Default: ElevenLabs' public "Rachel" premade voice.
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_base_url: str = "https://api.elevenlabs.io"

    # -- Music bed under the voice --
    # "" = auto: library when MUSIC_LIBRARY_DIR has audio files, else a generated pad.
    # Explicit values: generated | library | none.
    music_bed_provider: str = ""
    # Folder of tracks you are licensed to use; picked by a word of the mood in the file name.
    music_library_dir: str = ""

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

    @property
    def psycopg_database_url(self) -> str:
        """Return a libpq-compatible URL for direct psycopg.connect() calls."""
        if self.database_url.startswith("postgresql+psycopg://"):
            return "postgresql://" + self.database_url.split("://", 1)[1]
        return self.database_url
