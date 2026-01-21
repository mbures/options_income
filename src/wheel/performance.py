"""
Performance tracking for wheel strategy positions.

This module calculates and aggregates metrics for wheel strategy
performance, including premium collected, win rates, and P&L.
"""

import csv
import io
import json
import logging
from datetime import datetime
from typing import Optional

from .models import TradeRecord, WheelPerformance, WheelPosition
from .repository import WheelRepository
from .state import TradeOutcome, WheelState

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """
    Calculate and track wheel strategy performance metrics.

    Provides methods to calculate:
    - Total premium collected
    - Win rate (options expiring worthless)
    - Assignment/exercise rates
    - Average holding periods
    - Annualized returns
    """

    def __init__(self, repository: WheelRepository):
        """
        Initialize the performance tracker.

        Args:
            repository: WheelRepository for accessing trade data
        """
        self.repository = repository

    def get_performance(
        self, symbol: str, wheel: Optional[WheelPosition] = None
    ) -> WheelPerformance:
        """
        Calculate performance metrics for a single symbol.

        Args:
            symbol: Stock ticker symbol
            wheel: Optional WheelPosition (fetched if not provided)

        Returns:
            WheelPerformance with calculated metrics
        """
        symbol = symbol.upper()

        # Get wheel position
        if wheel is None:
            wheel = self.repository.get_wheel(symbol)

        if wheel is None:
            # Return empty performance for non-existent wheel
            return WheelPerformance(symbol=symbol)

        # Get all trades for this wheel
        trades = self.repository.get_trades(wheel_id=wheel.id)

        return self._calculate_metrics(symbol, wheel, trades)

    def get_portfolio_performance(self) -> WheelPerformance:
        """
        Calculate aggregate performance across all wheels.

        Returns:
            WheelPerformance with portfolio-wide metrics
        """
        wheels = self.repository.list_wheels(active_only=False)
        all_trades = self.repository.get_all_trades()

        # Aggregate capital
        total_capital = sum(w.capital_allocated for w in wheels if w.is_active)

        # Calculate combined metrics
        perf = self._calculate_metrics("ALL", None, all_trades)
        perf.capital_deployed = total_capital

        return perf

    def _calculate_metrics(
        self,
        symbol: str,
        wheel: Optional[WheelPosition],
        trades: list[TradeRecord],
    ) -> WheelPerformance:
        """
        Calculate performance metrics from trades.

        Args:
            symbol: Symbol or "ALL" for portfolio
            wheel: WheelPosition (None for portfolio)
            trades: List of TradeRecord objects

        Returns:
            WheelPerformance with calculated metrics
        """
        perf = WheelPerformance(symbol=symbol)

        if not trades:
            if wheel:
                perf.current_state = wheel.state
                perf.current_shares = wheel.shares_held
                perf.current_cost_basis = wheel.cost_basis
                perf.capital_deployed = wheel.capital_allocated
            return perf

        # Count trades by type and outcome
        total_premium = 0.0
        puts_sold = 0
        calls_sold = 0
        winning_trades = 0
        assignment_events = 0
        called_away_events = 0
        closed_early_count = 0
        open_trades = 0
        total_days_held = 0
        completed_trades = 0

        for trade in trades:
            total_premium += trade.total_premium

            if trade.direction == "put":
                puts_sold += 1
            else:
                calls_sold += 1

            if trade.outcome == TradeOutcome.OPEN:
                open_trades += 1
            else:
                completed_trades += 1

                # Calculate holding period
                if trade.closed_at and trade.opened_at:
                    days_held = (trade.closed_at - trade.opened_at).days
                    total_days_held += max(1, days_held)

                if trade.outcome == TradeOutcome.EXPIRED_WORTHLESS:
                    winning_trades += 1
                elif trade.outcome == TradeOutcome.ASSIGNED:
                    assignment_events += 1
                elif trade.outcome == TradeOutcome.CALLED_AWAY:
                    called_away_events += 1
                elif trade.outcome == TradeOutcome.CLOSED_EARLY:
                    closed_early_count += 1
                    # Consider early close with profit as a win
                    if trade.net_premium > 0:
                        winning_trades += 1

        # Calculate win rate
        if completed_trades > 0:
            win_rate = (winning_trades / completed_trades) * 100
        else:
            win_rate = 0.0

        # Calculate average days held
        if completed_trades > 0:
            avg_days = total_days_held / completed_trades
        else:
            avg_days = 0.0

        # Calculate realized P&L
        # This is simplified - premium collected minus any losses from assignment
        realized_pnl = total_premium  # Premium is always collected

        # Calculate annualized yield
        # Based on capital deployed and total premium over time
        if wheel and wheel.capital_allocated > 0:
            # Get time span of trades
            if trades:
                oldest = min(t.opened_at for t in trades)
                days_active = (datetime.now() - oldest).days
                if days_active > 0:
                    annualized_yield = (
                        (total_premium / wheel.capital_allocated)
                        * (365 / days_active)
                        * 100
                    )
                else:
                    annualized_yield = 0.0
            else:
                annualized_yield = 0.0
        else:
            annualized_yield = 0.0

        # Populate performance object
        perf.total_premium = total_premium
        perf.total_trades = len(trades)
        perf.winning_trades = winning_trades
        perf.assignment_events = assignment_events
        perf.called_away_events = called_away_events
        perf.closed_early_count = closed_early_count
        perf.win_rate_pct = win_rate
        perf.puts_sold = puts_sold
        perf.calls_sold = calls_sold
        perf.average_days_held = avg_days
        perf.annualized_yield_pct = annualized_yield
        perf.realized_pnl = realized_pnl
        perf.open_trades = open_trades

        if wheel:
            perf.current_state = wheel.state
            perf.current_shares = wheel.shares_held
            perf.current_cost_basis = wheel.cost_basis
            perf.capital_deployed = wheel.capital_allocated

        return perf

    def export_trades(
        self,
        symbol: Optional[str] = None,
        format: str = "csv",
    ) -> str:
        """
        Export trade history to CSV or JSON.

        Args:
            symbol: Optional symbol filter (None = all trades)
            format: "csv" or "json"

        Returns:
            Formatted string with trade data
        """
        if symbol:
            trades = self.repository.get_trades(symbol=symbol.upper())
        else:
            trades = self.repository.get_all_trades()

        if format == "json":
            return self._export_json(trades)
        else:
            return self._export_csv(trades)

    def _export_csv(self, trades: list[TradeRecord]) -> str:
        """Export trades to CSV format."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(
            [
                "id",
                "symbol",
                "direction",
                "strike",
                "expiration_date",
                "premium_per_share",
                "contracts",
                "total_premium",
                "opened_at",
                "closed_at",
                "outcome",
                "price_at_expiry",
                "net_premium",
            ]
        )

        # Write trades
        for trade in trades:
            writer.writerow(
                [
                    trade.id,
                    trade.symbol,
                    trade.direction,
                    trade.strike,
                    trade.expiration_date,
                    trade.premium_per_share,
                    trade.contracts,
                    trade.total_premium,
                    trade.opened_at.isoformat() if trade.opened_at else "",
                    trade.closed_at.isoformat() if trade.closed_at else "",
                    trade.outcome.value,
                    trade.price_at_expiry or "",
                    trade.net_premium,
                ]
            )

        return output.getvalue()

    def _export_json(self, trades: list[TradeRecord]) -> str:
        """Export trades to JSON format."""
        data = []
        for trade in trades:
            data.append(
                {
                    "id": trade.id,
                    "symbol": trade.symbol,
                    "direction": trade.direction,
                    "strike": trade.strike,
                    "expiration_date": trade.expiration_date,
                    "premium_per_share": trade.premium_per_share,
                    "contracts": trade.contracts,
                    "total_premium": trade.total_premium,
                    "opened_at": trade.opened_at.isoformat() if trade.opened_at else None,
                    "closed_at": trade.closed_at.isoformat() if trade.closed_at else None,
                    "outcome": trade.outcome.value,
                    "price_at_expiry": trade.price_at_expiry,
                    "net_premium": trade.net_premium,
                }
            )
        return json.dumps(data, indent=2)

    def get_summary(self, symbol: Optional[str] = None) -> dict:
        """
        Get a summary dictionary for display.

        Args:
            symbol: Optional symbol filter

        Returns:
            Dictionary with formatted summary data
        """
        if symbol:
            perf = self.get_performance(symbol)
        else:
            perf = self.get_portfolio_performance()

        return {
            "symbol": perf.symbol,
            "total_premium": f"${perf.total_premium:,.2f}",
            "total_trades": perf.total_trades,
            "open_trades": perf.open_trades,
            "completed_trades": perf.completed_trades,
            "winning_trades": perf.winning_trades,
            "win_rate": f"{perf.win_rate_pct:.1f}%",
            "assignments": perf.assignment_events,
            "called_away": perf.called_away_events,
            "puts_sold": perf.puts_sold,
            "calls_sold": perf.calls_sold,
            "avg_days_held": f"{perf.average_days_held:.1f}",
            "annualized_yield": f"{perf.annualized_yield_pct:.1f}%",
            "current_state": perf.current_state.value,
            "current_shares": perf.current_shares,
            "cost_basis": (
                f"${perf.current_cost_basis:.2f}"
                if perf.current_cost_basis
                else "N/A"
            ),
        }
