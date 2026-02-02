"""Tests for plugin framework.

Tests plugin discovery, registration, execution, and lifecycle management.
"""

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from src.server.database.models.plugin_config import PluginConfig
from src.server.plugins.base import BasePlugin, PluginContext
from src.server.plugins.manager import PluginManager
from src.server.repositories.plugin_config import PluginConfigRepository


class TestPlugin(BasePlugin):
    """Test plugin for unit tests."""

    def __init__(self, name="test_plugin"):
        self._name = name
        self.executed = False
        self.startup_called = False
        self.success_called = False
        self.failure_called = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Test plugin for unit tests"

    @property
    def default_schedule(self) -> Dict[str, Any]:
        return {"trigger": "interval", "minutes": 5}

    def execute(self, context: PluginContext) -> None:
        self.executed = True

    def on_startup(self, context: PluginContext) -> None:
        self.startup_called = True

    def on_success(self, context: PluginContext, result: Any = None) -> None:
        self.success_called = True

    def on_failure(self, context: PluginContext, error: Exception) -> None:
        self.failure_called = True


class FailingPlugin(BasePlugin):
    """Plugin that always fails for testing error handling."""

    @property
    def name(self) -> str:
        return "failing_plugin"

    @property
    def description(self) -> str:
        return "Plugin that fails for testing"

    @property
    def default_schedule(self) -> Dict[str, Any]:
        return {"trigger": "interval", "minutes": 10}

    def execute(self, context: PluginContext) -> None:
        raise Exception("Plugin execution failed")


class TestPluginConfigRepository:
    """Test cases for plugin configuration repository."""

    def test_create_config(self, test_db):
        """Test creating plugin configuration."""
        repo = PluginConfigRepository(test_db)

        config = repo.create_config(
            plugin_name="test_plugin",
            schedule_type="interval",
            schedule_params={"minutes": 5},
            enabled=True,
            config_data={"key": "value"},
        )

        assert config.plugin_name == "test_plugin"
        assert config.schedule_type == "interval"
        assert config.enabled is True
        assert json.loads(config.schedule_params) == {"minutes": 5}
        assert json.loads(config.config_data) == {"key": "value"}

    def test_get_config(self, test_db):
        """Test retrieving plugin configuration."""
        repo = PluginConfigRepository(test_db)

        repo.create_config(
            plugin_name="test_plugin",
            schedule_type="interval",
            schedule_params={"minutes": 5},
        )

        config = repo.get_config("test_plugin")
        assert config is not None
        assert config.plugin_name == "test_plugin"

    def test_get_nonexistent_config(self, test_db):
        """Test retrieving non-existent configuration."""
        repo = PluginConfigRepository(test_db)
        config = repo.get_config("nonexistent")
        assert config is None

    def test_list_configs(self, test_db):
        """Test listing all configurations."""
        repo = PluginConfigRepository(test_db)

        repo.create_config("plugin1", "interval", {"minutes": 5})
        repo.create_config("plugin2", "cron", {"hour": 10})

        configs = repo.list_configs()
        assert len(configs) == 2

    def test_list_enabled_configs(self, test_db):
        """Test listing only enabled configurations."""
        repo = PluginConfigRepository(test_db)

        repo.create_config("plugin1", "interval", {"minutes": 5}, enabled=True)
        repo.create_config("plugin2", "cron", {"hour": 10}, enabled=False)

        configs = repo.list_configs(enabled_only=True)
        assert len(configs) == 1
        assert configs[0].plugin_name == "plugin1"

    def test_update_config(self, test_db):
        """Test updating plugin configuration."""
        repo = PluginConfigRepository(test_db)

        repo.create_config("test_plugin", "interval", {"minutes": 5})

        updated = repo.update_config(
            "test_plugin",
            schedule_type="cron",
            schedule_params={"hour": 10},
            enabled=False,
        )

        assert updated.schedule_type == "cron"
        assert json.loads(updated.schedule_params) == {"hour": 10}
        assert updated.enabled is False

    def test_delete_config(self, test_db):
        """Test deleting plugin configuration."""
        repo = PluginConfigRepository(test_db)

        repo.create_config("test_plugin", "interval", {"minutes": 5})
        result = repo.delete_config("test_plugin")
        assert result is True

        config = repo.get_config("test_plugin")
        assert config is None

    def test_enable_plugin(self, test_db):
        """Test enabling a plugin."""
        repo = PluginConfigRepository(test_db)

        repo.create_config("test_plugin", "interval", {"minutes": 5}, enabled=False)
        config = repo.enable_plugin("test_plugin")

        assert config.enabled is True
        assert config.last_enabled_at is not None

    def test_disable_plugin(self, test_db):
        """Test disabling a plugin."""
        repo = PluginConfigRepository(test_db)

        repo.create_config("test_plugin", "interval", {"minutes": 5}, enabled=True)
        config = repo.disable_plugin("test_plugin")

        assert config.enabled is False

    def test_parse_schedule_params(self, test_db):
        """Test parsing schedule parameters."""
        repo = PluginConfigRepository(test_db)

        config = repo.create_config(
            "test_plugin", "interval", {"minutes": 5, "seconds": 30}
        )

        params = repo.parse_schedule_params(config)
        assert params == {"minutes": 5, "seconds": 30}

    def test_parse_config_data(self, test_db):
        """Test parsing plugin configuration data."""
        repo = PluginConfigRepository(test_db)

        config = repo.create_config(
            "test_plugin",
            "interval",
            {"minutes": 5},
            config_data={"setting1": "value1", "setting2": 123},
        )

        data = repo.parse_config_data(config)
        assert data == {"setting1": "value1", "setting2": 123}


class TestPluginManager:
    """Test cases for plugin manager."""

    @patch("src.server.plugins.manager.get_session_factory")
    def test_register_plugin(self, mock_session_factory, test_db):
        """Test registering a plugin."""
        mock_session_factory.return_value = lambda: test_db

        from src.server.services.scheduler_service import SchedulerService

        scheduler = SchedulerService(db_url="sqlite:///:memory:")
        scheduler.initialize()
        scheduler.start()

        manager = PluginManager(scheduler)
        plugin = TestPlugin()

        result = manager.register_plugin(plugin, enable=False)
        assert result is True
        assert plugin.startup_called is True

        # Verify plugin is registered
        assert manager.get_plugin("test_plugin") == plugin

        scheduler.shutdown(wait=False)

    @patch("src.server.plugins.manager.get_session_factory")
    def test_register_duplicate_plugin(self, mock_session_factory, test_db):
        """Test registering duplicate plugin fails."""
        mock_session_factory.return_value = lambda: test_db

        from src.server.services.scheduler_service import SchedulerService

        scheduler = SchedulerService(db_url="sqlite:///:memory:")
        scheduler.initialize()
        scheduler.start()

        manager = PluginManager(scheduler)
        plugin1 = TestPlugin()
        plugin2 = TestPlugin()

        manager.register_plugin(plugin1, enable=False)
        result = manager.register_plugin(plugin2, enable=False)

        assert result is False

        scheduler.shutdown(wait=False)

    @patch("src.server.plugins.manager.get_session_factory")
    def test_unregister_plugin(self, mock_session_factory, test_db):
        """Test unregistering a plugin."""
        mock_session_factory.return_value = lambda: test_db

        from src.server.services.scheduler_service import SchedulerService

        scheduler = SchedulerService(db_url="sqlite:///:memory:")
        scheduler.initialize()
        scheduler.start()

        manager = PluginManager(scheduler)
        plugin = TestPlugin()

        manager.register_plugin(plugin, enable=False)
        result = manager.unregister_plugin("test_plugin")

        assert result is True
        assert manager.get_plugin("test_plugin") is None

        scheduler.shutdown(wait=False)

    @patch("src.server.plugins.manager.get_session_factory")
    def test_enable_plugin(self, mock_session_factory, test_db):
        """Test enabling a plugin adds it to scheduler."""
        mock_session_factory.return_value = lambda: test_db

        from apscheduler.executors.pool import ThreadPoolExecutor
        from apscheduler.jobstores.memory import MemoryJobStore
        from apscheduler.schedulers.background import BackgroundScheduler

        from src.server.services.scheduler_service import SchedulerService

        scheduler = SchedulerService(db_url="sqlite:///:memory:")

        # Use MemoryJobStore for tests to avoid serialization issues
        jobstores = {"default": MemoryJobStore()}
        executors = {"default": ThreadPoolExecutor(max_workers=5)}
        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        }

        scheduler.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone="America/New_York",
        )
        scheduler.start()

        manager = PluginManager(scheduler)
        plugin = TestPlugin()

        manager.register_plugin(plugin, enable=False)
        result = manager.enable_plugin("test_plugin")

        assert result is True

        # Verify job was added to scheduler
        jobs = scheduler.get_jobs()
        job_ids = [job.id for job in jobs]
        assert "plugin_test_plugin" in job_ids

        scheduler.shutdown(wait=False)

    @patch("src.server.plugins.manager.get_session_factory")
    def test_disable_plugin(self, mock_session_factory, test_db):
        """Test disabling a plugin removes it from scheduler."""
        mock_session_factory.return_value = lambda: test_db

        from apscheduler.executors.pool import ThreadPoolExecutor
        from apscheduler.jobstores.memory import MemoryJobStore
        from apscheduler.schedulers.background import BackgroundScheduler

        from src.server.services.scheduler_service import SchedulerService

        scheduler = SchedulerService(db_url="sqlite:///:memory:")

        # Use MemoryJobStore for tests to avoid serialization issues
        jobstores = {"default": MemoryJobStore()}
        executors = {"default": ThreadPoolExecutor(max_workers=5)}
        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        }

        scheduler.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone="America/New_York",
        )
        scheduler.start()

        manager = PluginManager(scheduler)
        plugin = TestPlugin()

        manager.register_plugin(plugin, enable=True)
        result = manager.disable_plugin("test_plugin")

        assert result is True

        # Verify job was removed from scheduler
        jobs = scheduler.get_jobs()
        job_ids = [job.id for job in jobs]
        assert "plugin_test_plugin" not in job_ids

        scheduler.shutdown(wait=False)

    @patch("src.server.plugins.manager.get_session_factory")
    def test_list_plugins(self, mock_session_factory, test_db):
        """Test listing all registered plugins."""
        mock_session_factory.return_value = lambda: test_db

        from src.server.services.scheduler_service import SchedulerService

        scheduler = SchedulerService(db_url="sqlite:///:memory:")
        scheduler.initialize()
        scheduler.start()

        manager = PluginManager(scheduler)
        plugin1 = TestPlugin("plugin1")
        plugin2 = TestPlugin("plugin2")

        manager.register_plugin(plugin1, enable=False)
        manager.register_plugin(plugin2, enable=False)

        plugins = manager.list_plugins()
        assert len(plugins) == 2

        scheduler.shutdown(wait=False)

    def test_discover_plugins(self, tmp_path):
        """Test discovering plugins from directory."""
        from src.server.services.scheduler_service import SchedulerService

        scheduler = SchedulerService(db_url="sqlite:///:memory:")
        scheduler.initialize()
        scheduler.start()

        # Create test plugin file
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text('''
from src.server.plugins.base import BasePlugin, PluginContext
from typing import Dict, Any

class DiscoveredPlugin(BasePlugin):
    @property
    def name(self) -> str:
        return "discovered"

    @property
    def description(self) -> str:
        return "Discovered plugin"

    @property
    def default_schedule(self) -> Dict[str, Any]:
        return {"trigger": "interval", "minutes": 1}

    def execute(self, context: PluginContext) -> None:
        pass
''')

        manager = PluginManager(scheduler, plugins_dir=tmp_path)
        discovered = manager.discover_plugins()

        assert len(discovered) == 1
        assert discovered[0].__name__ == "DiscoveredPlugin"

        scheduler.shutdown(wait=False)


class TestPluginExecution:
    """Test cases for plugin execution."""

    @patch("src.server.plugins.manager.get_session_factory")
    def test_plugin_execution(self, mock_session_factory, test_db):
        """Test plugin executes successfully."""
        mock_session_factory.return_value = lambda: test_db

        plugin = TestPlugin()
        context = PluginContext(db=test_db, config={}, scheduler=None)

        plugin.execute(context)
        assert plugin.executed is True

    @patch("src.server.plugins.manager.get_session_factory")
    def test_plugin_failure(self, mock_session_factory, test_db):
        """Test plugin failure handling."""
        mock_session_factory.return_value = lambda: test_db

        plugin = FailingPlugin()
        context = PluginContext(db=test_db, config={}, scheduler=None)

        with pytest.raises(Exception, match="Plugin execution failed"):
            plugin.execute(context)


class TestPluginHooks:
    """Test cases for plugin lifecycle hooks."""

    @patch("src.server.plugins.manager.get_session_factory")
    def test_on_startup_hook(self, mock_session_factory, test_db):
        """Test on_startup hook is called."""
        mock_session_factory.return_value = lambda: test_db

        from src.server.services.scheduler_service import SchedulerService

        scheduler = SchedulerService(db_url="sqlite:///:memory:")
        scheduler.initialize()
        scheduler.start()

        manager = PluginManager(scheduler)
        plugin = TestPlugin()

        manager.register_plugin(plugin, enable=False)
        assert plugin.startup_called is True

        scheduler.shutdown(wait=False)

    def test_on_success_hook(self, test_db):
        """Test on_success hook is called after execution."""
        plugin = TestPlugin()
        context = PluginContext(db=test_db, config={}, scheduler=None)

        plugin.execute(context)
        plugin.on_success(context)

        assert plugin.success_called is True

    def test_on_failure_hook(self, test_db):
        """Test on_failure hook is called after failure."""
        plugin = TestPlugin()
        context = PluginContext(db=test_db, config={}, scheduler=None)

        error = Exception("Test error")
        plugin.on_failure(context, error)

        assert plugin.failure_called is True
