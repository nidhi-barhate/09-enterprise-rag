import uuid

from sqlalchemy.orm import Session

from app.api.dto.document import Document
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
