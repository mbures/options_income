"""
Trade execution commands for the wheel CLI.

This module provides commands for recording trades, expirations,
and early closures.
"""

import sys

import click

from ..exceptions import (
    InsufficientCapitalError,
    InvalidStateError,
    SymbolNotFoundError,
    TradeNotFoundError,
)
from ..state import TradeOutcome
from .utils import get_manager, print_error, print_success, print_warning


@click.command()
@click.argument("symbol")
@click.argument("direction", type=click.Choice(["put", "call"]))
@click.option("--strike", required=True, type=float, help="Strike price ($)")
@click.option("--expiration", required=True, help="Expiration date (YYYY-MM-DD)")
@click.option("--premium", required=True, type=float, help="Premium per share ($)")
@click.option("--contracts", default=1, type=int, help="Number of contracts")
@click.pass_context
def record(
    ctx: click.Context,
    symbol: str,
    direction: str,
    strike: float,
    expiration: str,
    premium: float,
    contracts: int,
) -> None:
    """
    Record a sold option (collect premium).

    Example: wheel record AAPL put --strike 145 --expiration 2025-02-21 --premium 1.50
    """
    manager = get_manager(ctx)

    try:
        trade = manager.record_trade(
            symbol=symbol.upper(),
            direction=direction,
            strike=strike,
            expiration_date=expiration,
            premium=premium,
            contracts=contracts,
        )
        print_success(
            f"Recorded: SELL {contracts}x {symbol.upper()} ${strike} {direction.upper()}"
        )
        click.echo(f"Premium collected: ${trade.total_premium:.2f} (${premium:.2f}/share)")
        click.echo(f"Expiration: {expiration}")
    except (SymbolNotFoundError, InvalidStateError, InsufficientCapitalError) as e:
        print_error(str(e))
        sys.exit(1)


@click.command()
@click.argument("symbol")
@click.option(
    "--price", required=True, type=float, help="Stock price at expiration ($)"
)
@click.pass_context
def expire(ctx: click.Context, symbol: str, price: float) -> None:
    """
    Record expiration outcome.

    Determines if assigned/exercised or expired worthless based on price vs strike.

    Example: wheel expire AAPL --price 148.50
    """
    manager = get_manager(ctx)

    try:
        outcome = manager.record_expiration(symbol.upper(), price)
        wheel = manager.get_wheel(symbol.upper())

        if outcome == TradeOutcome.EXPIRED_WORTHLESS:
            print_success("Option EXPIRED WORTHLESS - premium kept!")
        elif outcome == TradeOutcome.ASSIGNED:
            print_warning(
                f"PUT ASSIGNED - bought {wheel.shares_held} shares @ ${wheel.cost_basis:.2f}"
            )
        elif outcome == TradeOutcome.CALLED_AWAY:
            print_warning("CALL EXERCISED - sold shares, received cash")

        click.echo(f"New state: {wheel.state.value}")
    except (SymbolNotFoundError, TradeNotFoundError, InvalidStateError) as e:
        print_error(str(e))
        sys.exit(1)


@click.command()
@click.argument("symbol")
@click.option("--price", required=True, type=float, help="Price to buy back ($)")
@click.pass_context
def close(ctx: click.Context, symbol: str, price: float) -> None:
    """
    Close an open trade early (buy back the option).

    Example: wheel close AAPL --price 0.50
    """
    manager = get_manager(ctx)

    try:
        trade = manager.close_trade_early(symbol.upper(), price)
        net = trade.net_premium
        print_success(f"Closed {symbol.upper()} trade early")
        click.echo(f"Buy-back price: ${price:.2f}/share")
        click.echo(f"Net premium: ${net:.2f}")
    except (SymbolNotFoundError, TradeNotFoundError) as e:
        print_error(str(e))
        sys.exit(1)


@click.command()
@click.argument("symbol")
@click.pass_context
def archive(ctx: click.Context, symbol: str) -> None:
    """
    Archive/close a wheel position.

    Cannot archive if there's an open trade.

    Example: wheel archive AAPL
    """
    manager = get_manager(ctx)

    try:
        manager.close_wheel(symbol.upper())
        print_success(f"Archived wheel for {symbol.upper()}")
    except (SymbolNotFoundError, InvalidStateError) as e:
        print_error(str(e))
        sys.exit(1)
