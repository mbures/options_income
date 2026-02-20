"""Service layer for computing wheel performance metrics.

This module provides P&L computation including option premium P&L,
stock P&L from completed wheel cycles, and time-windowed metrics.
"""

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from src.server.database.models.trade import Trade
from src.server.models.performance import PerformanceResponse, PeriodMetrics, WheelPerformanceResponse
from src.server.repositories.trade import TradeRepository
from src.server.repositories.wheel import WheelRepository

logger = logging.getLogger(__name__)


@dataclass
class StockCycle:
    """A completed wheel cycle: put assigned then call called away.

    Attributes:
        put_trade: The put trade that was assigned
        call_trade: The call trade that was called away
        put_strike: Strike price of the assigned put
        call_strike: Strike price of the called-away call
        contracts: Number of contracts in the cycle
        pnl: Stock P&L = (call_strike - put_strike) * contracts * 100
        completed_at: When the cycle completed (call's closed_at)
    """

    put_trade: Trade
    call_trade: Trade
    put_strike: float
    call_strike: float
    contracts: int
    pnl: float
    completed_at: datetime


class PerformanceService:
    """Service for computing wheel performance metrics.

    Computes option premium P&L and stock P&L from trade history,
    with time-windowed breakdowns.

    Attributes:
        db: SQLAlchemy database session
        wheel_repo: Repository for wheel data access
        trade_repo: Repository for trade data access
    """

    def __init__(self, db: Session):
        """Initialize performance service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.wheel_repo = WheelRepository(db)
        self.trade_repo = TradeRepository(db)

    def get_aggregate_performance(self) -> PerformanceResponse:
        """Compute aggregate performance metrics across all wheels.

        Fetches all trades, groups by wheel_id for stock cycle detection,
        then combines metrics across all wheels.

        Returns:
            PerformanceResponse with aggregate period metrics
        """
        all_trades = self.trade_repo.list_trades(limit=10000)

        # Only closed trades contribute to P&L
        closed_trades = [t for t in all_trades if t.outcome != "open"]

        # Detect stock cycles per wheel (cycles must match within a wheel)
        trades_by_wheel: dict[int, list[Trade]] = {}
        for trade in all_trades:
            trades_by_wheel.setdefault(trade.wheel_id, []).append(trade)

        all_cycles: list[StockCycle] = []
        for wheel_trades in trades_by_wheel.values():
            all_cycles.extend(self._find_stock_cycles(wheel_trades))

        now = datetime.utcnow()

        return PerformanceResponse(
            all_time=self._compute_period(closed_trades, all_cycles, cutoff=None),
            one_week=self._compute_period(closed_trades, all_cycles, cutoff=now - timedelta(days=7)),
            one_month=self._compute_period(closed_trades, all_cycles, cutoff=now - timedelta(days=30)),
            one_quarter=self._compute_period(closed_trades, all_cycles, cutoff=now - timedelta(days=90)),
        )

    def get_wheel_performance(self, wheel_id: int) -> WheelPerformanceResponse:
        """Compute performance metrics for a wheel.

        Fetches all closed trades for the wheel, detects stock cycles,
        and computes P&L metrics across time windows.

        Args:
            wheel_id: Wheel identifier

        Returns:
            WheelPerformanceResponse with all-time and windowed metrics

        Raises:
            ValueError: If wheel not found
        """
        wheel = self.wheel_repo.get_wheel(wheel_id)
        if not wheel:
            raise ValueError(f"Wheel {wheel_id} not found")

        # Get all trades for this wheel (no pagination limit)
        trades = self.trade_repo.list_trades_by_wheel(wheel_id, limit=10000)

        # Only closed trades contribute to P&L
        closed_trades = [t for t in trades if t.outcome != "open"]

        # Detect completed stock cycles from chronological trade history
        cycles = self._find_stock_cycles(trades)

        now = datetime.utcnow()

        return WheelPerformanceResponse(
            wheel_id=wheel_id,
            symbol=wheel.symbol,
            all_time=self._compute_period(closed_trades, cycles, cutoff=None),
            one_week=self._compute_period(closed_trades, cycles, cutoff=now - timedelta(days=7)),
            one_month=self._compute_period(closed_trades, cycles, cutoff=now - timedelta(days=30)),
            one_quarter=self._compute_period(closed_trades, cycles, cutoff=now - timedelta(days=90)),
        )

    def _find_stock_cycles(self, trades: list[Trade]) -> list[StockCycle]:
        """Detect completed wheel cycles using FIFO matching.

        Walks trades chronologically. Each "assigned" put is queued.
        Each "called_away" call is matched with the oldest queued put
        to form a completed stock cycle.

        Args:
            trades: All trades for a wheel (any order; will be sorted)

        Returns:
            List of completed StockCycle instances
        """
        # Sort by opened_at ascending for chronological processing
        sorted_trades = sorted(trades, key=lambda t: t.opened_at)

        assigned_puts: deque[Trade] = deque()
        cycles: list[StockCycle] = []

        for trade in sorted_trades:
            if trade.direction == "put" and trade.outcome == "assigned":
                assigned_puts.append(trade)
            elif trade.direction == "call" and trade.outcome == "called_away":
                if assigned_puts:
                    put_trade = assigned_puts.popleft()
                    contracts = min(put_trade.contracts, trade.contracts)
                    pnl = (trade.strike - put_trade.strike) * contracts * 100
                    cycles.append(StockCycle(
                        put_trade=put_trade,
                        call_trade=trade,
                        put_strike=put_trade.strike,
                        call_strike=trade.strike,
                        contracts=contracts,
                        pnl=pnl,
                        completed_at=trade.closed_at,
                    ))

        return cycles

    def _compute_period(
        self,
        closed_trades: list[Trade],
        cycles: list[StockCycle],
        cutoff: Optional[datetime],
    ) -> PeriodMetrics:
        """Compute metrics for trades and cycles closed after cutoff.

        Args:
            closed_trades: All closed trades for the wheel
            cycles: All completed stock cycles
            cutoff: Only include items closed after this datetime.
                    None means all-time (no filtering).

        Returns:
            PeriodMetrics for the time window
        """
        # Filter trades by cutoff
        if cutoff is not None:
            period_trades = [t for t in closed_trades if t.closed_at and t.closed_at >= cutoff]
        else:
            period_trades = closed_trades

        # Compute option premium P&L
        option_pnl = 0.0
        wins = 0
        for trade in period_trades:
            if trade.outcome == "closed_early":
                # Net = premium collected minus buyback cost
                close_cost = (trade.close_price or 0.0) * trade.contracts * 100
                option_pnl += trade.total_premium - close_cost
                # Win if net positive
                if trade.total_premium - close_cost > 0:
                    wins += 1
            else:
                # expired_worthless, assigned, called_away: keep full premium
                option_pnl += trade.total_premium
                wins += 1

        # Filter cycles by cutoff (attributed to when cycle completed)
        if cutoff is not None:
            period_cycles = [c for c in cycles if c.completed_at and c.completed_at >= cutoff]
        else:
            period_cycles = cycles

        stock_pnl = sum(c.pnl for c in period_cycles)

        trades_closed = len(period_trades)
        contracts_traded = sum(t.contracts for t in period_trades)
        win_rate = wins / trades_closed if trades_closed > 0 else 0.0

        return PeriodMetrics(
            option_premium_pnl=round(option_pnl, 2),
            stock_pnl=round(stock_pnl, 2),
            total_pnl=round(option_pnl + stock_pnl, 2),
            trades_closed=trades_closed,
            contracts_traded=contracts_traded,
            win_rate=round(win_rate, 4),
        )
