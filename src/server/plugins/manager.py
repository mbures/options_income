"""Plugin manager for dynamic task registration.

Handles plugin discovery, registration, and lifecycle management
for custom scheduled tasks.
"""

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Type

from sqlalchemy.orm import Session

from src.server.database.session import get_session_factory
from src.server.plugins.base import BasePlugin, PluginContext
from src.server.repositories.plugin_config import PluginConfigRepository
from src.server.services.scheduler_service import SchedulerService
from src.server.tasks.execution_logger import log_execution

logger = logging.getLogger(__name__)


class PluginManager:
    """Manager for scheduler plugins.

    Handles plugin discovery, registration, enabling/disabling,
    and integration with the task scheduler.
    """

    def __init__(self, scheduler: SchedulerService, plugins_dir: Optional[Path] = None):
        """Initialize plugin manager.

        Args:
            scheduler: Scheduler service instance
            plugins_dir: Directory to scan for plugins (default: ./plugins)
        """
        self.scheduler = scheduler
        self.plugins_dir = plugins_dir or Path("plugins")
        self._registered_plugins: Dict[str, BasePlugin] = {}

    def register_plugin(
        self,
        plugin: BasePlugin,
        custom_schedule: Optional[Dict] = None,
        enable: bool = True,
    ) -> bool:
        """Register a plugin instance.

        Adds the plugin to the registry and optionally schedules it.

        Args:
            plugin: Plugin instance to register
            custom_schedule: Custom schedule to override default
            enable: Whether to immediately enable the plugin

        Returns:
            True if registered successfully, False otherwise
        """
        plugin_name = plugin.name

        if plugin_name in self._registered_plugins:
            logger.warning(f"Plugin {plugin_name} already registered")
            return False

        # Register plugin
        self._registered_plugins[plugin_name] = plugin
        logger.info(f"Registered plugin: {plugin_name}")

        # Call on_startup hook
        try:
            SessionLocal = get_session_factory()
            db = SessionLocal()
            try:
                context = PluginContext(db=db, scheduler=self.scheduler)
                plugin.on_startup(context)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Plugin {plugin_name} on_startup failed: {e}", exc_info=True)

        # Persist configuration
        try:
            SessionLocal = get_session_factory()
            db = SessionLocal()
            try:
                repo = PluginConfigRepository(db)
                existing_config = repo.get_config(plugin_name)

                if not existing_config:
                    # Create new config
                    schedule = custom_schedule or plugin.default_schedule
                    repo.create_config(
                        plugin_name=plugin_name,
                        schedule_type=schedule.get("trigger", "interval"),
                        schedule_params=schedule,
                        enabled=enable,
                    )
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to persist config for {plugin_name}: {e}", exc_info=True)

        # Add to scheduler if enabled
        if enable:
            self._schedule_plugin(plugin, custom_schedule)

        return True

    def unregister_plugin(self, plugin_name: str) -> bool:
        """Unregister a plugin.

        Removes the plugin from the registry and scheduler.

        Args:
            plugin_name: Name of plugin to unregister

        Returns:
            True if unregistered successfully, False if not found
        """
        if plugin_name not in self._registered_plugins:
            logger.warning(f"Plugin {plugin_name} not registered")
            return False

        # Remove from scheduler
        try:
            job_id = f"plugin_{plugin_name}"
            self.scheduler.remove_job(job_id)
        except Exception as e:
            logger.warning(f"Failed to remove job for {plugin_name}: {e}")

        # Remove from registry
        del self._registered_plugins[plugin_name]
        logger.info(f"Unregistered plugin: {plugin_name}")
        return True

    def enable_plugin(self, plugin_name: str) -> bool:
        """Enable a registered plugin.

        Adds the plugin to the scheduler.

        Args:
            plugin_name: Name of plugin to enable

        Returns:
            True if enabled successfully, False if not found
        """
        plugin = self._registered_plugins.get(plugin_name)
        if not plugin:
            logger.warning(f"Plugin {plugin_name} not registered")
            return False

        # Update config
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            repo = PluginConfigRepository(db)
            repo.enable_plugin(plugin_name)
        finally:
            db.close()

        # Add to scheduler
        self._schedule_plugin(plugin)
        logger.info(f"Enabled plugin: {plugin_name}")
        return True

    def disable_plugin(self, plugin_name: str) -> bool:
        """Disable a registered plugin.

        Removes the plugin from the scheduler but keeps it registered.

        Args:
            plugin_name: Name of plugin to disable

        Returns:
            True if disabled successfully, False if not found
        """
        if plugin_name not in self._registered_plugins:
            logger.warning(f"Plugin {plugin_name} not registered")
            return False

        # Update config
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            repo = PluginConfigRepository(db)
            repo.disable_plugin(plugin_name)
        finally:
            db.close()

        # Remove from scheduler
        try:
            job_id = f"plugin_{plugin_name}"
            self.scheduler.remove_job(job_id)
        except Exception as e:
            logger.warning(f"Failed to remove job for {plugin_name}: {e}")

        logger.info(f"Disabled plugin: {plugin_name}")
        return True

    def discover_plugins(self) -> List[Type[BasePlugin]]:
        """Discover plugins from plugins directory.

        Scans the plugins directory for Python modules and attempts
        to import BasePlugin subclasses.

        Returns:
            List of discovered plugin classes
        """
        if not self.plugins_dir.exists():
            logger.info(f"Plugins directory {self.plugins_dir} does not exist")
            return []

        discovered = []

        for plugin_file in self.plugins_dir.glob("*.py"):
            if plugin_file.name.startswith("_"):
                continue

            try:
                # Import module
                module_name = f"plugins.{plugin_file.stem}"
                spec = importlib.util.spec_from_file_location(module_name, plugin_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)

                    # Find BasePlugin subclasses
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, BasePlugin)
                            and attr is not BasePlugin
                        ):
                            discovered.append(attr)
                            logger.info(f"Discovered plugin class: {attr.__name__}")

            except Exception as e:
                logger.error(
                    f"Failed to import plugin from {plugin_file}: {e}", exc_info=True
                )

        return discovered

    def load_plugins(self) -> int:
        """Discover and register all plugins.

        Scans plugins directory and registers all discovered plugins.

        Returns:
            Number of plugins loaded
        """
        plugin_classes = self.discover_plugins()
        loaded_count = 0

        for plugin_class in plugin_classes:
            try:
                plugin = plugin_class()
                if self.register_plugin(plugin, enable=False):
                    loaded_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to instantiate plugin {plugin_class.__name__}: {e}",
                    exc_info=True,
                )

        logger.info(f"Loaded {loaded_count} plugins")
        return loaded_count

    def load_enabled_plugins(self) -> int:
        """Load and enable plugins from database configuration.

        Reads plugin configurations and enables those marked as enabled.

        Returns:
            Number of plugins enabled
        """
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            repo = PluginConfigRepository(db)
            enabled_configs = repo.list_configs(enabled_only=True)

            for config in enabled_configs:
                plugin = self._registered_plugins.get(config.plugin_name)
                if plugin:
                    schedule_params = repo.parse_schedule_params(config)
                    self._schedule_plugin(plugin, schedule_params)

            return len(enabled_configs)
        finally:
            db.close()

    def get_plugin(self, plugin_name: str) -> Optional[BasePlugin]:
        """Get a registered plugin by name.

        Args:
            plugin_name: Plugin identifier

        Returns:
            Plugin instance or None if not found
        """
        return self._registered_plugins.get(plugin_name)

    def list_plugins(self) -> List[BasePlugin]:
        """List all registered plugins.

        Returns:
            List of plugin instances
        """
        return list(self._registered_plugins.values())

    def _schedule_plugin(
        self,
        plugin: BasePlugin,
        custom_schedule: Optional[Dict] = None,
    ) -> None:
        """Add plugin to scheduler.

        Args:
            plugin: Plugin instance
            custom_schedule: Custom schedule parameters
        """
        schedule = custom_schedule or plugin.default_schedule
        job_id = f"plugin_{plugin.name}"

        # Create wrapped execution function with logging
        @log_execution(job_id, f"Plugin: {plugin.name}")
        def execute_plugin():
            SessionLocal = get_session_factory()
            db = SessionLocal()
            try:
                # Get plugin config
                repo = PluginConfigRepository(db)
                config_model = repo.get_config(plugin.name)
                config_data = repo.parse_config_data(config_model) if config_model else {}

                # Create context
                context = PluginContext(
                    db=db, config=config_data, scheduler=self.scheduler
                )

                # Execute plugin
                try:
                    result = plugin.execute(context)
                    plugin.on_success(context, result)
                except Exception as e:
                    plugin.on_failure(context, e)
                    raise

            finally:
                db.close()

        # Add to scheduler
        trigger = schedule.pop("trigger", "interval")
        self.scheduler.add_job(
            func=execute_plugin,
            trigger=trigger,
            id=job_id,
            name=f"Plugin: {plugin.description}",
            replace_existing=True,
            **schedule,
        )
        logger.info(f"Scheduled plugin {plugin.name} with trigger {trigger}")


# Global plugin manager instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> Optional[PluginManager]:
    """Get global plugin manager instance.

    Returns:
        PluginManager instance or None if not initialized
    """
    return _plugin_manager


def initialize_plugin_manager(scheduler: SchedulerService) -> PluginManager:
    """Initialize global plugin manager.

    Args:
        scheduler: Scheduler service instance

    Returns:
        Initialized PluginManager instance
    """
    global _plugin_manager
    _plugin_manager = PluginManager(scheduler)
    return _plugin_manager
