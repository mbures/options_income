#!/usr/bin/env python3
"""Database migration script for upgrading CLI database to backend schema.

This script:
1. Backs up the existing database
2. Applies Alembic migrations to add portfolio support
3. Validates the migration
4. Provides rollback capability if needed

Usage:
    python scripts/migrate_database.py [--dry-run] [--backup-dir PATH]
"""

import argparse
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from src.server.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DatabaseMigrator:
    """Manages database migration from CLI to backend schema.

    Attributes:
        db_path: Path to database file
        backup_dir: Directory for backup files
        dry_run: If True, only simulate migration
    """

    def __init__(self, db_path: Path, backup_dir: Path, dry_run: bool = False):
        """Initialize the migrator.

        Args:
            db_path: Path to the database file
            backup_dir: Directory to store backups
            dry_run: If True, only validate without applying changes
        """
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.dry_run = dry_run
        self.backup_path = None

    def check_database_exists(self) -> bool:
        """Check if database file exists.

        Returns:
            True if database exists, False otherwise
        """
        exists = self.db_path.exists()
        if exists:
            logger.info(f"Found database at: {self.db_path}")
            logger.info(f"Database size: {self.db_path.stat().st_size / 1024:.2f} KB")
        else:
            logger.info(f"No database found at: {self.db_path}")
        return exists

    def backup_database(self) -> Path:
        """Create a backup of the database.

        Returns:
            Path to backup file

        Raises:
            IOError: If backup fails
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"trades_backup_{timestamp}.db"
        self.backup_path = self.backup_dir / backup_filename

        logger.info(f"Creating backup: {self.backup_path}")

        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.db_path, self.backup_path)
            logger.info(f"Backup created successfully ({self.backup_path.stat().st_size / 1024:.2f} KB)")
            return self.backup_path
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            raise

    def inspect_current_schema(self) -> dict:
        """Inspect current database schema.

        Returns:
            Dictionary with schema information

        Example:
            >>> schema = migrator.inspect_current_schema()
            >>> print(schema['tables'])
            ['wheels', 'trades', 'position_snapshots']
        """
        engine = create_engine(f"sqlite:///{self.db_path}")
        inspector = inspect(engine)

        schema_info = {
            "tables": inspector.get_table_names(),
            "table_details": {}
        }

        for table_name in schema_info["tables"]:
            columns = inspector.get_columns(table_name)
            foreign_keys = inspector.get_foreign_keys(table_name)
            indexes = inspector.get_indexes(table_name)

            schema_info["table_details"][table_name] = {
                "columns": [col["name"] for col in columns],
                "foreign_keys": foreign_keys,
                "indexes": [idx["name"] for idx in indexes]
            }

        engine.dispose()
        return schema_info

    def count_records(self) -> dict:
        """Count records in each table.

        Returns:
            Dictionary mapping table names to record counts

        Example:
            >>> counts = migrator.count_records()
            >>> print(f"Wheels: {counts['wheels']}")
            Wheels: 5
        """
        engine = create_engine(f"sqlite:///{self.db_path}")

        counts = {}
        with engine.connect() as conn:
            for table in ["wheels", "trades", "position_snapshots"]:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    counts[table] = result.scalar()
                except Exception as e:
                    logger.warning(f"Could not count {table}: {e}")
                    counts[table] = 0

        engine.dispose()
        return counts

    def apply_migration(self) -> bool:
        """Apply Alembic migrations to upgrade schema.

        Returns:
            True if migration succeeded, False otherwise

        Raises:
            Exception: If migration fails
        """
        if self.dry_run:
            logger.info("DRY RUN: Would apply Alembic migration 'upgrade head'")
            return True

        logger.info("Applying Alembic migrations...")

        try:
            # Get Alembic config
            alembic_ini = Path(__file__).parent.parent / "alembic.ini"
            alembic_cfg = Config(str(alembic_ini))

            # Run upgrade
            command.upgrade(alembic_cfg, "head")

            logger.info("Migration completed successfully")
            return True

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise

    def validate_migration(self) -> bool:
        """Validate that migration was successful.

        Returns:
            True if validation passes, False otherwise

        Example:
            >>> if migrator.validate_migration():
            ...     print("Migration validated successfully")
        """
        logger.info("Validating migration...")

        engine = create_engine(f"sqlite:///{self.db_path}")
        inspector = inspect(engine)

        checks_passed = 0
        checks_total = 0

        # Check 1: Portfolios table exists
        checks_total += 1
        if "portfolios" in inspector.get_table_names():
            logger.info("✓ Portfolios table exists")
            checks_passed += 1
        else:
            logger.error("✗ Portfolios table missing")

        # Check 2: Wheels has portfolio_id column
        checks_total += 1
        wheels_columns = [col["name"] for col in inspector.get_columns("wheels")]
        if "portfolio_id" in wheels_columns:
            logger.info("✓ Wheels.portfolio_id column exists")
            checks_passed += 1
        else:
            logger.error("✗ Wheels.portfolio_id column missing")

        # Check 3: Snapshots table exists (renamed from position_snapshots)
        checks_total += 1
        if "snapshots" in inspector.get_table_names():
            logger.info("✓ Snapshots table exists")
            checks_passed += 1
        else:
            logger.error("✗ Snapshots table missing")

        # Check 4: Performance metrics table exists
        checks_total += 1
        if "performance_metrics" in inspector.get_table_names():
            logger.info("✓ Performance metrics table exists")
            checks_passed += 1
        else:
            logger.error("✗ Performance metrics table missing")

        # Check 5: Scheduler config table exists
        checks_total += 1
        if "scheduler_config" in inspector.get_table_names():
            logger.info("✓ Scheduler config table exists")
            checks_passed += 1
        else:
            logger.error("✗ Scheduler config table missing")

        # Check 6: Default portfolio exists
        checks_total += 1
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM portfolios"))
            portfolio_count = result.scalar()
            if portfolio_count > 0:
                logger.info(f"✓ Default portfolio exists ({portfolio_count} portfolio(s) total)")
                checks_passed += 1
            else:
                logger.error("✗ No portfolios found")

        # Check 7: All wheels have portfolio_id
        checks_total += 1
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT COUNT(*) FROM wheels WHERE portfolio_id IS NULL")
            )
            null_count = result.scalar()
            if null_count == 0:
                logger.info("✓ All wheels have portfolio_id assigned")
                checks_passed += 1
            else:
                logger.error(f"✗ {null_count} wheels missing portfolio_id")

        engine.dispose()

        logger.info(f"Validation: {checks_passed}/{checks_total} checks passed")
        return checks_passed == checks_total

    def rollback_migration(self) -> bool:
        """Rollback migration by restoring from backup.

        Returns:
            True if rollback succeeded, False otherwise

        Raises:
            IOError: If rollback fails
        """
        if not self.backup_path or not self.backup_path.exists():
            logger.error("No backup available for rollback")
            return False

        logger.warning("Rolling back migration...")

        try:
            shutil.copy2(self.backup_path, self.db_path)
            logger.info(f"Restored database from backup: {self.backup_path}")
            return True
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            raise

    def run(self) -> bool:
        """Run the complete migration process.

        Returns:
            True if migration succeeded, False otherwise

        Example:
            >>> migrator = DatabaseMigrator(db_path, backup_dir, dry_run=False)
            >>> success = migrator.run()
            >>> if success:
            ...     print("Migration completed successfully")
        """
        logger.info("=" * 60)
        logger.info("Database Migration Tool")
        logger.info("=" * 60)

        # Step 1: Check if database exists
        if not self.check_database_exists():
            logger.info("No database to migrate. Run application to create new database.")
            return True

        # Step 2: Inspect current schema
        logger.info("\n--- Current Schema ---")
        schema = self.inspect_current_schema()
        logger.info(f"Tables: {', '.join(schema['tables'])}")

        counts = self.count_records()
        logger.info(f"Record counts: {counts}")

        # Step 3: Create backup
        if not self.dry_run:
            logger.info("\n--- Creating Backup ---")
            try:
                self.backup_database()
            except Exception:
                logger.error("Backup failed. Aborting migration.")
                return False
        else:
            logger.info("\n--- Dry Run Mode ---")
            logger.info("Skipping backup in dry run mode")

        # Step 4: Apply migration
        logger.info("\n--- Applying Migration ---")
        try:
            self.apply_migration()
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            if not self.dry_run and self.backup_path:
                logger.info("Attempting rollback...")
                self.rollback_migration()
            return False

        # Step 5: Validate migration
        if not self.dry_run:
            logger.info("\n--- Validating Migration ---")
            if not self.validate_migration():
                logger.error("Validation failed. Consider rollback.")
                return False

        # Step 6: Summary
        logger.info("\n" + "=" * 60)
        if self.dry_run:
            logger.info("DRY RUN COMPLETE - No changes made")
        else:
            logger.info("MIGRATION COMPLETE")
            logger.info(f"Backup location: {self.backup_path}")
            logger.info("To rollback, run:")
            logger.info(f"  cp {self.backup_path} {self.db_path}")
        logger.info("=" * 60)

        return True


def main():
    """Main entry point for migration script.

    Example:
        $ python scripts/migrate_database.py
        $ python scripts/migrate_database.py --dry-run
        $ python scripts/migrate_database.py --backup-dir /path/to/backups
    """
    parser = argparse.ArgumentParser(
        description="Migrate wheel strategy database to backend schema"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration without applying changes"
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path.home() / ".wheel_strategy" / "backups",
        help="Directory for database backups (default: ~/.wheel_strategy/backups)"
    )

    args = parser.parse_args()

    # Get database path from settings
    db_path = settings.get_database_path()

    # Create migrator and run
    migrator = DatabaseMigrator(
        db_path=db_path,
        backup_dir=args.backup_dir,
        dry_run=args.dry_run
    )

    success = migrator.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
