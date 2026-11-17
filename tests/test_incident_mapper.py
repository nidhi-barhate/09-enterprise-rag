import datetime
import uuid

import pytest
from pydantic import ValidationError

from app.api.dto.incident import Incident, IncidentStatus, Severity
from app.model.incident_record import IncidentRecord
from app.repository.incident_mapper import to_domain, to_record

UTC = datetime.timezone.utc
REPORTED = datetime.datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
RESOLVED = datetime.datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


def make_incident(**overrides) -> Incident:
    data = dict(
        id=uuid.uuid4(),
        title="payment-service 503s",
        description="Spike of 503s after deploy",
        severity=Severity.SEV2,
        status=IncidentStatus.OPEN,
        service="payment-service",
        reported_at=REPORTED,
        tags=["deploy", "http-503"],
    )
    data.update(overrides)
    return Incident(**data)


def test_round_trip_open_incident():
    incident = make_incident()
    assert to_domain(to_record(incident)) == incident


def test_round_trip_resolved_incident():
    incident = make_incident(
        status=IncidentStatus.RESOLVED,
        resolved_at=RESOLVED,
        root_cause="connection pool exhaustion",
        resolution="increased pool size",
    )
    assert to_domain(to_record(incident)) == incident


def test_round_trip_empty_tags():
    incident = make_incident(tags=[])
    assert to_domain(to_record(incident)).tags == []


def test_to_record_stores_enum_values_as_strings():
    record = to_record(make_incident())
    assert record.severity == "SEV2"
    assert record.status == "open"


def test_to_domain_rejects_inconsistent_row():
    record = to_record(make_incident())
    record.status = "resolved"  # resolved but resolved_at is None
    with pytest.raises(ValidationError):
        to_domain(record)


def test_to_domain_rejects_unknown_enum_value():
    record: IncidentRecord = to_record(make_incident())
    record.severity = "SEV9"
    with pytest.raises(ValueError):
        to_domain(record)
