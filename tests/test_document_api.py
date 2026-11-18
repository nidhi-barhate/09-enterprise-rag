import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_session
from main import app

VALID_BODY = {
    "title": "DB failover runbook",
    "doc_type": "runbook",
    "service": "payment-service",
    "content": "1. Check replica lag. 2. Promote the replica.",
    "source": "runbooks/db-failover.md",
    "tags": ["database"],
}


@pytest.fixture
def client(session):
    # Reuse the rollback session so API tests never commit into the real DB.
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _post(client, **overrides):
    response = client.post("/documents", json={**VALID_BODY, **overrides})
    assert response.status_code == 201
    return response.json()


def test_post_returns_201_with_generated_id_and_utc_created_at(client):
    body = _post(client)
    uuid.UUID(body["id"])
    created_at = datetime.datetime.fromisoformat(body["created_at"])
    assert created_at.utcoffset() == datetime.timedelta(0)
    assert body["title"] == VALID_BODY["title"]


def test_post_ignores_client_supplied_id_and_created_at(client):
    forced_id = str(uuid.uuid4())
    body = _post(client, id=forced_id, created_at="2000-01-01T00:00:00Z")
    assert body["id"] != forced_id
    assert not body["created_at"].startswith("2000")


def test_post_global_document_without_service_and_source(client):
    body = client.post(
        "/documents",
        json={"title": "On-call handbook", "doc_type": "technical_doc", "content": "x"},
    )
    assert body.status_code == 201
    assert body.json()["service"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"title": "x" * 256},
        {"service": "s" * 101},
        {"service": ""},
        {"source": "u" * 501},
        {"content": ""},
        {"doc_type": "wiki"},
    ],
)
def test_post_invalid_values_return_422(client, overrides):
    assert client.post("/documents", json={**VALID_BODY, **overrides}).status_code == 422


def test_get_returns_created_document(client):
    created = _post(client)
    response = client.get(f"/documents/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_get_unknown_id_returns_404(client):
    assert client.get(f"/documents/{uuid.uuid4()}").status_code == 404


def test_get_malformed_id_returns_422(client):
    assert client.get("/documents/not-a-uuid").status_code == 422


def test_list_filters_by_service_and_type_newest_first(client):
    service = f"svc-{uuid.uuid4()}"
    older = _post(client, service=service)
    newer = _post(client, service=service)
    _post(client, service=service, doc_type="technical_doc")
    _post(client, service=f"other-{uuid.uuid4()}")
    response = client.get(
        "/documents", params={"service": service, "doc_type": "runbook"}
    )
    assert response.status_code == 200
    assert [d["id"] for d in response.json()] == [newer["id"], older["id"]]


def test_list_limit_and_offset(client):
    service = f"svc-{uuid.uuid4()}"
    for _ in range(3):
        _post(client, service=service)
    page = client.get("/documents", params={"service": service, "limit": 2, "offset": 2})
    assert len(page.json()) == 1


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"doc_type": "wiki"}],
)
def test_list_invalid_params_return_422(client, params):
    assert client.get("/documents", params=params).status_code == 422
