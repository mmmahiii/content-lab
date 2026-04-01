from __future__ import annotations

import os
from unittest.mock import patch

from pydantic import SecretStr

from content_lab_shared.settings import Settings


class TestSettingsDefaults:
    """All defaults must match the local development stack."""

    def test_infrastructure_defaults(self) -> None:
        s = Settings()
        assert (
            s.database_url == "postgresql+psycopg://contentlab:contentlab@localhost:5433/contentlab"
        )
        assert s.redis_url == "redis://localhost:6379/0"
        assert s.minio_endpoint == "http://localhost:9000"
        assert s.minio_bucket == "content-lab"
        assert s.minio_root_user == "minioadmin"
        assert s.minio_root_password.get_secret_value() == "minioadmin"

    def test_provider_key_defaults(self) -> None:
        s = Settings()
        assert isinstance(s.runway_api_key, SecretStr)
        assert s.runway_api_key.get_secret_value() == "changeme"
        assert s.runway_api_base_url == "https://api.dev.runwayml.com"
        assert s.runway_api_version == "2024-11-06"

    def test_security_defaults(self) -> None:
        s = Settings()
        assert isinstance(s.api_key_salt, SecretStr)
        assert s.api_key_salt.get_secret_value() == "changeme-salt"
        assert s.jwt_secret is None

    def test_storage_prefix_defaults(self) -> None:
        s = Settings()
        assert s.package_storage_prefix == "packages/"
        assert s.asset_storage_prefix == "assets/"

    def test_budget_defaults(self) -> None:
        s = Settings()
        assert s.monthly_budget_usd == 100.0
        assert s.budget_alert_threshold_pct == 80.0

    def test_runtime_defaults(self) -> None:
        s = Settings()
        assert s.environment == "local"
        assert s.log_level == "INFO"


class TestSettingsEnvOverride:
    """Env vars override defaults (pydantic-settings contract)."""

    def test_override_via_env(self) -> None:
        overrides = {
            "REDIS_URL": "redis://custom:6380/1",
            "JWT_SECRET": "super-secret",
            "MONTHLY_BUDGET_USD": "250.0",
            "ENVIRONMENT": "staging",
            "LOG_LEVEL": "DEBUG",
        }
        with patch.dict(os.environ, overrides, clear=False):
            s = Settings()
        assert s.redis_url == "redis://custom:6380/1"
        assert s.jwt_secret is not None
        assert s.jwt_secret.get_secret_value() == "super-secret"
        assert s.monthly_budget_usd == 250.0
        assert s.environment == "staging"
        assert s.log_level == "DEBUG"


class TestSecretStrFields:
    """Secret-bearing fields must use SecretStr so they don't leak in repr/str."""

    def test_secret_fields_hidden_in_repr(self) -> None:
        s = Settings()
        text = repr(s)
        assert "minioadmin" not in text or "SecretStr" in text
        assert "changeme" not in text or "SecretStr" in text

    def test_secret_fields_hidden_in_json(self) -> None:
        s = Settings()
        json_str = s.model_dump_json()
        assert "changeme-salt" not in json_str
        assert '"minio_root_password":"**********"' in json_str
        assert '"runway_api_key":"**********"' in json_str
        assert '"api_key_salt":"**********"' in json_str
