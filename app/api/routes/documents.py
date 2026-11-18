import datetime
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_document_indexer, get_session
from app.api.dto.document import Document, DocumentCreate, DocumentType
from app.repository.document_repository import DocumentRepository
from app.services.document_indexer import DocumentIndexer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=Document, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreate,
    session: Session = Depends(get_session),
    indexer: DocumentIndexer = Depends(get_document_indexer),
):
    document = Document(
        id=uuid.uuid4(),
        created_at=datetime.datetime.now(datetime.timezone.utc),
        **payload.model_dump(),
    )
    DocumentRepository(session).add(document)
    # Best effort, like incidents: PostgreSQL is the source of truth, so an
    # embedding/Qdrant outage must not block saving a document. A missed index
    # is healed by `python -m app.scripts.reindex`.
    try:
        indexer.index(document)
    except Exception:
        logger.warning("Failed to index document %s", document.id, exc_info=True)
    return document


@router.get("", response_model=list[Document])
def list_documents(
    service: str | None = None,
    doc_type: DocumentType | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    return DocumentRepository(session).list(
        service=service, doc_type=doc_type, limit=limit, offset=offset
    )


@router.get("/{document_id}", response_model=Document)
def get_document(document_id: uuid.UUID, session: Session = Depends(get_session)):
    document = DocumentRepository(session).get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document
