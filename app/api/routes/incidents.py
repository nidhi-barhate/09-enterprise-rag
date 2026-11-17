import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.dto.incident import Incident, IncidentCreate
from app.repository.incident_repository import IncidentRepository

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.post("", response_model=Incident, status_code=status.HTTP_201_CREATED)
def create_incident(payload: IncidentCreate, session: Session = Depends(get_session)):
    incident = Incident(id=uuid.uuid4(), **payload.model_dump())
    IncidentRepository(session).add(incident)
    return incident


@router.get("/{incident_id}", response_model=Incident)
def get_incident(incident_id: uuid.UUID, session: Session = Depends(get_session)):
    incident = IncidentRepository(session).get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident
