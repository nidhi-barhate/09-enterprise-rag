"""Retrieval: question -> Qdrant (ids + scores) -> Postgres (incident data).

Postgres rows live in the rolled-back `session` fixture; Qdrant collections are
throwaway and deleted afterwards. Most tests use a keyword-based fake embedder so
rankings are deterministic; the last test uses real Ollama.
"""

import datetime
import uuid

import pytest

from app.api.dto.incident import Incident, IncidentStatus, Severity
from app.config.qdrant import get_qdrant_client
from app.repository.incident_repository import IncidentRepository
from app.services.embedding_service import get_embedding_service
from app.services.incident_indexer import (
    EMBEDDING_DIMENSIONS,
    IncidentIndexer,
    ensure_collection,
)
from app.services.incident_search_service import IncidentSearchService

UTC = datetime.timezone.utc


def make_incident(**overrides) -> Incident:
    data = dict(
        id=uuid.uuid4(),
        title="generic incident",
        description="something happened",
        severity=Severity.SEV2,
        status=IncidentStatus.OPEN,
        service="svc",
        reported_at=datetime.datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
    )
    data.update(overrides)
    return Incident(**data)


class KeywordEmbedder:
    """Deterministic 4-d vectors: 'payment' -> x axis, 'search' -> y axis, else z."""

    def embed(self, text):
        lowered = text.lower()
        if "payment" in lowered:
            return [1.0, 0.0, 0.0, 0.0]
        if "search" in lowered:
            return [0.0, 1.0, 0.0, 0.0]
        return [0.0, 0.0, 1.0, 0.0]


@pytest.fixture
def client():
    return get_qdrant_client()


@pytest.fixture
def collection(client):
    name = f"test-{uuid.uuid4()}"
    ensure_collection(client, name=name, size=4)
    yield name
    client.delete_collection(name)


@pytest.fixture
def setup(client, collection, session):
    repo = IncidentRepository(session)
    indexer = IncidentIndexer(client, KeywordEmbedder(), collection=collection)
    search = IncidentSearchService(
        client, KeywordEmbedder(), repo, collection=collection
    )

    def add(incident, *, in_postgres=True):
        if in_postgres:
            repo.add(incident)
        indexer.index(incident)
        return incident

    return add, search


def test_results_are_ranked_by_similarity_and_hydrated_from_postgres(setup):
    add, search = setup
    payments = add(make_incident(title="payment failures", service="payments"))
    unrelated = add(make_incident(title="disk full on batch box"))
    hits = search.search("payment problem", limit=2)
    assert [h.incident.id for h in hits] == [payments.id, unrelated.id]
    assert hits[0].incident == payments  # full Incident object from Postgres
    assert hits[0].score == pytest.approx(1.0)
    assert hits[0].score > hits[1].score


def test_filter_by_service(setup):
    add, search = setup
    add(make_incident(title="payment failures", service="payments"))
    other = add(make_incident(title="payment retries", service="billing"))
    hits = search.search("payment", service="billing")
    assert [h.incident.id for h in hits] == [other.id]


def test_filters_combine_with_and(setup):
    add, search = setup
    add(make_incident(title="payment a", service="payments", severity=Severity.SEV3))
    match = add(make_incident(title="payment b", service="payments", severity=Severity.SEV1))
    hits = search.search("payment", service="payments", severity=Severity.SEV1)
    assert [h.incident.id for h in hits] == [match.id]


def test_filter_by_status(setup):
    add, search = setup
    add(make_incident(title="payment open"))
    mitigated = add(make_incident(title="payment mitigated", status=IncidentStatus.MITIGATED))
    hits = search.search("payment", status=IncidentStatus.MITIGATED)
    assert [h.incident.id for h in hits] == [mitigated.id]


def test_limit_caps_results(setup):
    add, search = setup
    for _ in range(3):
        add(make_incident(title="payment issue"))
    assert len(search.search("payment", limit=2)) == 2


def test_min_score_drops_weak_matches(setup):
    add, search = setup
    payments = add(make_incident(title="payment failures"))
    add(make_incident(title="search is slow"))  # orthogonal vector, score 0.0
    hits = search.search("payment", min_score=0.5)
    assert [h.incident.id for h in hits] == [payments.id]


def test_hit_missing_from_postgres_is_skipped(setup):
    add, search = setup
    kept = add(make_incident(title="payment kept"))
    add(make_incident(title="payment ghost"), in_postgres=False)  # index drift
    hits = search.search("payment")
    assert [h.incident.id for h in hits] == [kept.id]


def test_no_matches_returns_empty_list(setup):
    _, search = setup
    assert search.search("payment") == []


def test_invalid_limit_is_rejected_before_any_search():
    service = IncidentSearchService(None, KeywordEmbedder(), None)
    with pytest.raises(ValueError):
        service.search("payment", limit=0)


# --- real Ollama + Qdrant + Postgres ---


def test_real_embeddings_end_to_end(client, session):
    name = f"test-{uuid.uuid4()}"
    ensure_collection(client, name=name, size=EMBEDDING_DIMENSIONS)
    try:
        embedder = get_embedding_service()
        repo = IncidentRepository(session)
        indexer = IncidentIndexer(client, embedder, collection=name)
        search = IncidentSearchService(client, embedder, repo, collection=name)

        payments = make_incident(
            title="Checkout failing with HTTP 503",
            description="Payment API returns 503 errors after the latest release",
            root_cause="connection pool exhaustion in the payments database",
            service="payments",
        )
        stale = make_incident(
            title="Search results are stale",
            description="Elasticsearch index is not refreshing, results lag by hours",
            service="search",
        )
        for incident in (payments, stale):
            repo.add(incident)
            indexer.index(incident)

        hits = search.search("payments service returning 503 after deploy", limit=2)
        assert hits[0].incident.id == payments.id

        only_search = search.search("anything is broken", service="search")
        assert [h.incident.id for h in only_search] == [stale.id]
    finally:
        client.delete_collection(name)
