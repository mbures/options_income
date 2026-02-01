"""Tests for scheduler management API endpoints.

Tests job listing, schedule updates, manual triggering, and
execution history retrieval.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.server.database.models.job_execution import JobExecution
from src.server.repositories.job_execution import JobExecutionRepository


class TestListJobs:
    """Test cases for listing scheduled jobs."""

    def test_list_jobs_returns_all_jobs(self, client):
        """Test listing jobs returns all registered jobs."""
        response = client.get("/api/v1/scheduler/jobs")

        assert response.status_code == 200
        data = response.json()

        assert "jobs" in data
        assert "total" in data
        assert isinstance(data["jobs"], list)
        assert data["total"] == len(data["jobs"])

    def test_list_jobs_includes_core_tasks(self, client):
        """Test that core scheduled tasks are in the job list."""
        response = client.get("/api/v1/scheduler/jobs")
        data = response.json()

        job_ids = [job["id"] for job in data["jobs"]]

        # Core tasks should be registered
        assert "price_refresh" in job_ids
        assert "risk_monitoring" in job_ids
        assert "daily_snapshot" in job_ids
        assert "opportunity_scanning" in job_ids

    def test_list_jobs_includes_job_details(self, client):
        """Test job list includes required fields."""
        response = client.get("/api/v1/scheduler/jobs")
        data = response.json()

        if data["jobs"]:
            job = data["jobs"][0]
            assert "id" in job
            assert "name" in job
            assert "func" in job
            assert "trigger" in job
            assert "schedule_description" in job
            assert "enabled" in job


class TestGetJob:
    """Test cases for getting specific job details."""

    def test_get_job_returns_details(self, client):
        """Test getting details for a specific job."""
        response = client.get("/api/v1/scheduler/jobs/price_refresh")

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == "price_refresh"
        assert data["name"] == "Price Refresh Task"
        assert "trigger" in data
        assert "schedule_description" in data

    def test_get_nonexistent_job_returns_404(self, client):
        """Test getting non-existent job returns 404."""
        response = client.get("/api/v1/scheduler/jobs/nonexistent_job")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_get_job_includes_last_execution(self, client, test_db):
        """Test job details include last execution info."""
        # Create an execution record
        exec_repo = JobExecutionRepository(test_db)
        execution = exec_repo.create_execution(
            job_id="price_refresh",
            job_name="Price Refresh Task",
            started_at=datetime.utcnow() - timedelta(minutes=5),
        )
        exec_repo.finish_execution(
            execution_id=execution.id,
            finished_at=datetime.utcnow(),
            status="success",
        )

        # Get job details
        response = client.get("/api/v1/scheduler/jobs/price_refresh")
        data = response.json()

        assert data["last_run_time"] is not None
        assert data["last_status"] == "success"


class TestUpdateJobSchedule:
    """Test cases for updating job schedules."""

    def test_pause_job(self, client):
        """Test pausing a job."""
        response = client.put(
            "/api/v1/scheduler/jobs/price_refresh",
            json={"enabled": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "price_refresh"

    def test_resume_job(self, client):
        """Test resuming a paused job."""
        # First pause
        client.put("/api/v1/scheduler/jobs/price_refresh", json={"enabled": False})

        # Then resume
        response = client.put(
            "/api/v1/scheduler/jobs/price_refresh",
            json={"enabled": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "price_refresh"

    def test_update_nonexistent_job_returns_404(self, client):
        """Test updating non-existent job returns 404."""
        response = client.put(
            "/api/v1/scheduler/jobs/nonexistent_job",
            json={"enabled": False},
        )

        assert response.status_code == 404

    def test_reschedule_job(self, client):
        """Test rescheduling a job with new parameters."""
        response = client.put(
            "/api/v1/scheduler/jobs/price_refresh",
            json={
                "trigger": "interval",
                "schedule_params": {"minutes": 10},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "price_refresh"


class TestTriggerJob:
    """Test cases for manually triggering jobs."""

    def test_trigger_job(self, client):
        """Test manually triggering a job."""
        response = client.post("/api/v1/scheduler/jobs/price_refresh/trigger")

        assert response.status_code == 200
        data = response.json()

        assert data["job_id"] == "price_refresh"
        assert "message" in data
        assert "triggered_at" in data

    def test_trigger_nonexistent_job_returns_404(self, client):
        """Test triggering non-existent job returns 404."""
        response = client.post("/api/v1/scheduler/jobs/nonexistent_job/trigger")

        assert response.status_code == 404


class TestExecutionHistory:
    """Test cases for job execution history."""

    def test_get_execution_history(self, client, test_db):
        """Test getting execution history."""
        # Create some execution records
        exec_repo = JobExecutionRepository(test_db)
        for i in range(3):
            execution = exec_repo.create_execution(
                job_id="price_refresh",
                job_name="Price Refresh Task",
                started_at=datetime.utcnow() - timedelta(minutes=i * 5),
            )
            exec_repo.finish_execution(
                execution_id=execution.id,
                finished_at=datetime.utcnow() - timedelta(minutes=i * 5 - 1),
                status="success",
            )

        # Get history
        response = client.get("/api/v1/scheduler/history")

        assert response.status_code == 200
        data = response.json()

        assert "executions" in data
        assert "total" in data
        assert len(data["executions"]) >= 3
        assert data["total"] >= 3

    def test_filter_execution_history_by_job_id(self, client, test_db):
        """Test filtering execution history by job ID."""
        exec_repo = JobExecutionRepository(test_db)

        # Create executions for different jobs
        for job_id in ["price_refresh", "daily_snapshot"]:
            execution = exec_repo.create_execution(
                job_id=job_id,
                job_name=f"{job_id} Task",
                started_at=datetime.utcnow(),
            )
            exec_repo.finish_execution(
                execution_id=execution.id,
                finished_at=datetime.utcnow(),
                status="success",
            )

        # Filter by price_refresh
        response = client.get("/api/v1/scheduler/history?job_id=price_refresh")
        data = response.json()

        assert all(exec["job_id"] == "price_refresh" for exec in data["executions"])

    def test_filter_execution_history_by_status(self, client, test_db):
        """Test filtering execution history by status."""
        exec_repo = JobExecutionRepository(test_db)

        # Create success and failure executions
        for status in ["success", "failure"]:
            execution = exec_repo.create_execution(
                job_id="price_refresh",
                job_name="Price Refresh Task",
                started_at=datetime.utcnow(),
            )
            exec_repo.finish_execution(
                execution_id=execution.id,
                finished_at=datetime.utcnow(),
                status=status,
                error_message="Test error" if status == "failure" else None,
            )

        # Filter by success
        response = client.get("/api/v1/scheduler/history?status=success")
        data = response.json()

        assert all(exec["status"] == "success" for exec in data["executions"] if exec["status"])

    def test_execution_history_pagination(self, client, test_db):
        """Test pagination of execution history."""
        exec_repo = JobExecutionRepository(test_db)

        # Create many executions
        for i in range(10):
            execution = exec_repo.create_execution(
                job_id="price_refresh",
                job_name="Price Refresh Task",
                started_at=datetime.utcnow() - timedelta(minutes=i),
            )
            exec_repo.finish_execution(
                execution_id=execution.id,
                finished_at=datetime.utcnow() - timedelta(minutes=i - 1),
                status="success",
            )

        # Get first page
        response = client.get("/api/v1/scheduler/history?page=1&page_size=5")
        data = response.json()

        assert data["page"] == 1
        assert data["page_size"] == 5
        assert len(data["executions"]) <= 5
        assert data["total"] >= 10

    def test_execution_record_includes_details(self, client, test_db):
        """Test execution records include all required fields."""
        exec_repo = JobExecutionRepository(test_db)
        execution = exec_repo.create_execution(
            job_id="price_refresh",
            job_name="Price Refresh Task",
            started_at=datetime.utcnow(),
        )
        exec_repo.finish_execution(
            execution_id=execution.id,
            finished_at=datetime.utcnow(),
            status="success",
        )

        response = client.get("/api/v1/scheduler/history")
        data = response.json()

        if data["executions"]:
            exec_record = data["executions"][0]
            assert "id" in exec_record
            assert "job_id" in exec_record
            assert "job_name" in exec_record
            assert "started_at" in exec_record
            assert "finished_at" in exec_record
            assert "duration_seconds" in exec_record
            assert "status" in exec_record


class TestExecutionLogger:
    """Test cases for automatic execution logging."""

    @patch("src.server.tasks.scheduled_tasks.is_market_open")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.execution_logger.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    def test_successful_execution_logs_success(
        self, mock_service_class, mock_exec_logger_session, mock_task_session_factory, mock_market_open, test_db
    ):
        """Test successful task execution creates success log."""
        from src.server.tasks.scheduled_tasks import price_refresh_task

        mock_market_open.return_value = True
        mock_task_session_factory.return_value = lambda: test_db
        mock_exec_logger_session.return_value = lambda: test_db

        # Mock position service
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.total_count = 5
        mock_result.high_risk_count = 1
        mock_service.get_all_open_positions.return_value = mock_result
        mock_service_class.return_value = mock_service

        # Execute task
        price_refresh_task()

        # Check execution log
        exec_repo = JobExecutionRepository(test_db)
        executions = exec_repo.list_executions(job_id="price_refresh", limit=1)

        assert len(executions) > 0
        execution = executions[0]
        assert execution.status == "success"
        assert execution.finished_at is not None
        assert execution.duration_seconds is not None

    @patch("src.server.tasks.execution_logger.get_session_factory")
    def test_failed_execution_logs_failure(
        self, mock_exec_logger_session, test_db
    ):
        """Test failed task execution creates failure log."""
        from src.server.tasks.execution_logger import log_execution

        mock_exec_logger_session.return_value = lambda: test_db

        # Create a test function that raises an error
        @log_execution("test_job", "Test Job")
        def failing_task():
            raise Exception("Test error")

        # Execute task and expect exception
        with pytest.raises(Exception, match="Test error"):
            failing_task()

        # Check execution log
        exec_repo = JobExecutionRepository(test_db)
        executions = exec_repo.list_executions(job_id="test_job", limit=1)

        assert len(executions) > 0
        execution = executions[0]
        assert execution.status == "failure"
        assert execution.error_message == "Test error"
        assert execution.finished_at is not None
