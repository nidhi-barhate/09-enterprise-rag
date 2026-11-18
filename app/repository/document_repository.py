import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dto.document import Document, DocumentType
from app.model.document_record import DocumentRecord
from app.repository.document_mapper import to_domain, to_record


class DocumentRepository:
    """Persistence for knowledge documents. The caller owns the transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, document: Document) -> None:
        self._session.add(to_record(document))
        self._session.flush()

    def get(self, document_id: uuid.UUID) -> Document | None:
        record = self._session.get(DocumentRecord, document_id)
        return None if record is None else to_domain(record)

    def list(
        self,
        *,
        service: str | None = None,
        doc_type: DocumentType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Document]:
        """Newest first. Filters are optional and combined with AND."""
        stmt = select(DocumentRecord)
        if service is not None:
            stmt = stmt.where(DocumentRecord.service == service)
        if doc_type is not None:
            stmt = stmt.where(DocumentRecord.doc_type == doc_type.value)
        stmt = (
            stmt.order_by(DocumentRecord.created_at.desc(), DocumentRecord.id)
            .limit(limit)
            .offset(offset)
        )
        return [to_domain(record) for record in self._session.scalars(stmt)]
