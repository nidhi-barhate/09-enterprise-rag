from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config.connection import SessionLocal
from app.config.qdrant import get_qdrant_client
from app.repository.incident_repository import IncidentRepository
from app.services.embedding_service import get_embedding_service
from app.services.incident_indexer import IncidentIndexer
from app.services.incident_search_service import IncidentSearchService


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


def get_incident_indexer() -> IncidentIndexer:
    return IncidentIndexer(get_qdrant_client(), get_embedding_service())


def get_incident_search_service(
    session: Session = Depends(get_session),
) -> IncidentSearchService:
    return IncidentSearchService(
        get_qdrant_client(), get_embedding_service(), IncidentRepository(session)
    )
