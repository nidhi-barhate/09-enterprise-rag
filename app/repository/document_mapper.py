from app.api.dto.document import Document, DocumentType
from app.model.document_record import DocumentRecord


def to_record(document: Document) -> DocumentRecord:
    return DocumentRecord(
        id=document.id,
        title=document.title,
        doc_type=document.doc_type.value,
        service=document.service,
        content=document.content,
        source=document.source,
        tags=list(document.tags),
        created_at=document.created_at,
    )


def to_domain(record: DocumentRecord) -> Document:
    # Re-runs validation, so a corrupt row fails loudly instead of leaking out.
    return Document(
        id=record.id,
        title=record.title,
        doc_type=DocumentType(record.doc_type),
        service=record.service,
        content=record.content,
        source=record.source,
        tags=list(record.tags),
        created_at=record.created_at,
    )
