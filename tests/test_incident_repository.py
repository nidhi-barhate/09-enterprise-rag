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
