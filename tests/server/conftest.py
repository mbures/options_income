"""Pytest fixtures for FastAPI server tests.

This module provides test fixtures for database sessions, test clients,
and other common test utilities.
"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.server.config import settings
from src.server.database.session import Base, get_db
from src.server.main import app

# Import all models to ensure they're registered with Base
from src.server.database.models import (  # noqa: F401
    JobExecution,
    Opportunity,
    PerformanceMetrics,
    PluginConfig,
    Portfolio,
    SchedulerConfig,
    Snapshot,
    Trade,
    WatchlistItem,
    Wheel,
)


@pytest.fixture(scope="function")
def test_db() -> Generator[Session, None, None]:
    """Create a test database session.

    Creates an in-memory SQLite database for testing that is
    destroyed after each test function completes.

    Yields:
        SQLAlchemy session for testing

    Example:
        >>> def test_something(test_db):
        >>>     result = test_db.query(Model).all()
        >>>     assert len(result) == 0
    """
    # Create in-memory SQLite database for testing
    # Use poolclass to keep connection alive
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # Keep connection alive for in-memory database
    )

    # Enable foreign key constraints for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create session
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db: Session) -> TestClient:
    """Create a test client with test database.

    Creates a FastAPI TestClient that uses the test database
    instead of the real database.

    Args:
        test_db: Test database session fixture

    Returns:
        FastAPI TestClient for making test requests

    Example:
        >>> def test_endpoint(client):
        >>>     response = client.get("/health")
        >>>     assert response.status_code == 200
    """

    def override_get_db():
        """Override database dependency with test database."""
        # Return the same session for all requests in a test
        yield test_db

    # Override the database dependency
    app.dependency_overrides[get_db] = override_get_db

    # Create test client
    with TestClient(app) as test_client:
        yield test_client

    # Clear overrides and rollback any uncommitted changes
    test_db.rollback()
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def client_no_db() -> TestClient:
    """Create a test client without database mocking.

    Creates a FastAPI TestClient that uses the real database
    dependency. Useful for testing endpoints that don't need
    database access.

    Returns:
        FastAPI TestClient for making test requests

    Example:
        >>> def test_health(client_no_db):
        >>>     response = client_no_db.get("/health")
        >>>     assert response.status_code == 200
    """
    with TestClient(app) as test_client:
        yield test_client
