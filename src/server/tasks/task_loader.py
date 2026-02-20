"""Task loader for registering scheduled tasks with APScheduler.

This module provides utilities to register all core scheduled tasks
with the scheduler on application startup.
"""

import logging

from src.server.services.scheduler_service import SchedulerService
from src.server.tasks.scheduled_tasks import (
    daily_snapshot_task,
    opportunity_scanning_task,
    price_refresh_task,
    risk_monitoring_task,
)

logger = logging.getLogger(__name__)


def register_core_tasks(scheduler: SchedulerService) -> None:
    """Register all core scheduled tasks with the scheduler.

    Args:
        scheduler: SchedulerService instance to register tasks with

    Tasks registered:
        - price_refresh: Every 5 minutes
        - risk_monitoring: Every 15 minutes
        - daily_snapshot: Daily at 4:30 PM ET
        - opportunity_scanning: Daily at 9:45 AM ET
    """
    logger.info("Registering core scheduled tasks")

    # Price Refresh Task - Every 5 minutes
    scheduler.add_job(
        func=price_refresh_task,
        trigger="interval",
        minutes=5,
        id="price_refresh",
        name="Price Refresh Task",
        replace_existing=True,
    )
    logger.info("Registered: Price Refresh Task (every 5 minutes)")

    # Risk Monitoring Task - Every 15 minutes
    scheduler.add_job(
        func=risk_monitoring_task,
        trigger="interval",
        minutes=15,
        id="risk_monitoring",
        name="Risk Monitoring Task",
        replace_existing=True,
    )
    logger.info("Registered: Risk Monitoring Task (every 15 minutes)")

    # Daily Snapshot Task - Daily at 4:30 PM ET
    scheduler.add_job(
        func=daily_snapshot_task,
        trigger="cron",
        hour=16,
        minute=30,
        id="daily_snapshot",
        name="Daily Snapshot Task",
        replace_existing=True,
    )
    logger.info("Registered: Daily Snapshot Task (daily at 4:30 PM ET)")

    # Opportunity Scanning Tasks - 4x/day during market hours
    scan_times = [
        ("opportunity_scanning_1000", 10, 0, "10:00 AM ET"),
        ("opportunity_scanning_1130", 11, 30, "11:30 AM ET"),
        ("opportunity_scanning_1300", 13, 0, "1:00 PM ET"),
        ("opportunity_scanning_1430", 14, 30, "2:30 PM ET"),
    ]
    for job_id, hour, minute, label in scan_times:
        scheduler.add_job(
            func=opportunity_scanning_task,
            trigger="cron",
            hour=hour,
            minute=minute,
            id=job_id,
            name=f"Opportunity Scanning Task ({label})",
            replace_existing=True,
        )
        logger.info(f"Registered: Opportunity Scanning Task ({label})")

    logger.info("All core scheduled tasks registered successfully")


def unregister_core_tasks(scheduler: SchedulerService) -> None:
    """Unregister all core scheduled tasks from the scheduler.

    Args:
        scheduler: SchedulerService instance to unregister tasks from

    Note:
        This is useful for testing or dynamic task management.
    """
    logger.info("Unregistering core scheduled tasks")

    task_ids = [
        "price_refresh",
        "risk_monitoring",
        "daily_snapshot",
        "opportunity_scanning_1000",
        "opportunity_scanning_1130",
        "opportunity_scanning_1300",
        "opportunity_scanning_1430",
    ]

    for task_id in task_ids:
        try:
            scheduler.remove_job(task_id)
            logger.info(f"Unregistered: {task_id}")
        except Exception as e:
            logger.warning(f"Failed to unregister {task_id}: {e}")

    logger.info("Core scheduled tasks unregistered")
