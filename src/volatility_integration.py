"""
Integration module connecting volatility calculation with options chain data.

This module provides helper functions to extract implied volatility from
options chains and integrate with the volatility calculator.
"""

import logging
from datetime import datetime
from typing import Optional

from .models import OptionsChain
from .volatility import PriceData, VolatilityCalculator, VolatilityResult

logger = logging.getLogger(__name__)


def extract_atm_implied_volatility(
    options_chain: OptionsChain,
    current_price: float,
    expiration_date: Optional[str] = None,
    option_type: str = "call",
) -> Optional[float]:
    """
    Extract ATM implied volatility from options chain.

    Args:
        options_chain: Options chain data
        current_price: Current stock price
        expiration_date: Specific expiration (None = nearest)
        option_type: "call" or "put"

    Returns:
        ATM implied volatility as decimal, or None if not found
    """
    # Filter by type
    contracts = (
        options_chain.get_calls() if option_type.lower() == "call" else options_chain.get_puts()
    )

    # Filter by expiration if specified
    if expiration_date:
        contracts = [c for c in contracts if c.expiration_date == expiration_date]

    if not contracts:
        logger.warning(f"No {option_type} contracts found")
        return None

    # Find ATM strike (closest to current price)
    atm_contract = min(contracts, key=lambda c: abs(c.strike - current_price))

    # Get implied volatility
    iv = atm_contract.implied_volatility
    if iv is None:
        logger.warning(f"No implied volatility for ATM strike {atm_contract.strike}")
        return None

    logger.info(
        f"Extracted ATM IV: {iv:.4f} ({iv * 100:.2f}%) "
        f"from strike ${atm_contract.strike} (price: ${current_price})"
    )

    return iv


def get_nearest_weekly_expiration(options_chain: OptionsChain) -> Optional[str]:
    """
    Get the nearest weekly expiration date from options chain.

    Args:
        options_chain: Options chain data

    Returns:
        Expiration date string (YYYY-MM-DD) or None
    """
    expirations = options_chain.get_expirations()
    if not expirations:
        return None

    # Sort and return nearest
    sorted_expirations = sorted(expirations)
    return sorted_expirations[0] if sorted_expirations else None


def calculate_volatility_with_iv(
    calculator: VolatilityCalculator,
    price_data: PriceData,
    options_chain: OptionsChain,
    current_price: float,
    method: str = "blended",
    expiration_date: Optional[str] = None,
) -> VolatilityResult:
    """
    Calculate volatility combining historical prices and implied volatility.

    This is the main integration point that brings together price history
    and options market data for a comprehensive volatility estimate.

    Args:
        calculator: VolatilityCalculator instance
        price_data: Historical price data
        options_chain: Options chain with IV data
        current_price: Current stock price
        method: Calculation method (blended, close_to_close, etc.)
        expiration_date: Specific expiration for IV extraction

    Returns:
        VolatilityResult with calculated volatility

    Raises:
        ValueError: If method is blended but IV cannot be extracted
    """
    if method == "blended":
        # Extract implied volatility
        iv = extract_atm_implied_volatility(
            options_chain=options_chain,
            current_price=current_price,
            expiration_date=expiration_date,
        )

        if iv is None:
            logger.warning("Could not extract IV, falling back to close-to-close")
            return calculator.calculate_from_price_data(
                price_data=price_data, method="close_to_close"
            )

        # Calculate blended volatility
        return calculator.calculate_blended(price_data=price_data, implied_volatility=iv)
    else:
        # Calculate using specified historical method
        return calculator.calculate_from_price_data(price_data=price_data, method=method)


def calculate_iv_term_structure(
    options_chain: OptionsChain, current_price: float, num_expirations: int = 4
) -> list[dict]:
    """
    Calculate implied volatility term structure.

    Args:
        options_chain: Options chain data
        current_price: Current stock price
        num_expirations: Number of expirations to include

    Returns:
        List of dicts with expiration, days_to_expiry, and iv
    """
    expirations = sorted(options_chain.get_expirations())[:num_expirations]
    term_structure = []

    for exp_date in expirations:
        iv = extract_atm_implied_volatility(
            options_chain=options_chain, current_price=current_price, expiration_date=exp_date
        )

        if iv:
            # Calculate days to expiry
            try:
                exp = datetime.fromisoformat(exp_date)
                today = datetime.now()
                dte = (exp - today).days
            except (ValueError, TypeError):
                dte = None

            term_structure.append(
                {
                    "expiration_date": exp_date,
                    "days_to_expiry": dte,
                    "implied_volatility": iv,
                    "implied_volatility_pct": iv * 100,
                }
            )

    return term_structure


def validate_price_data_quality(price_data: PriceData) -> dict:
    """
    Validate price data quality for volatility calculation.

    Args:
        price_data: Price data to validate

    Returns:
        Dict with validation results
    """
    issues = []
    warnings = []

    # Check data points
    n_points = len(price_data.closes)
    if n_points < 20:
        warnings.append(f"Only {n_points} data points (recommended: 60+)")

    # Check for gaps (missing data)
    if price_data.dates:
        dates = [datetime.fromisoformat(d) for d in price_data.dates]
        for i in range(1, len(dates)):
            gap = (dates[i] - dates[i - 1]).days
            if gap > 5:  # More than 5 days suggests missing data
                warnings.append(
                    f"Data gap detected: {gap} days between {dates[i - 1]} and {dates[i]}"
                )

    # Check price quality
    if any(c <= 0 for c in price_data.closes):
        issues.append("Found non-positive prices")

    # Check for unrealistic returns (>50% in one day)
    for i in range(1, len(price_data.closes)):
        ret = abs((price_data.closes[i] / price_data.closes[i - 1]) - 1)
        if ret > 0.5:
            warnings.append(
                f"Large price move detected: {ret * 100:.1f}% "
                f"on {price_data.dates[i] if price_data.dates else f'day {i}'}"
            )

    return {
        "is_valid": len(issues) == 0,
        "data_points": n_points,
        "issues": issues,
        "warnings": warnings,
        "quality_score": max(0, 100 - len(issues) * 50 - len(warnings) * 10),
    }
