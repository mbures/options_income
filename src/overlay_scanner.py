"""
Weekly Overlay Scanner - Backward compatibility shim.

This module maintains backward compatibility by re-exporting the scanner
from the src.scanning package. All new code should import from src.scanning.

Example:
    # Old (still works):
    from src.overlay_scanner import OverlayScanner

    # New (preferred):
    from src.scanning import OverlayScanner
"""

# Re-export everything from scanning package for backward compatibility
from .scanning import (
    DELTA_BAND_RANGES,
    BrokerChecklist,
    CandidateStrike,
    DeltaBand,
    EarningsCalendar,
    ExecutionCostEstimate,
    LLMMemoPayload,
    OverlayScanner,
    PortfolioHolding,
    RejectionDetail,
    RejectionReason,
    ScannerConfig,
    ScanResult,
    SlippageModel,
)

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
