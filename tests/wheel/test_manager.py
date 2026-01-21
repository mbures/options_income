"""Tests for wheel manager (integration tests)."""

import os
import tempfile

import pytest

from src.models.profiles import StrikeProfile
from src.wheel.exceptions import (
    DuplicateSymbolError,
    InsufficientCapitalError,
    InvalidStateError,
    SymbolNotFoundError,
    TradeNotFoundError,
)
from src.wheel.manager import WheelManager
from src.wheel.state import TradeOutcome, WheelState


@pytest.fixture
def temp_db() -> str:
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def manager(temp_db: str) -> WheelManager:
    """Create a manager with temporary database."""
    return WheelManager(db_path=temp_db)


class TestWheelCRUD:
    """Tests for wheel CRUD operations."""

    def test_create_wheel(self, manager: WheelManager) -> None:
        """Test creating a new wheel."""
        wheel = manager.create_wheel(
            symbol="AAPL",
            capital=10000.0,
            profile="conservative",
        )

        assert wheel.symbol == "AAPL"
        assert wheel.capital_allocated == 10000.0
        assert wheel.state == WheelState.CASH
        assert wheel.profile == StrikeProfile.CONSERVATIVE

    def test_create_wheel_uppercase_symbol(self, manager: WheelManager) -> None:
        """Symbol should be uppercased."""
        wheel = manager.create_wheel(
            symbol="aapl",
            capital=10000.0,
        )

        assert wheel.symbol == "AAPL"

    def test_create_wheel_duplicate_raises(self, manager: WheelManager) -> None:
        """Creating duplicate wheel should raise DuplicateSymbolError."""
        manager.create_wheel(symbol="AAPL", capital=10000.0)

        with pytest.raises(DuplicateSymbolError):
            manager.create_wheel(symbol="AAPL", capital=5000.0)

    def test_create_wheel_invalid_profile_raises(self, manager: WheelManager) -> None:
        """Invalid profile should raise ValueError."""
        with pytest.raises(ValueError):
            manager.create_wheel(symbol="AAPL", capital=10000.0, profile="invalid")

    def test_import_shares(self, manager: WheelManager) -> None:
        """Test importing existing shares."""
        wheel = manager.import_shares(
            symbol="AAPL",
            shares=200,
            cost_basis=150.0,
            capital=5000.0,
        )

        assert wheel.symbol == "AAPL"
        assert wheel.state == WheelState.SHARES
        assert wheel.shares_held == 200
        assert wheel.cost_basis == 150.0

    def test_import_shares_not_multiple_of_100_raises(
        self, manager: WheelManager
    ) -> None:
        """Shares must be multiple of 100."""
        with pytest.raises(ValueError):
            manager.import_shares(symbol="AAPL", shares=150, cost_basis=150.0)

    def test_get_wheel(self, manager: WheelManager) -> None:
        """Test getting a wheel by symbol."""
        manager.create_wheel(symbol="AAPL", capital=10000.0)

        wheel = manager.get_wheel("AAPL")

        assert wheel is not None
        assert wheel.symbol == "AAPL"

    def test_get_wheel_not_found(self, manager: WheelManager) -> None:
        """Getting non-existent wheel returns None."""
        wheel = manager.get_wheel("NOTEXIST")
        assert wheel is None

    def test_list_wheels(self, manager: WheelManager) -> None:
        """Test listing all wheels."""
        manager.create_wheel(symbol="AAPL", capital=10000.0)
        manager.create_wheel(symbol="MSFT", capital=15000.0)

        wheels = manager.list_wheels()

        assert len(wheels) == 2

    def test_close_wheel(self, manager: WheelManager) -> None:
        """Test closing a wheel."""
        manager.create_wheel(symbol="AAPL", capital=10000.0)

        manager.close_wheel("AAPL")

        wheel = manager.get_wheel("AAPL")
        assert wheel is None

    def test_close_wheel_not_found_raises(self, manager: WheelManager) -> None:
        """Closing non-existent wheel should raise."""
        with pytest.raises(SymbolNotFoundError):
            manager.close_wheel("NOTEXIST")

    def test_close_wheel_with_open_position_raises(
        self, manager: WheelManager
    ) -> None:
        """Cannot close wheel with open position."""
        manager.create_wheel(symbol="AAPL", capital=15000.0)
        manager.record_trade(
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-21",
            premium=1.50,
            contracts=1,
        )

        with pytest.raises(InvalidStateError):
            manager.close_wheel("AAPL")


class TestTradeRecording:
    """Tests for trade recording."""

    def test_record_put_trade(self, manager: WheelManager) -> None:
        """Test recording a put trade."""
        manager.create_wheel(symbol="AAPL", capital=15000.0)

        trade = manager.record_trade(
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-21",
            premium=1.50,
            contracts=1,
        )

        assert trade.direction == "put"
        assert trade.strike == 145.0
        assert trade.total_premium == 150.0
        assert trade.outcome == TradeOutcome.OPEN

        # State should have transitioned
        wheel = manager.get_wheel("AAPL")
        assert wheel.state == WheelState.CASH_PUT_OPEN

    def test_record_call_trade(self, manager: WheelManager) -> None:
        """Test recording a call trade."""
        manager.import_shares(symbol="AAPL", shares=100, cost_basis=150.0)

        trade = manager.record_trade(
            symbol="AAPL",
            direction="call",
            strike=160.0,
            expiration_date="2025-02-21",
            premium=1.25,
            contracts=1,
        )

        assert trade.direction == "call"
        assert trade.strike == 160.0

        wheel = manager.get_wheel("AAPL")
        assert wheel.state == WheelState.SHARES_CALL_OPEN

    def test_record_put_in_shares_state_raises(self, manager: WheelManager) -> None:
        """Cannot sell put when holding shares."""
        manager.import_shares(symbol="AAPL", shares=100, cost_basis=150.0)

        with pytest.raises(InvalidStateError):
            manager.record_trade(
                symbol="AAPL",
                direction="put",
                strike=145.0,
                expiration_date="2025-02-21",
                premium=1.50,
            )

    def test_record_call_in_cash_state_raises(self, manager: WheelManager) -> None:
        """Cannot sell call without shares."""
        manager.create_wheel(symbol="AAPL", capital=10000.0)

        with pytest.raises(InvalidStateError):
            manager.record_trade(
                symbol="AAPL",
                direction="call",
                strike=160.0,
                expiration_date="2025-02-21",
                premium=1.25,
            )

    def test_record_put_insufficient_capital_raises(
        self, manager: WheelManager
    ) -> None:
        """Cannot sell put without sufficient collateral."""
        manager.create_wheel(symbol="AAPL", capital=10000.0)

        # $150 strike needs $15,000 collateral
        with pytest.raises(InsufficientCapitalError):
            manager.record_trade(
                symbol="AAPL",
                direction="put",
                strike=150.0,
                expiration_date="2025-02-21",
                premium=1.50,
            )

    def test_record_call_insufficient_shares_raises(
        self, manager: WheelManager
    ) -> None:
        """Cannot sell more calls than shares support."""
        manager.import_shares(symbol="AAPL", shares=100, cost_basis=150.0)

        with pytest.raises(InsufficientCapitalError):
            manager.record_trade(
                symbol="AAPL",
                direction="call",
                strike=160.0,
                expiration_date="2025-02-21",
                premium=1.25,
                contracts=2,  # Need 200 shares
            )


class TestExpiration:
    """Tests for expiration recording."""

    def test_put_expired_worthless(self, manager: WheelManager) -> None:
        """Put expiring OTM should keep premium and stay in CASH."""
        manager.create_wheel(symbol="AAPL", capital=15000.0)
        manager.record_trade(
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-21",
            premium=1.50,
        )

        outcome = manager.record_expiration("AAPL", price_at_expiry=150.0)

        assert outcome == TradeOutcome.EXPIRED_WORTHLESS

        wheel = manager.get_wheel("AAPL")
        assert wheel.state == WheelState.CASH
        assert wheel.shares_held == 0

    def test_put_assigned(self, manager: WheelManager) -> None:
        """Put ITM should assign shares."""
        manager.create_wheel(symbol="AAPL", capital=15000.0)
        manager.record_trade(
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-21",
            premium=1.50,
        )

        outcome = manager.record_expiration("AAPL", price_at_expiry=140.0)

        assert outcome == TradeOutcome.ASSIGNED

        wheel = manager.get_wheel("AAPL")
        assert wheel.state == WheelState.SHARES
        assert wheel.shares_held == 100
        assert wheel.cost_basis == 145.0

    def test_call_expired_worthless(self, manager: WheelManager) -> None:
        """Call expiring OTM should keep premium and shares."""
        manager.import_shares(symbol="AAPL", shares=100, cost_basis=150.0)
        manager.record_trade(
            symbol="AAPL",
            direction="call",
            strike=160.0,
            expiration_date="2025-02-21",
            premium=1.25,
        )

        outcome = manager.record_expiration("AAPL", price_at_expiry=155.0)

        assert outcome == TradeOutcome.EXPIRED_WORTHLESS

        wheel = manager.get_wheel("AAPL")
        assert wheel.state == WheelState.SHARES
        assert wheel.shares_held == 100

    def test_call_called_away(self, manager: WheelManager) -> None:
        """Call ITM should sell shares."""
        manager.import_shares(symbol="AAPL", shares=100, cost_basis=150.0)
        manager.record_trade(
            symbol="AAPL",
            direction="call",
            strike=160.0,
            expiration_date="2025-02-21",
            premium=1.25,
        )

        outcome = manager.record_expiration("AAPL", price_at_expiry=165.0)

        assert outcome == TradeOutcome.CALLED_AWAY

        wheel = manager.get_wheel("AAPL")
        assert wheel.state == WheelState.CASH
        assert wheel.shares_held == 0
        assert wheel.cost_basis is None

    def test_expiration_no_open_trade_raises(self, manager: WheelManager) -> None:
        """Cannot record expiration without open trade."""
        manager.create_wheel(symbol="AAPL", capital=10000.0)

        with pytest.raises(InvalidStateError):
            manager.record_expiration("AAPL", price_at_expiry=150.0)


class TestEarlyClose:
    """Tests for closing trades early."""

    def test_close_put_early(self, manager: WheelManager) -> None:
        """Test closing a put trade early."""
        manager.create_wheel(symbol="AAPL", capital=15000.0)
        manager.record_trade(
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-21",
            premium=1.50,
        )

        trade = manager.close_trade_early("AAPL", close_price=0.50)

        assert trade.outcome == TradeOutcome.CLOSED_EARLY
        assert trade.close_price == 0.50
        assert trade.net_premium == 100.0  # 150 - 50

        wheel = manager.get_wheel("AAPL")
        assert wheel.state == WheelState.CASH

    def test_close_call_early(self, manager: WheelManager) -> None:
        """Test closing a call trade early."""
        manager.import_shares(symbol="AAPL", shares=100, cost_basis=150.0)
        manager.record_trade(
            symbol="AAPL",
            direction="call",
            strike=160.0,
            expiration_date="2025-02-21",
            premium=1.25,
        )

        trade = manager.close_trade_early("AAPL", close_price=0.25)

        assert trade.outcome == TradeOutcome.CLOSED_EARLY

        wheel = manager.get_wheel("AAPL")
        assert wheel.state == WheelState.SHARES

    def test_close_no_open_trade_raises(self, manager: WheelManager) -> None:
        """Cannot close without open trade."""
        manager.create_wheel(symbol="AAPL", capital=10000.0)

        with pytest.raises(TradeNotFoundError):
            manager.close_trade_early("AAPL", close_price=0.50)


class TestFullWheelCycle:
    """Integration tests for complete wheel cycles."""

    def test_cash_only_cycle(self, manager: WheelManager) -> None:
        """Test a cycle where puts keep expiring worthless."""
        manager.create_wheel(symbol="AAPL", capital=15000.0, profile="conservative")

        # Sell put #1
        manager.record_trade(
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-21",
            premium=1.50,
        )
        manager.record_expiration("AAPL", price_at_expiry=150.0)

        # Sell put #2
        manager.record_trade(
            symbol="AAPL",
            direction="put",
            strike=148.0,
            expiration_date="2025-02-28",
            premium=1.25,
        )
        manager.record_expiration("AAPL", price_at_expiry=152.0)

        # Check performance
        perf = manager.get_performance("AAPL")
        assert perf.total_trades == 2
        assert perf.winning_trades == 2
        assert perf.total_premium == 275.0  # 150 + 125
        assert perf.assignment_events == 0

    def test_full_wheel_cycle(self, manager: WheelManager) -> None:
        """Test complete wheel: put assigned, then call exercised."""
        manager.create_wheel(symbol="AAPL", capital=15000.0)

        # Sell put -> assigned
        manager.record_trade(
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-21",
            premium=1.50,
        )
        manager.record_expiration("AAPL", price_at_expiry=140.0)

        wheel = manager.get_wheel("AAPL")
        assert wheel.state == WheelState.SHARES
        assert wheel.shares_held == 100

        # Sell call -> exercised
        manager.record_trade(
            symbol="AAPL",
            direction="call",
            strike=155.0,
            expiration_date="2025-03-21",
            premium=1.25,
        )
        manager.record_expiration("AAPL", price_at_expiry=160.0)

        wheel = manager.get_wheel("AAPL")
        assert wheel.state == WheelState.CASH
        assert wheel.shares_held == 0

        # Check performance
        perf = manager.get_performance("AAPL")
        assert perf.total_trades == 2
        assert perf.assignment_events == 1
        assert perf.called_away_events == 1
        assert perf.total_premium == 275.0  # 150 + 125

    def test_multi_symbol_wheels(self, manager: WheelManager) -> None:
        """Test running multiple wheels independently."""
        manager.create_wheel(symbol="AAPL", capital=15000.0)
        manager.create_wheel(symbol="MSFT", capital=40000.0)
        manager.import_shares(symbol="GOOG", shares=100, cost_basis=180.0)

        # AAPL: sell put
        manager.record_trade(
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-21",
            premium=1.50,
        )

        # MSFT: sell put
        manager.record_trade(
            symbol="MSFT",
            direction="put",
            strike=390.0,
            expiration_date="2025-02-21",
            premium=3.00,
        )

        # GOOG: sell call
        manager.record_trade(
            symbol="GOOG",
            direction="call",
            strike=195.0,
            expiration_date="2025-02-21",
            premium=2.50,
        )

        # Verify independent states
        aapl = manager.get_wheel("AAPL")
        msft = manager.get_wheel("MSFT")
        goog = manager.get_wheel("GOOG")

        assert aapl.state == WheelState.CASH_PUT_OPEN
        assert msft.state == WheelState.CASH_PUT_OPEN
        assert goog.state == WheelState.SHARES_CALL_OPEN

        # List all
        wheels = manager.list_wheels()
        assert len(wheels) == 3
