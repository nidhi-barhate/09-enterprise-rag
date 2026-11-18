"""Column length limits shared by the Pydantic DTOs and the ORM models.

Keeping them in one place means an over-long value is rejected with a 422 at
the API boundary instead of failing in Postgres as a 500.
"""

TITLE_MAX = 255
SERVICE_MAX = 100
SOURCE_MAX = 500
# Documents are chunked and embedded while the request is open, so cap their size.
# 100,000 characters is roughly 125 chunks: a few embedding batches.
CONTENT_MAX = 100_000
