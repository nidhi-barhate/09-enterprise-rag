from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.config.connection import SessionLocal


def get_session() -> Iterator[Session]:
    """One Session (= one transaction) per request.

    Commit on success, roll back on any exception, always close.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
