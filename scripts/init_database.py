#!/usr/bin/env python3
"""Database initialization script for creating fresh backend database.

This script:
1. Creates a fresh database with the complete backend schema
2. Creates a default portfolio
3. Adds sample scheduler configuration (optional)
4. Adds indexes for performance
5. Validates the schema

Usage:
    python scripts/init_database.py [--force] [--sample-data]
"""

import argparse
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from src.server.config import settings
from src.server.database.session import Base, init_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DatabaseInitializer:
    """Manages initialization of a fresh backend database.

    Attributes:
        db_path: Path to database file
        force: If True, overwrite existing database
        sample_data: If True, add sample configuration data
    """

    def __init__(self, db_path: Path, force: bool = False, sample_data: bool = False):
        """Initialize the database initializer.

        Args:
            db_path: Path to the database file
            force: If True, overwrite existing database
            sample_data: If True, add sample data
        """
        self.db_path = db_path
        self.force = force
        self.sample_data = sample_data

    def check_database_exists(self) -> bool:
        """Check if database file already exists.

        Returns:
            True if database exists, False otherwise
        """
        return self.db_path.exists()

    def remove_existing_database(self) -> None:
        """Remove existing database file.

        Raises:
            IOError: If removal fails
        """
        if self.db_path.exists():
            logger.warning(f"Removing existing database: {self.db_path}")
            self.db_path.unlink()

    def create_schema(self) -> None:
        """Create database schema using Alembic migrations.

        Raises:
            Exception: If schema creation fails
        """
        logger.info("Creating database schema...")

        try:
            # Get Alembic config
            alembic_ini = Path(__file__).parent.parent / "alembic.ini"
            alembic_cfg = Config(str(alembic_ini))

            # Stamp the database as being at the latest revision
            # (since we're creating from scratch, we stamp without running migrations)
            command.stamp(alembic_cfg, "head")

            logger.info("Database schema created successfully")

        except Exception as e:
            logger.error(f"Schema creation failed: {e}")
            raise

    def create_tables(self) -> None:
        """Create all database tables directly from models.

        This is an alternative to Alembic migrations for fresh databases.
        """
        logger.info("Creating database tables from models...")

        try:
            # Import all models to ensure they're registered
            from src.server.database.models import (
                Portfolio,
                Wheel,
                Trade,
                Snapshot,
                PerformanceMetrics,
                SchedulerConfig,
            )

            # Create all tables
            engine = init_engine()
            Base.metadata.create_all(bind=engine)

            logger.info("Database tables created successfully")

        except Exception as e:
            logger.error(f"Table creation failed: {e}")
            raise

    def create_default_portfolio(self) -> str:
        """Create default portfolio.

        Returns:
            ID of created portfolio

        Example:
            >>> portfolio_id = initializer.create_default_portfolio()
            >>> print(f"Created portfolio: {portfolio_id}")
        """
        logger.info("Creating default portfolio...")

        portfolio_id = str(uuid.uuid4())
        now = datetime.utcnow()

        engine = create_engine(f"sqlite:///{self.db_path}")

        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO portfolios (id, name, description, default_capital, created_at, updated_at)
                    VALUES (:id, :name, :description, :capital, :created, :updated)
                """),
                {
                    "id": portfolio_id,
                    "name": "Default Portfolio",
                    "description": "Primary trading portfolio",
                    "capital": 50000.0,
                    "created": now,
                    "updated": now
                }
            )
            conn.commit()

        logger.info(f"Created default portfolio: {portfolio_id}")
        return portfolio_id

    def create_sample_scheduler_config(self, portfolio_id: str) -> None:
        """Create sample scheduler configuration.

        Args:
            portfolio_id: ID of portfolio for portfolio-specific tasks

        Example:
            >>> initializer.create_sample_scheduler_config(portfolio_id)
        """
        logger.info("Creating sample scheduler configuration...")

        now = datetime.utcnow()
        engine = create_engine(f"sqlite:///{self.db_path}")

        configs = [
            {
                "portfolio_id": None,  # System-wide
                "task_name": "price_refresh",
                "enabled": True,
                "schedule_type": "interval",
                "schedule_params": '{"minutes": 5}',
            },
            {
                "portfolio_id": None,  # System-wide
                "task_name": "daily_snapshot",
                "enabled": True,
                "schedule_type": "cron",
                "schedule_params": '{"hour": 16, "minute": 30}',
            },
            {
                "portfolio_id": None,  # System-wide
                "task_name": "risk_monitoring",
                "enabled": True,
                "schedule_type": "interval",
                "schedule_params": '{"minutes": 15}',
            },
            {
                "portfolio_id": portfolio_id,  # Portfolio-specific
                "task_name": "opportunity_scanning",
                "enabled": True,
                "schedule_type": "cron",
                "schedule_params": '{"hour": 9, "minute": 45}',
            },
        ]

        with engine.connect() as conn:
            for config in configs:
                conn.execute(
                    text("""
                        INSERT INTO scheduler_config
                        (portfolio_id, task_name, enabled, schedule_type, schedule_params, created_at, updated_at)
                        VALUES (:portfolio_id, :task_name, :enabled, :schedule_type, :schedule_params, :created, :updated)
                    """),
                    {
                        **config,
                        "created": now,
                        "updated": now
                    }
                )
            conn.commit()

        logger.info(f"Created {len(configs)} scheduler configurations")

    def validate_schema(self) -> bool:
        """Validate that schema is complete and correct.

        Returns:
            True if validation passes, False otherwise

        Example:
            >>> if initializer.validate_schema():
            ...     print("Schema validated successfully")
        """
        logger.info("Validating database schema...")

        engine = create_engine(f"sqlite:///{self.db_path}")
        inspector = inspect(engine)

        expected_tables = [
            "portfolios",
            "wheels",
            "trades",
            "snapshots",
            "performance_metrics",
            "scheduler_config",
        ]

        checks_passed = 0
        checks_total = len(expected_tables)

        for table in expected_tables:
            if table in inspector.get_table_names():
                logger.info(f"✓ Table '{table}' exists")
                checks_passed += 1
            else:
                logger.error(f"✗ Table '{table}' missing")

        # Check foreign key constraints
        checks_total += 1
        wheels_fks = inspector.get_foreign_keys("wheels")
        if any(fk["referred_table"] == "portfolios" for fk in wheels_fks):
            logger.info("✓ Wheels -> Portfolios foreign key exists")
            checks_passed += 1
        else:
            logger.error("✗ Wheels -> Portfolios foreign key missing")

        # Check indexes
        checks_total += 1
        wheels_indexes = inspector.get_indexes("wheels")
        index_names = [idx["name"] for idx in wheels_indexes]
        if "ix_wheels_portfolio_id" in index_names:
            logger.info("✓ Wheels.portfolio_id index exists")
            checks_passed += 1
        else:
            logger.error("✗ Wheels.portfolio_id index missing")

        engine.dispose()

        logger.info(f"Validation: {checks_passed}/{checks_total} checks passed")
        return checks_passed == checks_total

    def run(self) -> bool:
        """Run the complete initialization process.

        Returns:
            True if initialization succeeded, False otherwise

        Example:
            >>> initializer = DatabaseInitializer(db_path, force=True)
            >>> success = initializer.run()
            >>> if success:
            ...     print("Database initialized successfully")
        """
        logger.info("=" * 60)
        logger.info("Database Initialization Tool")
        logger.info("=" * 60)

        # Step 1: Check for existing database
        if self.check_database_exists():
            if self.force:
                logger.warning("Database exists. Force mode enabled - will overwrite.")
                self.remove_existing_database()
            else:
                logger.error(
                    "Database already exists. Use --force to overwrite, "
                    "or remove the database manually."
                )
                return False

        # Step 2: Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Database location: {self.db_path}")

        # Step 3: Create tables
        logger.info("\n--- Creating Schema ---")
        try:
            self.create_tables()
        except Exception as e:
            logger.error(f"Schema creation failed: {e}")
            return False

        # Step 4: Create default portfolio
        logger.info("\n--- Creating Default Portfolio ---")
        try:
            portfolio_id = self.create_default_portfolio()
        except Exception as e:
            logger.error(f"Portfolio creation failed: {e}")
            return False

        # Step 5: Create sample scheduler config (if requested)
        if self.sample_data:
            logger.info("\n--- Creating Sample Scheduler Config ---")
            try:
                self.create_sample_scheduler_config(portfolio_id)
            except Exception as e:
                logger.error(f"Scheduler config creation failed: {e}")
                return False

        # Step 6: Validate schema
        logger.info("\n--- Validating Schema ---")
        if not self.validate_schema():
            logger.error("Schema validation failed")
            return False

        # Step 7: Summary
        logger.info("\n" + "=" * 60)
        logger.info("DATABASE INITIALIZED SUCCESSFULLY")
        logger.info(f"Location: {self.db_path}")
        logger.info(f"Default Portfolio ID: {portfolio_id}")
        logger.info("=" * 60)

        return True


def main():
    """Main entry point for initialization script.

    Example:
        $ python scripts/init_database.py
        $ python scripts/init_database.py --force
        $ python scripts/init_database.py --force --sample-data
    """
    parser = argparse.ArgumentParser(
        description="Initialize fresh wheel strategy backend database"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing database if present"
    )
    parser.add_argument(
        "--sample-data",
        action="store_true",
        help="Add sample scheduler configuration"
    )

    args = parser.parse_args()

    # Get database path from settings
    db_path = settings.get_database_path()

    # Create initializer and run
    initializer = DatabaseInitializer(
        db_path=db_path,
        force=args.force,
        sample_data=args.sample_data
    )

    success = initializer.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
