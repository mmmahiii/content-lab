from __future__ import annotations

import os
from unittest.mock import patch

from pydantic import SecretStr

from content_lab_shared.settings import Settings

DEFAULT_TEST_ENV = {
    "DATABASE_URL": "postgresql+psycopg://contentlab:contentlab@localhost:5433/contentlab",
    "REDIS_URL": "redis://localhost:6379/0",
    "MINIO_ENDPOINT": "http://localhost:9000",
    "MINIO_BUCKET": "content-lab",
    "MINIO_ROOT_USER": "minioadmin",
    "MINIO_ROOT_PASSWORD": "minioadmin",
    "RUNWAY_API_KEY": "changeme",
    "RUNWAY_API_BASE_URL": "https://api.dev.runwayml.com",
    "RUNWAY_API_VERSION": "2024-11-06",
    "RUNWAY_API_MODE": "live",
    "API_KEY_SALT": "changeme-salt",
    "JWT_SECRET": "",
    "PACKAGE_STORAGE_PREFIX": "packages/",
    "ASSET_STORAGE_PREFIX": "assets/",
    "MONTHLY_BUDGET_USD": "100.0",
    "BUDGET_ALERT_THRESHOLD_PCT": "80.0",
    "ENVIRONMENT": "local",
    "LOG_LEVEL": "INFO",
}


def load_default_settings() -> Settings:
    with patch.dict(os.environ, DEFAULT_TEST_ENV, clear=True):
        return Settings(_env_file=None)


class TestSettingsDefaults:
    """Declared field defaults (no repo .env); use _env_file=None so local .env cannot override."""

    def test_infrastructure_defaults(self) -> None:
        s = load_default_settings()
        assert (
            s.database_url == "postgresql+psycopg://contentlab:contentlab@localhost:5433/contentlab"
        )
        assert s.redis_url == "redis://localhost:6379/0"
        assert s.minio_endpoint == "http://localhost:9000"
        assert s.minio_bucket == "content-lab"
        assert s.minio_root_user == "minioadmin"
        assert s.minio_root_password.get_secret_value() == "minioadmin"

    def test_provider_key_defaults(self) -> None:
        s = load_default_settings()
        assert isinstance(s.runway_api_key, SecretStr)
        assert s.runway_api_key.get_secret_value() == "changeme"
        assert s.runway_api_base_url == "https://api.dev.runwayml.com"
        assert s.runway_api_version == "2024-11-06"
        assert s.runway_api_mode == "live"

    def test_security_defaults(self) -> None:
        s = load_default_settings()
        assert isinstance(s.api_key_salt, SecretStr)
        assert s.api_key_salt.get_secret_value() == "changeme-salt"
        assert isinstance(s.jwt_secret, SecretStr)
        assert s.jwt_secret.get_secret_value() == ""

    def test_storage_prefix_defaults(self) -> None:
        s = load_default_settings()
        assert s.package_storage_prefix == "packages/"
        assert s.asset_storage_prefix == "assets/"

    def test_budget_defaults(self) -> None:
        s = load_default_settings()
        assert s.monthly_budget_usd == 100.0
        assert s.budget_alert_threshold_pct == 80.0

    def test_runtime_defaults(self) -> None:
        s = load_default_settings()
        assert s.environment == "local"
        assert s.log_level == "INFO"

    def test_psycopg_database_url_strips_sqlalchemy_driver(self) -> None:
        s = load_default_settings()
        assert (
            s.psycopg_database_url == "postgresql://contentlab:contentlab@localhost:5433/contentlab"
        )

    def test_psycopg_database_url_leaves_plain_postgresql_url(self) -> None:
        with patch.dict(
            os.environ,
            {
                **DEFAULT_TEST_ENV,
                "DATABASE_URL": "postgresql://contentlab:contentlab@localhost:5433/contentlab",
            },
            clear=True,
        ):
            s = Settings(_env_file=None)
        assert (
            s.psycopg_database_url == "postgresql://contentlab:contentlab@localhost:5433/contentlab"
        )


class TestSettingsEnvOverride:
    """Env vars override defaults (pydantic-settings contract)."""

    def test_override_via_env(self) -> None:
        overrides = {
            "REDIS_URL": "redis://custom:6380/1",
            "JWT_SECRET": "super-secret",
            "MONTHLY_BUDGET_USD": "250.0",
            "ENVIRONMENT": "staging",
            "LOG_LEVEL": "DEBUG",
            "RUNWAY_API_MODE": "mock",
        }
        with patch.dict(os.environ, overrides, clear=False):
            s = Settings(_env_file=None)
        assert s.redis_url == "redis://custom:6380/1"
        assert s.jwt_secret is not None
        assert s.jwt_secret.get_secret_value() == "super-secret"
        assert s.monthly_budget_usd == 250.0
        assert s.environment == "staging"
        assert s.log_level == "DEBUG"
        assert s.runway_api_mode == "mock"


class TestSecretStrFields:
    """Secret-bearing fields must use SecretStr so they don't leak in repr/str."""

    def test_secret_fields_hidden_in_repr(self) -> None:
        s = load_default_settings()
        text = repr(s)
        assert "minioadmin" not in text or "SecretStr" in text
        assert "changeme" not in text or "SecretStr" in text

    def test_secret_fields_hidden_in_json(self) -> None:
        s = load_default_settings()
        json_str = s.model_dump_json()
        assert "changeme-salt" not in json_str
        assert '"minio_root_password":"**********"' in json_str
        assert '"runway_api_key":"**********"' in json_str
        assert '"api_key_salt":"**********"' in json_str
