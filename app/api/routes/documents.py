import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.dto.document import Document, DocumentCreate, DocumentType
from app.repository.document_repository import DocumentRepository

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=Document, status_code=status.HTTP_201_CREATED)
def create_document(payload: DocumentCreate, session: Session = Depends(get_session)):
    document = Document(
        id=uuid.uuid4(),
        created_at=datetime.datetime.now(datetime.timezone.utc),
        **payload.model_dump(),
    )
    DocumentRepository(session).add(document)
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
