import pytest
from sqlalchemy.orm import Session

from app.config.connection import engine


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
