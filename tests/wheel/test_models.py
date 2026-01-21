"""Tests for wheel data models."""

from datetime import datetime

import pytest

from src.models.profiles import StrikeProfile
from src.wheel.models import (
    TradeRecord,
    WheelPerformance,
    WheelPosition,
    WheelRecommendation,
)
from src.wheel.state import TradeOutcome, WheelState


class TestWheelPosition:
    """Tests for WheelPosition model."""

    def test_default_values(self) -> None:
        """Test default initialization."""
        position = WheelPosition()
        assert position.id is None
        assert position.symbol == ""
        assert position.state == WheelState.CASH
        assert position.capital_allocated == 0.0
        assert position.shares_held == 0
        assert position.cost_basis is None
        assert position.profile == StrikeProfile.CONSERVATIVE
        assert position.is_active is True

    def test_can_sell_put_in_cash_state(self) -> None:
        """Can sell put only in CASH state."""
        position = WheelPosition(state=WheelState.CASH)
        assert position.can_sell_put is True

        position.state = WheelState.SHARES
        assert position.can_sell_put is False

        position.state = WheelState.CASH_PUT_OPEN
        assert position.can_sell_put is False

    def test_can_sell_call_in_shares_state(self) -> None:
        """Can sell call only in SHARES state."""
        position = WheelPosition(state=WheelState.SHARES)
        assert position.can_sell_call is True

        position.state = WheelState.CASH
        assert position.can_sell_call is False

        position.state = WheelState.SHARES_CALL_OPEN
        assert position.can_sell_call is False

    def test_has_open_position(self) -> None:
        """Test has_open_position property."""
        position = WheelPosition(state=WheelState.CASH)
        assert position.has_open_position is False

        position.state = WheelState.CASH_PUT_OPEN
        assert position.has_open_position is True

        position.state = WheelState.SHARES
        assert position.has_open_position is False

        position.state = WheelState.SHARES_CALL_OPEN
        assert position.has_open_position is True

    def test_contracts_from_shares(self) -> None:
        """Test contracts calculation from shares."""
        position = WheelPosition(shares_held=0)
        assert position.contracts_from_shares == 0

        position.shares_held = 100
        assert position.contracts_from_shares == 1

        position.shares_held = 250
        assert position.contracts_from_shares == 2

        position.shares_held = 1000
        assert position.contracts_from_shares == 10

    def test_contracts_from_capital(self) -> None:
        """Test contracts calculation from capital."""
        position = WheelPosition(capital_allocated=10000)

        # $100 strike = $10,000 collateral per contract
        assert position.contracts_from_capital(100) == 1

        # $50 strike = $5,000 collateral per contract
        assert position.contracts_from_capital(50) == 2

        # $200 strike = $20,000 collateral per contract
        assert position.contracts_from_capital(200) == 0

        # Edge case: zero strike
        assert position.contracts_from_capital(0) == 0


class TestTradeRecord:
    """Tests for TradeRecord model."""

    def test_default_values(self) -> None:
        """Test default initialization."""
        trade = TradeRecord()
        assert trade.id is None
        assert trade.wheel_id == 0
        assert trade.symbol == ""
        assert trade.direction == ""
        assert trade.strike == 0.0
        assert trade.outcome == TradeOutcome.OPEN

    def test_total_premium_calculation(self) -> None:
        """Total premium should be calculated in __post_init__."""
        trade = TradeRecord(
            premium_per_share=1.50,
            contracts=2,
        )
        assert trade.total_premium == 300.0  # 1.50 * 2 * 100

    def test_total_premium_not_overwritten(self) -> None:
        """If total_premium is provided, don't recalculate."""
        trade = TradeRecord(
            premium_per_share=1.50,
            contracts=2,
            total_premium=500.0,  # Explicitly set
        )
        assert trade.total_premium == 500.0

    def test_shares_equivalent(self) -> None:
        """Test shares equivalent calculation."""
        trade = TradeRecord(contracts=3)
        assert trade.shares_equivalent == 300

    def test_net_premium_no_close(self) -> None:
        """Net premium equals total when not closed early."""
        trade = TradeRecord(total_premium=150.0)
        assert trade.net_premium == 150.0

    def test_net_premium_with_close(self) -> None:
        """Net premium subtracts close cost when closed early."""
        trade = TradeRecord(
            premium_per_share=1.50,
            contracts=1,
            total_premium=150.0,
            close_price=0.50,
            outcome=TradeOutcome.CLOSED_EARLY,
        )
        # Net = 150 - (0.50 * 1 * 100) = 100
        assert trade.net_premium == 100.0

    def test_is_open(self) -> None:
        """Test is_open property."""
        trade = TradeRecord(outcome=TradeOutcome.OPEN)
        assert trade.is_open is True

        trade.outcome = TradeOutcome.EXPIRED_WORTHLESS
        assert trade.is_open is False


class TestWheelRecommendation:
    """Tests for WheelRecommendation model."""

    def test_effective_yield_for_put(self) -> None:
        """Effective cost if assigned = strike - premium."""
        rec = WheelRecommendation(
            symbol="AAPL",
            direction="put",
            strike=150.0,
            expiration_date="2025-02-21",
            premium_per_share=2.50,
            contracts=1,
            total_premium=250.0,
            sigma_distance=1.5,
            p_itm=0.15,
            annualized_yield_pct=12.0,
        )
        # Effective cost = 150 - 2.50 = 147.50
        assert rec.effective_yield_if_assigned == 147.50

    def test_effective_yield_for_call(self) -> None:
        """Effective sale price = strike + premium."""
        rec = WheelRecommendation(
            symbol="AAPL",
            direction="call",
            strike=160.0,
            expiration_date="2025-02-21",
            premium_per_share=1.50,
            contracts=1,
            total_premium=150.0,
            sigma_distance=1.5,
            p_itm=0.15,
            annualized_yield_pct=10.0,
        )
        # Effective sale = 160 + 1.50 = 161.50
        assert rec.effective_yield_if_assigned == 161.50


class TestWheelPerformance:
    """Tests for WheelPerformance model."""

    def test_default_values(self) -> None:
        """Test default initialization."""
        perf = WheelPerformance(symbol="AAPL")
        assert perf.symbol == "AAPL"
        assert perf.total_premium == 0.0
        assert perf.total_trades == 0
        assert perf.win_rate_pct == 0.0

    def test_completed_trades(self) -> None:
        """Completed trades = total - open."""
        perf = WheelPerformance(
            symbol="AAPL",
            total_trades=10,
            open_trades=2,
        )
        assert perf.completed_trades == 8

    def test_loss_rate_pct(self) -> None:
        """Loss rate = (assignments + called_away) / completed."""
        perf = WheelPerformance(
            symbol="AAPL",
            total_trades=10,
            open_trades=0,
            assignment_events=2,
            called_away_events=1,
        )
        # Loss rate = (2 + 1) / 10 * 100 = 30%
        assert perf.loss_rate_pct == 30.0

    def test_loss_rate_no_completed(self) -> None:
        """Loss rate should be 0 if no completed trades."""
        perf = WheelPerformance(
            symbol="AAPL",
            total_trades=2,
            open_trades=2,
        )
        assert perf.loss_rate_pct == 0.0
