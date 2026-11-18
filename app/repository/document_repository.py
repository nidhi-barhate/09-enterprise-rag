import uuid
from collections.abc import Iterable

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

    def get_many(self, document_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Document]:
        """One query for many ids. Unknown ids are simply absent from the result."""
        ids = set(document_ids)
        if not ids:
            return {}
        stmt = select(DocumentRecord).where(DocumentRecord.id.in_(ids))
        return {r.id: to_domain(r) for r in self._session.scalars(stmt)}

    def delete(self, document_id: uuid.UUID) -> bool:
        """Delete one document. Returns False if it did not exist."""
        record = self._session.get(DocumentRecord, document_id)
        if record is None:
            return False
        self._session.delete(record)
        self._session.flush()
        return True

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
