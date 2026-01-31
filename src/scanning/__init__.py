"""
Weekly Overlay Scanner for covered call strategies.

This package provides a holdings-driven scanner for generating weekly covered
call recommendations with:
- Portfolio holdings input with overwrite cap sizing
- Earnings week exclusion as hard gate
- Execution cost model with fees and slippage
- Delta-band risk profiles for weekly selection
- Tradability filters
- Broker checklist and LLM memo payload output

The scanner is designed for a broker-first workflow where the system generates
recommendations and the user executes trades manually at their broker.

Example:
    from src.scanning import OverlayScanner
    from src.models import PortfolioHolding, ScannerConfig

    holdings = [
        PortfolioHolding(symbol="AAPL", shares=500),
        PortfolioHolding(symbol="MSFT", shares=300),
    ]

    scanner = OverlayScanner(
        finnhub_client=finnhub_client,
        strike_optimizer=optimizer,
        config=ScannerConfig()
    )

    results = scanner.scan_portfolio(holdings, current_prices, options_chains, volatilities)
"""

from .scanner import OverlayScanner

# Re-export commonly used types from models for backward compatibility
from ..models import (
    DELTA_BAND_RANGES,
    BrokerChecklist,
    CandidateStrike,
    DeltaBand,
    ExecutionCostEstimate,
    LLMMemoPayload,
    PortfolioHolding,
    RejectionDetail,
    RejectionReason,
    ScannerConfig,
    ScanResult,
    SlippageModel,
)
from ..earnings_calendar import EarningsCalendar

__all__ = [
    "OverlayScanner",
    "EarningsCalendar",
    # Models (re-exported for convenience)
    "DeltaBand",
    "DELTA_BAND_RANGES",
    "SlippageModel",
    "RejectionReason",
    "RejectionDetail",
    "PortfolioHolding",
    "ScannerConfig",
    "ExecutionCostEstimate",
    "CandidateStrike",
    "BrokerChecklist",
    "LLMMemoPayload",
    "ScanResult",
]
