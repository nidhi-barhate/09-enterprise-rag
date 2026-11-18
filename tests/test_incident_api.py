import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.api.deps import get_session
from main import app

VALID_BODY = {
    "title": "payment-service 503s",
    "description": "Spike of 503s after deploy",
    "severity": "SEV2",
    "status": "open",
    "service": "payment-service",
    "reported_at": "2026-01-02T10:00:00Z",
    "tags": ["deploy"],
}


@pytest.fixture
def client(session):
    # Reuse the rollback session so API tests never commit into the real DB.
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_post_returns_201_with_generated_id(client):
    response = client.post("/incidents", json=VALID_BODY)
    assert response.status_code == 201
    body = response.json()
    uuid.UUID(body["id"])
    assert body["title"] == VALID_BODY["title"]


def test_post_ignores_client_supplied_id(client):
    forced = str(uuid.uuid4())
    response = client.post("/incidents", json={**VALID_BODY, "id": forced})
    assert response.status_code == 201
    assert response.json()["id"] != forced


def test_post_resolved_without_resolved_at_returns_422(client):
    response = client.post("/incidents", json={**VALID_BODY, "status": "resolved"})
    assert response.status_code == 422


def test_get_returns_created_incident(client):
    created = client.post("/incidents", json=VALID_BODY).json()
    response = client.get(f"/incidents/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_get_unknown_id_returns_404(client):
    assert client.get(f"/incidents/{uuid.uuid4()}").status_code == 404


def test_get_malformed_id_returns_422(client):
    assert client.get("/incidents/not-a-uuid").status_code == 422


# --- get_session transaction boundary (no database: SessionLocal is mocked) ---


def test_get_session_commits_on_success(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(deps, "SessionLocal", lambda: fake)
    gen = get_session()
    assert next(gen) is fake
    with pytest.raises(StopIteration):
        next(gen)
    fake.commit.assert_called_once()
    fake.rollback.assert_not_called()
    fake.close.assert_called_once()


def test_get_session_rolls_back_on_error(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(deps, "SessionLocal", lambda: fake)
    gen = get_session()
    next(gen)
    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("boom"))
    fake.commit.assert_not_called()
    fake.rollback.assert_called_once()
    fake.close.assert_called_once()


# --- GET /incidents (list) ---


def _post(client, service, **overrides):
    body = {**VALID_BODY, "service": service, **overrides}
    response = client.post("/incidents", json=body)
    assert response.status_code == 201
    return response.json()


def test_list_filters_by_service_newest_first(client):
    service = f"svc-{uuid.uuid4()}"
    older = _post(client, service, reported_at="2026-03-01T10:00:00Z")
    newer = _post(client, service, reported_at="2026-03-01T11:00:00Z")
    _post(client, f"other-{uuid.uuid4()}")
    response = client.get("/incidents", params={"service": service})
    assert response.status_code == 200
    assert [i["id"] for i in response.json()] == [newer["id"], older["id"]]


def test_list_filters_by_severity_and_status(client):
    service = f"svc-{uuid.uuid4()}"
    match = _post(client, service, severity="SEV1")
    _post(client, service, severity="SEV3")
    response = client.get(
        "/incidents", params={"service": service, "severity": "SEV1", "status": "open"}
    )
    assert [i["id"] for i in response.json()] == [match["id"]]


def test_list_limit_and_offset(client):
    service = f"svc-{uuid.uuid4()}"
    for minute in range(3):
        _post(client, service, reported_at=f"2026-03-01T10:0{minute}:00Z")
    page = client.get("/incidents", params={"service": service, "limit": 2, "offset": 2})
    assert len(page.json()) == 1


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"severity": "SEV9"},
        {"status": "closed"},
    ],
)
def test_list_invalid_params_return_422(client, params):
    assert client.get("/incidents", params=params).status_code == 422


# --- length limits: over-long values must be a 422, never a database 500 ---


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "x" * 256},
        {"service": "s" * 101},
        {"service": ""},
    ],
)
def test_post_over_limit_values_return_422(client, overrides):
    assert client.post("/incidents", json={**VALID_BODY, **overrides}).status_code == 422


def test_post_values_at_the_limit_are_accepted(client):
    body = {**VALID_BODY, "title": "x" * 255, "service": "s" * 100}
    assert client.post("/incidents", json=body).status_code == 201
