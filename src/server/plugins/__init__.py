"""Plugin system for dynamic task registration.

This module provides the plugin framework for creating custom
scheduled tasks that can be dynamically loaded and registered.
"""

from src.server.plugins.base import BasePlugin, PluginContext
from src.server.plugins.manager import (
    PluginManager,
    get_plugin_manager,
    initialize_plugin_manager,
)

__all__ = [
    "BasePlugin",
    "PluginContext",
    "PluginManager",
    "get_plugin_manager",
    "initialize_plugin_manager",
]
