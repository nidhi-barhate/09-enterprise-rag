from app.api.dto.incident import Incident, IncidentStatus, Severity
from app.model.incident_record import IncidentRecord


def to_record(incident: Incident) -> IncidentRecord:
    # Enums are stored as their string values (matches the DB CHECK constraints).
    return IncidentRecord(
        id=incident.id,
        title=incident.title,
        description=incident.description,
        severity=incident.severity.value,
        status=incident.status.value,
        service=incident.service,
        reported_at=incident.reported_at,
        resolved_at=incident.resolved_at,
        root_cause=incident.root_cause,
        resolution=incident.resolution,
        tags=list(incident.tags),
    )


def to_domain(record: IncidentRecord) -> Incident:
    # Constructing Incident re-runs validation, so a corrupt row raises
    # pydantic.ValidationError instead of silently leaking into the API.
    return Incident(
        id=record.id,
        title=record.title,
        description=record.description,
        severity=Severity(record.severity),
        status=IncidentStatus(record.status),
        service=record.service,
        reported_at=record.reported_at,
        resolved_at=record.resolved_at,
        root_cause=record.root_cause,
        resolution=record.resolution,
        tags=list(record.tags),
    )
