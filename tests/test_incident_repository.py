import datetime
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.api.dto.incident import Incident, IncidentStatus, Severity
from app.repository.incident_repository import IncidentRepository

UTC = datetime.timezone.utc
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def make_incident(**overrides) -> Incident:
    data = dict(
        id=uuid.uuid4(),
        title="payment-service 503s",
        description="Spike of 503s after deploy",
        severity=Severity.SEV2,
        status=IncidentStatus.OPEN,
        service="payment-service",
        reported_at=datetime.datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
        tags=["deploy", "http-503"],
    )
    data.update(overrides)
    return Incident(**data)


def test_add_then_get_returns_equal_incident(session):
    repo = IncidentRepository(session)
    incident = make_incident()
    repo.add(incident)
    session.expire_all()  # force a real SELECT instead of the identity map
    assert repo.get(incident.id) == incident


def test_get_unknown_id_returns_none(session):
    assert IncidentRepository(session).get(uuid.uuid4()) is None


def test_add_duplicate_id_raises_integrity_error(session):
    repo = IncidentRepository(session)
    incident = make_incident()
    repo.add(incident)
    with pytest.raises(IntegrityError):
        repo.add(incident.model_copy())


def test_round_trip_resolved_incident_with_empty_tags(session):
    repo = IncidentRepository(session)
    incident = make_incident(
        status=IncidentStatus.RESOLVED,
        resolved_at=datetime.datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
        root_cause="connection pool exhaustion",
        resolution="increased pool size",
        tags=[],
    )
    repo.add(incident)
    session.expire_all()
    assert repo.get(incident.id) == incident


def test_datetimes_come_back_aware_and_utc(session):
    repo = IncidentRepository(session)
    incident = make_incident()  # reported_at already UTC via the DTO validator
    repo.add(incident)
    session.expire_all()
    loaded = repo.get(incident.id)
    assert loaded.reported_at.tzinfo is not None
    assert loaded.reported_at.utcoffset() == datetime.timedelta(0)


def test_non_utc_input_is_normalised_before_storage(session):
    repo = IncidentRepository(session)
    incident = make_incident(
        reported_at=datetime.datetime(2026, 1, 2, 15, 30, tzinfo=IST)
    )
    repo.add(incident)
    session.expire_all()
    assert repo.get(incident.id).reported_at == datetime.datetime(
        2026, 1, 2, 10, 0, tzinfo=UTC
    )


# --- list(): each test uses a unique service name so existing rows can't interfere ---


def _seed(repo, service, count, **overrides):
    incidents = []
    for i in range(count):
        incident = make_incident(
            service=service,
            reported_at=datetime.datetime(2026, 2, 1, 10, i, tzinfo=UTC),
            **overrides,
        )
        repo.add(incident)
        incidents.append(incident)
    return incidents


def test_list_filters_by_service_newest_first(session):
    repo = IncidentRepository(session)
    service = f"svc-{uuid.uuid4()}"
    seeded = _seed(repo, service, 3)
    _seed(repo, f"other-{uuid.uuid4()}", 2)
    result = repo.list(service=service)
    assert [i.id for i in result] == [i.id for i in reversed(seeded)]


def test_list_filters_by_severity_and_status_combined(session):
    repo = IncidentRepository(session)
    service = f"svc-{uuid.uuid4()}"
    sev1_open = make_incident(service=service, severity=Severity.SEV1)
    sev3_open = make_incident(service=service, severity=Severity.SEV3)
    sev1_mitigated = make_incident(
        service=service, severity=Severity.SEV1, status=IncidentStatus.MITIGATED
    )
    for incident in (sev1_open, sev3_open, sev1_mitigated):
        repo.add(incident)
    result = repo.list(
        service=service, severity=Severity.SEV1, status=IncidentStatus.OPEN
    )
    assert [i.id for i in result] == [sev1_open.id]


def test_list_paginates_without_overlap(session):
    repo = IncidentRepository(session)
    service = f"svc-{uuid.uuid4()}"
    _seed(repo, service, 5)
    page1 = repo.list(service=service, limit=2, offset=0)
    page2 = repo.list(service=service, limit=2, offset=2)
    page3 = repo.list(service=service, limit=2, offset=4)
    ids = [i.id for i in page1 + page2 + page3]
    assert len(ids) == 5
    assert len(set(ids)) == 5


def test_list_without_filters_respects_limit(session):
    repo = IncidentRepository(session)
    _seed(repo, f"svc-{uuid.uuid4()}", 3)
    assert len(repo.list(limit=2)) == 2


def test_list_unknown_service_returns_empty(session):
    assert IncidentRepository(session).list(service=f"none-{uuid.uuid4()}") == []


# --- get_many ---


def test_get_many_returns_found_incidents_keyed_by_id(session):
    repo = IncidentRepository(session)
    a, b = make_incident(), make_incident()
    repo.add(a)
    repo.add(b)
    session.expire_all()
    result = repo.get_many([a.id, b.id, uuid.uuid4()])  # one unknown id
    assert result == {a.id: a, b.id: b}


def test_get_many_with_no_ids_returns_empty_dict(session):
    assert IncidentRepository(session).get_many([]) == {}


# --- delete ---


def test_delete_removes_incident_and_reports_it(session):
    repo = IncidentRepository(session)
    incident = make_incident()
    repo.add(incident)
    assert repo.delete(incident.id) is True
    assert repo.get(incident.id) is None


def test_delete_unknown_id_returns_false(session):
    assert IncidentRepository(session).delete(uuid.uuid4()) is False
