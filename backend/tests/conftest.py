import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# A placeholder allows database-free HTTP validation tests to import the app.
# It does not connect; catalog integration tests require TEST_DATABASE_URL.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1:1/unused"
)
os.environ.setdefault("JWT_SECRET", "test-only-secret-at-least-32-bytes-long")

from app.db.session import get_db
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def catalog_client():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a migrated, seeded test PostgreSQL database")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            app.dependency_overrides[get_db] = lambda: session
            try:
                with TestClient(app) as test_client:
                    yield test_client, session
            finally:
                app.dependency_overrides.clear()
        transaction.rollback()
    engine.dispose()
