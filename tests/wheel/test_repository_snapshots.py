"""Tests for repository snapshot operations."""

import pytest
import tempfile
import os
from datetime import date, datetime

from src.wheel.repository import WheelRepository
from src.wheel.models import WheelPosition, TradeRecord, PositionSnapshot
from src.wheel.state import WheelState, TradeOutcome
from src.models.profiles import StrikeProfile


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        yield db_path


@pytest.fixture
def repo(temp_db):
    """Create a repository with temporary database."""
    return WheelRepository(temp_db)


@pytest.fixture
def test_wheel(repo):
    """Create a test wheel position."""
    wheel = WheelPosition(
        symbol="AAPL",
        state=WheelState.CASH_PUT_OPEN,
        capital_allocated=20000.0,
        profile=StrikeProfile.CONSERVATIVE,
    )
    return repo.create_wheel(wheel)


@pytest.fixture
def test_trade(repo, test_wheel):
    """Create a test trade."""
    trade = TradeRecord(
        wheel_id=test_wheel.id,
        symbol="AAPL",
        direction="put",
        strike=150.0,
        expiration_date="2025-02-21",
        premium_per_share=2.50,
        contracts=1,
        outcome=TradeOutcome.OPEN,
    )
    return repo.create_trade(trade)


class TestSnapshotOperations:
    """Test suite for snapshot CRUD operations."""

    def test_create_snapshot(self, repo, test_trade):
        """Test creating a snapshot."""
        snapshot = PositionSnapshot(
            trade_id=test_trade.id,
            snapshot_date="2025-01-28",
            current_price=155.0,
            dte_calendar=24,
            dte_trading=17,
            moneyness_pct=3.33,
            is_itm=False,
            risk_level="MEDIUM",
        )

        result = repo.create_snapshot(snapshot)

        assert result.id is not None
        assert result.trade_id == test_trade.id
        assert result.snapshot_date == "2025-01-28"
        assert result.current_price == 155.0
        assert result.created_at is not None

    def test_create_snapshot_assigns_id(self, repo, test_trade):
        """Test that create_snapshot assigns an id."""
        snapshot = PositionSnapshot(
            trade_id=test_trade.id, snapshot_date="2025-01-28", current_price=155.0
        )

        result = repo.create_snapshot(snapshot)

        assert result.id is not None
        assert isinstance(result.id, int)

    def test_create_duplicate_snapshot_raises_integrity_error(self, repo, test_trade):
        """Test that duplicate (trade_id, date) raises error."""
        snapshot1 = PositionSnapshot(
            trade_id=test_trade.id, snapshot_date="2025-01-28", current_price=155.0
        )
        repo.create_snapshot(snapshot1)

        # Try to create duplicate
        snapshot2 = PositionSnapshot(
            trade_id=test_trade.id, snapshot_date="2025-01-28", current_price=160.0
        )

        with pytest.raises(Exception) as exc_info:
            repo.create_snapshot(snapshot2)

        assert "UNIQUE constraint" in str(exc_info.value)

    def test_get_snapshots_all(self, repo, test_trade):
        """Test getting all snapshots for a trade."""
        # Create multiple snapshots
        for i, date_str in enumerate(["2025-01-28", "2025-01-29", "2025-01-30"]):
            snapshot = PositionSnapshot(
                trade_id=test_trade.id,
                snapshot_date=date_str,
                current_price=150.0 + i,
                dte_calendar=24 - i,
                dte_trading=17 - i,
                moneyness_pct=3.0 - i,
                is_itm=False,
                risk_level="MEDIUM",
            )
            repo.create_snapshot(snapshot)

        # Get all snapshots
        snapshots = repo.get_snapshots(test_trade.id)

        assert len(snapshots) == 3
        assert snapshots[0].snapshot_date == "2025-01-28"
        assert snapshots[1].snapshot_date == "2025-01-29"
        assert snapshots[2].snapshot_date == "2025-01-30"

    def test_get_snapshots_ordered_by_date(self, repo, test_trade):
        """Test that snapshots are returned in date order."""
        # Create snapshots out of order
        dates = ["2025-01-30", "2025-01-28", "2025-01-29"]
        for date_str in dates:
            snapshot = PositionSnapshot(
                trade_id=test_trade.id, snapshot_date=date_str, current_price=150.0
            )
            repo.create_snapshot(snapshot)

        snapshots = repo.get_snapshots(test_trade.id)

        # Should be ordered ascending by date
        assert snapshots[0].snapshot_date == "2025-01-28"
        assert snapshots[1].snapshot_date == "2025-01-29"
        assert snapshots[2].snapshot_date == "2025-01-30"

    def test_get_snapshots_with_date_range(self, repo, test_trade):
        """Test getting snapshots filtered by date range."""
        # Create snapshots
        for i in range(5):
            snapshot = PositionSnapshot(
                trade_id=test_trade.id,
                snapshot_date=f"2025-01-{28+i:02d}",
                current_price=150.0 + i,
            )
            repo.create_snapshot(snapshot)

        # Get snapshots for specific range
        snapshots = repo.get_snapshots(
            test_trade.id, start_date="2025-01-29", end_date="2025-01-31"
        )

        assert len(snapshots) == 3
        assert snapshots[0].snapshot_date == "2025-01-29"
        assert snapshots[2].snapshot_date == "2025-01-31"

    def test_get_snapshots_with_start_date_only(self, repo, test_trade):
        """Test getting snapshots from a start date onwards."""
        # Create snapshots
        for i in range(5):
            snapshot = PositionSnapshot(
                trade_id=test_trade.id,
                snapshot_date=f"2025-01-{28+i:02d}",
                current_price=150.0,
            )
            repo.create_snapshot(snapshot)

        snapshots = repo.get_snapshots(test_trade.id, start_date="2025-01-30")

        assert len(snapshots) == 3
        assert all(s.snapshot_date >= "2025-01-30" for s in snapshots)

    def test_get_snapshots_empty_list_for_unknown_trade(self, repo):
        """Test that unknown trade_id returns empty list."""
        snapshots = repo.get_snapshots(trade_id=999)

        assert snapshots == []

    def test_has_snapshots_for_date_true(self, repo, test_trade):
        """Test has_snapshots_for_date returns True when snapshots exist."""
        snapshot = PositionSnapshot(
            trade_id=test_trade.id, snapshot_date="2025-01-28", current_price=150.0
        )
        repo.create_snapshot(snapshot)

        exists = repo.has_snapshots_for_date(date(2025, 1, 28))

        assert exists is True

    def test_has_snapshots_for_date_false(self, repo):
        """Test has_snapshots_for_date returns False when no snapshots."""
        exists = repo.has_snapshots_for_date(date(2025, 1, 28))

        assert exists is False

    def test_has_snapshots_for_date_multiple_trades(self, repo, test_trade):
        """Test has_snapshots_for_date with multiple trades on same date."""
        # Create another wheel and trade
        wheel2 = WheelPosition(symbol="MSFT", state=WheelState.CASH_PUT_OPEN)
        wheel2 = repo.create_wheel(wheel2)
        trade2 = TradeRecord(
            wheel_id=wheel2.id,
            symbol="MSFT",
            direction="put",
            strike=300.0,
            expiration_date="2025-02-21",
            outcome=TradeOutcome.OPEN,
        )
        trade2 = repo.create_trade(trade2)

        # Create snapshots for both trades on same date
        snapshot1 = PositionSnapshot(
            trade_id=test_trade.id, snapshot_date="2025-01-28", current_price=150.0
        )
        snapshot2 = PositionSnapshot(
            trade_id=trade2.id, snapshot_date="2025-01-28", current_price=300.0
        )
        repo.create_snapshot(snapshot1)
        repo.create_snapshot(snapshot2)

        exists = repo.has_snapshots_for_date(date(2025, 1, 28))

        assert exists is True

    def test_row_to_snapshot_conversion(self, repo, test_trade):
        """Test that database row is correctly converted to PositionSnapshot."""
        snapshot = PositionSnapshot(
            trade_id=test_trade.id,
            snapshot_date="2025-01-28",
            current_price=155.50,
            dte_calendar=24,
            dte_trading=17,
            moneyness_pct=3.67,
            is_itm=False,
            risk_level="MEDIUM",
        )
        created = repo.create_snapshot(snapshot)

        # Retrieve and verify conversion
        retrieved = repo.get_snapshots(test_trade.id)[0]

        assert retrieved.id == created.id
        assert retrieved.trade_id == test_trade.id
        assert retrieved.snapshot_date == "2025-01-28"
        assert retrieved.current_price == 155.50
        assert retrieved.dte_calendar == 24
        assert retrieved.dte_trading == 17
        assert retrieved.moneyness_pct == pytest.approx(3.67)
        assert retrieved.is_itm is False
        assert retrieved.risk_level == "MEDIUM"
        assert isinstance(retrieved.created_at, datetime)

    def test_row_to_snapshot_boolean_conversion(self, repo, test_trade):
        """Test that is_itm boolean is correctly converted."""
        # Test with True
        snapshot_itm = PositionSnapshot(
            trade_id=test_trade.id,
            snapshot_date="2025-01-28",
            current_price=145.0,
            is_itm=True,
            risk_level="HIGH",
        )
        repo.create_snapshot(snapshot_itm)

        # Test with False
        snapshot_otm = PositionSnapshot(
            trade_id=test_trade.id,
            snapshot_date="2025-01-29",
            current_price=155.0,
            is_itm=False,
            risk_level="MEDIUM",
        )
        repo.create_snapshot(snapshot_otm)

        snapshots = repo.get_snapshots(test_trade.id)

        assert snapshots[0].is_itm is True
        assert snapshots[1].is_itm is False
