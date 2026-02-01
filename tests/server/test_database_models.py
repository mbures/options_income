"""Tests for SQLAlchemy database models.

Tests model creation, relationships, cascading deletes, and constraints.
"""

import pytest
from datetime import datetime, date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import IntegrityError

from src.server.database.session import Base
from src.server.database.models import (
    Portfolio,
    Wheel,
    Trade,
    Snapshot,
    PerformanceMetrics,
    SchedulerConfig,
)


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine for testing.

    Yields:
        SQLAlchemy engine instance
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def session(engine):
    """Create a database session for testing.

    Args:
        engine: SQLAlchemy engine fixture

    Yields:
        SQLAlchemy session instance
    """
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_portfolio(session: Session) -> Portfolio:
    """Create a sample portfolio for testing.

    Args:
        session: Database session fixture

    Returns:
        Portfolio instance
    """
    portfolio = Portfolio(
        id="test-portfolio-1",
        name="Test Portfolio",
        description="Portfolio for testing",
        default_capital=50000.0,
    )
    session.add(portfolio)
    session.commit()
    return portfolio


@pytest.fixture
def sample_wheel(session: Session, sample_portfolio: Portfolio) -> Wheel:
    """Create a sample wheel for testing.

    Args:
        session: Database session fixture
        sample_portfolio: Portfolio fixture

    Returns:
        Wheel instance
    """
    wheel = Wheel(
        portfolio_id=sample_portfolio.id,
        symbol="AAPL",
        state="cash",
        capital_allocated=10000.0,
        profile="conservative",
    )
    session.add(wheel)
    session.commit()
    return wheel


@pytest.fixture
def sample_trade(session: Session, sample_wheel: Wheel) -> Trade:
    """Create a sample trade for testing.

    Args:
        session: Database session fixture
        sample_wheel: Wheel fixture

    Returns:
        Trade instance
    """
    trade = Trade(
        wheel_id=sample_wheel.id,
        symbol=sample_wheel.symbol,
        direction="put",
        strike=150.0,
        expiration_date="2026-02-14",
        premium_per_share=1.50,
        contracts=1,
        total_premium=150.0,
        outcome="open",
    )
    session.add(trade)
    session.commit()
    return trade


class TestPortfolioModel:
    """Tests for Portfolio model."""

    def test_create_portfolio(self, session: Session):
        """Test creating a portfolio."""
        portfolio = Portfolio(
            id="portfolio-1",
            name="My Portfolio",
            description="Test description",
            default_capital=100000.0,
        )
        session.add(portfolio)
        session.commit()

        assert portfolio.id == "portfolio-1"
        assert portfolio.name == "My Portfolio"
        assert portfolio.default_capital == 100000.0
        assert portfolio.created_at is not None
        assert portfolio.updated_at is not None

    def test_portfolio_repr(self, sample_portfolio: Portfolio):
        """Test portfolio string representation."""
        repr_str = repr(sample_portfolio)
        assert "Portfolio" in repr_str
        assert sample_portfolio.id in repr_str
        assert sample_portfolio.name in repr_str

    def test_portfolio_wheels_relationship(self, session: Session, sample_portfolio: Portfolio):
        """Test portfolio-to-wheels relationship."""
        wheel1 = Wheel(
            portfolio_id=sample_portfolio.id,
            symbol="AAPL",
            state="cash",
            capital_allocated=10000.0,
            profile="conservative",
        )
        wheel2 = Wheel(
            portfolio_id=sample_portfolio.id,
            symbol="MSFT",
            state="cash",
            capital_allocated=15000.0,
            profile="conservative",
        )
        session.add_all([wheel1, wheel2])
        session.commit()

        session.refresh(sample_portfolio)
        assert len(sample_portfolio.wheels) == 2
        assert {w.symbol for w in sample_portfolio.wheels} == {"AAPL", "MSFT"}

    def test_portfolio_cascade_delete(self, session: Session, sample_portfolio: Portfolio):
        """Test that deleting portfolio cascades to wheels."""
        wheel = Wheel(
            portfolio_id=sample_portfolio.id,
            symbol="AAPL",
            state="cash",
            capital_allocated=10000.0,
            profile="conservative",
        )
        session.add(wheel)
        session.commit()
        wheel_id = wheel.id

        # Delete portfolio
        session.delete(sample_portfolio)
        session.commit()

        # Verify wheel was also deleted
        deleted_wheel = session.get(Wheel, wheel_id)
        assert deleted_wheel is None


class TestWheelModel:
    """Tests for Wheel model."""

    def test_create_wheel(self, session: Session, sample_portfolio: Portfolio):
        """Test creating a wheel."""
        wheel = Wheel(
            portfolio_id=sample_portfolio.id,
            symbol="TSLA",
            state="cash",
            shares_held=0,
            capital_allocated=25000.0,
            profile="aggressive",
        )
        session.add(wheel)
        session.commit()

        assert wheel.id is not None
        assert wheel.portfolio_id == sample_portfolio.id
        assert wheel.symbol == "TSLA"
        assert wheel.state == "cash"
        assert wheel.capital_allocated == 25000.0
        assert wheel.is_active is True

    def test_wheel_repr(self, sample_wheel: Wheel):
        """Test wheel string representation."""
        repr_str = repr(sample_wheel)
        assert "Wheel" in repr_str
        assert str(sample_wheel.id) in repr_str
        assert sample_wheel.symbol in repr_str

    def test_wheel_unique_portfolio_symbol(self, session: Session, sample_portfolio: Portfolio):
        """Test that portfolio + symbol combination is unique."""
        wheel1 = Wheel(
            portfolio_id=sample_portfolio.id,
            symbol="AAPL",
            state="cash",
            capital_allocated=10000.0,
            profile="conservative",
        )
        session.add(wheel1)
        session.commit()

        # Try to create another wheel with same portfolio + symbol
        wheel2 = Wheel(
            portfolio_id=sample_portfolio.id,
            symbol="AAPL",
            state="cash",
            capital_allocated=5000.0,
            profile="conservative",
        )
        session.add(wheel2)

        with pytest.raises(IntegrityError):
            session.commit()

    def test_wheel_trades_relationship(self, session: Session, sample_wheel: Wheel):
        """Test wheel-to-trades relationship."""
        trade1 = Trade(
            wheel_id=sample_wheel.id,
            symbol=sample_wheel.symbol,
            direction="put",
            strike=150.0,
            expiration_date="2026-02-14",
            premium_per_share=1.50,
            contracts=1,
            total_premium=150.0,
            outcome="open",
        )
        trade2 = Trade(
            wheel_id=sample_wheel.id,
            symbol=sample_wheel.symbol,
            direction="call",
            strike=160.0,
            expiration_date="2026-02-21",
            premium_per_share=2.00,
            contracts=1,
            total_premium=200.0,
            outcome="open",
        )
        session.add_all([trade1, trade2])
        session.commit()

        session.refresh(sample_wheel)
        assert len(sample_wheel.trades) == 2

    def test_wheel_cascade_delete_to_trades(self, session: Session, sample_wheel: Wheel):
        """Test that deleting wheel cascades to trades."""
        trade = Trade(
            wheel_id=sample_wheel.id,
            symbol=sample_wheel.symbol,
            direction="put",
            strike=150.0,
            expiration_date="2026-02-14",
            premium_per_share=1.50,
            contracts=1,
            total_premium=150.0,
            outcome="open",
        )
        session.add(trade)
        session.commit()
        trade_id = trade.id

        # Delete wheel
        session.delete(sample_wheel)
        session.commit()

        # Verify trade was also deleted
        deleted_trade = session.get(Trade, trade_id)
        assert deleted_trade is None


class TestTradeModel:
    """Tests for Trade model."""

    def test_create_trade(self, session: Session, sample_wheel: Wheel):
        """Test creating a trade."""
        trade = Trade(
            wheel_id=sample_wheel.id,
            symbol=sample_wheel.symbol,
            direction="put",
            strike=145.0,
            expiration_date="2026-02-14",
            premium_per_share=1.75,
            contracts=2,
            total_premium=350.0,
            outcome="open",
        )
        session.add(trade)
        session.commit()

        assert trade.id is not None
        assert trade.wheel_id == sample_wheel.id
        assert trade.symbol == sample_wheel.symbol
        assert trade.strike == 145.0
        assert trade.outcome == "open"

    def test_trade_repr(self, sample_trade: Trade):
        """Test trade string representation."""
        repr_str = repr(sample_trade)
        assert "Trade" in repr_str
        assert str(sample_trade.id) in repr_str
        assert sample_trade.symbol in repr_str

    def test_trade_snapshots_relationship(self, session: Session, sample_trade: Trade, sample_wheel: Wheel):
        """Test trade-to-snapshots relationship."""
        snapshot1 = Snapshot(
            trade_id=sample_trade.id,
            wheel_id=sample_wheel.id,
            snapshot_date="2026-02-01",
            current_price=155.0,
            dte_calendar=13,
            dte_trading=9,
            moneyness_pct=3.3,
            is_itm=False,
            risk_level="LOW",
        )
        snapshot2 = Snapshot(
            trade_id=sample_trade.id,
            wheel_id=sample_wheel.id,
            snapshot_date="2026-02-02",
            current_price=152.0,
            dte_calendar=12,
            dte_trading=8,
            moneyness_pct=1.3,
            is_itm=False,
            risk_level="MEDIUM",
        )
        session.add_all([snapshot1, snapshot2])
        session.commit()

        session.refresh(sample_trade)
        assert len(sample_trade.snapshots) == 2


class TestSnapshotModel:
    """Tests for Snapshot model."""

    def test_create_snapshot(self, session: Session, sample_trade: Trade, sample_wheel: Wheel):
        """Test creating a snapshot."""
        snapshot = Snapshot(
            trade_id=sample_trade.id,
            wheel_id=sample_wheel.id,
            snapshot_date="2026-02-01",
            current_price=155.0,
            dte_calendar=13,
            dte_trading=9,
            moneyness_pct=3.3,
            is_itm=False,
            risk_level="LOW",
        )
        session.add(snapshot)
        session.commit()

        assert snapshot.id is not None
        assert snapshot.trade_id == sample_trade.id
        assert snapshot.wheel_id == sample_wheel.id
        assert snapshot.snapshot_date == "2026-02-01"
        assert snapshot.current_price == 155.0

    def test_snapshot_repr(self, session: Session, sample_trade: Trade, sample_wheel: Wheel):
        """Test snapshot string representation."""
        snapshot = Snapshot(
            trade_id=sample_trade.id,
            wheel_id=sample_wheel.id,
            snapshot_date="2026-02-01",
            current_price=155.0,
            dte_calendar=13,
            dte_trading=9,
            moneyness_pct=3.3,
            is_itm=False,
            risk_level="LOW",
        )
        repr_str = repr(snapshot)
        assert "Snapshot" in repr_str
        assert "2026-02-01" in repr_str

    def test_snapshot_unique_trade_date(self, session: Session, sample_trade: Trade, sample_wheel: Wheel):
        """Test that trade + date combination is unique."""
        snapshot1 = Snapshot(
            trade_id=sample_trade.id,
            wheel_id=sample_wheel.id,
            snapshot_date="2026-02-01",
            current_price=155.0,
            dte_calendar=13,
            dte_trading=9,
            moneyness_pct=3.3,
            is_itm=False,
            risk_level="LOW",
        )
        session.add(snapshot1)
        session.commit()

        # Try to create another snapshot with same trade + date
        snapshot2 = Snapshot(
            trade_id=sample_trade.id,
            wheel_id=sample_wheel.id,
            snapshot_date="2026-02-01",
            current_price=160.0,
            dte_calendar=13,
            dte_trading=9,
            moneyness_pct=6.7,
            is_itm=False,
            risk_level="LOW",
        )
        session.add(snapshot2)

        with pytest.raises(IntegrityError):
            session.commit()


class TestPerformanceMetricsModel:
    """Tests for PerformanceMetrics model."""

    def test_create_wheel_metrics(self, session: Session, sample_portfolio: Portfolio, sample_wheel: Wheel):
        """Test creating wheel-level performance metrics."""
        metrics = PerformanceMetrics(
            portfolio_id=sample_portfolio.id,
            wheel_id=sample_wheel.id,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            total_premium=500.0,
            total_trades=5,
            winning_trades=4,
            losing_trades=1,
            win_rate=80.0,
            annualized_return=15.5,
        )
        session.add(metrics)
        session.commit()

        assert metrics.id is not None
        assert metrics.wheel_id == sample_wheel.id
        assert metrics.total_premium == 500.0
        assert metrics.win_rate == 80.0

    def test_create_portfolio_metrics(self, session: Session, sample_portfolio: Portfolio):
        """Test creating portfolio-level performance metrics."""
        metrics = PerformanceMetrics(
            portfolio_id=sample_portfolio.id,
            wheel_id=None,  # Portfolio aggregate
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            total_premium=1500.0,
            total_trades=15,
            winning_trades=12,
            losing_trades=3,
            win_rate=80.0,
        )
        session.add(metrics)
        session.commit()

        assert metrics.id is not None
        assert metrics.portfolio_id == sample_portfolio.id
        assert metrics.wheel_id is None

    def test_performance_metrics_repr(self, session: Session, sample_portfolio: Portfolio):
        """Test performance metrics string representation."""
        metrics = PerformanceMetrics(
            portfolio_id=sample_portfolio.id,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            total_premium=1500.0,
            total_trades=15,
            winning_trades=12,
            losing_trades=3,
            win_rate=80.0,
        )
        repr_str = repr(metrics)
        assert "PerformanceMetrics" in repr_str
        assert "2026-01-01" in repr_str


class TestSchedulerConfigModel:
    """Tests for SchedulerConfig model."""

    def test_create_system_wide_config(self, session: Session):
        """Test creating system-wide scheduler config."""
        config = SchedulerConfig(
            portfolio_id=None,  # System-wide
            task_name="price_refresh",
            enabled=True,
            schedule_type="interval",
            schedule_params='{"minutes": 5}',
        )
        session.add(config)
        session.commit()

        assert config.id is not None
        assert config.portfolio_id is None
        assert config.task_name == "price_refresh"
        assert config.enabled is True

    def test_create_portfolio_specific_config(self, session: Session, sample_portfolio: Portfolio):
        """Test creating portfolio-specific scheduler config."""
        config = SchedulerConfig(
            portfolio_id=sample_portfolio.id,
            task_name="opportunity_scanning",
            enabled=True,
            schedule_type="cron",
            schedule_params='{"hour": 9, "minute": 45}',
        )
        session.add(config)
        session.commit()

        assert config.id is not None
        assert config.portfolio_id == sample_portfolio.id

    def test_scheduler_config_unique_portfolio_task(self, session: Session, sample_portfolio: Portfolio):
        """Test that portfolio + task_name combination is unique."""
        config1 = SchedulerConfig(
            portfolio_id=sample_portfolio.id,
            task_name="daily_snapshot",
            enabled=True,
            schedule_type="cron",
            schedule_params='{"hour": 16, "minute": 30}',
        )
        session.add(config1)
        session.commit()

        # Try to create another config with same portfolio + task_name
        config2 = SchedulerConfig(
            portfolio_id=sample_portfolio.id,
            task_name="daily_snapshot",
            enabled=False,
            schedule_type="cron",
            schedule_params='{"hour": 17, "minute": 0}',
        )
        session.add(config2)

        with pytest.raises(IntegrityError):
            session.commit()

    def test_scheduler_config_repr(self, session: Session):
        """Test scheduler config string representation."""
        config = SchedulerConfig(
            task_name="price_refresh",
            enabled=True,
            schedule_type="interval",
            schedule_params='{"minutes": 5}',
        )
        repr_str = repr(config)
        assert "SchedulerConfig" in repr_str
        assert "price_refresh" in repr_str
