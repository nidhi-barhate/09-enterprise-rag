import pytest
from sqlalchemy.orm import Session

from app.config.connection import engine


class RecordingIndexer:
    """Stand-in for IncidentIndexer: records calls, never touches Ollama/Qdrant."""

    def __init__(self):
        self.indexed = []
        self.fail = False

    def index(self, incident):
        if self.fail:
            raise RuntimeError("indexing is down")
        self.indexed.append(incident)


@pytest.fixture
def indexer():
    return RecordingIndexer()


@pytest.fixture
def session():
    """A Session wrapped in an outer transaction that is always rolled back.

    Nothing a test does is ever committed, so the database stays clean.
    """
    connection = engine.connect()
    transaction = connection.begin()
    db_session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield db_session
    finally:
        db_session.close()
        transaction.rollback()
        connection.close()
