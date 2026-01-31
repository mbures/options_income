"""
Earnings calendar for options strategy filtering.

This module provides cached earnings date lookups for excluding options
that span earnings announcements, which can cause elevated volatility
and assignment risk.

Example:
    from src.earnings_calendar import EarningsCalendar, EarningsEvent

    calendar = EarningsCalendar(finnhub_client)
    earnings_dates = calendar.get_earnings_dates("AAPL")
    spans, date = calendar.expiration_spans_earnings("AAPL", "2025-02-21")

    # Get detailed earnings events
    events = calendar.get_earnings_events("AAPL")
    for event in events:
        print(f"{event.symbol}: {event.date} ({event.time_of_day})")
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class EarningsEvent:
    """
    Structured earnings event information.

    Attributes:
        symbol: Stock ticker symbol
        date: Earnings announcement date (YYYY-MM-DD)
        time_of_day: When earnings are announced ("BMO", "AMC", or "unknown")
            BMO = Before Market Open
            AMC = After Market Close
        eps_estimate: Consensus EPS estimate (if available)
        eps_actual: Actual reported EPS (if available, after announcement)
        revenue_estimate: Consensus revenue estimate (if available)
        revenue_actual: Actual reported revenue (if available)
        days_until: Days until earnings (negative if past)
    """

    symbol: str
    date: str
    time_of_day: str = "unknown"
    eps_estimate: Optional[float] = None
    eps_actual: Optional[float] = None
    revenue_estimate: Optional[float] = None
    revenue_actual: Optional[float] = None
    days_until: Optional[int] = None

    def __post_init__(self) -> None:
        """Calculate days until earnings."""
        if self.days_until is None:
            try:
                earn_dt = datetime.fromisoformat(self.date)
                self.days_until = (earn_dt - datetime.now()).days
            except ValueError:
                self.days_until = None

    @property
    def is_upcoming(self) -> bool:
        """Check if earnings is in the future."""
        return self.days_until is not None and self.days_until >= 0

    @property
    def is_imminent(self) -> bool:
        """Check if earnings is within 7 days."""
        return self.days_until is not None and 0 <= self.days_until <= 7

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "date": self.date,
            "time_of_day": self.time_of_day,
            "eps_estimate": self.eps_estimate,
            "eps_actual": self.eps_actual,
            "revenue_estimate": self.revenue_estimate,
            "revenue_actual": self.revenue_actual,
            "days_until": self.days_until,
            "is_upcoming": self.is_upcoming,
            "is_imminent": self.is_imminent,
        }


class EarningsCalendar:
    """
    Cached earnings calendar for earnings week exclusion.

    Fetches and caches earnings dates from Finnhub for efficient
    repeated lookups.

    Attributes:
        finnhub_client: Client for API calls
        cache_ttl_hours: How long to cache earnings data
    """

    def __init__(self, finnhub_client: Any, cache_ttl_hours: int = 24):
        """
        Initialize earnings calendar.

        Args:
            finnhub_client: FinnhubClient instance for API calls
            cache_ttl_hours: Cache time-to-live in hours (default 24)
        """
        self._client = finnhub_client
        self._cache: dict[str, tuple[list[str], float]] = {}
        self._cache_ttl = cache_ttl_hours * 3600

    def get_earnings_dates(
        self, symbol: str, from_date: Optional[str] = None, to_date: Optional[str] = None
    ) -> list[str]:
        """
        Get earnings dates for a symbol within date range.

        Args:
            symbol: Stock ticker symbol
            from_date: Start date (YYYY-MM-DD), default today
            to_date: End date (YYYY-MM-DD), default +60 days

        Returns:
            List of earnings dates (YYYY-MM-DD format)
        """
        symbol = symbol.upper()

        # Check cache
        cache_key = symbol
        if cache_key in self._cache:
            dates, cached_at = self._cache[cache_key]
            if (datetime.now().timestamp() - cached_at) < self._cache_ttl:
                logger.debug(f"Cache hit for {symbol} earnings dates")
                return dates

        # Set default date range
        now = datetime.now()
        if from_date is None:
            from_date = now.strftime("%Y-%m-%d")
        if to_date is None:
            to_date = (now + timedelta(days=60)).strftime("%Y-%m-%d")

        # Fetch from Finnhub
        try:
            earnings_dates = self._fetch_earnings_from_finnhub(symbol, from_date, to_date)
            # Cache the results
            self._cache[cache_key] = (earnings_dates, datetime.now().timestamp())
            logger.info(f"Fetched {len(earnings_dates)} earnings dates for {symbol}")
            return earnings_dates
        except Exception as e:
            logger.warning(f"Failed to fetch earnings for {symbol}: {e}")
            return []

    def _fetch_earnings_from_finnhub(self, symbol: str, from_date: str, to_date: str) -> list[str]:
        """
        Fetch earnings dates from Finnhub API via FinnhubClient.

        Args:
            symbol: Stock ticker symbol
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)

        Returns:
            List of earnings dates (YYYY-MM-DD format)
        """
        return self._client.get_earnings_calendar(symbol, from_date, to_date)

    def expiration_spans_earnings(
        self, symbol: str, expiration_date: str
    ) -> tuple[bool, Optional[str]]:
        """
        Check if an expiration date spans an earnings announcement.

        Args:
            symbol: Stock ticker symbol
            expiration_date: Option expiration date (YYYY-MM-DD)

        Returns:
            Tuple of (spans_earnings: bool, earnings_date: str or None)
        """
        now = datetime.now()
        try:
            exp_dt = datetime.fromisoformat(expiration_date)
        except ValueError:
            return False, None

        earnings_dates = self.get_earnings_dates(symbol)

        for earn_date in earnings_dates:
            try:
                earn_dt = datetime.fromisoformat(earn_date)
                if now <= earn_dt <= exp_dt:
                    return True, earn_date
            except ValueError:
                continue

        return False, None

    def get_earnings_events(
        self, symbol: str, from_date: Optional[str] = None, to_date: Optional[str] = None
    ) -> list[EarningsEvent]:
        """
        Get structured earnings events for a symbol.

        Args:
            symbol: Stock ticker symbol
            from_date: Start date (YYYY-MM-DD), default today
            to_date: End date (YYYY-MM-DD), default +60 days

        Returns:
            List of EarningsEvent objects with detailed information
        """
        symbol = symbol.upper()
        dates = self.get_earnings_dates(symbol, from_date, to_date)

        events = []
        for date in dates:
            event = EarningsEvent(symbol=symbol, date=date)
            events.append(event)

        return events

    def get_next_earnings(self, symbol: str) -> Optional[EarningsEvent]:
        """
        Get the next upcoming earnings event for a symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Next EarningsEvent or None if none found
        """
        events = self.get_earnings_events(symbol)
        upcoming = [e for e in events if e.is_upcoming]

        if upcoming:
            # Sort by date and return the nearest
            upcoming.sort(key=lambda e: e.date)
            return upcoming[0]
        return None

    def days_to_earnings(self, symbol: str) -> Optional[int]:
        """
        Get days until next earnings for a symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Days until next earnings, or None if none found
        """
        event = self.get_next_earnings(symbol)
        return event.days_until if event else None

    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """
        Clear cache for symbol or all symbols.

        Args:
            symbol: Symbol to clear, or None to clear all
        """
        if symbol:
            self._cache.pop(symbol.upper(), None)
        else:
            self._cache.clear()
