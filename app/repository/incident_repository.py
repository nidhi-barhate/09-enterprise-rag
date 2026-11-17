import uuid

from sqlalchemy.orm import Session

from app.api.dto.incident import Incident
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
