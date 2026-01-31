"""SQLAlchemy database session management.

This module provides database engine configuration, session factory,
and dependency injection for FastAPI endpoints.
"""

import logging
import os
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from src.server.config import settings

logger = logging.getLogger(__name__)

# SQLAlchemy declarative base for ORM models
Base = declarative_base()

# Global engine instance
_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable foreign key constraints for SQLite.

    Args:
        dbapi_conn: Database API connection
        connection_record: Connection record
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_engine() -> Engine:
    """Initialize SQLAlchemy engine.

    Creates the database directory if it doesn't exist and initializes
    the engine with appropriate settings for SQLite.

    Returns:
        Configured SQLAlchemy engine

    Raises:
        Exception: If engine initialization fails
    """
    global _engine

    if _engine is not None:
        return _engine

    # Ensure database directory exists
    db_path = settings.get_database_path()
    db_dir = db_path.parent
    if not db_dir.exists():
        db_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created database directory: {db_dir}")

    # Create engine with connection pooling disabled for SQLite
    _engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},  # Needed for SQLite
        pool_pre_ping=True,  # Verify connections before using
        echo=settings.debug,  # Log SQL queries in debug mode
    )

    logger.info(f"Database engine initialized: {settings.database_url}")
    return _engine


def get_session_factory() -> sessionmaker:
    """Get SQLAlchemy session factory.

    Returns:
        Configured sessionmaker instance
    """
    global _SessionLocal

    if _SessionLocal is None:
        engine = init_engine()
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
        )

    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions.

    Provides a database session that is automatically closed after use.
    Use this as a dependency in FastAPI path operations.

    Yields:
        SQLAlchemy database session

    Example:
        >>> @app.get("/items/")
        >>> def read_items(db: Session = Depends(get_db)):
        >>>     return db.query(Item).all()
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """Create all database tables.

    Creates tables for all models that inherit from Base.
    This should only be used in development; use Alembic migrations
    in production.
    """
    engine = init_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")


def check_database_connection() -> bool:
    """Check if database connection is working.

    Returns:
        True if connection is successful, False otherwise
    """
    try:
        from sqlalchemy import text

        engine = init_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False
