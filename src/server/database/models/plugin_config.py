"""Plugin configuration database model.

Stores configuration for dynamically loaded scheduler plugins,
including enabled state, custom schedules, and plugin-specific settings.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from src.server.database.session import Base


class PluginConfig(Base):
    """Plugin configuration model.

    Stores configuration for registered plugins including their
    enabled state, schedule parameters, and custom settings.

    Attributes:
        id: Unique identifier (auto-incrementing integer)
        plugin_name: Unique plugin identifier
        enabled: Whether plugin is currently enabled
        schedule_type: Type of schedule ("interval" or "cron")
        schedule_params: JSON string with schedule parameters
        config_data: JSON string with plugin-specific configuration
        last_enabled_at: Timestamp when plugin was last enabled
        created_at: Timestamp when config was created
        updated_at: Timestamp when config was last modified
    """

    __tablename__ = "plugin_configs"

    # Columns
    id = Column(Integer, primary_key=True, autoincrement=True)
    plugin_name = Column(String, nullable=False, unique=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    schedule_type = Column(String, nullable=False)  # "interval" or "cron"
    schedule_params = Column(Text, nullable=False)  # JSON string
    config_data = Column(Text, nullable=True)  # JSON string for plugin-specific config
    last_enabled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        """String representation for debugging.

        Returns:
            Formatted string with plugin config details
        """
        return (
            f"<PluginConfig(id={self.id}, plugin={self.plugin_name}, "
            f"enabled={self.enabled}, schedule={self.schedule_type})>"
        )
