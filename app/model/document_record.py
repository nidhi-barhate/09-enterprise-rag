import datetime
import uuid

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.api.dto.document import DocumentType
from app.api.dto.limits import SERVICE_MAX, SOURCE_MAX, TITLE_MAX
from app.model.base import Base


def _in_list(column: str, enum_cls: type) -> str:
    # Build the CHECK from the domain enum so DB and API values can't drift apart.
    values = ", ".join(f"'{member.value}'" for member in enum_cls)
    return f"{column} IN ({values})"


class DocumentRecord(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    doc_type: Mapped[str] = mapped_column(String(30))
    service: Mapped[str | None] = mapped_column(String(SERVICE_MAX))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(SOURCE_MAX))
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default=text("'{}'")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_in_list("doc_type", DocumentType), name="ck_documents_doc_type"),
        # Serves "documents for service X" lookups.
        Index("ix_documents_service", "service"),
    )
