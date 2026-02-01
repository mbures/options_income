"""Market hours utilities for scheduled task management.

This module provides utilities to determine if the market is open
and manage task execution based on trading hours.
"""

import logging
from datetime import datetime, time
from typing import Optional

import pytz

logger = logging.getLogger(__name__)

# US Eastern timezone for market hours
EASTERN = pytz.timezone("America/New_York")

# Standard market hours (Eastern Time)
MARKET_OPEN_TIME = time(9, 30)  # 9:30 AM ET
MARKET_CLOSE_TIME = time(16, 0)  # 4:00 PM ET

# Days when market is closed (0=Monday, 6=Sunday)
MARKET_CLOSED_DAYS = [5, 6]  # Saturday, Sunday


def is_market_open(now: Optional[datetime] = None) -> bool:
    """Check if the US stock market is currently open.

    Args:
        now: Optional datetime to check (defaults to current time)

    Returns:
        True if market is open, False otherwise

    Note:
        This is a simplified implementation that only checks:
        - Day of week (weekdays only)
        - Time of day (9:30 AM - 4:00 PM ET)

        Does NOT account for:
        - Market holidays (New Year's, MLK Day, Presidents Day, etc.)
        - Early closures (day before holidays)
        - Extended hours trading

        For production use, integrate with a trading calendar API.
    """
    if now is None:
        now = datetime.now(EASTERN)
    elif now.tzinfo is None:
        # Assume UTC if no timezone, convert to Eastern
        now = pytz.utc.localize(now).astimezone(EASTERN)
    else:
        now = now.astimezone(EASTERN)

    # Check if weekend
    if now.weekday() in MARKET_CLOSED_DAYS:
        return False

    # Check if within trading hours
    current_time = now.time()
    if current_time < MARKET_OPEN_TIME or current_time >= MARKET_CLOSE_TIME:
        return False

    return True


def should_run_task(task_name: str, now: Optional[datetime] = None) -> bool:
    """Determine if a scheduled task should run based on market hours.

    Some tasks should only run during market hours, while others
    (like EOD snapshots) should run after market close.

    Args:
        task_name: Name of the task to check
        now: Optional datetime to check (defaults to current time)

    Returns:
        True if task should run, False otherwise
    """
    # Tasks that only run during market hours
    market_hours_tasks = {
        "price_refresh",
        "risk_monitoring",
        "opportunity_scanning",
    }

    # Tasks that run after market close
    after_hours_tasks = {
        "daily_snapshot",
    }

    if task_name in market_hours_tasks:
        return is_market_open(now)
    elif task_name in after_hours_tasks:
        # For after-hours tasks, check if it's after market close
        # but still on a weekday
        if now is None:
            now = datetime.now(EASTERN)
        elif now.tzinfo is None:
            now = pytz.utc.localize(now).astimezone(EASTERN)
        else:
            now = now.astimezone(EASTERN)

        # Not on weekend
        if now.weekday() in MARKET_CLOSED_DAYS:
            return False

        # After market close but before midnight
        current_time = now.time()
        return current_time >= MARKET_CLOSE_TIME

    # Unknown task - let it run
    return True


def get_next_market_open(now: Optional[datetime] = None) -> datetime:
    """Get the datetime of the next market open.

    Args:
        now: Optional datetime to check from (defaults to current time)

    Returns:
        Datetime of next market open (Eastern timezone)

    Note:
        This does not account for market holidays.
    """
    from datetime import timedelta

    if now is None:
        now = datetime.now(EASTERN)
    elif now.tzinfo is None:
        now = pytz.utc.localize(now).astimezone(EASTERN)
    else:
        now = now.astimezone(EASTERN)

    # Start with tomorrow
    next_open = now.replace(
        hour=MARKET_OPEN_TIME.hour,
        minute=MARKET_OPEN_TIME.minute,
        second=0,
        microsecond=0,
    )

    # If current time is before market open today, use today
    if now.time() < MARKET_OPEN_TIME:
        next_open = next_open
    else:
        # Otherwise use tomorrow
        next_open = next_open + timedelta(days=1)

    # Skip weekends
    while next_open.weekday() in MARKET_CLOSED_DAYS:
        next_open = next_open + timedelta(days=1)

    return next_open


def get_next_market_close(now: Optional[datetime] = None) -> datetime:
    """Get the datetime of the next market close.

    Args:
        now: Optional datetime to check from (defaults to current time)

    Returns:
        Datetime of next market close (Eastern timezone)

    Note:
        This does not account for market holidays or early closures.
    """
    from datetime import timedelta

    if now is None:
        now = datetime.now(EASTERN)
    elif now.tzinfo is None:
        now = pytz.utc.localize(now).astimezone(EASTERN)
    else:
        now = now.astimezone(EASTERN)

    # Start with today's close
    next_close = now.replace(
        hour=MARKET_CLOSE_TIME.hour,
        minute=MARKET_CLOSE_TIME.minute,
        second=0,
        microsecond=0,
    )

    # If current time is before market close today, use today
    if now.time() < MARKET_CLOSE_TIME and now.weekday() not in MARKET_CLOSED_DAYS:
        return next_close

    # Otherwise find next weekday
    next_close = next_close + timedelta(days=1)
    while next_close.weekday() in MARKET_CLOSED_DAYS:
        next_close = next_close + timedelta(days=1)

    return next_close
