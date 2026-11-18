import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dto.incident import Incident, IncidentStatus, Severity
from app.model.incident_record import IncidentRecord
from app.repository.incident_mapper import to_domain, to_record


class IncidentRepository:
    """Persistence for incidents. Accepts and returns domain `Incident` objects.

    The caller owns the transaction: this class never commits.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, incident: Incident) -> None:
        self._session.add(to_record(incident))
        # Send the INSERT now so constraint violations surface here, not at commit.
        self._session.flush()

    def get(self, incident_id: uuid.UUID) -> Incident | None:
        record = self._session.get(IncidentRecord, incident_id)
        return None if record is None else to_domain(record)

    def get_many(self, incident_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Incident]:
        """One query for many ids. Unknown ids are simply absent from the result."""
        ids = set(incident_ids)
        if not ids:
            return {}
        stmt = select(IncidentRecord).where(IncidentRecord.id.in_(ids))
        return {r.id: to_domain(r) for r in self._session.scalars(stmt)}

    def list(
        self,
        *,
        service: str | None = None,
        severity: Severity | None = None,
        status: IncidentStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Incident]:
        """Newest first. Filters are optional and combined with AND.

        Served by ix_incidents_service_reported_at when filtering by service.
        `id` is a tiebreaker so pages stay stable when timestamps are equal.
        """
        stmt = select(IncidentRecord)
        if service is not None:
            stmt = stmt.where(IncidentRecord.service == service)
        if severity is not None:
            stmt = stmt.where(IncidentRecord.severity == severity.value)
        if status is not None:
            stmt = stmt.where(IncidentRecord.status == status.value)
        stmt = (
            stmt.order_by(IncidentRecord.reported_at.desc(), IncidentRecord.id)
            .limit(limit)
            .offset(offset)
        )
        return [to_domain(record) for record in self._session.scalars(stmt)]
