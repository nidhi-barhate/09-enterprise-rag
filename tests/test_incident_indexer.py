"""Indexing incidents into Qdrant.

Uses throwaway collections (never the real 'incidents' one), deleted afterwards.
Unit-style tests use a fake embedder; the last two use real Ollama.
"""

import datetime
import uuid

import pytest

from app.api.dto.incident import Incident, IncidentStatus, Severity
from app.config.qdrant import get_qdrant_client
from app.services.embedding_service import get_embedding_service
from app.services.incident_indexer import (
    EMBEDDING_DIMENSIONS,
    IncidentIndexer,
    ensure_collection,
    incident_to_payload,
    incident_to_text,
)

UTC = datetime.timezone.utc


def make_incident(**overrides) -> Incident:
    data = dict(
        id=uuid.uuid4(),
        title="payment-service 503s",
        description="Spike of 503s after deploy",
        severity=Severity.SEV2,
        status=IncidentStatus.OPEN,
        service="payment-service",
        reported_at=datetime.datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
        tags=["deploy"],
    )
    data.update(overrides)
    return Incident(**data)


class FakeEmbedder:
    """Returns a fixed 4-dimensional vector and records what it was asked to embed."""

    def __init__(self, vector=(1.0, 0.0, 0.0, 0.0)):
        self.vector = list(vector)
        self.texts = []

    def embed(self, text):
        self.texts.append(text)
        return self.vector


@pytest.fixture
def client():
    return get_qdrant_client()


@pytest.fixture
def make_collection(client):
    created = []

    def _make(size):
        name = f"test-{uuid.uuid4()}"
        ensure_collection(client, name=name, size=size)
        created.append(name)
        return name

    yield _make
    for name in created:
        client.delete_collection(name)


# --- pure functions ---


def test_text_contains_meaningful_fields_only():
    incident = make_incident(
        status=IncidentStatus.RESOLVED,
        resolved_at=datetime.datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
        root_cause="connection pool exhaustion",
        resolution="increased pool size",
    )
    text = incident_to_text(incident)
    assert "payment-service 503s" in text
    assert "Spike of 503s after deploy" in text
    assert "Root cause: connection pool exhaustion" in text
    assert "Resolution: increased pool size" in text
    assert "SEV2" not in text  # metadata is payload, not embedded text


def test_text_omits_missing_root_cause_and_resolution():
    text = incident_to_text(make_incident())
    assert "Root cause" not in text
    assert "Resolution" not in text


def test_payload_has_filterable_metadata():
    payload = incident_to_payload(make_incident())
    assert payload == {
        "service": "payment-service",
        "severity": "SEV2",
        "status": "open",
        "tags": ["deploy"],
        "reported_at": "2026-01-02T10:00:00+00:00",
    }


# --- ensure_collection ---


def test_ensure_collection_creates_with_requested_size_and_cosine(client, make_collection):
    name = make_collection(4)
    params = client.get_collection(name).config.params.vectors
    assert params.size == 4
    assert params.distance.value == "Cosine"


def test_ensure_collection_is_idempotent(client, make_collection):
    name = make_collection(4)
    ensure_collection(client, name=name, size=4)  # no error, no change
    assert client.get_collection(name).config.params.vectors.size == 4


def test_ensure_collection_rejects_size_mismatch(client, make_collection):
    name = make_collection(4)
    with pytest.raises(RuntimeError, match="vector size"):
        ensure_collection(client, name=name, size=768)


# --- IncidentIndexer (fake embedder) ---


def test_index_stores_point_with_postgres_uuid_and_payload(client, make_collection):
    name = make_collection(4)
    embedder = FakeEmbedder()
    incident = make_incident()
    IncidentIndexer(client, embedder, collection=name).index(incident)

    point = client.retrieve(collection_name=name, ids=[str(incident.id)])[0]
    assert str(point.id) == str(incident.id)
    assert point.payload == incident_to_payload(incident)
    assert embedder.texts == [incident_to_text(incident)]


def test_reindexing_overwrites_instead_of_duplicating(client, make_collection):
    name = make_collection(4)
    indexer = IncidentIndexer(client, FakeEmbedder(), collection=name)
    incident = make_incident()
    indexer.index(incident)
    indexer.index(incident.model_copy(update={"service": "renamed-service"}))

    assert client.count(collection_name=name).count == 1
    point = client.retrieve(collection_name=name, ids=[str(incident.id)])[0]
    assert point.payload["service"] == "renamed-service"


def test_delete_removes_point(client, make_collection):
    name = make_collection(4)
    indexer = IncidentIndexer(client, FakeEmbedder(), collection=name)
    incident = make_incident()
    indexer.index(incident)
    indexer.delete(incident.id)
    assert client.count(collection_name=name).count == 0


# --- end to end with real Ollama + Qdrant ---


def test_default_collection_size_matches_the_real_embedding_model():
    vector = get_embedding_service().embed("size check")
    assert len(vector) == EMBEDDING_DIMENSIONS


def test_real_embeddings_find_the_semantically_closest_incident(client, make_collection):
    name = make_collection(EMBEDDING_DIMENSIONS)
    embedder = get_embedding_service()
    indexer = IncidentIndexer(client, embedder, collection=name)

    payments = make_incident(
        title="Checkout failing with HTTP 503",
        description="Payment API returns 503 errors after the latest release",
        root_cause="connection pool exhaustion in the payments database",
    )
    search = make_incident(
        title="Search results are stale",
        description="Elasticsearch index is not refreshing, results lag by hours",
        service="search-service",
    )
    indexer.index(payments)
    indexer.index(search)

    query = embedder.embed("payments service returning 503 after deploy")
    result = client.query_points(collection_name=name, query=query, limit=2)
    assert str(result.points[0].id) == str(payments.id)
