"""Base plugin class for wheel strategy scheduler plugins.

Defines the interface for custom scheduled tasks that can be
dynamically loaded and registered with the scheduler.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session


class PluginContext:
    """Context object passed to plugin execution.

    Provides access to database session, services, and configuration
    for plugin implementations.

    Attributes:
        db: SQLAlchemy database session
        config: Plugin-specific configuration dictionary
        scheduler: SchedulerService instance
    """

    def __init__(
        self,
        db: Session,
        config: Optional[Dict[str, Any]] = None,
        scheduler: Optional[Any] = None,
    ):
        """Initialize plugin context.

        Args:
            db: Database session
            config: Plugin configuration
            scheduler: Scheduler service instance
        """
        self.db = db
        self.config = config or {}
        self.scheduler = scheduler


class BasePlugin(ABC):
    """Base class for scheduler plugins.

    All plugins must inherit from this class and implement the required
    abstract methods. Plugins can optionally override hook methods for
    lifecycle events.

    Example:
        >>> class MyPlugin(BasePlugin):
        >>>     @property
        >>>     def name(self) -> str:
        >>>         return "my_plugin"
        >>>
        >>>     @property
        >>>     def default_schedule(self) -> Dict[str, Any]:
        >>>         return {"trigger": "interval", "hours": 1}
        >>>
        >>>     def execute(self, context: PluginContext) -> None:
        >>>         # Plugin implementation
        >>>         pass
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Get plugin name.

        Must be unique across all registered plugins.
        Used as identifier for registration and configuration.

        Returns:
            Plugin name (lowercase, underscores for spaces)
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Get plugin description.

        Human-readable description of what the plugin does.

        Returns:
            Plugin description
        """
        pass

    @property
    @abstractmethod
    def default_schedule(self) -> Dict[str, Any]:
        """Get default schedule parameters.

        Returns dictionary with schedule configuration for APScheduler.

        For interval triggers:
            {"trigger": "interval", "minutes": 5}
            {"trigger": "interval", "hours": 1}

        For cron triggers:
            {"trigger": "cron", "hour": 16, "minute": 30}
            {"trigger": "cron", "day_of_week": "mon-fri", "hour": 9}

        Returns:
            Schedule parameters dictionary
        """
        pass

    @abstractmethod
    def execute(self, context: PluginContext) -> None:
        """Execute plugin logic.

        This method is called by the scheduler according to the
        configured schedule. All plugin logic should be implemented here.

        Args:
            context: Plugin execution context with db, config, and scheduler

        Raises:
            Exception: Any exception raised will be logged and trigger on_failure hook
        """
        pass

    def on_startup(self, context: PluginContext) -> None:
        """Hook called when plugin is registered/loaded.

        Override to perform initialization tasks when the plugin
        is first loaded into the system.

        Args:
            context: Plugin context
        """
        pass

    def on_success(self, context: PluginContext, result: Any = None) -> None:
        """Hook called after successful execution.

        Override to perform cleanup or logging after successful execution.

        Args:
            context: Plugin context
            result: Return value from execute() method
        """
        pass

    def on_failure(self, context: PluginContext, error: Exception) -> None:
        """Hook called after failed execution.

        Override to perform error handling, alerting, or cleanup
        after execution failure.

        Args:
            context: Plugin context
            error: Exception that was raised during execution
        """
        pass

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate plugin configuration.

        Override to validate plugin-specific configuration before
        it is applied. Return False to reject invalid configuration.

        Args:
            config: Configuration dictionary to validate

        Returns:
            True if configuration is valid, False otherwise
        """
        return True

    def get_config_schema(self) -> Optional[Dict[str, Any]]:
        """Get JSON schema for plugin configuration.

        Override to provide a JSON schema that describes the
        expected configuration structure for this plugin.

        Returns:
            JSON schema dictionary or None
        """
        return None
