import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import content_lab_api.models  # noqa: F401  ensure models registered
from content_lab_api.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_url() -> str:
    """Prefer DATABASE_URL env var over the hardcoded alembic.ini value.

    This lets migrations run both locally (where alembic.ini's localhost
    default is fine) and inside Docker (where DATABASE_URL points at the
    ``postgres`` service name).
    """
    return os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url", "")


def run_migrations_offline() -> None:
    context.configure(url=_get_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_get_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
