"""Integration tests for scheduler service and lifecycle management.

Tests scheduler initialization, job management, persistence, and
integration with FastAPI application.
"""

import json
import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.server.database.models.scheduler import SchedulerConfig
from src.server.repositories.scheduler_config import SchedulerConfigRepository
from src.server.services.scheduler_service import SchedulerService


# Module-level function for persistence testing (can be serialized)
def _persistent_test_job():
    """Module-level test function that can be serialized by APScheduler."""
    pass


@pytest.fixture
def scheduler_service(test_db):
    """Create a scheduler service instance for testing.

    Uses MemoryJobStore to avoid serialization issues with local test functions.
    """
    from apscheduler.executors.pool import ThreadPoolExecutor
    from apscheduler.jobstores.memory import MemoryJobStore
    from apscheduler.schedulers.background import BackgroundScheduler

    # Create scheduler with memory jobstore for testing
    jobstores = {"default": MemoryJobStore()}
    executors = {"default": ThreadPoolExecutor(max_workers=5)}
    job_defaults = {
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 60,
    }

    service = SchedulerService(db_url="sqlite:///:memory:")
    service.scheduler = BackgroundScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone="America/New_York",
    )
    yield service
    # Clean up
    if service.is_running:
        service.shutdown(wait=False)


@pytest.fixture
def config_repo(test_db):
    """Create a scheduler config repository."""
    return SchedulerConfigRepository(test_db)


class TestSchedulerService:
    """Test cases for SchedulerService."""

    def test_scheduler_initialization(self, scheduler_service):
        """Test scheduler can be initialized."""
        assert scheduler_service.scheduler is not None
        assert scheduler_service.is_running is False

    def test_scheduler_start_stop(self, scheduler_service):
        """Test scheduler lifecycle (start/stop)."""
        # Start scheduler
        scheduler_service.start()
        assert scheduler_service.is_running is True

        # Stop scheduler
        scheduler_service.shutdown()
        assert scheduler_service.is_running is False

    def test_scheduler_status(self, scheduler_service):
        """Test scheduler status reporting."""
        # Initial status
        status = scheduler_service.get_status()
        assert status["initialized"] is True
        assert status["running"] is False
        assert status["jobs_count"] == 0

        # After starting
        scheduler_service.start()
        status = scheduler_service.get_status()
        assert status["running"] is True

    def test_add_job_interval(self, scheduler_service):
        """Test adding an interval-based job."""
        # Track job execution
        execution_count = {"count": 0}

        def test_job():
            execution_count["count"] += 1

        # Start scheduler
        scheduler_service.start()

        # Add job (every second)
        job = scheduler_service.add_job(
            test_job, "interval", id="test_job", name="Test Job", seconds=1
        )

        assert job.id == "test_job"
        assert job.name == "Test Job"

        # Wait for a couple executions
        time.sleep(2.5)

        # Should have executed 2-3 times
        assert execution_count["count"] >= 2

    def test_add_job_cron(self, scheduler_service):
        """Test adding a cron-based job."""

        def test_job():
            pass

        scheduler_service.start()

        # Add job (every hour at minute 0)
        job = scheduler_service.add_job(
            test_job, "cron", id="hourly_job", name="Hourly Job", hour="*", minute="0"
        )

        assert job.id == "hourly_job"
        assert job.trigger is not None

    def test_remove_job(self, scheduler_service):
        """Test removing a job."""

        def test_job():
            pass

        scheduler_service.start()

        # Add job
        scheduler_service.add_job(
            test_job, "interval", id="removable_job", seconds=60
        )

        # Verify job exists
        job = scheduler_service.get_job("removable_job")
        assert job is not None

        # Remove job
        scheduler_service.remove_job("removable_job")

        # Verify job removed
        job = scheduler_service.get_job("removable_job")
        assert job is None

    def test_pause_resume_job(self, scheduler_service):
        """Test pausing and resuming a job."""
        execution_count = {"count": 0}

        def test_job():
            execution_count["count"] += 1

        scheduler_service.start()

        # Add job
        scheduler_service.add_job(
            test_job, "interval", id="pausable_job", seconds=1
        )

        # Wait for some executions
        time.sleep(1.5)
        count_before_pause = execution_count["count"]
        assert count_before_pause >= 1

        # Pause job
        scheduler_service.pause_job("pausable_job")

        # Wait and verify no new executions
        time.sleep(1.5)
        count_after_pause = execution_count["count"]
        assert count_after_pause == count_before_pause

        # Resume job
        scheduler_service.resume_job("pausable_job")

        # Wait and verify executions resumed
        time.sleep(1.5)
        count_after_resume = execution_count["count"]
        assert count_after_resume > count_after_pause

    def test_reschedule_job(self, scheduler_service):
        """Test rescheduling a job."""

        def test_job():
            pass

        scheduler_service.start()

        # Add job (every minute)
        scheduler_service.add_job(
            test_job, "interval", id="reschedulable_job", minutes=1
        )

        # Reschedule to every 2 minutes
        job = scheduler_service.reschedule_job(
            "reschedulable_job", "interval", minutes=2
        )

        assert job.id == "reschedulable_job"
        # Verify trigger was updated (would need to inspect trigger internals)

    def test_get_jobs(self, scheduler_service):
        """Test listing all jobs."""

        def job1():
            pass

        def job2():
            pass

        scheduler_service.start()

        # Add multiple jobs
        scheduler_service.add_job(job1, "interval", id="job1", seconds=60)
        scheduler_service.add_job(job2, "interval", id="job2", seconds=120)

        # Get all jobs
        jobs = scheduler_service.get_jobs()
        assert len(jobs) == 2

        job_ids = [j.id for j in jobs]
        assert "job1" in job_ids
        assert "job2" in job_ids


class TestSchedulerConfigRepository:
    """Test cases for SchedulerConfigRepository."""

    def test_create_config(self, config_repo):
        """Test creating a scheduler configuration."""
        config = config_repo.create_config(
            task_name="test_task",
            schedule_type="interval",
            schedule_params={"minutes": 5},
        )

        assert config.id is not None
        assert config.task_name == "test_task"
        assert config.schedule_type == "interval"
        assert config.enabled is True
        assert config.portfolio_id is None

        # Parse params
        params = config_repo.parse_schedule_params(config)
        assert params == {"minutes": 5}

    def test_create_duplicate_config_fails(self, config_repo):
        """Test creating duplicate config fails."""
        config_repo.create_config(
            task_name="test_task",
            schedule_type="interval",
            schedule_params={"minutes": 5},
        )

        with pytest.raises(ValueError, match="already exists"):
            config_repo.create_config(
                task_name="test_task",
                schedule_type="interval",
                schedule_params={"minutes": 10},
            )

    def test_create_portfolio_specific_config(self, config_repo, client, test_db):
        """Test creating portfolio-specific configuration."""
        # Create portfolio first
        portfolio = client.post(
            "/api/v1/portfolios/", json={"name": "Test Portfolio"}
        ).json()

        config = config_repo.create_config(
            task_name="test_task",
            schedule_type="cron",
            schedule_params={"hour": "9", "minute": "30"},
            portfolio_id=portfolio["id"],
        )

        assert config.portfolio_id == portfolio["id"]
        assert config.task_name == "test_task"

    def test_get_config(self, config_repo):
        """Test retrieving configuration."""
        # Create config
        created = config_repo.create_config(
            task_name="test_task",
            schedule_type="interval",
            schedule_params={"minutes": 5},
        )

        # Retrieve config
        config = config_repo.get_config("test_task")
        assert config is not None
        assert config.id == created.id
        assert config.task_name == "test_task"

    def test_get_config_by_id(self, config_repo):
        """Test retrieving configuration by ID."""
        created = config_repo.create_config(
            task_name="test_task",
            schedule_type="interval",
            schedule_params={"seconds": 30},
        )

        config = config_repo.get_config_by_id(created.id)
        assert config is not None
        assert config.id == created.id

    def test_list_configs(self, config_repo):
        """Test listing configurations."""
        # Create multiple configs
        config_repo.create_config(
            "task1", "interval", {"minutes": 5}, enabled=True
        )
        config_repo.create_config(
            "task2", "cron", {"hour": "10"}, enabled=False
        )
        config_repo.create_config(
            "task3", "interval", {"seconds": 30}, enabled=True
        )

        # List all configs
        all_configs = config_repo.list_configs()
        assert len(all_configs) == 3

        # List enabled only
        enabled_configs = config_repo.list_configs(enabled_only=True)
        assert len(enabled_configs) == 2

    def test_list_all_enabled_configs(self, config_repo, client):
        """Test listing all enabled configs across portfolios."""
        # Create portfolio
        portfolio = client.post(
            "/api/v1/portfolios/", json={"name": "Test Portfolio"}
        ).json()

        # Create system-wide config
        config_repo.create_config("system_task", "interval", {"minutes": 5})

        # Create portfolio-specific config
        config_repo.create_config(
            "portfolio_task",
            "cron",
            {"hour": "9"},
            portfolio_id=portfolio["id"],
        )

        # List all enabled
        configs = config_repo.list_all_enabled_configs()
        assert len(configs) == 2

    def test_update_config(self, config_repo):
        """Test updating configuration."""
        config = config_repo.create_config(
            "test_task", "interval", {"minutes": 5}
        )

        # Update config
        updated = config_repo.update_config(
            config.id,
            schedule_params={"minutes": 10},
            enabled=False,
        )

        assert updated.enabled is False
        params = config_repo.parse_schedule_params(updated)
        assert params == {"minutes": 10}

    def test_update_run_times(self, config_repo):
        """Test updating run times."""
        config = config_repo.create_config(
            "test_task", "interval", {"minutes": 5}
        )

        # Initially no run times
        assert config.last_run is None
        assert config.next_run is None

        # Update run times
        now = datetime.utcnow()
        next_run = now + timedelta(minutes=5)

        updated = config_repo.update_run_times(
            config.id, last_run=now, next_run=next_run
        )

        assert updated.last_run is not None
        assert updated.next_run is not None

    def test_delete_config(self, config_repo):
        """Test deleting configuration."""
        config = config_repo.create_config(
            "test_task", "interval", {"minutes": 5}
        )

        # Delete config
        deleted = config_repo.delete_config(config.id)
        assert deleted is True

        # Verify config is gone
        config = config_repo.get_config_by_id(config.id)
        assert config is None

    def test_invalid_schedule_type(self, config_repo):
        """Test creating config with invalid schedule type fails."""
        with pytest.raises(ValueError, match="Invalid schedule_type"):
            config_repo.create_config(
                "test_task", "invalid_type", {"minutes": 5}
            )


class TestSchedulerIntegration:
    """Test cases for scheduler integration with FastAPI."""

    def test_health_check_includes_scheduler(self, client):
        """Test health check endpoint includes scheduler status."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "scheduler_running" in data
        # Scheduler should be running after app startup
        assert data["scheduler_running"] is True

    def test_scheduler_starts_on_app_startup(self, client):
        """Test scheduler automatically starts with application."""
        # Health check confirms scheduler is running
        response = client.get("/health")
        data = response.json()
        assert data["scheduler_running"] is True


class TestSchedulerPersistence:
    """Test cases for job persistence."""

    def test_jobs_persist_across_restarts(self):
        """Test jobs are persisted and restored on restart."""
        # Use a temporary file for persistence
        import tempfile

        db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        db_url = f"sqlite:///{db_file.name}"

        # Create scheduler and add job
        service1 = SchedulerService(db_url=db_url)
        service1.initialize()
        service1.start()

        # Use module-level function so it can be serialized
        service1.add_job(
            _persistent_test_job, "interval", id="persistent_job", minutes=5
        )

        # Verify job exists
        jobs = service1.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "persistent_job"

        # Shutdown
        service1.shutdown()

        # Create new scheduler instance with same database
        service2 = SchedulerService(db_url=db_url)
        service2.initialize()
        service2.start()

        # Verify job was restored
        jobs = service2.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "persistent_job"

        # Clean up
        service2.shutdown()
        import os

        os.unlink(db_file.name)
