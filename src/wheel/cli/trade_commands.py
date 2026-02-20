"""
Trade execution commands for the wheel CLI.

This module provides commands for recording trades, expirations,
and early closures.
"""

import sys

import click

from ..api_client import APIConnectionError, APIError, APIValidationError
from ..exceptions import (
    InsufficientCapitalError,
    InvalidStateError,
    SymbolNotFoundError,
    TradeNotFoundError,
)
from ..state import TradeOutcome
from .utils import get_cli_context, get_manager, print_error, print_success, print_warning


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
    cli_ctx = get_cli_context(ctx)
    manager = get_manager(ctx)

    symbol_upper = symbol.upper()

    # Try API mode first, fall back to direct mode
    if cli_ctx.mode == "api" and cli_ctx.api_client:
        try:
            # Get wheel by symbol
            wheel = cli_ctx.api_client.get_wheel_by_symbol(symbol_upper)
            if not wheel:
                print_error(f"No wheel found for {symbol_upper}")
                sys.exit(1)

            # Record trade via API
            trade_resp = cli_ctx.api_client.record_trade(
                wheel_id=wheel.id,
                direction=direction,
                strike=strike,
                expiration=expiration,
                premium=premium,
                contracts=contracts,
            )

            print_success(
                f"Recorded: SELL {contracts}x {symbol_upper} ${strike} {direction.upper()}"
            )
            click.echo(f"Premium collected: ${trade_resp.total_premium:.2f} (${premium:.2f}/share)")
            click.echo(f"Expiration: {expiration}")

        except APIConnectionError as e:
            # Fall back to direct mode
            if cli_ctx.verbose:
                click.echo(f"! API unavailable, using direct mode: {e}", err=True)
            _record_trade_direct_mode(manager, symbol_upper, direction, strike, expiration, premium, contracts)
        except APIValidationError as e:
            print_error(f"Validation error: {e.detail}")
            sys.exit(1)
        except APIError as e:
            print_error(str(e))
            sys.exit(1)
    else:
        # Direct mode
        _record_trade_direct_mode(manager, symbol_upper, direction, strike, expiration, premium, contracts)


def _record_trade_direct_mode(manager, symbol: str, direction: str, strike: float, expiration: str, premium: float, contracts: int):
    """Handle trade recording in direct mode.

    Args:
        manager: WheelManager instance
        symbol: Stock symbol
        direction: Trade direction (put or call)
        strike: Strike price
        expiration: Expiration date
        premium: Premium per share
        contracts: Number of contracts
    """
    try:
        trade = manager.record_trade(
            symbol=symbol,
            direction=direction,
            strike=strike,
            expiration_date=expiration,
            premium=premium,
            contracts=contracts,
        )
        print_success(
            f"Recorded: SELL {contracts}x {symbol} ${strike} {direction.upper()}"
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
    cli_ctx = get_cli_context(ctx)
    manager = get_manager(ctx)

    symbol_upper = symbol.upper()

    # Try API mode first, fall back to direct mode
    if cli_ctx.mode == "api" and cli_ctx.api_client:
        try:
            # Get wheel by symbol
            wheel = cli_ctx.api_client.get_wheel_by_symbol(symbol_upper)
            if not wheel:
                print_error(f"No wheel found for {symbol_upper}")
                sys.exit(1)

            # Get open trades
            trades = cli_ctx.api_client.list_trades(wheel.id, outcome="open")
            if not trades:
                print_error(f"No open trade found for {symbol_upper}")
                sys.exit(1)

            trade = trades[0]

            # Expire trade via API
            trade_resp = cli_ctx.api_client.expire_trade(trade.id, price)

            # Get updated wheel state
            wheel = cli_ctx.api_client.get_wheel(wheel.id)

            # Determine outcome and display message
            if trade_resp.outcome == "expired_worthless":
                print_success("Option EXPIRED WORTHLESS - premium kept!")
            elif trade_resp.outcome == "assigned":
                print_warning(
                    f"PUT ASSIGNED - bought {wheel.shares_held or 0} shares @ ${wheel.cost_basis:.2f}"
                )
            elif trade_resp.outcome == "called_away":
                print_warning("CALL EXERCISED - sold shares, received cash")

            click.echo(f"New state: {wheel.state}")

        except APIConnectionError as e:
            # Fall back to direct mode
            if cli_ctx.verbose:
                click.echo(f"! API unavailable, using direct mode: {e}", err=True)
            _expire_trade_direct_mode(manager, symbol_upper, price)
        except APIError as e:
            print_error(str(e))
            sys.exit(1)
    else:
        # Direct mode
        _expire_trade_direct_mode(manager, symbol_upper, price)


def _expire_trade_direct_mode(manager, symbol: str, price: float):
    """Handle trade expiration in direct mode.

    Args:
        manager: WheelManager instance
        symbol: Stock symbol
        price: Price at expiration
    """
    try:
        outcome = manager.record_expiration(symbol, price)
        wheel = manager.get_wheel(symbol)

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
    cli_ctx = get_cli_context(ctx)
    manager = get_manager(ctx)

    symbol_upper = symbol.upper()

    # Try API mode first, fall back to direct mode
    if cli_ctx.mode == "api" and cli_ctx.api_client:
        try:
            # Get wheel by symbol
            wheel = cli_ctx.api_client.get_wheel_by_symbol(symbol_upper)
            if not wheel:
                print_error(f"No wheel found for {symbol_upper}")
                sys.exit(1)

            # Get open trades
            trades = cli_ctx.api_client.list_trades(wheel.id, outcome="open")
            if not trades:
                print_error(f"No open trade found for {symbol_upper}")
                sys.exit(1)

            trade = trades[0]

            # Close trade via API
            trade_resp = cli_ctx.api_client.close_trade(trade.id, price)

            net = trade_resp.net_premium or 0.0
            print_success(f"Closed {symbol_upper} trade early")
            click.echo(f"Buy-back price: ${price:.2f}/share")
            click.echo(f"Net premium: ${net:.2f}")

        except APIConnectionError as e:
            # Fall back to direct mode
            if cli_ctx.verbose:
                click.echo(f"! API unavailable, using direct mode: {e}", err=True)
            _close_trade_direct_mode(manager, symbol_upper, price)
        except APIError as e:
            print_error(str(e))
            sys.exit(1)
    else:
        # Direct mode
        _close_trade_direct_mode(manager, symbol_upper, price)


def _close_trade_direct_mode(manager, symbol: str, price: float):
    """Handle trade closure in direct mode.

    Args:
        manager: WheelManager instance
        symbol: Stock symbol
        price: Close price
    """
    try:
        trade = manager.close_trade_early(symbol, price)
        net = trade.net_premium
        print_success(f"Closed {symbol} trade early")
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
    cli_ctx = get_cli_context(ctx)
    manager = get_manager(ctx)

    symbol_upper = symbol.upper()

    # Try API mode first, fall back to direct mode
    if cli_ctx.mode == "api" and cli_ctx.api_client:
        try:
            # Get wheel by symbol
            wheel = cli_ctx.api_client.get_wheel_by_symbol(symbol_upper)
            if not wheel:
                print_error(f"No wheel found for {symbol_upper}")
                sys.exit(1)

            # Check if there are open trades
            trades = cli_ctx.api_client.list_trades(wheel.id, outcome="open")
            if trades:
                print_error("Cannot archive wheel with open trades. Close or expire trades first.")
                sys.exit(1)

            # Delete wheel via API
            cli_ctx.api_client.delete_wheel(wheel.id)
            print_success(f"Archived wheel for {symbol_upper}")

        except APIConnectionError as e:
            # Fall back to direct mode
            if cli_ctx.verbose:
                click.echo(f"! API unavailable, using direct mode: {e}", err=True)
            _archive_wheel_direct_mode(manager, symbol_upper)
        except APIError as e:
            print_error(str(e))
            sys.exit(1)
    else:
        # Direct mode
        _archive_wheel_direct_mode(manager, symbol_upper)


def _archive_wheel_direct_mode(manager, symbol: str):
    """Handle wheel archival in direct mode.

    Args:
        manager: WheelManager instance
        symbol: Stock symbol
    """
    try:
        manager.close_wheel(symbol)
        print_success(f"Archived wheel for {symbol}")
    except (SymbolNotFoundError, InvalidStateError) as e:
        print_error(str(e))
        sys.exit(1)
