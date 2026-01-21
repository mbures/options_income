"""Tests for the earnings calendar module."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.earnings_calendar import EarningsCalendar, EarningsEvent


class TestEarningsEvent:
    """Tests for EarningsEvent dataclass."""

    def test_basic_creation(self):
        """Test creating an EarningsEvent."""
        event = EarningsEvent(
            symbol="AAPL",
            date="2025-02-15",
            time_of_day="AMC",
        )

        assert event.symbol == "AAPL"
        assert event.date == "2025-02-15"
        assert event.time_of_day == "AMC"

    def test_default_values(self):
        """Test default values for optional fields."""
        event = EarningsEvent(symbol="AAPL", date="2025-02-15")

        assert event.time_of_day == "unknown"
        assert event.eps_estimate is None
        assert event.eps_actual is None
        assert event.revenue_estimate is None
        assert event.revenue_actual is None

    def test_days_until_calculation(self):
        """Test automatic calculation of days_until."""
        # Create event for 30 days from now
        future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        event = EarningsEvent(symbol="AAPL", date=future_date)

        assert event.days_until == pytest.approx(30, abs=1)
        assert event.is_upcoming is True

    def test_is_imminent(self):
        """Test is_imminent property."""
        # Event 5 days from now
        near_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        near_event = EarningsEvent(symbol="AAPL", date=near_date)
        assert near_event.is_imminent is True

        # Event 10 days from now
        far_date = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        far_event = EarningsEvent(symbol="AAPL", date=far_date)
        assert far_event.is_imminent is False

    def test_is_upcoming_past_date(self):
        """Test is_upcoming for past dates."""
        past_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        event = EarningsEvent(symbol="AAPL", date=past_date)

        assert event.is_upcoming is False

    def test_to_dict(self):
        """Test serialization to dictionary."""
        event = EarningsEvent(
            symbol="AAPL",
            date="2025-02-15",
            time_of_day="BMO",
            eps_estimate=2.50,
        )

        d = event.to_dict()
        assert d["symbol"] == "AAPL"
        assert d["date"] == "2025-02-15"
        assert d["time_of_day"] == "BMO"
        assert d["eps_estimate"] == 2.50
        assert "is_upcoming" in d
        assert "is_imminent" in d

    def test_invalid_date(self):
        """Test handling of invalid date format."""
        event = EarningsEvent(symbol="AAPL", date="invalid-date")
        assert event.days_until is None


class TestEarningsCalendar:
    """Tests for EarningsCalendar class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Finnhub client."""
        client = MagicMock()
        # Set up default return value
        future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        client.get_earnings_calendar.return_value = [future_date]
        return client

    @pytest.fixture
    def calendar(self, mock_client):
        """Create an EarningsCalendar with mock client."""
        return EarningsCalendar(mock_client, cache_ttl_hours=24)

    def test_get_earnings_dates(self, calendar, mock_client):
        """Test fetching earnings dates."""
        dates = calendar.get_earnings_dates("AAPL")

        assert len(dates) == 1
        mock_client.get_earnings_calendar.assert_called_once()

    def test_caching(self, calendar, mock_client):
        """Test that results are cached."""
        # First call
        dates1 = calendar.get_earnings_dates("AAPL")
        # Second call
        dates2 = calendar.get_earnings_dates("AAPL")

        # Should only call API once
        assert mock_client.get_earnings_calendar.call_count == 1
        assert dates1 == dates2

    def test_different_symbols_not_cached(self, calendar, mock_client):
        """Test that different symbols aren't shared in cache."""
        calendar.get_earnings_dates("AAPL")
        calendar.get_earnings_dates("MSFT")

        assert mock_client.get_earnings_calendar.call_count == 2

    def test_clear_cache_single_symbol(self, calendar, mock_client):
        """Test clearing cache for single symbol."""
        calendar.get_earnings_dates("AAPL")
        calendar.get_earnings_dates("MSFT")

        calendar.clear_cache("AAPL")

        # AAPL should refetch
        calendar.get_earnings_dates("AAPL")
        # MSFT should still be cached
        calendar.get_earnings_dates("MSFT")

        # AAPL called twice, MSFT once
        calls = mock_client.get_earnings_calendar.call_args_list
        aapl_calls = [c for c in calls if c[0][0] == "AAPL"]
        assert len(aapl_calls) == 2

    def test_clear_cache_all(self, calendar, mock_client):
        """Test clearing all cached data."""
        calendar.get_earnings_dates("AAPL")
        calendar.get_earnings_dates("MSFT")

        calendar.clear_cache()

        # Both should refetch
        calendar.get_earnings_dates("AAPL")
        calendar.get_earnings_dates("MSFT")

        assert mock_client.get_earnings_calendar.call_count == 4

    def test_expiration_spans_earnings_true(self, mock_client):
        """Test detecting when expiration spans earnings."""
        # Earnings 15 days from now
        earnings_date = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")
        mock_client.get_earnings_calendar.return_value = [earnings_date]

        calendar = EarningsCalendar(mock_client)

        # Expiration 30 days from now (after earnings)
        expiration = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        spans, date = calendar.expiration_spans_earnings("AAPL", expiration)

        assert spans is True
        assert date == earnings_date

    def test_expiration_spans_earnings_false(self, mock_client):
        """Test when expiration doesn't span earnings."""
        # Earnings 30 days from now
        earnings_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        mock_client.get_earnings_calendar.return_value = [earnings_date]

        calendar = EarningsCalendar(mock_client)

        # Expiration 15 days from now (before earnings)
        expiration = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")

        spans, date = calendar.expiration_spans_earnings("AAPL", expiration)

        assert spans is False
        assert date is None

    def test_expiration_spans_earnings_invalid_date(self, calendar):
        """Test handling of invalid expiration date."""
        spans, date = calendar.expiration_spans_earnings("AAPL", "invalid-date")

        assert spans is False
        assert date is None

    def test_get_earnings_events(self, mock_client):
        """Test getting structured earnings events."""
        future_dates = [
            (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d"),
            (datetime.now() + timedelta(days=45)).strftime("%Y-%m-%d"),
        ]
        mock_client.get_earnings_calendar.return_value = future_dates

        calendar = EarningsCalendar(mock_client)
        events = calendar.get_earnings_events("AAPL")

        assert len(events) == 2
        assert all(isinstance(e, EarningsEvent) for e in events)
        assert all(e.symbol == "AAPL" for e in events)

    def test_get_next_earnings(self, mock_client):
        """Test getting next upcoming earnings."""
        future_dates = [
            (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
            (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d"),
        ]
        mock_client.get_earnings_calendar.return_value = future_dates

        calendar = EarningsCalendar(mock_client)
        event = calendar.get_next_earnings("AAPL")

        assert event is not None
        assert event.date == future_dates[0]  # Nearest one

    def test_get_next_earnings_none(self, mock_client):
        """Test when no upcoming earnings."""
        mock_client.get_earnings_calendar.return_value = []

        calendar = EarningsCalendar(mock_client)
        event = calendar.get_next_earnings("AAPL")

        assert event is None

    def test_days_to_earnings(self, mock_client):
        """Test getting days until next earnings."""
        future_date = (datetime.now() + timedelta(days=20)).strftime("%Y-%m-%d")
        mock_client.get_earnings_calendar.return_value = [future_date]

        calendar = EarningsCalendar(mock_client)
        days = calendar.days_to_earnings("AAPL")

        assert days == pytest.approx(20, abs=1)

    def test_days_to_earnings_none(self, mock_client):
        """Test when no earnings dates available."""
        mock_client.get_earnings_calendar.return_value = []

        calendar = EarningsCalendar(mock_client)
        days = calendar.days_to_earnings("AAPL")

        assert days is None

    def test_api_error_handling(self, mock_client):
        """Test graceful handling of API errors."""
        mock_client.get_earnings_calendar.side_effect = Exception("API Error")

        calendar = EarningsCalendar(mock_client)
        dates = calendar.get_earnings_dates("AAPL")

        assert dates == []

    def test_symbol_normalization(self, calendar, mock_client):
        """Test that symbols are normalized to uppercase."""
        calendar.get_earnings_dates("aapl")
        calendar.get_earnings_dates("AAPL")

        # Should only call once due to caching with normalized key
        assert mock_client.get_earnings_calendar.call_count == 1


class TestEarningsCalendarIntegration:
    """Integration-style tests for EarningsCalendar."""

    @pytest.fixture
    def mock_client_with_dates(self):
        """Create a mock client with realistic earnings dates."""
        client = MagicMock()

        # Simulate quarterly earnings
        dates = [
            (datetime.now() + timedelta(days=45)).strftime("%Y-%m-%d"),
            (datetime.now() + timedelta(days=135)).strftime("%Y-%m-%d"),
        ]
        client.get_earnings_calendar.return_value = dates
        return client

    def test_full_workflow(self, mock_client_with_dates):
        """Test complete workflow of checking earnings for options."""
        calendar = EarningsCalendar(mock_client_with_dates)

        # Check next earnings
        next_earnings = calendar.get_next_earnings("AAPL")
        assert next_earnings is not None
        assert next_earnings.is_upcoming

        # Check if weekly expiration spans earnings
        weekly_exp = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        spans, _ = calendar.expiration_spans_earnings("AAPL", weekly_exp)
        assert spans is False  # 7 days before 45-day earnings

        # Check if monthly expiration spans earnings
        monthly_exp = (datetime.now() + timedelta(days=50)).strftime("%Y-%m-%d")
        spans, earn_date = calendar.expiration_spans_earnings("AAPL", monthly_exp)
        assert spans is True  # 50 days spans 45-day earnings
