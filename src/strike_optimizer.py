"""
Strike optimization module for covered options strategies.

This module provides tools for:
- Calculating optimal strike prices at N standard deviations (sigma)
- Rounding to tradeable strike increments
- Computing assignment probabilities using Black-Scholes
- Generating strike recommendations based on risk profiles

Formula Reference:
    Strike at N sigma: K = S x exp(n x sigma x sqrt(T))
    where:
        K = Strike price
        S = Current stock price
        n = Number of standard deviations (+ for calls, - for puts)
        sigma = Annualized volatility (as decimal, e.g., 0.30 for 30%)
        T = Time to expiration in years

Assignment Probability (Black-Scholes):
    For calls: P(ITM at expiry) approx N(d2)
    For puts: P(ITM at expiry) approx N(-d2)
    where:
        d2 = [ln(S/K) + (r - sigma^2/2)T] / (sigma sqrt(T))
        N() = Standard normal CDF
"""

import logging
import math
from typing import Optional

from .constants import (
    DEFAULT_RISK_FREE_RATE,
    MAX_BID_ASK_SPREAD_PCT,
    MIN_OPEN_INTEREST,
    STRIKE_INCREMENTS,
)
from .models import (
    PROFILE_SIGMA_RANGES,
    OptionsChain,
    ProbabilityResult,
    ProfileStrikesResult,
    StrikeProfile,
    StrikeRecommendation,
    StrikeResult,
)
from .utils import calculate_days_to_expiry

logger = logging.getLogger(__name__)


# Re-export models for backward compatibility
__all__ = [
    "StrikeOptimizer",
    "StrikeProfile",
    "PROFILE_SIGMA_RANGES",
    "StrikeResult",
    "ProbabilityResult",
    "StrikeRecommendation",
    "ProfileStrikesResult",
]


class StrikeOptimizer:
    """
    Optimizer for selecting optimal option strikes.

    This class provides methods to:
    - Calculate strike prices at N standard deviations from current price
    - Round strikes to tradeable increments
    - Compute assignment probabilities
    - Generate filtered recommendations based on risk profiles

    Example:
        optimizer = StrikeOptimizer()

        # Calculate a 1.5 sigma OTM call strike
        result = optimizer.calculate_strike_at_sigma(
            current_price=10.50,
            volatility=0.35,
            days_to_expiry=30,
            sigma=1.5,
            option_type="call"
        )

        # Get recommendations for a specific profile
        recs = optimizer.get_strike_recommendations(
            options_chain=chain,
            current_price=10.50,
            volatility=0.35,
            profile=StrikeProfile.MODERATE
        )
    """

    # Class-level thresholds (for reference, actual values come from constants)
    STRIKE_INCREMENTS = STRIKE_INCREMENTS
    DEFAULT_RISK_FREE_RATE = DEFAULT_RISK_FREE_RATE
    MIN_OPEN_INTEREST = MIN_OPEN_INTEREST
    MAX_BID_ASK_SPREAD_PCT = MAX_BID_ASK_SPREAD_PCT

    def __init__(self, risk_free_rate: Optional[float] = None):
        """
        Initialize the strike optimizer.

        Args:
            risk_free_rate: Annual risk-free rate (default: 0.05 = 5%)
        """
        self.risk_free_rate = risk_free_rate or self.DEFAULT_RISK_FREE_RATE

    def calculate_strike_at_sigma(
        self,
        current_price: float,
        volatility: float,
        days_to_expiry: int,
        sigma: float,
        option_type: str = "call",
        round_strike: bool = True,
    ) -> StrikeResult:
        """
        Calculate the strike price at N standard deviations from current price.

        Uses the formula: K = S x exp(n x sigma x sqrt(T))

        For calls (positive n): Strike is ABOVE current price (OTM call)
        For puts (negative n): Strike is BELOW current price (OTM put)

        Args:
            current_price: Current stock price
            volatility: Annualized volatility as decimal (e.g., 0.30 for 30%)
            days_to_expiry: Days until option expiration
            sigma: Number of standard deviations (positive for calls, negative for puts)
            option_type: "call" or "put"
            round_strike: Whether to round to tradeable strike

        Returns:
            StrikeResult with theoretical and tradeable strikes

        Raises:
            ValueError: If inputs are invalid
        """
        # Validate inputs
        if current_price <= 0:
            raise ValueError(f"Current price must be positive, got {current_price}")
        if volatility <= 0:
            raise ValueError(f"Volatility must be positive, got {volatility}")
        if days_to_expiry <= 0:
            raise ValueError(f"Days to expiry must be positive, got {days_to_expiry}")

        option_type = option_type.lower()
        if option_type not in ("call", "put"):
            raise ValueError(f"Option type must be 'call' or 'put', got {option_type}")

        # Adjust sigma sign based on option type
        # Calls: positive sigma = OTM (above current price)
        # Puts: negative sigma = OTM (below current price)
        if option_type == "call":
            n = abs(sigma)  # Ensure positive for calls
        else:
            n = -abs(sigma)  # Ensure negative for puts

        # Calculate time to expiry in years
        time_to_expiry = days_to_expiry / 365.0

        # Calculate theoretical strike: K = S x exp(n x sigma x sqrt(T))
        theoretical_strike = current_price * math.exp(n * volatility * math.sqrt(time_to_expiry))

        # Round to tradeable strike if requested
        if round_strike:
            tradeable_strike = self.round_to_tradeable_strike(
                theoretical_strike, current_price, option_type
            )
        else:
            tradeable_strike = theoretical_strike

        # Calculate assignment probability for the tradeable strike
        prob_result = self.calculate_assignment_probability(
            strike=tradeable_strike,
            current_price=current_price,
            volatility=volatility,
            days_to_expiry=days_to_expiry,
            option_type=option_type,
        )

        logger.info(
            f"Calculated {sigma}sigma {option_type} strike: "
            f"theoretical=${theoretical_strike:.2f}, tradeable=${tradeable_strike:.2f}, "
            f"P(ITM)={prob_result.probability * 100:.1f}%"
        )

        return StrikeResult(
            theoretical_strike=theoretical_strike,
            tradeable_strike=tradeable_strike,
            sigma=sigma,
            current_price=current_price,
            volatility=volatility,
            days_to_expiry=days_to_expiry,
            option_type=option_type,
            assignment_probability=prob_result.probability,
        )

    def round_to_tradeable_strike(
        self,
        strike: float,
        current_price: float,
        option_type: str,
        available_strikes: Optional[list[float]] = None,
    ) -> float:
        """
        Round a theoretical strike to a tradeable strike price.

        Uses conservative rounding:
        - Calls: Round UP (further OTM, less risk of assignment)
        - Puts: Round DOWN (further OTM, less risk of assignment)

        Args:
            strike: Theoretical strike price
            current_price: Current stock price (for determining increment)
            option_type: "call" or "put"
            available_strikes: Optional list of actual available strikes from chain

        Returns:
            Rounded tradeable strike price
        """
        option_type = option_type.lower()

        # If we have actual available strikes, find nearest appropriate one
        if available_strikes:
            available_strikes = sorted(available_strikes)

            if option_type == "call":
                # For calls, find smallest strike >= theoretical
                for s in available_strikes:
                    if s >= strike:
                        return s
                # If no strike found, return highest available
                return available_strikes[-1]
            else:
                # For puts, find largest strike <= theoretical
                for s in reversed(available_strikes):
                    if s <= strike:
                        return s
                # If no strike found, return lowest available
                return available_strikes[0]

        # Otherwise, use standard increment rounding
        increment = self._get_strike_increment(current_price)

        if option_type == "call":
            # Round up for calls (conservative)
            return math.ceil(strike / increment) * increment
        else:
            # Round down for puts (conservative)
            return math.floor(strike / increment) * increment

    def _get_strike_increment(self, price: float) -> float:
        """
        Get the standard strike increment for a given price level.

        Args:
            price: Stock price

        Returns:
            Strike increment (e.g., 0.50, 1.00, 2.50, 5.00)
        """
        for (low, high), increment in self.STRIKE_INCREMENTS.items():
            if low <= price < high:
                return increment
        return 1.00  # Default

    def calculate_assignment_probability(
        self,
        strike: float,
        current_price: float,
        volatility: float,
        days_to_expiry: int,
        option_type: str = "call",
    ) -> ProbabilityResult:
        """
        Calculate the probability of an option being ITM at expiration.

        Uses Black-Scholes framework:
        - For calls: P(ITM) = N(d2)
        - For puts: P(ITM) = N(-d2)

        where d2 = [ln(S/K) + (r - sigma^2/2)T] / (sigma sqrt(T))

        Note: This assumes log-normal price distribution and is a theoretical
        estimate. Actual assignment probability may differ due to early
        exercise, market conditions, etc.

        Args:
            strike: Strike price
            current_price: Current stock price
            volatility: Annualized volatility as decimal
            days_to_expiry: Days until expiration
            option_type: "call" or "put"

        Returns:
            ProbabilityResult with probability and Greeks

        Raises:
            ValueError: If inputs are invalid
        """
        if strike <= 0:
            raise ValueError(f"Strike must be positive, got {strike}")
        if current_price <= 0:
            raise ValueError(f"Current price must be positive, got {current_price}")
        if volatility <= 0:
            raise ValueError(f"Volatility must be positive, got {volatility}")
        if days_to_expiry <= 0:
            raise ValueError(f"Days to expiry must be positive, got {days_to_expiry}")

        option_type = option_type.lower()
        if option_type not in ("call", "put"):
            raise ValueError(f"Option type must be 'call' or 'put', got {option_type}")

        # Time to expiry in years
        T = days_to_expiry / 365.0

        # Calculate d1 and d2
        d1 = (
            math.log(current_price / strike) + (self.risk_free_rate + 0.5 * volatility**2) * T
        ) / (volatility * math.sqrt(T))
        d2 = d1 - volatility * math.sqrt(T)

        # Calculate probability and delta
        if option_type == "call":
            probability = self._norm_cdf(d2)  # N(d2) for calls
            delta = self._norm_cdf(d1)  # Delta = N(d1) for calls
        else:
            probability = self._norm_cdf(-d2)  # N(-d2) for puts
            delta = self._norm_cdf(d1) - 1  # Delta = N(d1) - 1 for puts

        return ProbabilityResult(
            probability=probability,
            d1=d1,
            d2=d2,
            delta=delta,
            strike=strike,
            current_price=current_price,
            volatility=volatility,
            time_to_expiry=T,
            risk_free_rate=self.risk_free_rate,
            option_type=option_type,
        )

    @staticmethod
    def _norm_cdf(x: float) -> float:
        """
        Calculate the standard normal cumulative distribution function.

        Uses the error function: N(x) = 0.5 * (1 + erf(x / sqrt(2)))

        Args:
            x: Value to evaluate

        Returns:
            Probability that a standard normal RV is <= x
        """
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def get_sigma_for_strike(
        self,
        strike: float,
        current_price: float,
        volatility: float,
        days_to_expiry: int,
        option_type: str = "call",
    ) -> float:
        """
        Calculate how many sigmas a strike is from the current price.

        Inverse of calculate_strike_at_sigma:
        n = ln(K/S) / (sigma x sqrt(T))

        Args:
            strike: Strike price
            current_price: Current stock price
            volatility: Annualized volatility as decimal
            days_to_expiry: Days until expiration
            option_type: "call" or "put" (affects sign)

        Returns:
            Number of standard deviations (positive for OTM)
        """
        if strike <= 0 or current_price <= 0:
            raise ValueError("Strike and current price must be positive")
        if volatility <= 0:
            raise ValueError("Volatility must be positive")
        if days_to_expiry <= 0:
            raise ValueError("Days to expiry must be positive")

        T = days_to_expiry / 365.0
        sigma_distance = math.log(strike / current_price) / (volatility * math.sqrt(T))

        # For OTM options, return absolute value
        option_type = option_type.lower()
        if option_type == "call":
            # OTM calls have strike > current_price, so sigma_distance is positive
            return sigma_distance
        else:
            # OTM puts have strike < current_price, so sigma_distance is negative
            # Return absolute value for consistency
            return -sigma_distance

    def get_profile_for_sigma(self, sigma: float) -> Optional[StrikeProfile]:
        """
        Determine which risk profile a given sigma distance falls into.

        Args:
            sigma: Number of standard deviations (positive)

        Returns:
            StrikeProfile or None if outside all ranges
        """
        sigma = abs(sigma)
        for profile, (min_sig, max_sig) in PROFILE_SIGMA_RANGES.items():
            if min_sig <= sigma < max_sig:
                return profile
        return None

    def get_strike_recommendations(
        self,
        options_chain: OptionsChain,
        current_price: float,
        volatility: float,
        option_type: str = "call",
        expiration_date: Optional[str] = None,
        profile: Optional[StrikeProfile] = None,
        min_open_interest: Optional[int] = None,
        max_bid_ask_spread_pct: Optional[float] = None,
        limit: int = 10,
    ) -> list[StrikeRecommendation]:
        """
        Generate ranked strike recommendations based on criteria.

        Filters options by:
        - Option type (call/put)
        - Expiration date (optional)
        - Risk profile sigma range (optional)
        - Minimum open interest (liquidity)
        - Maximum bid-ask spread percentage

        Args:
            options_chain: Options chain data
            current_price: Current stock price
            volatility: Annualized volatility for calculations
            option_type: "call" or "put"
            expiration_date: Specific expiration (None = nearest)
            profile: StrikeProfile to filter by (None = all profiles)
            min_open_interest: Minimum OI threshold (default: 100)
            max_bid_ask_spread_pct: Max spread % (default: 10%)
            limit: Maximum recommendations to return

        Returns:
            List of StrikeRecommendation sorted by profile priority then sigma
        """
        option_type = option_type.lower()
        min_oi = min_open_interest if min_open_interest is not None else self.MIN_OPEN_INTEREST
        max_spread = (
            max_bid_ask_spread_pct
            if max_bid_ask_spread_pct is not None
            else self.MAX_BID_ASK_SPREAD_PCT
        )

        # Get contracts of the right type
        if option_type == "call":
            contracts = options_chain.get_calls()
        else:
            contracts = options_chain.get_puts()

        # Filter by expiration if specified
        if expiration_date:
            contracts = [c for c in contracts if c.expiration_date == expiration_date]
        else:
            # Use nearest expiration
            expirations = sorted({c.expiration_date for c in contracts})
            if expirations:
                expiration_date = expirations[0]
                contracts = [c for c in contracts if c.expiration_date == expiration_date]

        if not contracts:
            logger.warning(f"No {option_type} contracts found for recommendations")
            return []

        # Calculate days to expiry (calendar days, not trading days)
        days_to_expiry = calculate_days_to_expiry(expiration_date)

        recommendations = []

        for contract in contracts:
            # Skip ITM options
            if option_type == "call" and contract.strike <= current_price:
                continue
            if option_type == "put" and contract.strike >= current_price:
                continue

            # Calculate sigma distance
            try:
                sigma_distance = self.get_sigma_for_strike(
                    strike=contract.strike,
                    current_price=current_price,
                    volatility=volatility,
                    days_to_expiry=days_to_expiry,
                    option_type=option_type,
                )
            except (ValueError, ZeroDivisionError):
                continue

            # Filter by profile if specified
            contract_profile = self.get_profile_for_sigma(sigma_distance)
            if profile and contract_profile != profile:
                continue

            # Calculate assignment probability
            try:
                prob_result = self.calculate_assignment_probability(
                    strike=contract.strike,
                    current_price=current_price,
                    volatility=volatility,
                    days_to_expiry=days_to_expiry,
                    option_type=option_type,
                )
                assignment_prob = prob_result.probability
            except (ValueError, ZeroDivisionError):
                assignment_prob = 0.0

            # Calculate mid price and spread
            bid = contract.bid
            ask = contract.ask
            mid_price = None
            bid_ask_spread_pct = None
            warnings = []

            if bid is not None and ask is not None:
                mid_price = (bid + ask) / 2
                if mid_price > 0:
                    bid_ask_spread_pct = ((ask - bid) / mid_price) * 100

            # Apply liquidity filters
            if contract.open_interest is not None and contract.open_interest < min_oi:
                warnings.append(f"Low open interest: {contract.open_interest}")
                # Still include but with warning

            if bid_ask_spread_pct is not None and bid_ask_spread_pct > max_spread:
                warnings.append(f"Wide bid-ask spread: {bid_ask_spread_pct:.1f}%")
                # Still include but with warning

            if bid is None or bid <= 0:
                warnings.append("No bid price available")

            rec = StrikeRecommendation(
                contract=contract,
                strike=contract.strike,
                expiration_date=contract.expiration_date,
                option_type=option_type,
                sigma_distance=sigma_distance,
                assignment_probability=assignment_prob,
                bid=bid,
                ask=ask,
                mid_price=mid_price,
                bid_ask_spread_pct=bid_ask_spread_pct,
                open_interest=contract.open_interest,
                volume=contract.volume,
                implied_volatility=contract.implied_volatility,
                profile=contract_profile,
                warnings=warnings,
            )
            recommendations.append(rec)

        # Sort by profile priority (Conservative > Moderate > Aggressive > Defensive)
        # then by sigma distance (closest to target profile center first)
        profile_priority = {
            StrikeProfile.CONSERVATIVE: 0,
            StrikeProfile.MODERATE: 1,
            StrikeProfile.AGGRESSIVE: 2,
            StrikeProfile.DEFENSIVE: 3,
            None: 4,
        }

        recommendations.sort(
            key=lambda r: (
                profile_priority.get(r.profile, 4),
                abs(r.sigma_distance - 1.5),  # Prefer strikes near 1.5sigma (moderate)
            )
        )

        logger.info(
            f"Generated {len(recommendations[:limit])} strike recommendations "
            f"for {option_type}s expiring {expiration_date}"
        )

        return recommendations[:limit]

    def calculate_strikes_for_profiles(
        self,
        current_price: float,
        volatility: float,
        days_to_expiry: int,
        option_type: str = "call",
    ) -> ProfileStrikesResult:
        """
        Calculate representative strikes for all risk profiles.

        Uses the midpoint of each profile's sigma range.

        IMPORTANT: P(ITM) percentages in profile descriptions are approximate
        and calibrated for ~30 DTE. With shorter DTE, the same sigma distance
        produces lower P(ITM) because there's less time for price movement.

        The result includes warnings when:
        - Multiple profiles collapse to the same tradeable strike (common with
          short DTE or low volatility where price movement is small)
        - DTE is very short (<14 days), suggesting longer expirations for
          better strike differentiation

        Args:
            current_price: Current stock price
            volatility: Annualized volatility
            days_to_expiry: Days until expiration
            option_type: "call" or "put"

        Returns:
            ProfileStrikesResult with strikes dict and any warnings
        """
        strikes = {}
        warnings = []
        collapsed_profiles = []
        is_short_dte = days_to_expiry < 14

        for profile, (min_sigma, max_sigma) in PROFILE_SIGMA_RANGES.items():
            mid_sigma = (min_sigma + max_sigma) / 2

            result = self.calculate_strike_at_sigma(
                current_price=current_price,
                volatility=volatility,
                days_to_expiry=days_to_expiry,
                sigma=mid_sigma,
                option_type=option_type,
            )
            strikes[profile] = result

        # Detect strike collisions (multiple profiles mapping to same tradeable strike)
        strike_to_profiles: dict[float, list[StrikeProfile]] = {}
        for profile, result in strikes.items():
            strike = result.tradeable_strike
            if strike not in strike_to_profiles:
                strike_to_profiles[strike] = []
            strike_to_profiles[strike].append(profile)

        for strike, profiles in strike_to_profiles.items():
            if len(profiles) > 1:
                profile_names = [p.value for p in profiles]
                collapsed_profiles.append(tuple(profiles))
                warnings.append(
                    f"Profiles {', '.join(profile_names)} collapse to same strike ${strike:.2f} "
                    f"(consider longer DTE for differentiation)"
                )

        # Add short DTE warning
        if is_short_dte:
            warnings.append(
                f"Short DTE ({days_to_expiry} days): P(ITM) values will be lower than typical "
                f"30-day targets. Consider 30+ DTE for profile-aligned probabilities."
            )

        if warnings:
            for w in warnings:
                logger.warning(w)

        return ProfileStrikesResult(
            strikes=strikes,
            warnings=warnings,
            collapsed_profiles=collapsed_profiles,
            is_short_dte=is_short_dte,
        )
