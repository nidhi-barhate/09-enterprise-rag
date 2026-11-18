import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_incident_indexer, get_session
from app.api.dto.incident import Incident, IncidentCreate, IncidentStatus, Severity
from app.repository.incident_repository import IncidentRepository
from app.services.incident_indexer import IncidentIndexer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.post("", response_model=Incident, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreate,
    session: Session = Depends(get_session),
    indexer: IncidentIndexer = Depends(get_incident_indexer),
):
    incident = Incident(id=uuid.uuid4(), **payload.model_dump())
    IncidentRepository(session).add(incident)
    # Best effort: Postgres is the source of truth, so an embedding/Qdrant outage
    # must not block recording an incident (exactly when people need it most).
    # A missed index is healed by `python -m app.scripts.reindex`. If the later
    # commit fails, the orphan vector is harmless: search skips ids not in Postgres.
    try:
        indexer.index(incident)
    except Exception:
        logger.warning("Failed to index incident %s", incident.id, exc_info=True)
    return incident


@router.get("", response_model=list[Incident])
def list_incidents(
    service: str | None = None,
    severity: Severity | None = None,
    # Aliased: a parameter literally named `status` would shadow fastapi's `status` module.
    incident_status: IncidentStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    return IncidentRepository(session).list(
        service=service,
        severity=severity,
        status=incident_status,
        limit=limit,
        offset=offset,
    )


@router.get("/{incident_id}", response_model=Incident)
def get_incident(incident_id: uuid.UUID, session: Session = Depends(get_session)):
    incident = IncidentRepository(session).get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident
