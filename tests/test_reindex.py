import datetime
import uuid

import pytest

from app.api.dto.incident import Incident, IncidentStatus, Severity
from app.config.qdrant import get_qdrant_client
from app.repository.incident_repository import IncidentRepository
from app.services.incident_indexer import IncidentIndexer, ensure_collection
from app.services.reindex import reindex_all

UTC = datetime.timezone.utc


def make_incident(**overrides) -> Incident:
    data = dict(
        id=uuid.uuid4(),
        title="incident",
        description="details",
        severity=Severity.SEV2,
        status=IncidentStatus.OPEN,
        service="svc",
        reported_at=datetime.datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
    )
    data.update(overrides)
    return Incident(**data)


class FixedEmbedder:
    def embed(self, text):
        return [1.0, 0.0, 0.0, 0.0]


@pytest.fixture
def collection():
    client = get_qdrant_client()
    name = f"test-{uuid.uuid4()}"
    ensure_collection(client, name=name, size=4)
    yield name
    client.delete_collection(name)


def test_reindex_all_indexes_every_incident_in_postgres(session, collection):
    repo = IncidentRepository(session)
    mine = [make_incident(service=f"svc-{uuid.uuid4()}") for _ in range(5)]
    for incident in mine:
        repo.add(incident)

    client = get_qdrant_client()
    indexer = IncidentIndexer(client, FixedEmbedder(), collection=collection)
    # Small batch size forces several pages; the dev DB may hold other rows too.
    total = reindex_all(repo, indexer, batch_size=2)

    assert total >= 5
    stored = client.retrieve(collection_name=collection, ids=[str(i.id) for i in mine])
    assert {str(p.id) for p in stored} == {str(i.id) for i in mine}


def test_reindex_all_is_idempotent(session, collection):
    repo = IncidentRepository(session)
    repo.add(make_incident(service=f"svc-{uuid.uuid4()}"))
    client = get_qdrant_client()
    indexer = IncidentIndexer(client, FixedEmbedder(), collection=collection)

    first = reindex_all(repo, indexer)
    second = reindex_all(repo, indexer)

    assert first == second
    assert client.count(collection_name=collection).count == first


# --- documents ---

from app.api.dto.document import Document, DocumentType  # noqa: E402
from app.repository.document_repository import DocumentRepository  # noqa: E402
from app.services.document_indexer import DOCUMENT_FILTER_FIELDS, DocumentIndexer  # noqa: E402
from app.services.reindex import reindex_all_documents  # noqa: E402


class FixedBatchEmbedder:
    def embed_many(self, texts):
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


def make_document() -> Document:
    return Document(
        id=uuid.uuid4(),
        title="Runbook",
        doc_type=DocumentType.RUNBOOK,
        service=f"svc-{uuid.uuid4()}",
        content="Promote the replica to primary.",
        created_at=datetime.datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
    )


@pytest.fixture
def doc_collection():
    client = get_qdrant_client()
    name = f"test-{uuid.uuid4()}"
    ensure_collection(client, name=name, size=4, keyword_fields=DOCUMENT_FILTER_FIELDS)
    yield name
    client.delete_collection(name)


def test_reindex_all_documents_indexes_every_document_in_postgres(session, doc_collection):
    repo = DocumentRepository(session)
    mine = [make_document() for _ in range(5)]
    for document in mine:
        repo.add(document)
    client = get_qdrant_client()
    indexer = DocumentIndexer(client, FixedBatchEmbedder(), collection=doc_collection)

    total = reindex_all_documents(repo, indexer, batch_size=2)

    assert total >= 5
    points, _ = client.scroll(collection_name=doc_collection, limit=1000, with_payload=True)
    indexed_ids = {p.payload["document_id"] for p in points}
    assert {str(d.id) for d in mine} <= indexed_ids


def test_reindex_all_documents_is_idempotent(session, doc_collection):
    repo = DocumentRepository(session)
    repo.add(make_document())
    client = get_qdrant_client()
    indexer = DocumentIndexer(client, FixedBatchEmbedder(), collection=doc_collection)
    reindex_all_documents(repo, indexer)
    first = client.count(collection_name=doc_collection).count
    reindex_all_documents(repo, indexer)
    assert client.count(collection_name=doc_collection).count == first
