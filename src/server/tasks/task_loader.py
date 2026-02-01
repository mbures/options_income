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

    # Opportunity Scanning Task - Daily at 9:45 AM ET
    scheduler.add_job(
        func=opportunity_scanning_task,
        trigger="cron",
        hour=9,
        minute=45,
        id="opportunity_scanning",
        name="Opportunity Scanning Task",
        replace_existing=True,
    )
    logger.info("Registered: Opportunity Scanning Task (daily at 9:45 AM ET)")

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
        "opportunity_scanning",
    ]

    for task_id in task_ids:
        try:
            scheduler.remove_job(task_id)
            logger.info(f"Unregistered: {task_id}")
        except Exception as e:
            logger.warning(f"Failed to unregister {task_id}: {e}")

    logger.info("Core scheduled tasks unregistered")
