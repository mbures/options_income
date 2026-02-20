"""Tests for position monitoring functionality."""

import pytest
from datetime import date, datetime
from unittest.mock import Mock, patch

from src.wheel.monitor import PositionMonitor
from src.wheel.models import WheelPosition, TradeRecord, PositionStatus
from src.wheel.state import WheelState, TradeOutcome


class TestPositionMonitor:
    """Test suite for PositionMonitor class."""

    def test_init(self):
        """Test PositionMonitor initialization."""
        monitor = PositionMonitor()
        assert monitor.schwab_client is None
        assert monitor.price_fetcher is None
        assert monitor._cache == {}

    def test_init_with_clients(self):
        """Test PositionMonitor initialization with clients."""
        schwab = Mock()
        fetcher = Mock()
        monitor = PositionMonitor(schwab, fetcher)
        assert monitor.schwab_client == schwab
        assert monitor.price_fetcher == fetcher

    # Moneyness calculation tests

    def test_calculate_moneyness_put_itm(self):
        """Test moneyness calculation for ITM put."""
        monitor = PositionMonitor()
        result = monitor._calculate_moneyness(
            current_price=145.0, strike=150.0, direction="put"
        )

        assert result.is_itm is True
        assert result.is_otm is False
        assert result.pct == pytest.approx(-3.33, abs=0.01)
        assert "ITM" in result.label
        assert result.price_diff == 5.0  # strike - price when ITM

    def test_calculate_moneyness_put_otm(self):
        """Test moneyness calculation for OTM put."""
        monitor = PositionMonitor()
        result = monitor._calculate_moneyness(
            current_price=155.0, strike=150.0, direction="put"
        )

        assert result.is_itm is False
        assert result.is_otm is True
        assert result.pct == pytest.approx(3.33, abs=0.01)
        assert "OTM" in result.label
        assert result.price_diff == -5.0  # Negative when OTM

    def test_calculate_moneyness_put_atm(self):
        """Test moneyness calculation for ATM put."""
        monitor = PositionMonitor()
        result = monitor._calculate_moneyness(
            current_price=150.0, strike=150.0, direction="put"
        )

        # At strike, put is ITM (price <= strike)
        assert result.is_itm is True
        assert result.pct == pytest.approx(0.0)

    def test_calculate_moneyness_call_itm(self):
        """Test moneyness calculation for ITM call."""
        monitor = PositionMonitor()
        result = monitor._calculate_moneyness(
            current_price=155.0, strike=150.0, direction="call"
        )

        assert result.is_itm is True
        assert result.is_otm is False
        assert result.pct == pytest.approx(3.33, abs=0.01)
        assert "ITM" in result.label
        assert result.price_diff == 5.0  # price - strike when ITM

    def test_calculate_moneyness_call_otm(self):
        """Test moneyness calculation for OTM call."""
        monitor = PositionMonitor()
        result = monitor._calculate_moneyness(
            current_price=145.0, strike=150.0, direction="call"
        )

        assert result.is_itm is False
        assert result.is_otm is True
        assert result.pct == pytest.approx(-3.33, abs=0.01)
        assert "OTM" in result.label
        assert result.price_diff == -5.0  # Negative when OTM

    def test_calculate_moneyness_call_atm(self):
        """Test moneyness calculation for ATM call."""
        monitor = PositionMonitor()
        result = monitor._calculate_moneyness(
            current_price=150.0, strike=150.0, direction="call"
        )

        # At strike, call is ITM (price >= strike)
        assert result.is_itm is True
        assert result.pct == pytest.approx(0.0)

    # Risk assessment tests

    def test_assess_risk_high_itm(self):
        """Test risk assessment for ITM position."""
        monitor = PositionMonitor()
        risk_level, risk_icon = monitor._assess_risk(moneyness_pct=-1.0, is_itm=True)

        assert risk_level == "HIGH"
        assert risk_icon == "🔴"

    def test_assess_risk_medium_near_strike(self):
        """Test risk assessment for OTM position near strike."""
        monitor = PositionMonitor()
        risk_level, risk_icon = monitor._assess_risk(moneyness_pct=3.0, is_itm=False)

        assert risk_level == "MEDIUM"
        assert risk_icon == "🟡"

    def test_assess_risk_medium_boundary(self):
        """Test risk assessment at 5% boundary."""
        monitor = PositionMonitor()
        risk_level, risk_icon = monitor._assess_risk(moneyness_pct=5.0, is_itm=False)

        assert risk_level == "MEDIUM"
        assert risk_icon == "🟡"

    def test_assess_risk_low_far_otm(self):
        """Test risk assessment for far OTM position."""
        monitor = PositionMonitor()
        risk_level, risk_icon = monitor._assess_risk(moneyness_pct=8.0, is_itm=False)

        assert risk_level == "LOW"
        assert risk_icon == "🟢"

    def test_assess_risk_low_just_over_threshold(self):
        """Test risk assessment just over 5% threshold."""
        monitor = PositionMonitor()
        risk_level, risk_icon = monitor._assess_risk(moneyness_pct=5.1, is_itm=False)

        assert risk_level == "LOW"
        assert risk_icon == "🟢"

    # Price fetching tests

    def test_fetch_current_price_from_schwab(self):
        """Test price fetching from Schwab client."""
        schwab = Mock()
        schwab.get_quote.return_value = {"lastPrice": 155.50}
        monitor = PositionMonitor(schwab_client=schwab)

        price = monitor._fetch_current_price("AAPL", force_refresh=True)

        assert price == 155.50
        schwab.get_quote.assert_called_once_with("AAPL")
        assert "AAPL" in monitor._cache

    def test_fetch_current_price_schwab_fallback_to_close(self):
        """Test Schwab client using 'closePrice' when 'lastPrice' unavailable."""
        schwab = Mock()
        schwab.get_quote.return_value = {"closePrice": 155.50}  # No 'lastPrice'
        monitor = PositionMonitor(schwab_client=schwab)

        price = monitor._fetch_current_price("AAPL", force_refresh=True)

        assert price == 155.50

    def test_fetch_current_price_from_fallback_fetcher(self):
        """Test price fetching from fallback fetcher when Schwab fails."""
        schwab = Mock()
        schwab.get_quote.side_effect = Exception("Schwab error")
        fetcher = Mock()
        fetcher.get_current_price.return_value = 155.50
        monitor = PositionMonitor(schwab_client=schwab, price_fetcher=fetcher)

        price = monitor._fetch_current_price("AAPL", force_refresh=True)

        assert price == 155.50
        fetcher.get_current_price.assert_called_once_with("AAPL")

    def test_fetch_current_price_cache_hit(self):
        """Test price fetching uses cache within TTL."""
        monitor = PositionMonitor()
        monitor._cache["AAPL"] = ({"lastPrice": 155.50}, datetime.now())

        price = monitor._fetch_current_price("AAPL", force_refresh=False)

        assert price == 155.50
        # No API calls should be made

    def test_fetch_current_price_force_refresh_bypasses_cache(self):
        """Test force_refresh bypasses cache."""
        schwab = Mock()
        schwab.get_quote.return_value = {"lastPrice": 160.00}
        monitor = PositionMonitor(schwab_client=schwab)
        monitor._cache["AAPL"] = ({"lastPrice": 155.50}, datetime.now())

        price = monitor._fetch_current_price("AAPL", force_refresh=True)

        assert price == 160.00  # New price, not cached
        schwab.get_quote.assert_called_once()

    def test_fetch_current_price_no_provider_raises(self):
        """Test error when no price provider configured."""
        monitor = PositionMonitor()

        with pytest.raises(ValueError, match="No price data provider"):
            monitor._fetch_current_price("AAPL", force_refresh=True)

    # Quote data tests

    def test_fetch_quote_data_returns_ohlc(self):
        """Test _fetch_quote_data returns full OHLC dict from Schwab."""
        schwab = Mock()
        schwab.get_quote.return_value = {
            "lastPrice": 155.50,
            "openPrice": 153.00,
            "highPrice": 156.00,
            "lowPrice": 152.50,
            "closePrice": 154.00,
        }
        monitor = PositionMonitor(schwab_client=schwab)

        quote = monitor._fetch_quote_data("AAPL", force_refresh=True)

        assert quote["lastPrice"] == 155.50
        assert quote["openPrice"] == 153.00
        assert quote["highPrice"] == 156.00
        assert quote["lowPrice"] == 152.50
        assert quote["closePrice"] == 154.00

    def test_fetch_quote_data_fallback_has_none_ohlc(self):
        """Test _fetch_quote_data from fallback fetcher has None OHLC."""
        schwab = Mock()
        schwab.get_quote.side_effect = Exception("Schwab error")
        fetcher = Mock()
        fetcher.get_current_price.return_value = 155.50
        monitor = PositionMonitor(schwab_client=schwab, price_fetcher=fetcher)

        quote = monitor._fetch_quote_data("AAPL", force_refresh=True)

        assert quote["lastPrice"] == 155.50
        assert quote["openPrice"] is None
        assert quote["highPrice"] is None
        assert quote["lowPrice"] is None
        assert quote["closePrice"] is None

    # Helper method tests

    def test_find_open_trade(self):
        """Test finding open trade for a position."""
        monitor = PositionMonitor()
        position = WheelPosition(id=1, symbol="AAPL", state=WheelState.CASH_PUT_OPEN)
        trades = [
            TradeRecord(id=1, wheel_id=1, symbol="AAPL", outcome=TradeOutcome.OPEN),
            TradeRecord(
                id=2, wheel_id=1, symbol="AAPL", outcome=TradeOutcome.EXPIRED_WORTHLESS
            ),
            TradeRecord(id=3, wheel_id=2, symbol="MSFT", outcome=TradeOutcome.OPEN),
        ]

        found = monitor._find_open_trade(position, trades)

        assert found is not None
        assert found.id == 1
        assert found.outcome == TradeOutcome.OPEN

    def test_find_open_trade_not_found(self):
        """Test finding open trade when none exists."""
        monitor = PositionMonitor()
        position = WheelPosition(id=1, symbol="AAPL", state=WheelState.CASH_PUT_OPEN)
        trades = [
            TradeRecord(
                id=2, wheel_id=1, symbol="AAPL", outcome=TradeOutcome.EXPIRED_WORTHLESS
            ),
        ]

        found = monitor._find_open_trade(position, trades)

        assert found is None

    # Integration tests

    @patch("src.server.tasks.market_hours.is_market_open")
    @patch("src.wheel.monitor.calculate_days_to_expiry")
    @patch("src.wheel.monitor.calculate_trading_days")
    def test_get_position_status(
        self, mock_trading_days, mock_days_to_expiry, mock_market_open
    ):
        """Test getting position status with mocked price."""
        mock_days_to_expiry.return_value = 24
        mock_trading_days.return_value = 17
        mock_market_open.return_value = True

        schwab = Mock()
        schwab.get_quote.return_value = {
            "lastPrice": 155.00,
            "openPrice": 153.00,
            "highPrice": 156.00,
            "lowPrice": 152.50,
            "closePrice": 154.00,
        }
        monitor = PositionMonitor(schwab_client=schwab)

        position = WheelPosition(
            id=1, symbol="AAPL", state=WheelState.CASH_PUT_OPEN, capital_allocated=20000.0
        )
        trade = TradeRecord(
            id=1,
            wheel_id=1,
            symbol="AAPL",
            direction="put",
            strike=150.0,
            expiration_date="2025-02-21",
            premium_per_share=2.50,
            contracts=1,
            total_premium=250.0,
            outcome=TradeOutcome.OPEN,
        )

        status = monitor.get_position_status(position, trade, force_refresh=True)

        assert status.symbol == "AAPL"
        assert status.direction == "put"
        assert status.strike == 150.0
        assert status.current_price == 155.00
        assert status.dte_calendar == 24
        assert status.dte_trading == 17
        assert status.is_otm is True
        assert status.risk_level == "MEDIUM"
        assert status.premium_collected == 250.0
        # Verify OHLC fields
        assert status.open_price == 153.00
        assert status.high_price == 156.00
        assert status.low_price == 152.50
        assert status.close_price == 154.00
        assert status.market_open is True

    def test_get_position_status_invalid_state_raises(self):
        """Test error when position not in monitorable state."""
        monitor = PositionMonitor()
        position = WheelPosition(id=1, symbol="AAPL", state=WheelState.CASH)
        trade = TradeRecord(id=1, wheel_id=1, symbol="AAPL")

        with pytest.raises(ValueError, match="not in an open state"):
            monitor.get_position_status(position, trade)

    def test_create_snapshot(self):
        """Test creating a snapshot from status."""
        monitor = PositionMonitor()
        trade = TradeRecord(id=1, wheel_id=1, symbol="AAPL")
        status = PositionStatus(
            symbol="AAPL",
            direction="put",
            strike=150.0,
            expiration_date="2025-02-21",
            dte_calendar=24,
            dte_trading=17,
            current_price=155.0,
            price_vs_strike=-5.0,
            is_itm=False,
            is_otm=True,
            moneyness_pct=3.33,
            moneyness_label="OTM by 3.3%",
            risk_level="MEDIUM",
            risk_icon="🟡",
        )

        snapshot = monitor.create_snapshot(trade, status, date(2025, 1, 28))

        assert snapshot.trade_id == 1
        assert snapshot.snapshot_date == "2025-01-28"
        assert snapshot.current_price == 155.0
        assert snapshot.dte_calendar == 24
        assert snapshot.dte_trading == 17
        assert snapshot.moneyness_pct == 3.33
        assert snapshot.is_itm is False
        assert snapshot.risk_level == "MEDIUM"
