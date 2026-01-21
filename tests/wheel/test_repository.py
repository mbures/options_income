"""Tests for wheel repository (SQLite persistence)."""

import os
import tempfile
from datetime import datetime

import pytest

from src.models.profiles import StrikeProfile
from src.wheel.models import TradeRecord, WheelPosition
from src.wheel.repository import WheelRepository
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
def repository(temp_db: str) -> WheelRepository:
    """Create a repository with temporary database."""
    return WheelRepository(db_path=temp_db)


class TestWheelRepository:
    """Tests for WheelRepository wheel operations."""

    def test_create_wheel(self, repository: WheelRepository) -> None:
        """Test creating a new wheel position."""
        position = WheelPosition(
            symbol="AAPL",
            state=WheelState.CASH,
            capital_allocated=10000.0,
            profile=StrikeProfile.CONSERVATIVE,
        )

        created = repository.create_wheel(position)

        assert created.id is not None
        assert created.symbol == "AAPL"
        assert created.state == WheelState.CASH
        assert created.capital_allocated == 10000.0

    def test_create_duplicate_wheel_raises(self, repository: WheelRepository) -> None:
        """Creating duplicate wheel should raise IntegrityError."""
        position = WheelPosition(symbol="AAPL", capital_allocated=10000.0)
        repository.create_wheel(position)

        with pytest.raises(Exception):  # sqlite3.IntegrityError
            duplicate = WheelPosition(symbol="AAPL", capital_allocated=5000.0)
            repository.create_wheel(duplicate)

    def test_get_wheel_by_symbol(self, repository: WheelRepository) -> None:
        """Test retrieving wheel by symbol."""
        position = WheelPosition(symbol="AAPL", capital_allocated=10000.0)
        repository.create_wheel(position)

        retrieved = repository.get_wheel("AAPL")

        assert retrieved is not None
        assert retrieved.symbol == "AAPL"
        assert retrieved.capital_allocated == 10000.0

    def test_get_wheel_case_insensitive(self, repository: WheelRepository) -> None:
        """Symbol lookup should be case-insensitive."""
        position = WheelPosition(symbol="AAPL", capital_allocated=10000.0)
        repository.create_wheel(position)

        assert repository.get_wheel("aapl") is not None
        assert repository.get_wheel("Aapl") is not None

    def test_get_wheel_not_found(self, repository: WheelRepository) -> None:
        """Getting non-existent wheel should return None."""
        result = repository.get_wheel("NOTEXIST")
        assert result is None

    def test_update_wheel(self, repository: WheelRepository) -> None:
        """Test updating wheel position."""
        position = WheelPosition(
            symbol="AAPL",
            state=WheelState.CASH,
            capital_allocated=10000.0,
        )
        created = repository.create_wheel(position)

        # Update state
        created.state = WheelState.SHARES
        created.shares_held = 100
        created.cost_basis = 150.0
        repository.update_wheel(created)

        # Retrieve and verify
        retrieved = repository.get_wheel("AAPL")
        assert retrieved.state == WheelState.SHARES
        assert retrieved.shares_held == 100
        assert retrieved.cost_basis == 150.0

    def test_list_wheels(self, repository: WheelRepository) -> None:
        """Test listing all wheels."""
        repository.create_wheel(WheelPosition(symbol="AAPL", capital_allocated=10000.0))
        repository.create_wheel(WheelPosition(symbol="MSFT", capital_allocated=15000.0))
        repository.create_wheel(WheelPosition(symbol="GOOG", capital_allocated=20000.0))

        wheels = repository.list_wheels()

        assert len(wheels) == 3
        symbols = [w.symbol for w in wheels]
        assert "AAPL" in symbols
        assert "MSFT" in symbols
        assert "GOOG" in symbols

    def test_list_wheels_active_only(self, repository: WheelRepository) -> None:
        """Test listing only active wheels."""
        repository.create_wheel(WheelPosition(symbol="AAPL", capital_allocated=10000.0))
        position = WheelPosition(symbol="MSFT", capital_allocated=15000.0)
        repository.create_wheel(position)

        # Deactivate MSFT
        repository.delete_wheel("MSFT")

        active = repository.list_wheels(active_only=True)
        all_wheels = repository.list_wheels(active_only=False)

        assert len(active) == 1
        assert active[0].symbol == "AAPL"
        assert len(all_wheels) == 2

    def test_delete_wheel(self, repository: WheelRepository) -> None:
        """Test soft-deleting a wheel."""
        repository.create_wheel(WheelPosition(symbol="AAPL", capital_allocated=10000.0))

        deleted = repository.delete_wheel("AAPL")

        assert deleted is True

        # Should not be found in active list
        assert repository.get_wheel("AAPL") is None

    def test_delete_nonexistent_wheel(self, repository: WheelRepository) -> None:
        """Deleting non-existent wheel should return False."""
        deleted = repository.delete_wheel("NOTEXIST")
        assert deleted is False


class TestTradeRepository:
    """Tests for WheelRepository trade operations."""

    def test_create_trade(self, repository: WheelRepository) -> None:
        """Test creating a trade record."""
        wheel = repository.create_wheel(
            WheelPosition(symbol="AAPL", capital_allocated=10000.0)
        )

        trade = TradeRecord(
            wheel_id=wheel.id,
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-21",
            premium_per_share=1.50,
            contracts=1,
            total_premium=150.0,
        )

        created = repository.create_trade(trade)

        assert created.id is not None
        assert created.symbol == "AAPL"
        assert created.strike == 145.0
        assert created.outcome == TradeOutcome.OPEN

    def test_get_open_trade(self, repository: WheelRepository) -> None:
        """Test getting the open trade for a wheel."""
        wheel = repository.create_wheel(
            WheelPosition(symbol="AAPL", capital_allocated=10000.0)
        )

        trade = TradeRecord(
            wheel_id=wheel.id,
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-21",
            premium_per_share=1.50,
            contracts=1,
        )
        repository.create_trade(trade)

        open_trade = repository.get_open_trade(wheel.id)

        assert open_trade is not None
        assert open_trade.strike == 145.0
        assert open_trade.outcome == TradeOutcome.OPEN

    def test_get_open_trade_none_when_closed(self, repository: WheelRepository) -> None:
        """No open trade should be returned when all are closed."""
        wheel = repository.create_wheel(
            WheelPosition(symbol="AAPL", capital_allocated=10000.0)
        )

        trade = TradeRecord(
            wheel_id=wheel.id,
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-21",
            premium_per_share=1.50,
            contracts=1,
            outcome=TradeOutcome.EXPIRED_WORTHLESS,
        )
        repository.create_trade(trade)

        open_trade = repository.get_open_trade(wheel.id)
        assert open_trade is None

    def test_update_trade(self, repository: WheelRepository) -> None:
        """Test updating a trade record."""
        wheel = repository.create_wheel(
            WheelPosition(symbol="AAPL", capital_allocated=10000.0)
        )

        trade = TradeRecord(
            wheel_id=wheel.id,
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-21",
            premium_per_share=1.50,
            contracts=1,
        )
        created = repository.create_trade(trade)

        # Update trade
        created.outcome = TradeOutcome.EXPIRED_WORTHLESS
        created.price_at_expiry = 150.0
        created.closed_at = datetime.now()
        repository.update_trade(created)

        # Retrieve and verify
        trades = repository.get_trades(wheel_id=wheel.id)
        assert len(trades) == 1
        assert trades[0].outcome == TradeOutcome.EXPIRED_WORTHLESS
        assert trades[0].price_at_expiry == 150.0

    def test_get_trades_by_symbol(self, repository: WheelRepository) -> None:
        """Test filtering trades by symbol."""
        wheel_aapl = repository.create_wheel(
            WheelPosition(symbol="AAPL", capital_allocated=10000.0)
        )
        wheel_msft = repository.create_wheel(
            WheelPosition(symbol="MSFT", capital_allocated=10000.0)
        )

        repository.create_trade(
            TradeRecord(
                wheel_id=wheel_aapl.id,
                symbol="AAPL",
                direction="put",
                strike=145.0,
                expiration_date="2025-02-21",
                premium_per_share=1.50,
                contracts=1,
            )
        )
        repository.create_trade(
            TradeRecord(
                wheel_id=wheel_msft.id,
                symbol="MSFT",
                direction="put",
                strike=400.0,
                expiration_date="2025-02-21",
                premium_per_share=3.00,
                contracts=1,
            )
        )

        aapl_trades = repository.get_trades(symbol="AAPL")
        msft_trades = repository.get_trades(symbol="MSFT")

        assert len(aapl_trades) == 1
        assert aapl_trades[0].strike == 145.0
        assert len(msft_trades) == 1
        assert msft_trades[0].strike == 400.0

    def test_get_trades_by_outcome(self, repository: WheelRepository) -> None:
        """Test filtering trades by outcome."""
        wheel = repository.create_wheel(
            WheelPosition(symbol="AAPL", capital_allocated=10000.0)
        )

        # Create multiple trades with different outcomes
        repository.create_trade(
            TradeRecord(
                wheel_id=wheel.id,
                symbol="AAPL",
                direction="put",
                strike=145.0,
                expiration_date="2025-02-21",
                premium_per_share=1.50,
                contracts=1,
                outcome=TradeOutcome.EXPIRED_WORTHLESS,
            )
        )
        repository.create_trade(
            TradeRecord(
                wheel_id=wheel.id,
                symbol="AAPL",
                direction="put",
                strike=140.0,
                expiration_date="2025-02-28",
                premium_per_share=1.25,
                contracts=1,
                outcome=TradeOutcome.ASSIGNED,
            )
        )

        worthless = repository.get_trades(outcome=TradeOutcome.EXPIRED_WORTHLESS)
        assigned = repository.get_trades(outcome=TradeOutcome.ASSIGNED)

        assert len(worthless) == 1
        assert worthless[0].strike == 145.0
        assert len(assigned) == 1
        assert assigned[0].strike == 140.0

    def test_get_total_premium(self, repository: WheelRepository) -> None:
        """Test getting total premium for a wheel."""
        wheel = repository.create_wheel(
            WheelPosition(symbol="AAPL", capital_allocated=10000.0)
        )

        repository.create_trade(
            TradeRecord(
                wheel_id=wheel.id,
                symbol="AAPL",
                direction="put",
                strike=145.0,
                expiration_date="2025-02-21",
                premium_per_share=1.50,
                contracts=1,
                total_premium=150.0,
            )
        )
        repository.create_trade(
            TradeRecord(
                wheel_id=wheel.id,
                symbol="AAPL",
                direction="call",
                strike=155.0,
                expiration_date="2025-03-21",
                premium_per_share=1.25,
                contracts=1,
                total_premium=125.0,
            )
        )

        total = repository.get_total_premium(wheel.id)
        assert total == 275.0  # 150 + 125

    def test_get_trade_count(self, repository: WheelRepository) -> None:
        """Test getting trade count for a wheel."""
        wheel = repository.create_wheel(
            WheelPosition(symbol="AAPL", capital_allocated=10000.0)
        )

        assert repository.get_trade_count(wheel.id) == 0

        repository.create_trade(
            TradeRecord(
                wheel_id=wheel.id,
                symbol="AAPL",
                direction="put",
                strike=145.0,
                expiration_date="2025-02-21",
                premium_per_share=1.50,
                contracts=1,
            )
        )

        assert repository.get_trade_count(wheel.id) == 1
