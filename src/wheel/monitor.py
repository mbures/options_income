"""
Position monitoring service for wheel strategy.

Provides real-time status tracking for open positions including
moneyness, risk assessment, and time decay metrics.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Optional, Tuple

from src.price_fetcher import SchwabPriceDataFetcher
from src.schwab.client import SchwabClient
from src.utils.date_utils import calculate_days_to_expiry, calculate_trading_days

from .models import PositionSnapshot, PositionStatus, TradeRecord, WheelPosition
from .state import TradeOutcome

logger = logging.getLogger(__name__)


@dataclass
class MoneynessResult:
    """Helper dataclass for moneyness calculations."""

    is_itm: bool
    is_otm: bool
    pct: float
    label: str
    price_diff: float


class PositionMonitor:
    """
    Monitors open wheel positions and calculates real-time status.

    Integrates with existing price fetching infrastructure and caching.
    """

    def __init__(
        self,
        schwab_client: Optional[SchwabClient] = None,
        price_fetcher: Optional[SchwabPriceDataFetcher] = None,
    ):
        """
        Initialize with existing data providers.

        Reuses existing caching (5-minute TTL on quotes) to avoid
        excessive API calls.

        Args:
            schwab_client: SchwabClient for primary price data
            price_fetcher: SchwabPriceDataFetcher for fallback price data
        """
        self.schwab_client = schwab_client
        self.price_fetcher = price_fetcher
        self._cache: Dict[str, Tuple[float, datetime]] = {}  # symbol -> (price, timestamp)

    def get_position_status(
        self,
        position: WheelPosition,
        trade: TradeRecord,
        force_refresh: bool = False,
    ) -> PositionStatus:
        """
        Get current status for an open position.

        Args:
            position: The wheel position
            trade: The open trade record
            force_refresh: Bypass cache and fetch fresh data

        Returns:
            PositionStatus with all current metrics

        Raises:
            ValueError: If position is not in an OPEN state
        """
        if not position.has_monitorable_position:
            raise ValueError(
                f"Position {position.symbol} is not in an open state "
                f"(current state: {position.state.value})"
            )

        # Fetch current price (respects 5-min cache unless force_refresh)
        current_price = self._fetch_current_price(
            position.symbol, force_refresh=force_refresh
        )

        # Calculate time metrics
        dte_calendar = calculate_days_to_expiry(trade.expiration_date)
        exp_date = date.fromisoformat(trade.expiration_date)
        dte_trading = calculate_trading_days(date.today(), exp_date)

        # Calculate moneyness
        moneyness = self._calculate_moneyness(
            current_price=current_price,
            strike=trade.strike,
            direction=trade.direction,
        )

        # Determine risk level
        risk_level, risk_icon = self._assess_risk(
            moneyness_pct=moneyness.pct,
            is_itm=moneyness.is_itm,
        )

        return PositionStatus(
            symbol=position.symbol,
            direction=trade.direction,
            strike=trade.strike,
            expiration_date=trade.expiration_date,
            dte_calendar=dte_calendar,
            dte_trading=dte_trading,
            current_price=current_price,
            price_vs_strike=moneyness.price_diff,
            is_itm=moneyness.is_itm,
            is_otm=moneyness.is_otm,
            moneyness_pct=moneyness.pct,
            moneyness_label=moneyness.label,
            risk_level=risk_level,
            risk_icon=risk_icon,
            last_updated=datetime.now(),
            premium_collected=trade.total_premium,
        )

    def get_all_positions_status(
        self,
        positions: list[WheelPosition],
        trades: list[TradeRecord],
        force_refresh: bool = False,
    ) -> list[Tuple[WheelPosition, TradeRecord, PositionStatus]]:
        """
        Get status for all open positions.

        Efficiently batches API calls and respects caching.

        Args:
            positions: List of wheel positions
            trades: List of trade records
            force_refresh: Bypass cache and fetch fresh data

        Returns:
            List of tuples: (WheelPosition, TradeRecord, PositionStatus)
        """
        results = []

        for position in positions:
            if not position.has_monitorable_position:
                continue

            # Find the open trade for this position
            trade = self._find_open_trade(position, trades)
            if not trade:
                logger.warning(
                    f"Position {position.symbol} is in OPEN state but no open trade found"
                )
                continue

            try:
                status = self.get_position_status(position, trade, force_refresh)
                results.append((position, trade, status))
            except Exception as e:
                # Log error but continue with other positions
                logger.error(
                    f"Failed to get status for {position.symbol}: {e}", exc_info=True
                )

        return results

    def create_snapshot(
        self,
        trade: TradeRecord,
        status: PositionStatus,
        snapshot_date: Optional[date] = None,
    ) -> PositionSnapshot:
        """
        Create a historical snapshot from current status.

        Used for daily tracking of position evolution.

        Args:
            trade: The trade record
            status: Current position status
            snapshot_date: Date for snapshot (defaults to today)

        Returns:
            PositionSnapshot ready for persistence
        """
        return PositionSnapshot(
            trade_id=trade.id,
            snapshot_date=str(snapshot_date or date.today()),
            current_price=status.current_price,
            dte_calendar=status.dte_calendar,
            dte_trading=status.dte_trading,
            moneyness_pct=status.moneyness_pct,
            is_itm=status.is_itm,
            risk_level=status.risk_level,
        )

    # Private helper methods

    def _fetch_current_price(self, symbol: str, force_refresh: bool) -> float:
        """
        Fetch current price using existing infrastructure.

        Respects 5-minute cache unless force_refresh=True.

        Args:
            symbol: Stock ticker
            force_refresh: Bypass cache

        Returns:
            Current price

        Raises:
            ValueError: If no price data provider configured or price unavailable
        """
        # Check internal cache first (unless force refresh)
        if not force_refresh and symbol in self._cache:
            price, timestamp = self._cache[symbol]
            age = (datetime.now() - timestamp).total_seconds()
            if age < 300:  # 5 minutes
                logger.debug(f"Using cached price for {symbol}: ${price:.2f}")
                return price

        # Fetch from provider (Schwab preferred, fallback to AlphaVantage)
        price = None

        if self.schwab_client:
            try:
                quote = self.schwab_client.get_quote(symbol)
                # Try multiple price fields in order of preference
                price = (
                    quote.get("lastPrice")
                    or quote.get("closePrice")
                    or quote.get("bidPrice")  # Fallback to bid if no last/close
                )
                if price:
                    logger.debug(f"Fetched price from Schwab for {symbol}: ${price:.2f}")
            except Exception as e:
                logger.warning(f"Failed to fetch price from Schwab for {symbol}: {e}")

        if price is None and self.price_fetcher:
            try:
                price = self.price_fetcher.get_current_price(symbol)
                if price:
                    logger.debug(
                        f"Fetched price from fallback fetcher for {symbol}: ${price:.2f}"
                    )
            except Exception as e:
                logger.warning(f"Failed to fetch price from fallback for {symbol}: {e}")

        if price is None:
            raise ValueError(
                f"Unable to fetch price for {symbol}. "
                "No price data provider configured or price unavailable."
            )

        # Update cache
        self._cache[symbol] = (price, datetime.now())
        return price

    def _calculate_moneyness(
        self,
        current_price: float,
        strike: float,
        direction: str,
    ) -> MoneynessResult:
        """
        Calculate moneyness metrics for a position.

        Args:
            current_price: Current stock price
            strike: Option strike price
            direction: "put" or "call"

        Returns:
            MoneynessResult with is_itm, is_otm, pct, label, price_diff
        """
        if direction == "put":
            # Put: ITM when price <= strike (intrinsic value = strike - price)
            is_itm = current_price <= strike
            price_diff = strike - current_price  # Positive when ITM
            # Moneyness: positive % when OTM (price > strike)
            moneyness_pct = (current_price - strike) / strike * 100
        else:  # call
            # Call: ITM when price >= strike (intrinsic value = price - strike)
            is_itm = current_price >= strike
            price_diff = current_price - strike  # Positive when ITM
            # Moneyness: positive % when ITM (price > strike)
            moneyness_pct = (current_price - strike) / strike * 100

        is_otm = not is_itm

        # Create human-readable label
        if is_itm:
            label = f"ITM by {abs(moneyness_pct):.1f}%"
        else:
            label = f"OTM by {abs(moneyness_pct):.1f}%"

        return MoneynessResult(
            is_itm=is_itm,
            is_otm=is_otm,
            pct=moneyness_pct,
            label=label,
            price_diff=price_diff,
        )

    def _assess_risk(self, moneyness_pct: float, is_itm: bool) -> Tuple[str, str]:
        """
        Assess risk level based on moneyness.

        Risk Levels:
        - LOW (🟢): OTM by >5% - comfortable safety margin
        - MEDIUM (🟡): OTM by 0-5% - within danger zone
        - HIGH (🔴): ITM (any amount) - assignment likely

        Args:
            moneyness_pct: Percentage distance from strike
            is_itm: Whether position is in the money

        Returns:
            Tuple of (risk_level, risk_icon)
        """
        if is_itm:
            return ("HIGH", "🔴")
        elif abs(moneyness_pct) > 5.0:
            return ("LOW", "🟢")
        else:  # OTM but within 5%
            return ("MEDIUM", "🟡")

    def _find_open_trade(
        self,
        position: WheelPosition,
        trades: list[TradeRecord],
    ) -> Optional[TradeRecord]:
        """
        Find the open trade for a given position.

        Args:
            position: Wheel position
            trades: List of trade records

        Returns:
            Open trade record or None
        """
        for trade in trades:
            if trade.wheel_id == position.id and trade.outcome == TradeOutcome.OPEN:
                return trade
        return None
