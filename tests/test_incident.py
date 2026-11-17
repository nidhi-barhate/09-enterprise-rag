import datetime
import uuid

import pytest
from pydantic import ValidationError

from app.api.dto.incident import Incident, IncidentStatus, Severity

UTC = datetime.timezone.utc
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

REPORTED = datetime.datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
LATER = datetime.datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
EARLIER = datetime.datetime(2026, 1, 2, 8, 0, tzinfo=UTC)


@pytest.fixture
def valid_data() -> dict:
    """A fresh, valid OPEN incident payload. Tests override one field at a time."""
    return {
        "id": uuid.uuid4(),
        "title": "Payment API returning 500s",
        "description": "Checkout requests fail with HTTP 500 since 10:00 UTC.",
        "severity": Severity.SEV2,
        "status": IncidentStatus.OPEN,
        "service": "payment-api",
        "reported_at": REPORTED,
    }


def test_valid_open_incident_is_created(valid_data):
    incident = Incident(**valid_data)

    assert incident.status == IncidentStatus.OPEN
    assert incident.resolved_at is None
    assert incident.root_cause is None
    assert incident.resolution is None


def test_valid_resolved_incident_is_created(valid_data):
    incident = Incident(
        **{**valid_data, "status": IncidentStatus.RESOLVED, "resolved_at": LATER}
    )

    assert incident.resolved_at == LATER


def test_resolved_at_equal_to_reported_at_is_allowed(valid_data):
    incident = Incident(
        **{**valid_data, "status": IncidentStatus.RESOLVED, "resolved_at": REPORTED}
    )

    assert incident.resolved_at == incident.reported_at


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"title": ""}, id="empty-title"),
        pytest.param({"severity": "SEV9"}, id="invalid-severity"),
        pytest.param({"status": "closed"}, id="invalid-status"),
        pytest.param(
            {"reported_at": datetime.datetime(2026, 1, 2, 10, 0)},
            id="naive-reported-at",
        ),
        pytest.param(
            {
                "status": IncidentStatus.RESOLVED,
                "resolved_at": datetime.datetime(2026, 1, 2, 12, 0),
            },
            id="naive-resolved-at",
        ),
        pytest.param(
            {"status": IncidentStatus.RESOLVED, "resolved_at": EARLIER},
            id="resolved-before-reported",
        ),
        pytest.param(
            {"status": IncidentStatus.RESOLVED},
            id="resolved-status-without-resolved-at",
        ),
        pytest.param({"resolved_at": LATER}, id="open-status-with-resolved-at"),
        pytest.param(
            {"status": IncidentStatus.MITIGATED, "resolved_at": LATER},
            id="mitigated-status-with-resolved-at",
        ),
    ],
)
def test_invalid_incident_is_rejected(valid_data, overrides):
    with pytest.raises(ValidationError):
        Incident(**{**valid_data, **overrides})


def test_missing_required_field_is_rejected(valid_data):
    del valid_data["service"]

    with pytest.raises(ValidationError):
        Incident(**valid_data)


def test_datetimes_are_normalized_to_utc(valid_data):
    incident = Incident(
        **{
            **valid_data,
            "status": IncidentStatus.RESOLVED,
            "reported_at": datetime.datetime(2026, 1, 2, 10, 0, tzinfo=IST),
            "resolved_at": datetime.datetime(2026, 1, 2, 12, 0, tzinfo=IST),
        }
    )

    assert incident.reported_at == datetime.datetime(2026, 1, 2, 4, 30, tzinfo=UTC)
    assert incident.resolved_at == datetime.datetime(2026, 1, 2, 6, 30, tzinfo=UTC)
    assert incident.reported_at.utcoffset() == datetime.timedelta(0)
    assert incident.resolved_at.utcoffset() == datetime.timedelta(0)


def test_tags_default_to_empty_list_and_are_not_shared(valid_data):
    first = Incident(**valid_data)
    second = Incident(**valid_data)

    assert first.tags == []
    assert first.tags is not second.tags


def test_enums_compare_and_serialize_as_strings(valid_data):
    incident = Incident(**valid_data)

    assert incident.severity == "SEV2"
    assert incident.status == "open"
    assert incident.model_dump(mode="json")["severity"] == "SEV2"
