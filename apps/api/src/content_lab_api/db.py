from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass, Session, sessionmaker

from content_lab_shared.settings import Settings

_settings = Settings()

engine = create_engine(_settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


class Base(DeclarativeBase, MappedAsDataclass):
    pass


# Register ORM tables on ``Base.metadata`` for Alembic autogenerate.
import content_lab_api.models  # noqa: E402, F401
