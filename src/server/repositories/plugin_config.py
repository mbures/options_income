"""Repository for plugin configuration operations.

Provides database access layer for plugin configuration,
including enabling/disabling plugins and managing custom schedules.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.server.database.models.plugin_config import PluginConfig

logger = logging.getLogger(__name__)


class PluginConfigRepository:
    """Repository for managing plugin configuration.

    Handles CRUD operations for plugin configurations,
    including schedule management and plugin state.
    """

    def __init__(self, db: Session):
        """Initialize repository with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def create_config(
        self,
        plugin_name: str,
        schedule_type: str,
        schedule_params: Dict[str, Any],
        enabled: bool = True,
        config_data: Optional[Dict[str, Any]] = None,
    ) -> PluginConfig:
        """Create a new plugin configuration.

        Args:
            plugin_name: Unique plugin identifier
            schedule_type: Schedule type ("interval" or "cron")
            schedule_params: Schedule parameters dictionary
            enabled: Whether plugin should be enabled
            config_data: Plugin-specific configuration

        Returns:
            Created PluginConfig instance

        Raises:
            IntegrityError: If plugin_name already exists
        """
        config = PluginConfig(
            plugin_name=plugin_name,
            enabled=enabled,
            schedule_type=schedule_type,
            schedule_params=json.dumps(schedule_params),
            config_data=json.dumps(config_data) if config_data else None,
            last_enabled_at=datetime.utcnow() if enabled else None,
        )
        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        logger.info(f"Created config for plugin {plugin_name}")
        return config

    def get_config(self, plugin_name: str) -> Optional[PluginConfig]:
        """Get plugin configuration by name.

        Args:
            plugin_name: Plugin identifier

        Returns:
            PluginConfig instance or None if not found
        """
        return (
            self.db.query(PluginConfig)
            .filter(PluginConfig.plugin_name == plugin_name)
            .first()
        )

    def list_configs(
        self,
        enabled_only: bool = False,
    ) -> List[PluginConfig]:
        """List all plugin configurations.

        Args:
            enabled_only: If True, only return enabled plugins

        Returns:
            List of PluginConfig instances
        """
        query = self.db.query(PluginConfig)
        if enabled_only:
            query = query.filter(PluginConfig.enabled == True)
        return query.order_by(PluginConfig.plugin_name).all()

    def update_config(
        self,
        plugin_name: str,
        schedule_type: Optional[str] = None,
        schedule_params: Optional[Dict[str, Any]] = None,
        config_data: Optional[Dict[str, Any]] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[PluginConfig]:
        """Update plugin configuration.

        Args:
            plugin_name: Plugin identifier
            schedule_type: New schedule type
            schedule_params: New schedule parameters
            config_data: New plugin configuration
            enabled: New enabled state

        Returns:
            Updated PluginConfig instance or None if not found
        """
        config = self.get_config(plugin_name)
        if not config:
            logger.warning(f"Plugin config {plugin_name} not found")
            return None

        if schedule_type is not None:
            config.schedule_type = schedule_type
        if schedule_params is not None:
            config.schedule_params = json.dumps(schedule_params)
        if config_data is not None:
            config.config_data = json.dumps(config_data)
        if enabled is not None:
            old_enabled = config.enabled
            config.enabled = enabled
            if enabled and not old_enabled:
                config.last_enabled_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(config)
        logger.info(f"Updated config for plugin {plugin_name}")
        return config

    def delete_config(self, plugin_name: str) -> bool:
        """Delete plugin configuration.

        Args:
            plugin_name: Plugin identifier

        Returns:
            True if deleted, False if not found
        """
        config = self.get_config(plugin_name)
        if not config:
            return False

        self.db.delete(config)
        self.db.commit()
        logger.info(f"Deleted config for plugin {plugin_name}")
        return True

    def enable_plugin(self, plugin_name: str) -> Optional[PluginConfig]:
        """Enable a plugin.

        Args:
            plugin_name: Plugin identifier

        Returns:
            Updated PluginConfig or None if not found
        """
        return self.update_config(plugin_name, enabled=True)

    def disable_plugin(self, plugin_name: str) -> Optional[PluginConfig]:
        """Disable a plugin.

        Args:
            plugin_name: Plugin identifier

        Returns:
            Updated PluginConfig or None if not found
        """
        return self.update_config(plugin_name, enabled=False)

    def parse_schedule_params(self, config: PluginConfig) -> Dict[str, Any]:
        """Parse schedule parameters from JSON string.

        Args:
            config: PluginConfig instance

        Returns:
            Schedule parameters dictionary
        """
        try:
            return json.loads(config.schedule_params)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse schedule params for {config.plugin_name}")
            return {}

    def parse_config_data(self, config: PluginConfig) -> Dict[str, Any]:
        """Parse plugin configuration data from JSON string.

        Args:
            config: PluginConfig instance

        Returns:
            Configuration data dictionary
        """
        if not config.config_data:
            return {}
        try:
            return json.loads(config.config_data)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse config data for {config.plugin_name}")
            return {}
