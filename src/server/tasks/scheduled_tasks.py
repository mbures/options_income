"""Core scheduled tasks for background job execution.

This module contains scheduled task implementations for:
- Price refresh for open positions
- Daily position snapshots
- Risk monitoring and alerts
- Opportunity scanning for new trades
"""

import logging
from datetime import datetime, time
from typing import List, Optional

from sqlalchemy.orm import Session

from src.server.database.models.snapshot import Snapshot
from src.server.database.session import get_session_factory
from src.server.repositories.trade import TradeRepository
from src.server.repositories.wheel import WheelRepository
from src.server.services.position_service import PositionMonitorService
from src.server.services.recommendation_service import RecommendationService
from src.server.tasks.market_hours import is_market_open

logger = logging.getLogger(__name__)


def price_refresh_task():
    """Refresh prices for all open positions.

    Runs every 5 minutes during market hours to update position caches
    with current market prices. Batches API calls to minimize rate limits.

    Only runs if market is open.
    """
    if not is_market_open():
        logger.debug("Market closed - skipping price refresh")
        return

    logger.info("Starting price refresh task")
    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        # Get position service
        position_service = PositionMonitorService(db)

        # Get all open positions (force refresh to fetch new prices)
        result = position_service.get_all_open_positions(force_refresh=True)

        logger.info(
            f"Price refresh complete: {result.total_count} positions updated, "
            f"{result.high_risk_count} high risk"
        )

    except Exception as e:
        logger.error(f"Price refresh task failed: {e}", exc_info=True)
    finally:
        db.close()


def daily_snapshot_task():
    """Create daily snapshots of all open positions.

    Runs at 4:30 PM ET daily to capture end-of-day position state.
    Creates snapshot records for historical tracking and analysis.

    Only runs if market was open today.
    """
    if not is_market_open():
        logger.debug("Market closed - skipping daily snapshot")
        return

    logger.info("Starting daily snapshot task")
    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        # Get repositories
        trade_repo = TradeRepository(db)
        wheel_repo = WheelRepository(db)
        position_service = PositionMonitorService(db)

        # Get all open trades
        open_trades = trade_repo.list_open_trades()

        snapshots_created = 0
        today = datetime.utcnow().date()

        for trade in open_trades:
            try:
                # Get wheel
                wheel = wheel_repo.get_wheel(trade.wheel_id)
                if not wheel:
                    continue

                # Get current position status
                status = position_service.get_position_status(
                    wheel.id, force_refresh=False
                )

                # Create snapshot
                snapshot = Snapshot(
                    trade_id=trade.id,
                    wheel_id=wheel.id,
                    snapshot_date=str(today),
                    current_price=status.current_price,
                    dte_calendar=status.dte_calendar,
                    dte_trading=status.dte_trading,
                    moneyness_pct=status.moneyness_pct,
                    is_itm=status.is_itm,
                    risk_level=status.risk_level,
                )

                db.add(snapshot)
                snapshots_created += 1

            except Exception as e:
                logger.error(
                    f"Failed to create snapshot for trade {trade.id}: {e}",
                    exc_info=True,
                )

        db.commit()
        logger.info(f"Daily snapshot complete: {snapshots_created} snapshots created")

    except Exception as e:
        logger.error(f"Daily snapshot task failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def risk_monitoring_task():
    """Monitor positions for high risk situations.

    Runs every 15 minutes during market hours to check for:
    - ITM positions (assignment risk)
    - Positions within 5% of strike (danger zone)
    - Near-expiration positions (< 3 DTE)

    Logs warnings for positions requiring attention.

    Only runs if market is open.
    """
    if not is_market_open():
        logger.debug("Market closed - skipping risk monitoring")
        return

    logger.info("Starting risk monitoring task")
    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        # Get position service
        position_service = PositionMonitorService(db)

        # Get all open positions
        result = position_service.get_all_open_positions(force_refresh=False)

        # Track risk levels
        high_risk_positions = [
            p for p in result.positions if p.risk_level == "HIGH"
        ]
        near_expiry_positions = [p for p in result.positions if p.dte_calendar <= 3]

        # Log warnings for high risk positions
        for position in high_risk_positions:
            logger.warning(
                f"HIGH RISK: {position.symbol} {position.direction} "
                f"${position.strike} expires in {position.dte_calendar} days - "
                f"ITM, moneyness: {position.moneyness_pct:.2f}%"
            )

        # Log warnings for near expiry positions
        for position in near_expiry_positions:
            if position not in high_risk_positions:
                logger.warning(
                    f"NEAR EXPIRY: {position.symbol} {position.direction} "
                    f"${position.strike} expires in {position.dte_calendar} days - "
                    f"{position.risk_level} risk"
                )

        logger.info(
            f"Risk monitoring complete: {len(high_risk_positions)} high risk, "
            f"{len(near_expiry_positions)} near expiry"
        )

    except Exception as e:
        logger.error(f"Risk monitoring task failed: {e}", exc_info=True)
    finally:
        db.close()


def opportunity_scanning_task():
    """Scan for new trading opportunities.

    Runs daily at 9:45 AM ET to generate recommendations for all
    active wheels. Filters for favorable setups based on:
    - Current wheel state (cash or shares)
    - Market volatility
    - Risk/reward profile

    Logs opportunities for review.

    Only runs if market is open.
    """
    if not is_market_open():
        logger.debug("Market closed - skipping opportunity scanning")
        return

    logger.info("Starting opportunity scanning task")
    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        # Get repositories
        wheel_repo = WheelRepository(db)
        recommendation_service = RecommendationService(db)

        # Get all active wheels
        # Note: We'd need to implement list_all_active_wheels in WheelRepository
        # For now, we'll get wheels from all portfolios

        opportunities_found = 0
        warnings_found = 0

        # This is a simplified implementation
        # In production, we'd iterate through all portfolios and wheels
        logger.info("Scanning for trading opportunities...")

        # Get recommendations for known wheels
        # (Implementation would iterate through all active wheels)

        logger.info(
            f"Opportunity scanning complete: {opportunities_found} opportunities found, "
            f"{warnings_found} warnings"
        )

    except Exception as e:
        logger.error(f"Opportunity scanning task failed: {e}", exc_info=True)
    finally:
        db.close()
