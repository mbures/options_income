"""
Market data fetching package.

This package contains modules for fetching external market data:
- price_fetcher: Historical price data with caching
- earnings_calendar: Earnings event calendar data
- finnhub_client: Finnhub API client (legacy)

All classes and functions are re-exported at the package level for convenience.
"""

# Import from price_fetcher
from src.market_data.price_fetcher import (
    CacheEntry,
    PriceDataCache,
    PriceDataFetcher,
    SchwabPriceDataFetcher,
)

# Import from earnings_calendar
from src.market_data.earnings_calendar import EarningsCalendar, EarningsEvent

# Import from finnhub_client
from src.market_data.finnhub_client import FinnhubAPIError, FinnhubClient

__all__ = [
    # price_fetcher
    "CacheEntry",
    "PriceDataCache",
    "PriceDataFetcher",
    "SchwabPriceDataFetcher",
    # earnings_calendar
    "EarningsCalendar",
    "EarningsEvent",
    # finnhub_client
    "FinnhubAPIError",
    "FinnhubClient",
]
