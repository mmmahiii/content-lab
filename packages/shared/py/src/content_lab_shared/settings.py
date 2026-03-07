from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://contentlab:contentlab@localhost:5432/contentlab"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "http://localhost:9000"
    minio_bucket: str = "content-lab"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"

    runway_api_key: str = "changeme"
