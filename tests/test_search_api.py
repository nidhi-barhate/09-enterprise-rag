import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from qdrant_client.http.exceptions import ResponseHandlingException

from app.api.deps import (
    get_incident_indexer,
    get_incident_search_service,
    get_session,
)
from app.api.dto.incident import Incident, IncidentStatus, Severity
from app.config.qdrant import get_qdrant_client
from app.repository.incident_repository import IncidentRepository
from app.services.embedding_service import EmbeddingError, get_embedding_service
from app.services.incident_indexer import (
    EMBEDDING_DIMENSIONS,
    IncidentIndexer,
    ensure_collection,
)
from app.services.incident_search_service import IncidentHit, IncidentSearchService
from main import app

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
    )
    data.update(overrides)
    return Incident(**data)


class FakeSearchService:
    """Records the arguments it was called with and returns canned hits."""

    def __init__(self, hits=None, error=None):
        self.hits = hits or []
        self.error = error
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if self.error:
            raise self.error
        return self.hits


@pytest.fixture
def fake_search():
    service = FakeSearchService()
    app.dependency_overrides[get_incident_search_service] = lambda: service
    yield service
    app.dependency_overrides.clear()


@pytest.fixture
def client(fake_search):
    return TestClient(app)


def test_search_passes_query_and_filters_through(client, fake_search):
    response = client.get(
        "/search/incidents",
        params={
            "q": "payments 503",
            "service": "payment-service",
            "severity": "SEV1",
            "status": "open",
            "limit": 3,
            "min_score": 0.4,
        },
    )
    assert response.status_code == 200
    query, kwargs = fake_search.calls[0]
    assert query == "payments 503"
    assert kwargs == {
        "service": "payment-service",
        "severity": Severity.SEV1,
        "status": IncidentStatus.OPEN,
        "limit": 3,
        "min_score": 0.4,
    }


def test_search_defaults(client, fake_search):
    client.get("/search/incidents", params={"q": "anything"})
    _, kwargs = fake_search.calls[0]
    assert kwargs["limit"] == 5
    assert kwargs["service"] is None
    assert kwargs["min_score"] is None


def test_search_returns_incident_and_score(client, fake_search):
    incident = make_incident()
    fake_search.hits = [IncidentHit(incident=incident, score=0.87)]
    body = client.get("/search/incidents", params={"q": "payments"}).json()
    assert body[0]["score"] == pytest.approx(0.87)
    assert body[0]["incident"]["id"] == str(incident.id)
    assert body[0]["incident"]["title"] == incident.title


@pytest.mark.parametrize(
    "params",
    [
        {},  # q is required
        {"q": ""},
        {"q": "x", "limit": 0},
        {"q": "x", "limit": 51},
        {"q": "x", "min_score": 2},
        {"q": "x", "severity": "SEV9"},
        {"q": "x", "status": "closed"},
    ],
)
def test_search_invalid_params_return_422(client, params):
    assert client.get("/search/incidents", params=params).status_code == 422


def test_blank_query_returns_422(client, fake_search):
    fake_search.error = ValueError("Cannot embed empty text")
    assert client.get("/search/incidents", params={"q": "   "}).status_code == 422


@pytest.mark.parametrize(
    "error",
    [EmbeddingError("ollama down"), ResponseHandlingException("qdrant down")],
)
def test_backend_outage_returns_503_not_500(client, fake_search, error):
    fake_search.error = error
    response = client.get("/search/incidents", params={"q": "payments"})
    assert response.status_code == 503


# --- full stack: POST /incidents -> index -> GET /search/incidents (real Ollama/Qdrant) ---


def test_created_incident_is_searchable_end_to_end(session):
    name = f"test-{uuid.uuid4()}"
    client = get_qdrant_client()
    ensure_collection(client, name=name, size=EMBEDDING_DIMENSIONS)
    embedder = get_embedding_service()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_incident_indexer] = lambda: IncidentIndexer(
        client, embedder, collection=name
    )
    app.dependency_overrides[get_incident_search_service] = lambda: IncidentSearchService(
        client, embedder, IncidentRepository(session), collection=name
    )
    try:
        api = TestClient(app)
        payments = api.post(
            "/incidents",
            json={
                "title": "Checkout failing with HTTP 503",
                "description": "Payment API returns 503 errors after the latest release",
                "severity": "SEV1",
                "status": "open",
                "service": "payments",
                "reported_at": "2026-01-02T10:00:00Z",
            },
        ).json()
        api.post(
            "/incidents",
            json={
                "title": "Search results are stale",
                "description": "Elasticsearch index is not refreshing",
                "severity": "SEV3",
                "status": "open",
                "service": "search",
                "reported_at": "2026-01-02T11:00:00Z",
            },
        )

        hits = api.get(
            "/search/incidents", params={"q": "payments returning 503 after deploy"}
        ).json()
        assert hits[0]["incident"]["id"] == payments["id"]

        filtered = api.get(
            "/search/incidents", params={"q": "something broke", "service": "search"}
        ).json()
        assert [h["incident"]["service"] for h in filtered] == ["search"]
    finally:
        app.dependency_overrides.clear()
        client.delete_collection(name)
