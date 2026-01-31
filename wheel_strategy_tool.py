#!/usr/bin/env python3
"""
Wheel Strategy Tool - CLI and Module for managing options wheel strategies.

This tool helps track and optimize the wheel strategy (selling puts and calls
in a cycle) across multiple symbols, with a bias toward premium collection
over assignment.

CLI Usage:
    wheel init AAPL --capital 10000 --profile conservative
    wheel recommend AAPL
    wheel record AAPL put --strike 145 --expiration 2025-02-21 --premium 1.50
    wheel expire AAPL --price 148.50
    wheel status AAPL
    wheel performance AAPL --export csv
    wheel list

Module Usage:
    from wheel_strategy_tool import WheelManager

    manager = WheelManager()
    manager.create_wheel("AAPL", capital=10000, profile="conservative")
    rec = manager.get_recommendation("AAPL")
    manager.record_trade("AAPL", "put", strike=145, expiration_date="2025-02-21", premium=1.50)
    manager.record_expiration("AAPL", price_at_expiry=148.50)
    perf = manager.get_performance("AAPL")

State Machine:
    CASH -> sell put -> CASH_PUT_OPEN -> expire OTM -> CASH (keep premium)
                                      -> assigned  -> SHARES (bought at strike)

    SHARES -> sell call -> SHARES_CALL_OPEN -> expire OTM -> SHARES (keep premium)
                                            -> called away -> CASH (sold at strike)

Premium is collected every time an option is sold. The bias strategy prefers
further OTM strikes and shorter expirations to maximize the chance of
keeping premium without assignment.
"""

from src.wheel import (
    VALID_TRANSITIONS,
    PositionSnapshot,
    PositionStatus,
    TradeOutcome,
    TradeRecord,
    WheelPerformance,
    WheelPosition,
    WheelRecommendation,
    WheelState,
    can_transition,
    get_next_state,
    get_valid_actions,
)
from src.wheel.manager import WheelManager

__all__ = [
    # Main class
    "WheelManager",
    # Data models
    "WheelPosition",
    "TradeRecord",
    "WheelRecommendation",
    "WheelPerformance",
    "PositionStatus",
    "PositionSnapshot",
    # State machine
    "WheelState",
    "TradeOutcome",
    "VALID_TRANSITIONS",
    "can_transition",
    "get_next_state",
    "get_valid_actions",
]


def main() -> None:
    """CLI entry point."""
    from src.wheel.cli import cli

    cli()


if __name__ == "__main__":
    main()
