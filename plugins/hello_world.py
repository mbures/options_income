"""Example Hello World plugin.

Simple plugin that logs a hello message on a schedule.
Demonstrates basic plugin structure and implementation.
"""

import logging
from typing import Any, Dict

from src.server.plugins.base import BasePlugin, PluginContext

logger = logging.getLogger(__name__)


class HelloWorldPlugin(BasePlugin):
    """Example plugin that logs a hello message.

    This plugin demonstrates the basic structure of a plugin
    implementation. It logs a message on the configured schedule.
    """

    @property
    def name(self) -> str:
        """Get plugin name."""
        return "hello_world"

    @property
    def description(self) -> str:
        """Get plugin description."""
        return "Example plugin that logs hello messages"

    @property
    def default_schedule(self) -> Dict[str, Any]:
        """Get default schedule (every 1 hour)."""
        return {"trigger": "interval", "hours": 1}

    def execute(self, context: PluginContext) -> None:
        """Execute plugin logic."""
        message = context.config.get("message", "Hello, World!")
        logger.info(f"HelloWorldPlugin: {message}")

    def on_startup(self, context: PluginContext) -> None:
        """Hook called on plugin registration."""
        logger.info("HelloWorldPlugin registered and starting up")

    def on_success(self, context: PluginContext, result: Any = None) -> None:
        """Hook called after successful execution."""
        logger.debug("HelloWorldPlugin executed successfully")

    def on_failure(self, context: PluginContext, error: Exception) -> None:
        """Hook called after failed execution."""
        logger.error(f"HelloWorldPlugin failed: {error}")
