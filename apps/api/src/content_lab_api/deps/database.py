"""Database session dependency for FastAPI route injection."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from content_lab_api.db import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
