from app.model.document_record import DocumentRecord
from app.model.incident_record import IncidentRecord

# Importing this package registers every model on Base.metadata (needed by Alembic).
__all__ = ["DocumentRecord", "IncidentRecord"]
