"""
Recommendation engine for wheel strategy with premium collection bias.

This module generates biased recommendations that favor premium collection
over assignment by preferring further OTM strikes and shorter expirations.
"""

import logging
from datetime import datetime
from typing import Optional

from src.covered_strategies import CoveredCallAnalyzer, CoveredPutAnalyzer
from src.earnings_calendar import EarningsCalendar
from src.finnhub_client import FinnhubClient
from src.models import PROFILE_SIGMA_RANGES, OptionsChain, StrikeProfile
from src.options_service import OptionsChainService
from src.price_fetcher import AlphaVantagePriceDataFetcher
from src.strike_optimizer import StrikeOptimizer
from src.utils import calculate_days_to_expiry
from src.volatility import VolatilityCalculator

from .exceptions import DataFetchError, InvalidStateError
from .models import WheelPosition, WheelRecommendation
from .state import WheelState

logger = logging.getLogger(__name__)


# P(ITM) thresholds for warnings by profile
PITM_WARNING_THRESHOLDS: dict[StrikeProfile, float] = {
    StrikeProfile.AGGRESSIVE: 0.40,  # 40%
    StrikeProfile.MODERATE: 0.30,  # 30%
    StrikeProfile.CONSERVATIVE: 0.15,  # 15%
    StrikeProfile.DEFENSIVE: 0.07,  # 7%
}


class RecommendEngine:
    """
    Generates biased recommendations favoring premium collection.

    The goal is to COLLECT PREMIUM while AVOIDING ASSIGNMENT.

    Bias strategies:
    1. Select strikes toward the outer edge of profile sigma range (further OTM)
    2. Prefer shorter-dated expirations (less time for adverse price moves)
    3. Warn on high P(ITM) or event conflicts
    """

    def __init__(
        self,
        finnhub_client: Optional[FinnhubClient] = None,
        price_fetcher: Optional[AlphaVantagePriceDataFetcher] = None,
    ):
        """
        Initialize the recommendation engine.

        Args:
            finnhub_client: Optional FinnhubClient for options data
            price_fetcher: Optional price data fetcher
        """
        self.finnhub = finnhub_client
        self.price_fetcher = price_fetcher

        # Initialize core components
        self.strike_optimizer = StrikeOptimizer()
        self.volatility_calculator = VolatilityCalculator()
        self.call_analyzer = CoveredCallAnalyzer(self.strike_optimizer)
        self.put_analyzer = CoveredPutAnalyzer(self.strike_optimizer)

        # Earnings calendar (lazy initialized)
        self._earnings_calendar: Optional[EarningsCalendar] = None

    @property
    def earnings_calendar(self) -> Optional[EarningsCalendar]:
        """Lazy-initialized earnings calendar."""
        if self._earnings_calendar is None and self.finnhub is not None:
            self._earnings_calendar = EarningsCalendar(self.finnhub)
        return self._earnings_calendar

    def get_recommendation(
        self,
        position: WheelPosition,
        options_chain: Optional[OptionsChain] = None,
        current_price: Optional[float] = None,
        volatility: Optional[float] = None,
        expiration_date: Optional[str] = None,
    ) -> WheelRecommendation:
        """
        Generate a biased recommendation for the next trade.

        For CASH state: recommend a PUT to sell (further OTM = less likely to buy shares)
        For SHARES state: recommend a CALL to sell (further OTM = less likely to sell shares)

        Args:
            position: Current wheel position
            options_chain: Optional pre-fetched options chain
            current_price: Optional current stock price
            volatility: Optional volatility override
            expiration_date: Optional specific expiration to target

        Returns:
            WheelRecommendation with biased strike selection

        Raises:
            InvalidStateError: If position has open trade (cannot recommend)
            DataFetchError: If market data cannot be fetched
        """
        # Validate state
        if position.has_open_position:
            raise InvalidStateError(
                f"Cannot recommend in state {position.state.value}. "
                f"Wait for current position to expire or close it first."
            )

        # Determine direction from state
        if position.state == WheelState.CASH:
            direction = "put"
        elif position.state == WheelState.SHARES:
            direction = "call"
        else:
            raise InvalidStateError(
                f"Cannot recommend in state {position.state.value}. "
                f"Must be in CASH or SHARES state."
            )

        # Fetch market data if not provided
        if options_chain is None:
            options_chain = self._fetch_options_chain(position.symbol)

        if current_price is None:
            current_price = self._fetch_current_price(position.symbol)

        if volatility is None:
            volatility = self._estimate_volatility(position.symbol, current_price)

        # Get candidates within profile range
        candidates = self._get_candidates(
            options_chain=options_chain,
            current_price=current_price,
            volatility=volatility,
            direction=direction,
            profile=position.profile,
            expiration_date=expiration_date,
            position=position,
        )

        if not candidates:
            raise DataFetchError(
                f"No suitable {direction} options found for {position.symbol} "
                f"within {position.profile.value} profile range"
            )

        # Apply bias: prefer further OTM + shorter DTE
        biased = self._apply_collection_bias(candidates)

        # Add warnings
        self._add_warnings(biased, position.symbol)

        # Return best recommendation
        return biased[0]

    def _fetch_options_chain(self, symbol: str) -> OptionsChain:
        """Fetch options chain from API."""
        if self.finnhub is None:
            raise DataFetchError("No Finnhub client configured")

        try:
            service = OptionsChainService(self.finnhub)
            return service.get_options_chain(symbol)
        except Exception as e:
            raise DataFetchError(f"Failed to fetch options chain for {symbol}: {e}")

    def _fetch_current_price(self, symbol: str) -> float:
        """Fetch current stock price."""
        if self.price_fetcher is None:
            raise DataFetchError("No price fetcher configured")

        try:
            price_data = self.price_fetcher.fetch_price_data(symbol, lookback_days=5)
            if price_data and price_data.closes:
                return price_data.closes[-1]
            raise DataFetchError(f"No price data returned for {symbol}")
        except Exception as e:
            raise DataFetchError(f"Failed to fetch price for {symbol}: {e}")

    def _estimate_volatility(self, symbol: str, current_price: float) -> float:
        """Estimate volatility for the symbol."""
        if self.price_fetcher is None:
            # Return a reasonable default if no price fetcher
            logger.warning(f"No price fetcher for {symbol}, using default volatility")
            return 0.30  # 30% default

        try:
            price_data = self.price_fetcher.fetch_price_data(symbol, lookback_days=30)
            if price_data:
                result = self.volatility_calculator.calculate_from_price_data(
                    price_data, method="close_to_close"
                )
                return result.volatility
        except Exception as e:
            logger.warning(f"Failed to calculate volatility for {symbol}: {e}")

        return 0.30  # Default to 30%

    def _get_candidates(
        self,
        options_chain: OptionsChain,
        current_price: float,
        volatility: float,
        direction: str,
        profile: StrikeProfile,
        expiration_date: Optional[str],
        position: WheelPosition,
    ) -> list[WheelRecommendation]:
        """
        Get candidate options within the profile's sigma range.

        Biases toward the outer edge of the range (further OTM).
        """
        candidates: list[WheelRecommendation] = []

        # Get profile sigma range
        min_sigma, max_sigma = PROFILE_SIGMA_RANGES[profile]

        # Get contracts of the right type
        if direction == "put":
            contracts = options_chain.get_puts()
        else:
            contracts = options_chain.get_calls()

        # Filter by expiration if specified
        if expiration_date:
            contracts = [c for c in contracts if c.expiration_date == expiration_date]
        else:
            # Get available expirations and prefer shorter ones
            expirations = sorted({c.expiration_date for c in contracts})
            if not expirations:
                return []

            # Filter to first few expirations (prefer shorter DTE)
            target_expirations = expirations[:3]  # First 3 expirations
            contracts = [c for c in contracts if c.expiration_date in target_expirations]

        for contract in contracts:
            # Skip ITM options
            if direction == "call" and contract.strike <= current_price:
                continue
            if direction == "put" and contract.strike >= current_price:
                continue

            # Skip zero bid (no premium)
            if contract.bid is None or contract.bid <= 0:
                continue

            # Calculate days to expiry
            dte = calculate_days_to_expiry(contract.expiration_date)
            if dte <= 0:
                continue

            # Calculate sigma distance
            try:
                sigma_distance = self.strike_optimizer.get_sigma_for_strike(
                    strike=contract.strike,
                    current_price=current_price,
                    volatility=volatility,
                    days_to_expiry=max(1, dte),
                    option_type=direction,
                )
            except (ValueError, ZeroDivisionError):
                continue

            # Filter by profile range
            if sigma_distance < min_sigma or sigma_distance > max_sigma:
                continue

            # Calculate probability
            try:
                prob_result = self.strike_optimizer.calculate_assignment_probability(
                    strike=contract.strike,
                    current_price=current_price,
                    volatility=volatility,
                    days_to_expiry=max(1, dte),
                    option_type=direction,
                )
                p_itm = prob_result.probability
            except (ValueError, ZeroDivisionError):
                p_itm = 0.0

            # Calculate contracts available
            if direction == "put":
                contracts_available = position.contracts_from_capital(contract.strike)
            else:
                contracts_available = position.contracts_from_shares

            if contracts_available <= 0:
                continue

            # Calculate premium
            premium_per_share = contract.bid
            total_premium = premium_per_share * contracts_available * 100

            # Calculate annualized yield
            if direction == "put":
                collateral = contract.strike * 100 * contracts_available
            else:
                collateral = current_price * 100 * contracts_available

            if collateral > 0 and dte > 0:
                annualized_yield = (total_premium / collateral) * (365 / dte) * 100
            else:
                annualized_yield = 0.0

            rec = WheelRecommendation(
                symbol=position.symbol,
                direction=direction,
                strike=contract.strike,
                expiration_date=contract.expiration_date,
                premium_per_share=premium_per_share,
                contracts=contracts_available,
                total_premium=total_premium,
                sigma_distance=sigma_distance,
                p_itm=p_itm,
                annualized_yield_pct=annualized_yield,
                dte=dte,
                current_price=current_price,
                bid=contract.bid,
                ask=contract.ask if contract.ask else 0.0,
            )
            candidates.append(rec)

        return candidates

    def _apply_collection_bias(
        self,
        candidates: list[WheelRecommendation],
    ) -> list[WheelRecommendation]:
        """
        Score and sort candidates by "collection bias" - preference for
        options that will expire worthless (letting us keep premium).

        Bias scoring:
        - Higher sigma distance = better (further OTM, less likely to be ITM)
        - Lower DTE = better (less time for adverse price moves)
        - Lower P(ITM) = better (less assignment/exercise risk)
        """
        for c in candidates:
            # Normalize factors to 0-1 scale
            sigma_score = min(c.sigma_distance / 2.5, 1.0)  # Cap at 2.5 sigma
            dte_score = 1.0 - min(c.dte / 45, 1.0)  # Prefer < 45 DTE
            pitm_score = 1.0 - c.p_itm  # Lower P(ITM) = higher score

            # Weighted combination favoring low assignment probability
            c.bias_score = 0.4 * sigma_score + 0.3 * dte_score + 0.3 * pitm_score

        return sorted(candidates, key=lambda c: c.bias_score, reverse=True)

    def _add_warnings(
        self,
        candidates: list[WheelRecommendation],
        symbol: str,
    ) -> None:
        """Add warnings for conditions that increase assignment risk."""
        for c in candidates:
            # Determine profile from sigma distance
            profile = self.strike_optimizer.get_profile_for_sigma(c.sigma_distance)

            # High P(ITM) warning - increased risk of assignment
            if profile:
                threshold = PITM_WARNING_THRESHOLDS.get(profile, 0.15)
                if c.p_itm > threshold:
                    c.warnings.append(
                        f"P(ITM) {c.p_itm * 100:.1f}% exceeds "
                        f"{threshold * 100:.0f}% threshold - higher assignment risk"
                    )

            # Earnings warning - volatility spike risk
            if self.earnings_calendar:
                try:
                    spans, earn_date = self.earnings_calendar.expiration_spans_earnings(
                        symbol, c.expiration_date
                    )
                    if spans and earn_date:
                        c.warnings.append(
                            f"Earnings on {earn_date} before expiration - "
                            f"elevated volatility risk"
                        )
                except Exception as e:
                    logger.debug(f"Could not check earnings for {symbol}: {e}")

            # Low premium warning - may not be worth the risk
            if c.annualized_yield_pct < 5.0:
                c.warnings.append(
                    f"Low annualized yield: {c.annualized_yield_pct:.1f}%"
                )

            # Short DTE warning
            if c.dte <= 7:
                c.warnings.append(
                    f"Short DTE ({c.dte} days) - limited time for adjustment"
                )

    def get_multiple_recommendations(
        self,
        position: WheelPosition,
        options_chain: Optional[OptionsChain] = None,
        current_price: Optional[float] = None,
        volatility: Optional[float] = None,
        limit: int = 5,
    ) -> list[WheelRecommendation]:
        """
        Get multiple ranked recommendations for a position.

        Args:
            position: Current wheel position
            options_chain: Optional pre-fetched options chain
            current_price: Optional current stock price
            volatility: Optional volatility override
            limit: Maximum number of recommendations

        Returns:
            List of WheelRecommendation sorted by bias score
        """
        try:
            # Get one recommendation first to validate state
            rec = self.get_recommendation(
                position, options_chain, current_price, volatility
            )
            # The internal candidates are sorted, so we can return multiple
            # by re-running the internal logic
        except (InvalidStateError, DataFetchError):
            return []

        # Re-fetch to get all candidates
        if options_chain is None and self.finnhub:
            options_chain = self._fetch_options_chain(position.symbol)

        if current_price is None and self.price_fetcher:
            current_price = self._fetch_current_price(position.symbol)
        elif current_price is None:
            current_price = rec.current_price

        if volatility is None:
            volatility = self._estimate_volatility(position.symbol, current_price)

        direction = "put" if position.state == WheelState.CASH else "call"

        candidates = self._get_candidates(
            options_chain=options_chain,
            current_price=current_price,
            volatility=volatility,
            direction=direction,
            profile=position.profile,
            expiration_date=None,
            position=position,
        )

        if not candidates:
            return [rec]  # Return single recommendation if no more found

        biased = self._apply_collection_bias(candidates)
        self._add_warnings(biased, position.symbol)

        return biased[:limit]
