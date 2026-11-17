import datetime
import uuid

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.api.dto.incident import IncidentStatus, Severity
from app.model.base import Base


def _in_list(column: str, enum_cls: type) -> str:
    # Build the CHECK from the domain enums so DB and API values can't drift apart.
    values = ", ".join(f"'{member.value}'" for member in enum_cls)
    return f"{column} IN ({values})"


class IncidentRecord(Base):
    __tablename__ = "incidents"

    # App-generated UUID (the Pydantic model requires id), so no default here.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))
    service: Mapped[str] = mapped_column(String(100))
    reported_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    root_cause: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default=text("'{}'")
    )

    __table_args__ = (
        CheckConstraint(_in_list("severity", Severity), name="ck_incidents_severity"),
        CheckConstraint(_in_list("status", IncidentStatus), name="ck_incidents_status"),
        # Serves "incidents for service X, newest first" (service filter + time sort).
        Index("ix_incidents_service_reported_at", "service", "reported_at"),
    )
