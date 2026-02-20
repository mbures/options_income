"""Database models for the backend server.

This module exports all SQLAlchemy ORM models used by the backend server.
Models define the database schema and relationships between entities.

Models:
    Portfolio: Organizes wheels by strategy, account, or risk level
    Wheel: Represents a wheel position on a symbol within a portfolio
    Trade: Records individual option trades (puts and calls)
    Snapshot: Daily historical snapshots of open positions
    PerformanceMetrics: Pre-calculated performance analytics
    SchedulerConfig: Configuration for background scheduled tasks
    JobExecution: Execution history for scheduled background tasks
    PluginConfig: Configuration for dynamically loaded plugins
    WatchlistItem: Symbol on the user's opportunity scanning watchlist
    Opportunity: Scanned option-selling opportunity from watchlist scanner
"""

from .job_execution import JobExecution
from .opportunity import Opportunity
from .performance import PerformanceMetrics
from .plugin_config import PluginConfig
from .portfolio import Portfolio
from .scheduler import SchedulerConfig
from .snapshot import Snapshot
from .trade import Trade
from .watchlist import WatchlistItem
from .wheel import Wheel

__all__ = [
    "Portfolio",
    "Wheel",
    "Trade",
    "Snapshot",
    "PerformanceMetrics",
    "SchedulerConfig",
    "JobExecution",
    "PluginConfig",
    "WatchlistItem",
    "Opportunity",
]
