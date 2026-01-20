"""Date utility functions."""

import logging
from datetime import date

logger = logging.getLogger(__name__)


def calculate_days_to_expiry(expiration_date: str, default: int = 30) -> int:
    """
    Calculate calendar days until expiration.

    Uses calendar days (not trading days) as this is the standard
    convention for options pricing (Black-Scholes, IV term structure).

    Example: Jan 19 to Jan 23 = 4 calendar days

    Args:
        expiration_date: Date string in ISO format (YYYY-MM-DD)
        default: Default value if parsing fails

    Returns:
        Number of days to expiry (minimum 1)
    """
    try:
        exp_date_obj = date.fromisoformat(expiration_date)
        today = date.today()
        days = (exp_date_obj - today).days
        return max(1, days)
    except (ValueError, TypeError) as e:
        logger.warning(f"Could not parse expiration date '{expiration_date}': {e}")
        return default
