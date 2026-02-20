"""Unit tests for PerformanceService.

Tests stock cycle detection, option premium P&L computation,
time window filtering, win rate calculations, and aggregate performance.
"""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from src.server.database.models.portfolio import Portfolio
from src.server.database.models.trade import Trade
from src.server.database.models.wheel import Wheel
from src.server.services.performance_service import PerformanceService


@pytest.fixture
def wheel_with_portfolio(test_db: Session) -> Wheel:
    """Create a portfolio and wheel for testing."""
    portfolio = Portfolio(
        id=str(uuid.uuid4()),
        name="Test Portfolio",
        default_capital=50000.0,
    )
    test_db.add(portfolio)
    test_db.commit()
    test_db.refresh(portfolio)

    wheel = Wheel(
        portfolio_id=portfolio.id,
        symbol="AAPL",
        state="cash",
        shares_held=0,
        capital_allocated=20000.0,
        profile="conservative",
    )
    test_db.add(wheel)
    test_db.commit()
    test_db.refresh(wheel)
    return wheel


def _make_trade(
    wheel: Wheel,
    direction: str,
    strike: float,
    outcome: str,
    premium_per_share: float = 2.0,
    contracts: int = 1,
    close_price: float = None,
    opened_at: datetime = None,
    closed_at: datetime = None,
) -> Trade:
    """Helper to build a Trade instance."""
    now = datetime.utcnow()
    total_premium = premium_per_share * contracts * 100
    return Trade(
        wheel_id=wheel.id,
        symbol=wheel.symbol,
        direction=direction,
        strike=strike,
        expiration_date="2026-03-21",
        premium_per_share=premium_per_share,
        contracts=contracts,
        total_premium=total_premium,
        outcome=outcome,
        close_price=close_price,
        opened_at=opened_at or now,
        closed_at=closed_at if closed_at else (now if outcome != "open" else None),
    )


class TestFindStockCycles:
    """Tests for _find_stock_cycles."""

    def test_no_cycles_when_no_trades(self, test_db, wheel_with_portfolio):
        service = PerformanceService(test_db)
        cycles = service._find_stock_cycles([])
        assert cycles == []

    def test_no_cycles_when_no_assignments(self, test_db, wheel_with_portfolio):
        w = wheel_with_portfolio
        trades = [
            _make_trade(w, "put", 150.0, "expired_worthless"),
            _make_trade(w, "put", 148.0, "expired_worthless"),
        ]
        service = PerformanceService(test_db)
        cycles = service._find_stock_cycles(trades)
        assert cycles == []

    def test_single_cycle(self, test_db, wheel_with_portfolio):
        w = wheel_with_portfolio
        t1 = datetime.utcnow() - timedelta(days=60)
        t2 = t1 + timedelta(days=30)
        trades = [
            _make_trade(w, "put", 150.0, "assigned", opened_at=t1, closed_at=t1 + timedelta(days=14)),
            _make_trade(w, "call", 155.0, "called_away", opened_at=t2, closed_at=t2 + timedelta(days=14)),
        ]
        service = PerformanceService(test_db)
        cycles = service._find_stock_cycles(trades)
        assert len(cycles) == 1
        assert cycles[0].put_strike == 150.0
        assert cycles[0].call_strike == 155.0
        # (155 - 150) * 1 * 100 = 500
        assert cycles[0].pnl == 500.0

    def test_multiple_cycles(self, test_db, wheel_with_portfolio):
        w = wheel_with_portfolio
        base = datetime.utcnow() - timedelta(days=120)
        trades = [
            _make_trade(w, "put", 100.0, "assigned", opened_at=base, closed_at=base + timedelta(days=14)),
            _make_trade(w, "call", 110.0, "called_away", opened_at=base + timedelta(days=20), closed_at=base + timedelta(days=34)),
            _make_trade(w, "put", 105.0, "assigned", opened_at=base + timedelta(days=40), closed_at=base + timedelta(days=54)),
            _make_trade(w, "call", 108.0, "called_away", opened_at=base + timedelta(days=60), closed_at=base + timedelta(days=74)),
        ]
        service = PerformanceService(test_db)
        cycles = service._find_stock_cycles(trades)
        assert len(cycles) == 2
        assert cycles[0].pnl == (110 - 100) * 100  # 1000
        assert cycles[1].pnl == (108 - 105) * 100  # 300

    def test_negative_stock_pnl(self, test_db, wheel_with_portfolio):
        w = wheel_with_portfolio
        t1 = datetime.utcnow() - timedelta(days=60)
        t2 = t1 + timedelta(days=30)
        trades = [
            _make_trade(w, "put", 150.0, "assigned", opened_at=t1, closed_at=t1 + timedelta(days=14)),
            _make_trade(w, "call", 140.0, "called_away", opened_at=t2, closed_at=t2 + timedelta(days=14)),
        ]
        service = PerformanceService(test_db)
        cycles = service._find_stock_cycles(trades)
        assert len(cycles) == 1
        # (140 - 150) * 1 * 100 = -1000
        assert cycles[0].pnl == -1000.0

    def test_unmatched_put_not_counted(self, test_db, wheel_with_portfolio):
        """Assigned put with no subsequent called_away call produces no cycle."""
        w = wheel_with_portfolio
        trades = [
            _make_trade(w, "put", 150.0, "assigned"),
        ]
        service = PerformanceService(test_db)
        cycles = service._find_stock_cycles(trades)
        assert cycles == []


class TestComputePeriod:
    """Tests for _compute_period and overall get_wheel_performance."""

    def test_expired_worthless_full_premium(self, test_db, wheel_with_portfolio):
        w = wheel_with_portfolio
        trade = _make_trade(w, "put", 150.0, "expired_worthless", premium_per_share=2.5, contracts=1)
        test_db.add(trade)
        test_db.commit()

        service = PerformanceService(test_db)
        result = service.get_wheel_performance(w.id)
        assert result.all_time.option_premium_pnl == 250.0
        assert result.all_time.trades_closed == 1
        assert result.all_time.win_rate == 1.0

    def test_closed_early_net_premium(self, test_db, wheel_with_portfolio):
        w = wheel_with_portfolio
        # Sold for $2/share, bought back for $0.50/share
        trade = _make_trade(
            w, "put", 150.0, "closed_early",
            premium_per_share=2.0, contracts=1, close_price=0.50,
        )
        test_db.add(trade)
        test_db.commit()

        service = PerformanceService(test_db)
        result = service.get_wheel_performance(w.id)
        # Net = 200 - 50 = 150
        assert result.all_time.option_premium_pnl == 150.0
        assert result.all_time.win_rate == 1.0

    def test_closed_early_at_loss(self, test_db, wheel_with_portfolio):
        w = wheel_with_portfolio
        # Sold for $1/share, bought back for $3/share (loss)
        trade = _make_trade(
            w, "put", 150.0, "closed_early",
            premium_per_share=1.0, contracts=1, close_price=3.0,
        )
        test_db.add(trade)
        test_db.commit()

        service = PerformanceService(test_db)
        result = service.get_wheel_performance(w.id)
        # Net = 100 - 300 = -200
        assert result.all_time.option_premium_pnl == -200.0
        assert result.all_time.win_rate == 0.0

    def test_time_window_filtering(self, test_db, wheel_with_portfolio):
        w = wheel_with_portfolio
        now = datetime.utcnow()

        # Trade closed 3 days ago (within 1-week window)
        recent = _make_trade(
            w, "put", 150.0, "expired_worthless",
            premium_per_share=2.0, contracts=1,
            opened_at=now - timedelta(days=10),
            closed_at=now - timedelta(days=3),
        )

        # Trade closed 45 days ago (within 1-quarter but not 1-month)
        older = _make_trade(
            w, "put", 148.0, "expired_worthless",
            premium_per_share=1.5, contracts=1,
            opened_at=now - timedelta(days=60),
            closed_at=now - timedelta(days=45),
        )

        test_db.add_all([recent, older])
        test_db.commit()

        service = PerformanceService(test_db)
        result = service.get_wheel_performance(w.id)

        # All-time: both trades
        assert result.all_time.trades_closed == 2
        assert result.all_time.option_premium_pnl == 350.0  # 200 + 150

        # 1-week: only recent trade
        assert result.one_week.trades_closed == 1
        assert result.one_week.option_premium_pnl == 200.0

        # 1-month: only recent trade (older is 45 days ago, outside 30-day window)
        assert result.one_month.trades_closed == 1
        assert result.one_month.option_premium_pnl == 200.0

        # 1-quarter: both trades
        assert result.one_quarter.trades_closed == 2
        assert result.one_quarter.option_premium_pnl == 350.0

    def test_stock_pnl_in_window(self, test_db, wheel_with_portfolio):
        w = wheel_with_portfolio
        now = datetime.utcnow()

        # Assigned put + called away call = completed cycle
        put_trade = _make_trade(
            w, "put", 100.0, "assigned",
            premium_per_share=2.0, contracts=1,
            opened_at=now - timedelta(days=20),
            closed_at=now - timedelta(days=15),
        )
        call_trade = _make_trade(
            w, "call", 110.0, "called_away",
            premium_per_share=1.5, contracts=1,
            opened_at=now - timedelta(days=14),
            closed_at=now - timedelta(days=5),
        )

        test_db.add_all([put_trade, call_trade])
        test_db.commit()

        service = PerformanceService(test_db)
        result = service.get_wheel_performance(w.id)

        # Stock P&L = (110 - 100) * 1 * 100 = 1000
        assert result.all_time.stock_pnl == 1000.0
        # Option premium = 200 + 150 = 350
        assert result.all_time.option_premium_pnl == 350.0
        assert result.all_time.total_pnl == 1350.0

        # Cycle completed 5 days ago, within 1-week window
        assert result.one_week.stock_pnl == 1000.0

    def test_wheel_not_found(self, test_db):
        service = PerformanceService(test_db)
        with pytest.raises(ValueError, match="Wheel 9999 not found"):
            service.get_wheel_performance(9999)

    def test_wheel_with_no_trades(self, test_db, wheel_with_portfolio):
        service = PerformanceService(test_db)
        result = service.get_wheel_performance(wheel_with_portfolio.id)
        assert result.all_time.trades_closed == 0
        assert result.all_time.option_premium_pnl == 0.0
        assert result.all_time.stock_pnl == 0.0
        assert result.all_time.win_rate == 0.0

    def test_contracts_traded_sum(self, test_db, wheel_with_portfolio):
        w = wheel_with_portfolio
        t1 = _make_trade(w, "put", 150.0, "expired_worthless", contracts=2)
        t2 = _make_trade(w, "put", 148.0, "expired_worthless", contracts=3)
        test_db.add_all([t1, t2])
        test_db.commit()

        service = PerformanceService(test_db)
        result = service.get_wheel_performance(w.id)
        assert result.all_time.contracts_traded == 5

    def test_win_rate_mixed(self, test_db, wheel_with_portfolio):
        w = wheel_with_portfolio
        # 2 wins, 1 loss
        t1 = _make_trade(w, "put", 150.0, "expired_worthless")
        t2 = _make_trade(w, "put", 148.0, "assigned")  # assigned = win (kept premium)
        t3 = _make_trade(
            w, "put", 145.0, "closed_early",
            premium_per_share=1.0, close_price=3.0,  # loss
        )
        test_db.add_all([t1, t2, t3])
        test_db.commit()

        service = PerformanceService(test_db)
        result = service.get_wheel_performance(w.id)
        # 2 wins out of 3 trades
        assert result.all_time.win_rate == pytest.approx(0.6667, abs=0.001)


class TestGetAggregatePerformance:
    """Tests for get_aggregate_performance across all wheels."""

    def test_no_trades(self, test_db, wheel_with_portfolio):
        service = PerformanceService(test_db)
        result = service.get_aggregate_performance()
        assert result.all_time.trades_closed == 0
        assert result.all_time.option_premium_pnl == 0.0
        assert result.all_time.stock_pnl == 0.0
        assert result.all_time.win_rate == 0.0

    def test_aggregates_across_multiple_wheels(self, test_db, wheel_with_portfolio):
        """Trades from multiple wheels are combined in aggregate metrics."""
        w1 = wheel_with_portfolio

        # Create a second wheel
        portfolio = test_db.query(Portfolio).first()
        w2 = Wheel(
            portfolio_id=portfolio.id,
            symbol="MSFT",
            state="cash",
            shares_held=0,
            capital_allocated=15000.0,
            profile="moderate",
        )
        test_db.add(w2)
        test_db.commit()
        test_db.refresh(w2)

        # Add trades to both wheels
        t1 = _make_trade(w1, "put", 150.0, "expired_worthless", premium_per_share=2.0, contracts=1)
        t2 = _make_trade(w2, "put", 300.0, "expired_worthless", premium_per_share=3.0, contracts=2)
        test_db.add_all([t1, t2])
        test_db.commit()

        service = PerformanceService(test_db)
        result = service.get_aggregate_performance()

        assert result.all_time.trades_closed == 2
        # w1: 2.0 * 1 * 100 = 200, w2: 3.0 * 2 * 100 = 600
        assert result.all_time.option_premium_pnl == 800.0
        assert result.all_time.contracts_traded == 3

    def test_stock_cycles_isolated_per_wheel(self, test_db, wheel_with_portfolio):
        """Stock cycles only match put/call within the same wheel."""
        w1 = wheel_with_portfolio

        portfolio = test_db.query(Portfolio).first()
        w2 = Wheel(
            portfolio_id=portfolio.id,
            symbol="MSFT",
            state="cash",
            shares_held=0,
            capital_allocated=15000.0,
            profile="moderate",
        )
        test_db.add(w2)
        test_db.commit()
        test_db.refresh(w2)

        now = datetime.utcnow()
        # w1: assigned put, no matching call -> no cycle
        t1 = _make_trade(w1, "put", 100.0, "assigned", opened_at=now - timedelta(days=30), closed_at=now - timedelta(days=20))
        # w2: called_away call with no put -> no cycle
        t2 = _make_trade(w2, "call", 110.0, "called_away", opened_at=now - timedelta(days=15), closed_at=now - timedelta(days=5))
        test_db.add_all([t1, t2])
        test_db.commit()

        service = PerformanceService(test_db)
        result = service.get_aggregate_performance()

        # No stock cycles should be detected (put and call are in different wheels)
        assert result.all_time.stock_pnl == 0.0

    def test_response_has_no_wheel_id_or_symbol(self, test_db, wheel_with_portfolio):
        """Aggregate response should not have wheel_id or symbol fields."""
        service = PerformanceService(test_db)
        result = service.get_aggregate_performance()
        assert not hasattr(result, "wheel_id")
        assert not hasattr(result, "symbol")
