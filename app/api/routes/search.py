from fastapi import APIRouter, Depends, HTTPException, Query
from qdrant_client.http.exceptions import ApiException

from app.api.deps import get_document_search_service, get_incident_search_service
from app.api.dto.document import DocumentType
from app.api.dto.incident import IncidentStatus, Severity
from app.services.document_search_service import DocumentHit, DocumentSearchService
from app.services.embedding_service import EmbeddingError
from app.services.incident_search_service import IncidentHit, IncidentSearchService

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/incidents", response_model=list[IncidentHit])
def search_incidents(
    q: str = Query(min_length=1, description="Natural-language question"),
    service: str | None = None,
    severity: Severity | None = None,
    # Aliased to avoid clashing with fastapi's `status` in other modules.
    incident_status: IncidentStatus | None = Query(None, alias="status"),
    limit: int = Query(5, ge=1, le=50),
    min_score: float | None = Query(None, ge=-1.0, le=1.0),
    search_service: IncidentSearchService = Depends(get_incident_search_service),
):
    try:
        return search_service.search(
            q,
            service=service,
            severity=severity,
            status=incident_status,
            limit=limit,
            min_score=min_score,
        )
    except ValueError as exc:  # e.g. whitespace-only query
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (EmbeddingError, ApiException) as exc:
        # Embedding model or vector store unavailable: not the client's fault.
        raise HTTPException(status_code=503, detail="Search is temporarily unavailable") from exc


@router.get("/documents", response_model=list[DocumentHit])
def search_documents(
    q: str = Query(min_length=1, description="Natural-language question"),
    service: str | None = None,
    doc_type: DocumentType | None = None,
    limit: int = Query(5, ge=1, le=50),
    min_score: float | None = Query(None, ge=-1.0, le=1.0),
    search_service: DocumentSearchService = Depends(get_document_search_service),
):
    """Best matching passage of each document. A document without a service
    applies everywhere, so it is kept when filtering by service."""
    try:
        return search_service.search(
            q, service=service, doc_type=doc_type, limit=limit, min_score=min_score
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (EmbeddingError, ApiException) as exc:
        raise HTTPException(status_code=503, detail="Search is temporarily unavailable") from exc
