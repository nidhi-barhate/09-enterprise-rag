import datetime
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.api.dto.document import Document, DocumentType
from app.model.document_record import DocumentRecord
from app.repository.document_repository import DocumentRepository

UTC = datetime.timezone.utc


def make_document(**overrides) -> Document:
    data = dict(
        id=uuid.uuid4(),
        title="DB failover runbook",
        doc_type=DocumentType.RUNBOOK,
        service="payment-service",
        content="1. Check replica lag. 2. Promote the replica.",
        source="runbooks/db-failover.md",
        tags=["database", "failover"],
        created_at=datetime.datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
    )
    data.update(overrides)
    return Document(**data)


def test_add_then_get_returns_equal_document(session):
    repo = DocumentRepository(session)
    document = make_document()
    repo.add(document)
    session.expire_all()  # force a real SELECT, not the identity map
    assert repo.get(document.id) == document


def test_get_unknown_id_returns_none(session):
    assert DocumentRepository(session).get(uuid.uuid4()) is None


def test_global_document_without_service_round_trips(session):
    repo = DocumentRepository(session)
    document = make_document(service=None, source=None, tags=[])
    repo.add(document)
    session.expire_all()
    loaded = repo.get(document.id)
    assert loaded == document
    assert loaded.service is None


def test_add_duplicate_id_raises_integrity_error(session):
    repo = DocumentRepository(session)
    document = make_document()
    repo.add(document)
    with pytest.raises(IntegrityError):
        repo.add(document.model_copy())


def test_database_rejects_unknown_doc_type(session):
    # The CHECK constraint is the last line of defence if the DTO is bypassed.
    session.add(
        DocumentRecord(
            id=uuid.uuid4(),
            title="bad",
            doc_type="wiki",
            content="x",
            tags=[],
            created_at=datetime.datetime(2026, 1, 2, tzinfo=UTC),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
