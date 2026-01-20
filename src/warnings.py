"""
Warning utilities for options analysis.

This module provides shared warning functions used by covered call
and covered put analyzers to check for liquidity issues, earnings
dates, and early assignment risk.

Example:
    from src.warnings import add_liquidity_warnings, check_earnings_warning

    warnings = []
    add_liquidity_warnings(contract, warnings)
    check_earnings_warning(expiration, earnings_dates, warnings)
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import OptionContract

logger = logging.getLogger(__name__)

# Default thresholds (can be overridden by caller)
DEFAULT_MIN_OPEN_INTEREST = 100
DEFAULT_MAX_BID_ASK_SPREAD_PCT = 10.0


def add_liquidity_warnings(
    contract: "OptionContract",
    warnings: list[str],
    min_open_interest: int = DEFAULT_MIN_OPEN_INTEREST,
    max_spread_pct: float = DEFAULT_MAX_BID_ASK_SPREAD_PCT,
) -> None:
    """
    Add liquidity-related warnings to a contract analysis.

    Checks for:
    - Low open interest
    - Wide bid-ask spread
    - Missing or zero bid price

    Args:
        contract: Option contract to check
        warnings: List to append warnings to
        min_open_interest: Minimum acceptable OI (default 100)
        max_spread_pct: Maximum acceptable spread % (default 10%)
    """
    if contract.open_interest is not None and contract.open_interest < min_open_interest:
        warnings.append(f"Low open interest: {contract.open_interest}")

    if contract.bid is not None and contract.ask is not None:
        mid = (contract.bid + contract.ask) / 2
        if mid > 0:
            spread_pct = ((contract.ask - contract.bid) / mid) * 100
            if spread_pct > max_spread_pct:
                warnings.append(f"Wide bid-ask spread: {spread_pct:.1f}%")

    if contract.bid is None or contract.bid <= 0:
        warnings.append("No bid price available")


def check_earnings_warning(
    expiration_date: str,
    earnings_dates: list[str],
    warnings: list[str],
) -> None:
    """
    Check if expiration spans an earnings date and add warning if so.

    Args:
        expiration_date: Option expiration date (YYYY-MM-DD)
        earnings_dates: List of earnings dates to check against
        warnings: List to append warnings to
    """
    try:
        exp_dt = datetime.fromisoformat(expiration_date)
        now = datetime.now()

        for earn_date in earnings_dates:
            earn_dt = datetime.fromisoformat(earn_date)
            if now <= earn_dt <= exp_dt:
                warnings.append(f"Expiration spans earnings date: {earn_date}")
                break
    except (ValueError, TypeError):
        pass


def check_early_assignment_risk(
    contract: "OptionContract",
    current_price: float,
    ex_dividend_dates: list[str],
    warnings: list[str],
) -> None:
    """
    Check for early assignment risk on deep ITM puts near ex-dividend.

    Early assignment is more likely when:
    - Put is deep ITM (intrinsic value high)
    - Ex-dividend date is before expiration
    - Time value is low relative to dividend

    Args:
        contract: Put option contract to check
        current_price: Current stock price
        ex_dividend_dates: List of ex-dividend dates (YYYY-MM-DD)
        warnings: List to append warnings to
    """
    try:
        exp_dt = datetime.fromisoformat(contract.expiration_date)
        now = datetime.now()

        for ex_date in ex_dividend_dates:
            ex_dt = datetime.fromisoformat(ex_date)
            if now <= ex_dt <= exp_dt:
                # Check if put is significantly ITM
                intrinsic_value = contract.strike - current_price
                if intrinsic_value > 0:
                    warnings.append(
                        f"Elevated early assignment risk: ex-dividend {ex_date}, "
                        f"put is ${intrinsic_value:.2f} ITM"
                    )
                break
    except (ValueError, TypeError):
        pass
