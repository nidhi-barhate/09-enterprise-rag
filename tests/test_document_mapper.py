import datetime
import uuid

import pytest
from pydantic import ValidationError

from app.api.dto.document import Document, DocumentType
from app.repository.document_mapper import to_domain, to_record

UTC = datetime.timezone.utc
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


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


def test_round_trip():
    document = make_document()
    assert to_domain(to_record(document)) == document


def test_round_trip_global_document_without_service_and_source():
    document = make_document(service=None, source=None, tags=[])
    assert to_domain(to_record(document)) == document


def test_to_record_stores_doc_type_as_string():
    assert to_record(make_document()).doc_type == "runbook"


def test_created_at_is_normalised_to_utc():
    document = make_document(
        created_at=datetime.datetime(2026, 1, 2, 15, 30, tzinfo=IST)
    )
    assert document.created_at == datetime.datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
    assert document.created_at.utcoffset() == datetime.timedelta(0)


def test_naive_created_at_is_rejected():
    with pytest.raises(ValidationError):
        make_document(created_at=datetime.datetime(2026, 1, 2, 10, 0))


def test_empty_content_is_rejected():
    with pytest.raises(ValidationError):
        make_document(content="")


def test_to_domain_rejects_unknown_doc_type():
    record = to_record(make_document())
    record.doc_type = "wiki"
    with pytest.raises(ValueError):
        to_domain(record)


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "x" * 256},
        {"service": "s" * 101},
        {"service": ""},
        {"source": "u" * 501},
    ],
)
def test_over_limit_values_are_rejected(overrides):
    with pytest.raises(ValidationError):
        make_document(**overrides)


def test_values_at_the_limit_are_accepted():
    document = make_document(title="x" * 255, service="s" * 100, source="u" * 500)
    assert len(document.title) == 255
