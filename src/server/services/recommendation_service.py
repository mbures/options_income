"""Service layer for generating options recommendations.

This module provides the business logic for generating trade recommendations
using the RecommendEngine with API-friendly interfaces, caching, and error handling.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from src.config import FinnhubConfig
from src.market_data.finnhub_client import FinnhubClient
from src.market_data.price_fetcher import SchwabPriceDataFetcher
from src.models.profiles import StrikeProfile
from src.schwab.client import SchwabClient
from src.server.models.recommendation import RecommendationResponse
from src.server.repositories.wheel import WheelRepository
from src.wheel.models import WheelPosition as CLIWheelPosition
from src.wheel.recommend import RecommendEngine
from src.wheel.state import WheelState

logger = logging.getLogger(__name__)


class RecommendationService:
    """Service layer for generating options recommendations.

    Wraps RecommendEngine with caching, error handling, and API integration.
    Converts between ORM models and CLI models for seamless integration.

    Attributes:
        db: SQLAlchemy database session
        wheel_repo: Repository for wheel data access
        schwab_client: Schwab API client
        price_fetcher: Price data fetcher
        finnhub_client: Finnhub API client for earnings calendar
        recommend_engine: Core recommendation engine
        _cache: In-memory cache for recommendations
        _cache_ttl: Time-to-live for cached recommendations
    """

    def __init__(self, db: Session, schwab_client: Optional[SchwabClient] = None):
        """Initialize recommendation service.

        Args:
            db: SQLAlchemy database session
            schwab_client: Optional Schwab API client
        """
        self.db = db
        self.wheel_repo = WheelRepository(db)

        # Initialize external clients - handle missing credentials gracefully for testing
        if schwab_client:
            self.schwab_client = schwab_client
        else:
            try:
                self.schwab_client = SchwabClient()
            except Exception as e:
                logger.warning(f"Failed to initialize SchwabClient: {e}")
                self.schwab_client = None

        # Initialize other clients
        self.price_fetcher = (
            SchwabPriceDataFetcher(self.schwab_client)
            if self.schwab_client
            else None
        )
        try:
            finnhub_api_key = os.environ.get("FINNHUB_API_KEY", "")
            if finnhub_api_key:
                self.finnhub_client = FinnhubClient(FinnhubConfig(api_key=finnhub_api_key))
            else:
                logger.warning("FINNHUB_API_KEY not set, FinnhubClient disabled")
                self.finnhub_client = None
        except Exception as e:
            logger.warning(f"Failed to initialize FinnhubClient: {e}")
            self.finnhub_client = None

        # Initialize recommendation engine
        self.recommend_engine = RecommendEngine(
            finnhub_client=self.finnhub_client,
            price_fetcher=self.price_fetcher,
            schwab_client=self.schwab_client,
        )

        # Simple in-memory cache: {(wheel_id, expiration_date): (recommendation, timestamp)}
        self._cache: dict[
            tuple[int, Optional[str]], tuple[RecommendationResponse, datetime]
        ] = {}
        self._cache_ttl = timedelta(minutes=5)  # 5 minute cache

    def get_recommendation(
        self,
        wheel_id: int,
        expiration_date: Optional[str] = None,
        use_cache: bool = True,
        max_dte: int = 14,
    ) -> RecommendationResponse:
        """Generate recommendation for a wheel position.

        Uses cached recommendation if available and not expired. Otherwise,
        generates a new recommendation using RecommendEngine and caches it.

        Args:
            wheel_id: Wheel ID
            expiration_date: Optional target expiration date (YYYY-MM-DD)
            use_cache: Whether to use cached recommendations
            max_dte: Maximum days to expiration for search window

        Returns:
            RecommendationResponse with trade recommendation

        Raises:
            ValueError: If wheel not found or invalid state

        Example:
            >>> service = RecommendationService(db)
            >>> rec = service.get_recommendation(1, "2026-03-21")
            >>> print(f"Recommend {rec.direction} @ ${rec.strike}")
        """
        # Check cache
        cache_key = (wheel_id, expiration_date)
        if use_cache and cache_key in self._cache:
            cached_rec, cached_time = self._cache[cache_key]
            if datetime.utcnow() - cached_time < self._cache_ttl:
                logger.info(f"Using cached recommendation for wheel {wheel_id}")
                return cached_rec

        # Get wheel from database
        wheel = self.wheel_repo.get_wheel(wheel_id)
        if not wheel:
            raise ValueError(f"Wheel {wheel_id} not found")

        # Validate wheel state - must be in base state (CASH or SHARES)
        if wheel.state not in ("cash", "shares"):
            raise ValueError(
                f"Cannot generate recommendation for wheel in state {wheel.state}. "
                f"Must be in cash or shares state (no open positions)."
            )

        # Convert to CLI WheelPosition format for RecommendEngine
        cli_position = self._convert_to_cli_position(wheel)

        # Generate recommendation using RecommendEngine
        try:
            wheel_rec = self.recommend_engine.get_recommendation(
                position=cli_position, expiration_date=expiration_date,
                max_dte=max_dte,
            )
        except Exception as e:
            logger.error(f"Failed to generate recommendation for wheel {wheel_id}: {e}")
            raise ValueError(f"Recommendation generation failed: {str(e)}") from e

        # Convert WheelRecommendation to RecommendationResponse
        response = self._convert_to_api_response(wheel_rec, wheel_id, wheel)

        # Cache the result
        if use_cache:
            self._cache[cache_key] = (response, datetime.utcnow())
            logger.debug(f"Cached recommendation for wheel {wheel_id}")

        return response

    def get_batch_recommendations(
        self,
        symbols: list[str],
        expiration_date: Optional[str] = None,
        profile_override: Optional[str] = None,
        max_dte: int = 14,
    ) -> tuple[list[RecommendationResponse], dict[str, str]]:
        """Generate recommendations for multiple symbols.

        Attempts to generate a recommendation for each symbol by finding
        the corresponding wheel in active portfolios.

        Args:
            symbols: List of stock symbols
            expiration_date: Optional target expiration date for all
            profile_override: Optional profile to override for all wheels

        Returns:
            Tuple of (recommendations, errors)
            - recommendations: List of successful recommendations
            - errors: Dict of symbol -> error message for failures

        Example:
            >>> service = RecommendationService(db)
            >>> recs, errors = service.get_batch_recommendations(
            >>>     ["AAPL", "MSFT"],
            >>>     expiration_date="2026-03-21"
            >>> )
        """
        recommendations = []
        errors = {}

        for symbol in symbols:
            try:
                # Find wheel for this symbol
                # Note: This implementation assumes one wheel per symbol across all portfolios
                # A more sophisticated approach would allow specifying portfolio_id
                from src.server.database.models.wheel import Wheel

                wheel = (
                    self.db.query(Wheel)
                    .filter(Wheel.symbol == symbol, Wheel.is_active)
                    .first()
                )

                if not wheel:
                    errors[symbol] = "No active wheel found for symbol"
                    logger.warning(f"No active wheel found for {symbol}")
                    continue

                # Get recommendation
                rec = self.get_recommendation(
                    wheel.id, expiration_date=expiration_date, use_cache=True,
                    max_dte=max_dte,
                )
                recommendations.append(rec)

            except Exception as e:
                logger.error(f"Failed to get recommendation for {symbol}: {e}")
                errors[symbol] = str(e)

        return recommendations, errors

    def clear_cache(self):
        """Clear recommendation cache.

        Useful when market conditions change significantly or after
        extended downtime.

        Example:
            >>> service = RecommendationService(db)
            >>> service.clear_cache()
        """
        self._cache.clear()
        logger.info("Recommendation cache cleared")

    def _convert_to_cli_position(self, wheel) -> CLIWheelPosition:
        """Convert ORM Wheel to CLI WheelPosition.

        Args:
            wheel: ORM Wheel instance

        Returns:
            CLI WheelPosition instance

        Raises:
            ValueError: If state or profile conversion fails
        """
        # Convert state string to WheelState enum
        state_map = {
            "cash": WheelState.CASH,
            "cash_put_open": WheelState.CASH_PUT_OPEN,
            "shares": WheelState.SHARES,
            "shares_call_open": WheelState.SHARES_CALL_OPEN,
        }
        if wheel.state not in state_map:
            raise ValueError(f"Invalid wheel state: {wheel.state}")
        state_enum = state_map[wheel.state]

        # Convert profile string to StrikeProfile enum
        profile_map = {
            "aggressive": StrikeProfile.AGGRESSIVE,
            "moderate": StrikeProfile.MODERATE,
            "conservative": StrikeProfile.CONSERVATIVE,
            "defensive": StrikeProfile.DEFENSIVE,
        }
        if wheel.profile not in profile_map:
            raise ValueError(f"Invalid wheel profile: {wheel.profile}")
        profile_enum = profile_map[wheel.profile]

        return CLIWheelPosition(
            symbol=wheel.symbol,
            state=state_enum,
            shares_held=wheel.shares_held,
            capital_allocated=wheel.capital_allocated,
            cost_basis=wheel.cost_basis,
            profile=profile_enum,
        )

    def _convert_to_api_response(
        self, wheel_rec, wheel_id: int, wheel
    ) -> RecommendationResponse:
        """Convert CLI WheelRecommendation to API RecommendationResponse.

        Args:
            wheel_rec: CLI WheelRecommendation instance
            wheel_id: Wheel ID
            wheel: ORM Wheel instance

        Returns:
            RecommendationResponse for API
        """
        return RecommendationResponse(
            wheel_id=wheel_id,
            symbol=wheel.symbol,
            current_state=wheel.state,
            direction=wheel_rec.direction.lower(),
            strike=wheel_rec.strike,
            expiration_date=wheel_rec.expiration_date,
            premium_per_share=wheel_rec.premium_per_share,
            total_premium=wheel_rec.premium_per_share * 100,  # 1 contract
            probability_itm=wheel_rec.p_itm,
            probability_otm=1.0 - wheel_rec.p_itm,
            annualized_return=wheel_rec.annualized_yield_pct,
            days_to_expiry=wheel_rec.dte,
            warnings=wheel_rec.warnings,
            has_warnings=len(wheel_rec.warnings) > 0,
            current_price=wheel_rec.current_price,
            volatility=0.30,  # Default - would need to extract from engine
            profile=wheel.profile,
            recommended_at=datetime.utcnow(),
        )
