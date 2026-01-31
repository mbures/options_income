"""
Output formatting functions for the overlay scanner.

This module provides functions for generating broker checklists and LLM memo payloads
from scan results.
"""

from datetime import datetime

from src.models import (
    BrokerChecklist,
    CandidateStrike,
    LLMMemoPayload,
    PortfolioHolding,
    ScannerConfig,
)


def generate_broker_checklist(
    symbol: str,
    candidate: CandidateStrike,
    config: ScannerConfig,
    earnings_clear: bool,
    dividend_verified: bool = False,
) -> BrokerChecklist:
    """
    Generate a broker checklist for a recommended trade.

    Args:
        symbol: Stock symbol
        candidate: The recommended strike
        config: Scanner configuration
        earnings_clear: Whether earnings have been verified clear
        dividend_verified: Whether dividend has been verified

    Returns:
        BrokerChecklist for the trade
    """
    checks = [
        f"Verify current bid >= ${candidate.bid:.2f}",
        f"Verify spread <= ${config.max_spread_absolute:.2f} or {config.max_spread_relative_pct:.0f}%",
        f"Verify open interest >= {config.min_open_interest}",
        f"Confirm {candidate.contracts_to_sell} contracts x ${candidate.strike} strike",
        f"Expected net credit: ${candidate.total_net_credit:.2f}",
    ]

    if earnings_clear:
        checks.append("Earnings: CLEAR (no earnings before expiration)")
    else:
        checks.append("Earnings: VERIFY at broker (data may be stale)")

    if dividend_verified:
        checks.append("Dividend: VERIFIED (no ex-div before expiration)")
    else:
        checks.append("Dividend: UNVERIFIED (check for early exercise risk)")

    warnings = list(candidate.warnings)
    if not dividend_verified:
        warnings.append("Dividend data unverified - check at broker")

    return BrokerChecklist(
        symbol=symbol,
        action="SELL TO OPEN",
        contracts=candidate.contracts_to_sell,
        strike=candidate.strike,
        expiration=candidate.expiration_date,
        option_type="CALL",
        limit_price=candidate.mid_price,
        min_acceptable_credit=candidate.bid,
        checks=checks,
        warnings=warnings,
    )


def generate_llm_memo_payload(
    symbol: str,
    current_price: float,
    holding: PortfolioHolding,
    candidate: CandidateStrike,
    config: ScannerConfig,
    earnings_status: str,
    dividend_status: str,
) -> LLMMemoPayload:
    """
    Generate structured payload for LLM decision memo.

    Args:
        symbol: Stock symbol
        current_price: Current stock price
        holding: Portfolio holding info
        candidate: Recommended strike
        config: Scanner configuration
        earnings_status: Earnings verification status
        dividend_status: Dividend verification status

    Returns:
        LLMMemoPayload for memo generation
    """
    holding_dict = {
        "symbol": holding.symbol,
        "shares": holding.shares,
        "cost_basis": holding.cost_basis,
        "acquired_date": holding.acquired_date,
        "account_type": holding.account_type,
    }

    return LLMMemoPayload(
        symbol=symbol,
        current_price=current_price,
        shares_held=holding.shares,
        contracts_to_write=candidate.contracts_to_sell,
        candidate=candidate.to_dict(),
        holding=holding_dict,
        risk_profile=config.delta_band.value,
        earnings_status=earnings_status,
        dividend_status=dividend_status,
        account_type=holding.account_type,
        timestamp=datetime.now().isoformat(),
    )
