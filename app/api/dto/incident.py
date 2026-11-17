import datetime
import enum
from typing import Self
import uuid

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator


class Severity(str, enum.Enum):
    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"
    SEV4 = "SEV4"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"


class IncidentBase(BaseModel):
    """Fields and business rules shared by the create request and the stored incident."""

    title: str = Field(min_length=1)
    description: str
    severity: Severity
    status: IncidentStatus
    service: str
    reported_at: AwareDatetime
    resolved_at: AwareDatetime | None = None
    root_cause: str | None = None
    resolution: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("reported_at", "resolved_at")
    @classmethod
    def normalize_to_utc(cls, value: datetime.datetime | None) -> datetime.datetime | None:
        # Runs per field, before the cross-field check, so both sides are UTC.
        if value is None:
            return None
        return value.astimezone(datetime.timezone.utc)

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.resolved_at is not None and self.resolved_at < self.reported_at:
            raise ValueError("resolved_at must be greater than or equal to reported_at")
        return self

    @model_validator(mode="after")
    def validate_status_consistency(self) -> Self:
        # Business rule: RESOLVED <=> resolved_at is set.
        if self.status == IncidentStatus.RESOLVED and self.resolved_at is None:
            raise ValueError("resolved_at is required when status is RESOLVED")
        if self.status != IncidentStatus.RESOLVED and self.resolved_at is not None:
            raise ValueError("resolved_at must be empty unless status is RESOLVED")
        return self


class IncidentCreate(IncidentBase):
    """POST body: no id, the server generates it."""


class Incident(IncidentBase):
    id: uuid.UUID