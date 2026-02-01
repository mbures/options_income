"""Repository for scheduler configuration data access operations.

This module provides data access methods for scheduler configuration
CRUD operations, including querying, creating, updating configs.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.server.database.models.scheduler import SchedulerConfig

logger = logging.getLogger(__name__)


class SchedulerConfigRepository:
    """Repository for scheduler configuration data access.

    Handles all database operations related to scheduler configs,
    including CRUD operations and enabling/disabling tasks.

    Attributes:
        db: SQLAlchemy database session
    """

    def __init__(self, db: Session):
        """Initialize scheduler config repository.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def create_config(
        self,
        task_name: str,
        schedule_type: str,
        schedule_params: Dict,
        portfolio_id: Optional[str] = None,
        enabled: bool = True,
    ) -> SchedulerConfig:
        """Create a new scheduler configuration.

        Args:
            task_name: Name of the scheduled task
            schedule_type: Type of schedule ('interval' or 'cron')
            schedule_params: Schedule parameters as dictionary
            portfolio_id: Optional portfolio identifier (None for system-wide)
            enabled: Whether task is initially enabled

        Returns:
            Created scheduler config instance

        Raises:
            ValueError: If config already exists

        Example:
            >>> repo = SchedulerConfigRepository(db)
            >>> config = repo.create_config(
            >>>     task_name="price_refresh",
            >>>     schedule_type="interval",
            >>>     schedule_params={"minutes": 5}
            >>> )
        """
        # Check for existing config
        existing = self.get_config(task_name, portfolio_id)
        if existing:
            raise ValueError(
                f"Config already exists: {task_name} "
                f"for {'system' if portfolio_id is None else f'portfolio {portfolio_id}'}"
            )

        # Validate schedule_type
        if schedule_type not in ["interval", "cron"]:
            raise ValueError(f"Invalid schedule_type: {schedule_type}")

        # Create config
        config = SchedulerConfig(
            task_name=task_name,
            portfolio_id=portfolio_id,
            schedule_type=schedule_type,
            schedule_params=json.dumps(schedule_params),
            enabled=enabled,
        )

        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)

        logger.info(f"Created scheduler config: {config.id} - {task_name}")
        return config

    def get_config(
        self, task_name: str, portfolio_id: Optional[str] = None
    ) -> Optional[SchedulerConfig]:
        """Get scheduler configuration by task name and portfolio.

        Args:
            task_name: Name of the scheduled task
            portfolio_id: Optional portfolio identifier

        Returns:
            SchedulerConfig instance if found, None otherwise

        Example:
            >>> repo = SchedulerConfigRepository(db)
            >>> config = repo.get_config("price_refresh")
        """
        config = (
            self.db.query(SchedulerConfig)
            .filter(
                SchedulerConfig.task_name == task_name,
                SchedulerConfig.portfolio_id == portfolio_id,
            )
            .first()
        )
        return config

    def get_config_by_id(self, config_id: int) -> Optional[SchedulerConfig]:
        """Get scheduler configuration by ID.

        Args:
            config_id: Configuration identifier

        Returns:
            SchedulerConfig instance if found, None otherwise

        Example:
            >>> repo = SchedulerConfigRepository(db)
            >>> config = repo.get_config_by_id(1)
        """
        config = (
            self.db.query(SchedulerConfig)
            .filter(SchedulerConfig.id == config_id)
            .first()
        )
        return config

    def list_configs(
        self,
        portfolio_id: Optional[str] = None,
        enabled_only: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> List[SchedulerConfig]:
        """List scheduler configurations with optional filtering.

        Args:
            portfolio_id: Optional portfolio filter (None = system-wide only)
            enabled_only: Whether to return only enabled configs
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of scheduler config instances

        Example:
            >>> repo = SchedulerConfigRepository(db)
            >>> configs = repo.list_configs(enabled_only=True)
        """
        query = self.db.query(SchedulerConfig)

        # Filter by portfolio
        if portfolio_id is not None:
            query = query.filter(SchedulerConfig.portfolio_id == portfolio_id)
        else:
            # Return system-wide configs
            query = query.filter(SchedulerConfig.portfolio_id.is_(None))

        # Filter by enabled
        if enabled_only:
            query = query.filter(SchedulerConfig.enabled == True)

        configs = query.order_by(SchedulerConfig.task_name).offset(skip).limit(limit).all()
        return configs

    def list_all_enabled_configs(self) -> List[SchedulerConfig]:
        """List all enabled scheduler configurations (system-wide and portfolio-specific).

        Returns:
            List of all enabled scheduler config instances

        Example:
            >>> repo = SchedulerConfigRepository(db)
            >>> configs = repo.list_all_enabled_configs()
        """
        configs = (
            self.db.query(SchedulerConfig)
            .filter(SchedulerConfig.enabled == True)
            .order_by(SchedulerConfig.task_name)
            .all()
        )
        return configs

    def update_config(
        self,
        config_id: int,
        schedule_type: Optional[str] = None,
        schedule_params: Optional[Dict] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[SchedulerConfig]:
        """Update scheduler configuration.

        Args:
            config_id: Configuration identifier
            schedule_type: Optional new schedule type
            schedule_params: Optional new schedule parameters
            enabled: Optional new enabled state

        Returns:
            Updated scheduler config instance if found, None otherwise

        Example:
            >>> repo = SchedulerConfigRepository(db)
            >>> config = repo.update_config(1, enabled=False)
        """
        config = self.get_config_by_id(config_id)
        if not config:
            return None

        # Update fields
        if schedule_type is not None:
            if schedule_type not in ["interval", "cron"]:
                raise ValueError(f"Invalid schedule_type: {schedule_type}")
            config.schedule_type = schedule_type

        if schedule_params is not None:
            config.schedule_params = json.dumps(schedule_params)

        if enabled is not None:
            config.enabled = enabled

        # Update timestamp
        config.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(config)

        logger.info(f"Updated scheduler config: {config.id} - {config.task_name}")
        return config

    def update_run_times(
        self, config_id: int, last_run: datetime, next_run: Optional[datetime] = None
    ) -> Optional[SchedulerConfig]:
        """Update last and next run times for a configuration.

        Args:
            config_id: Configuration identifier
            last_run: Last execution timestamp
            next_run: Optional next scheduled execution timestamp

        Returns:
            Updated scheduler config instance if found, None otherwise

        Example:
            >>> repo = SchedulerConfigRepository(db)
            >>> config = repo.update_run_times(1, datetime.utcnow())
        """
        config = self.get_config_by_id(config_id)
        if not config:
            return None

        config.last_run = last_run
        if next_run is not None:
            config.next_run = next_run

        self.db.commit()
        self.db.refresh(config)

        return config

    def delete_config(self, config_id: int) -> bool:
        """Delete scheduler configuration.

        Args:
            config_id: Configuration identifier

        Returns:
            True if config was deleted, False if not found

        Example:
            >>> repo = SchedulerConfigRepository(db)
            >>> deleted = repo.delete_config(1)
        """
        config = self.get_config_by_id(config_id)
        if not config:
            return False

        self.db.delete(config)
        self.db.commit()

        logger.info(f"Deleted scheduler config: {config_id}")
        return True

    def parse_schedule_params(self, config: SchedulerConfig) -> Dict:
        """Parse schedule parameters from JSON string.

        Args:
            config: SchedulerConfig instance

        Returns:
            Dictionary with schedule parameters

        Example:
            >>> repo = SchedulerConfigRepository(db)
            >>> params = repo.parse_schedule_params(config)
            >>> print(params)  # {'minutes': 5}
        """
        try:
            return json.loads(config.schedule_params)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse schedule params for config {config.id}: {e}")
            return {}
