import datetime
import enum
import uuid

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from app.api.dto.limits import SERVICE_MAX, SOURCE_MAX, TITLE_MAX


class DocumentType(str, enum.Enum):
    RUNBOOK = "runbook"
    TROUBLESHOOTING_GUIDE = "troubleshooting_guide"
    TECHNICAL_DOC = "technical_doc"


class Document(BaseModel):
    id: uuid.UUID
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    doc_type: DocumentType
    # None = applies to every service
    service: str | None = Field(default=None, min_length=1, max_length=SERVICE_MAX)
    content: str = Field(min_length=1)
    # file name or URL the content came from
    source: str | None = Field(default=None, max_length=SOURCE_MAX)
    tags: list[str] = Field(default_factory=list)
    created_at: AwareDatetime

    @field_validator("created_at")
    @classmethod
    def normalize_to_utc(cls, value: datetime.datetime) -> datetime.datetime:
        return value.astimezone(datetime.timezone.utc)
