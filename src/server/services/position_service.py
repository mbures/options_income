"""Service layer for position monitoring operations.

This module provides business logic for position monitoring by wrapping
the PositionMonitor class and converting between ORM and CLI models.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.price_fetcher import SchwabPriceDataFetcher
from src.schwab.client import SchwabClient
from src.server.database.models.trade import Trade
from src.server.database.models.wheel import Wheel
from src.server.models.position import (
    BatchPositionResponse,
    PositionStatusResponse,
    PositionSummaryResponse,
    RiskAssessmentResponse,
)
from src.server.repositories.trade import TradeRepository
from src.server.repositories.wheel import WheelRepository
from src.wheel.models import PositionStatus, TradeRecord, WheelPosition
from src.wheel.monitor import PositionMonitor
from src.wheel.state import WheelState

logger = logging.getLogger(__name__)


class PositionMonitorService:
    """Service for monitoring open positions.

    Wraps PositionMonitor to provide position status, risk assessment,
    and batch monitoring capabilities with model conversion.

    Attributes:
        db: SQLAlchemy database session
        wheel_repo: Wheel repository
        trade_repo: Trade repository
        monitor: PositionMonitor instance
    """

    def __init__(
        self,
        db: Session,
        schwab_client: Optional[SchwabClient] = None,
        price_fetcher: Optional[SchwabPriceDataFetcher] = None,
    ):
        """Initialize position monitor service.

        Args:
            db: SQLAlchemy database session
            schwab_client: Optional Schwab client for price data
            price_fetcher: Optional price fetcher for fallback
        """
        self.db = db
        self.wheel_repo = WheelRepository(db)
        self.trade_repo = TradeRepository(db)
        self.monitor = PositionMonitor(
            schwab_client=schwab_client, price_fetcher=price_fetcher
        )

    def get_position_status(
        self, wheel_id: int, force_refresh: bool = False
    ) -> PositionStatusResponse:
        """Get current status for a wheel's open position.

        Args:
            wheel_id: Wheel identifier
            force_refresh: Bypass cache and fetch fresh data

        Returns:
            PositionStatusResponse with current metrics

        Raises:
            ValueError: If wheel not found or has no open position
        """
        # Get wheel from database
        wheel = self.wheel_repo.get_wheel(wheel_id)
        if not wheel:
            raise ValueError(f"Wheel {wheel_id} not found")

        # Get open trade
        trade = self.trade_repo.get_open_trade_for_wheel(wheel_id)
        if not trade:
            raise ValueError(
                f"Wheel {wheel_id} ({wheel.symbol}) has no open position to monitor"
            )

        # Convert to CLI models
        cli_position = self._convert_wheel_to_cli(wheel)
        cli_trade = self._convert_trade_to_cli(trade)

        # Get status from monitor
        status = self.monitor.get_position_status(
            cli_position, cli_trade, force_refresh=force_refresh
        )

        # Convert to API response
        return self._convert_status_to_response(wheel.id, trade.id, status)

    def get_portfolio_positions(
        self,
        portfolio_id: str,
        risk_level: Optional[str] = None,
        min_dte: Optional[int] = None,
        max_dte: Optional[int] = None,
        force_refresh: bool = False,
    ) -> BatchPositionResponse:
        """Get status for all open positions in a portfolio.

        Args:
            portfolio_id: Portfolio identifier
            risk_level: Optional filter by risk level (LOW, MEDIUM, HIGH)
            min_dte: Optional minimum days to expiration
            max_dte: Optional maximum days to expiration
            force_refresh: Bypass cache and fetch fresh data

        Returns:
            BatchPositionResponse with all matching positions

        Raises:
            ValueError: If portfolio not found
        """
        # Get all wheels in portfolio with open trades
        wheels = self.wheel_repo.list_wheels_by_portfolio(
            portfolio_id, active_only=True
        )

        if not wheels:
            return BatchPositionResponse(
                positions=[],
                total_count=0,
                high_risk_count=0,
                medium_risk_count=0,
                low_risk_count=0,
            )

        # Get positions with open trades
        positions = []
        for wheel in wheels:
            trade = self.trade_repo.get_open_trade_for_wheel(wheel.id)
            if not trade:
                continue

            try:
                # Convert and get status
                cli_position = self._convert_wheel_to_cli(wheel)
                cli_trade = self._convert_trade_to_cli(trade)
                status = self.monitor.get_position_status(
                    cli_position, cli_trade, force_refresh=force_refresh
                )

                # Apply filters
                if risk_level and status.risk_level != risk_level:
                    continue
                if min_dte is not None and status.dte_calendar < min_dte:
                    continue
                if max_dte is not None and status.dte_calendar > max_dte:
                    continue

                # Convert to summary
                summary = self._convert_status_to_summary(wheel.id, trade.id, status)
                positions.append(summary)

            except Exception as e:
                logger.error(
                    f"Failed to get position status for wheel {wheel.id}: {e}",
                    exc_info=True,
                )

        # Calculate risk counts
        high_risk_count = sum(1 for p in positions if p.risk_level == "HIGH")
        medium_risk_count = sum(1 for p in positions if p.risk_level == "MEDIUM")
        low_risk_count = sum(1 for p in positions if p.risk_level == "LOW")

        return BatchPositionResponse(
            positions=positions,
            total_count=len(positions),
            high_risk_count=high_risk_count,
            medium_risk_count=medium_risk_count,
            low_risk_count=low_risk_count,
        )

    def get_all_open_positions(
        self,
        risk_level: Optional[str] = None,
        min_dte: Optional[int] = None,
        max_dte: Optional[int] = None,
        force_refresh: bool = False,
    ) -> BatchPositionResponse:
        """Get status for all open positions across all portfolios.

        Args:
            risk_level: Optional filter by risk level (LOW, MEDIUM, HIGH)
            min_dte: Optional minimum days to expiration
            max_dte: Optional maximum days to expiration
            force_refresh: Bypass cache and fetch fresh data

        Returns:
            BatchPositionResponse with all matching positions
        """
        # Get all open trades
        open_trades = self.trade_repo.list_open_trades()

        if not open_trades:
            return BatchPositionResponse(
                positions=[],
                total_count=0,
                high_risk_count=0,
                medium_risk_count=0,
                low_risk_count=0,
            )

        # Get positions
        positions = []
        for trade in open_trades:
            wheel = self.wheel_repo.get_wheel(trade.wheel_id)
            if not wheel:
                logger.warning(f"Wheel {trade.wheel_id} not found for trade {trade.id}")
                continue

            try:
                # Convert and get status
                cli_position = self._convert_wheel_to_cli(wheel)
                cli_trade = self._convert_trade_to_cli(trade)
                status = self.monitor.get_position_status(
                    cli_position, cli_trade, force_refresh=force_refresh
                )

                # Apply filters
                if risk_level and status.risk_level != risk_level:
                    continue
                if min_dte is not None and status.dte_calendar < min_dte:
                    continue
                if max_dte is not None and status.dte_calendar > max_dte:
                    continue

                # Convert to summary
                summary = self._convert_status_to_summary(wheel.id, trade.id, status)
                positions.append(summary)

            except Exception as e:
                logger.error(
                    f"Failed to get position status for wheel {wheel.id}: {e}",
                    exc_info=True,
                )

        # Calculate risk counts
        high_risk_count = sum(1 for p in positions if p.risk_level == "HIGH")
        medium_risk_count = sum(1 for p in positions if p.risk_level == "MEDIUM")
        low_risk_count = sum(1 for p in positions if p.risk_level == "LOW")

        return BatchPositionResponse(
            positions=positions,
            total_count=len(positions),
            high_risk_count=high_risk_count,
            medium_risk_count=medium_risk_count,
            low_risk_count=low_risk_count,
        )

    def get_risk_assessment(
        self, wheel_id: int, force_refresh: bool = False
    ) -> RiskAssessmentResponse:
        """Get focused risk assessment for a wheel's open position.

        Args:
            wheel_id: Wheel identifier
            force_refresh: Bypass cache and fetch fresh data

        Returns:
            RiskAssessmentResponse with risk-focused metrics

        Raises:
            ValueError: If wheel not found or has no open position
        """
        # Get position status
        status = self.get_position_status(wheel_id, force_refresh=force_refresh)

        # Extract risk-focused fields
        return RiskAssessmentResponse(
            wheel_id=status.wheel_id,
            symbol=status.symbol,
            risk_level=status.risk_level,
            risk_icon=status.risk_icon,
            risk_description=status.risk_description,
            is_itm=status.is_itm,
            moneyness_pct=status.moneyness_pct,
            dte_calendar=status.dte_calendar,
            current_price=status.current_price,
            strike=status.strike,
            direction=status.direction,
        )

    # Private helper methods

    def _convert_wheel_to_cli(self, wheel: Wheel) -> WheelPosition:
        """Convert ORM Wheel to CLI WheelPosition.

        Args:
            wheel: ORM Wheel model

        Returns:
            CLI WheelPosition model
        """
        return WheelPosition(
            id=wheel.id,
            symbol=wheel.symbol,
            state=WheelState[wheel.state.upper()],
            shares_held=wheel.shares_held,
            capital_allocated=wheel.capital_allocated,
            cost_basis=wheel.cost_basis,
        )

    def _convert_trade_to_cli(self, trade: Trade) -> TradeRecord:
        """Convert ORM Trade to CLI TradeRecord.

        Args:
            trade: ORM Trade model

        Returns:
            CLI TradeRecord model
        """
        return TradeRecord(
            id=trade.id,
            wheel_id=trade.wheel_id,
            symbol=trade.symbol,
            direction=trade.direction,
            strike=trade.strike,
            expiration_date=trade.expiration_date,
            premium_per_share=trade.premium_per_share,
            contracts=trade.contracts,
            total_premium=trade.total_premium,
            outcome=trade.outcome,
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
            price_at_expiry=trade.price_at_expiry,
        )

    def _convert_status_to_response(
        self, wheel_id: int, trade_id: int, status: PositionStatus
    ) -> PositionStatusResponse:
        """Convert CLI PositionStatus to API response.

        Args:
            wheel_id: Wheel identifier
            trade_id: Trade identifier
            status: CLI PositionStatus

        Returns:
            API PositionStatusResponse
        """
        # Calculate risk description
        if status.risk_level == "LOW":
            risk_description = (
                f"Low risk - {status.moneyness_label}, comfortable margin"
            )
        elif status.risk_level == "MEDIUM":
            risk_description = (
                f"Medium risk - {status.moneyness_label}, approaching strike"
            )
        else:  # HIGH
            risk_description = (
                f"High risk - {status.moneyness_label}, assignment likely"
            )

        return PositionStatusResponse(
            wheel_id=wheel_id,
            trade_id=trade_id,
            symbol=status.symbol,
            direction=status.direction,
            strike=status.strike,
            expiration_date=status.expiration_date,
            dte_calendar=status.dte_calendar,
            dte_trading=status.dte_trading,
            current_price=status.current_price,
            price_vs_strike=status.price_vs_strike,
            is_itm=status.is_itm,
            is_otm=status.is_otm,
            moneyness_pct=status.moneyness_pct,
            moneyness_label=status.moneyness_label,
            risk_level=status.risk_level,
            risk_icon=status.risk_icon,
            risk_description=risk_description,
            last_updated=status.last_updated,
            premium_collected=status.premium_collected,
        )

    def _convert_status_to_summary(
        self, wheel_id: int, trade_id: int, status: PositionStatus
    ) -> PositionSummaryResponse:
        """Convert CLI PositionStatus to API summary.

        Args:
            wheel_id: Wheel identifier
            trade_id: Trade identifier
            status: CLI PositionStatus

        Returns:
            API PositionSummaryResponse
        """
        return PositionSummaryResponse(
            wheel_id=wheel_id,
            trade_id=trade_id,
            symbol=status.symbol,
            direction=status.direction,
            strike=status.strike,
            expiration_date=status.expiration_date,
            dte_calendar=status.dte_calendar,
            current_price=status.current_price,
            moneyness_pct=status.moneyness_pct,
            risk_level=status.risk_level,
            risk_icon=status.risk_icon,
            premium_collected=status.premium_collected,
        )
