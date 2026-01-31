"""
Position management commands for the wheel CLI.

This module provides commands for initializing, importing, and viewing
wheel positions.
"""

import sys
from typing import Optional

import click

from ..exceptions import DuplicateSymbolError
from .utils import (
    get_manager,
    print_error,
    print_status,
    print_status_with_monitoring,
    print_success,
)

# Profile choices for CLI
PROFILE_CHOICES = ["aggressive", "moderate", "conservative", "defensive"]


@click.command()
@click.argument("symbol")
@click.option("--capital", type=float, help="Capital allocation for selling puts ($)")
@click.option("--shares", type=int, help="Number of shares owned (for selling calls)")
@click.option("--cost-basis", type=float, help="Cost per share ($) - required with --shares")
@click.option(
    "--profile",
    default="conservative",
    type=click.Choice(PROFILE_CHOICES),
    help="Risk profile",
)
@click.pass_context
def init(
    ctx: click.Context,
    symbol: str,
    capital: float,
    shares: int,
    cost_basis: float,
    profile: str,
) -> None:
    """
    Initialize a new wheel position.

    Start with CASH (to sell puts) or SHARES (to sell calls).

    \b
    Examples:
      wheel init AAPL --capital 15000           # Start with cash, sell puts
      wheel init AAPL --shares 200 --cost-basis 150  # Start with shares, sell calls
      wheel init AAPL --capital 10000 --shares 100 --cost-basis 145  # Both
    """
    manager = get_manager(ctx)

    # Validate inputs
    if shares is not None and cost_basis is None:
        print_error("--cost-basis is required when --shares is specified")
        sys.exit(1)

    if shares is None and capital is None:
        print_error("Must specify --capital and/or --shares")
        sys.exit(1)

    try:
        if shares is not None and shares > 0:
            # Start with shares (SHARES state) - can sell calls
            wheel = manager.import_shares(
                symbol=symbol.upper(),
                shares=shares,
                cost_basis=cost_basis,
                capital=capital or 0.0,
                profile=profile,
            )
            print_success(
                f"Created wheel for {wheel.symbol} with {shares} shares @ ${cost_basis:.2f}"
            )
            if capital:
                click.echo(f"Additional capital: ${capital:,.2f}")
            click.echo(f"Profile: {profile}")
            click.echo(f"State: {wheel.state.value}")
            click.echo(f"Ready to sell calls (use 'wheel recommend {wheel.symbol}')")
        else:
            # Start with cash only (CASH state) - can sell puts
            wheel = manager.create_wheel(
                symbol=symbol.upper(),
                capital=capital,
                profile=profile,
            )
            print_success(
                f"Created wheel for {wheel.symbol} with ${capital:,.2f} capital"
            )
            click.echo(f"Profile: {profile}")
            click.echo(f"State: {wheel.state.value}")
            click.echo(f"Ready to sell puts (use 'wheel recommend {wheel.symbol}')")
    except DuplicateSymbolError as e:
        print_error(str(e))
        sys.exit(1)
    except ValueError as e:
        print_error(str(e))
        sys.exit(1)


@click.command("import")
@click.argument("symbol")
@click.option("--shares", required=True, type=int, help="Number of shares")
@click.option("--cost-basis", required=True, type=float, help="Cost per share ($)")
@click.option("--capital", default=0.0, type=float, help="Additional capital ($)")
@click.option(
    "--profile",
    default="conservative",
    type=click.Choice(PROFILE_CHOICES),
    help="Risk profile",
)
@click.pass_context
def import_shares(
    ctx: click.Context,
    symbol: str,
    shares: int,
    cost_basis: float,
    capital: float,
    profile: str,
) -> None:
    """
    Import existing shares to start selling calls.

    Starts in SHARES state, ready to sell covered calls.

    Example: wheel import AAPL --shares 200 --cost-basis 150.00
    """
    manager = get_manager(ctx)

    try:
        wheel = manager.import_shares(
            symbol=symbol.upper(),
            shares=shares,
            cost_basis=cost_basis,
            capital=capital,
            profile=profile,
        )
        print_success(f"Imported {shares} shares of {wheel.symbol} @ ${cost_basis:.2f}")
        click.echo(f"State: {wheel.state.value}")
        click.echo(f"Ready to sell calls (use 'wheel recommend {wheel.symbol}')")
    except (DuplicateSymbolError, ValueError) as e:
        print_error(str(e))
        sys.exit(1)


@click.command("list")
@click.option("--refresh", is_flag=True, help="Force fresh data from API")
@click.pass_context
def list_wheels(ctx: click.Context, refresh: bool) -> None:
    """
    List all wheel positions with live monitoring data.

    Shows DTE, moneyness, and risk for open positions.

    Example: wheel list --refresh
    """
    manager = get_manager(ctx)

    # Get all positions
    all_wheels = manager.list_wheels()

    if not all_wheels:
        click.echo("No active wheels. Use 'wheel init SYMBOL --capital N' to start.")
        return

    # Get monitoring data for open positions
    open_positions = manager.get_all_positions_status(force_refresh=refresh)
    status_map = {pos.symbol: (trade, status) for pos, trade, status in open_positions}

    # Table header
    click.echo()
    click.echo(
        f"{'Symbol':<8} {'State':<20} {'Strike':>8} {'Current':>8} "
        f"{'DTE':>12} {'Moneyness':>12} {'Risk':>6}"
    )
    click.echo("=" * 85)

    for wheel in all_wheels:
        # Basic info
        row = f"{wheel.symbol:<8} {wheel.state.value:<20}"

        # If has open position, add monitoring data
        if wheel.symbol in status_map:
            trade, status = status_map[wheel.symbol]
            row += f" ${trade.strike:>7.2f} ${status.current_price:>7.2f}"
            row += f" {status.dte_calendar:>3}d ({status.dte_trading:>2}t)"
            row += f" {status.moneyness_label:>12}"
            row += f" {status.risk_icon} {status.risk_level:>3}"
        else:
            # No open position
            row += f" {'---':>8} {'---':>8} {'---':>12} {'---':>12} {'---':>6}"

        click.echo(row)

    # Summary
    click.echo()
    click.echo(f"Total wheels: {len(all_wheels)}")
    click.echo(f"Open positions: {len(open_positions)}")

    high_risk = sum(1 for _, _, s in open_positions if s.risk_level == "HIGH")
    if high_risk > 0:
        click.echo()
        click.secho(f"⚠️  {high_risk} position(s) at HIGH RISK (ITM)", fg="red", bold=True)


@click.command()
@click.argument("symbol", required=False)
@click.option("--all", "all_symbols", is_flag=True, help="All active wheels")
@click.option("--refresh", is_flag=True, help="Force fresh data from API")
@click.pass_context
def status(
    ctx: click.Context, symbol: Optional[str], all_symbols: bool, refresh: bool
) -> None:
    """
    View current wheel status with live monitoring data.

    Shows real-time data including DTE, moneyness, and risk level for open positions.

    Example: wheel status AAPL --refresh
    """
    manager = get_manager(ctx)
    verbose = ctx.obj["verbose"]

    if all_symbols:
        # Get all positions with monitoring data
        results = manager.get_all_positions_status(force_refresh=refresh)

        if not results:
            wheels = manager.list_wheels()
            if not wheels:
                click.echo("No active wheels. Use 'wheel init SYMBOL --capital N' to start.")
                return
            # Show wheels without monitoring data
            for wheel in wheels:
                print_status(wheel, verbose)
                click.echo()
        else:
            for position, trade, mon_status in results:
                print_status_with_monitoring(position, trade, mon_status, verbose)
                click.echo()

    elif symbol:
        wheel = manager.get_wheel(symbol.upper())
        if not wheel:
            print_error(f"No wheel found for {symbol.upper()}")
            sys.exit(1)

        # Try to get monitoring status
        mon_status = manager.get_position_status(symbol.upper(), force_refresh=refresh)

        if mon_status:
            # Position has open trade - show with monitoring data
            trade = manager.get_open_trade(symbol.upper())
            print_status_with_monitoring(wheel, trade, mon_status, verbose)
        else:
            # No open position - show basic status
            print_status(wheel, verbose)

            # Check if there's a closed trade to show
            trade = manager.get_open_trade(symbol.upper())
            if trade:
                click.echo()
                click.secho("Open Trade:", bold=True)
                click.echo(
                    f"  {trade.direction.upper()} ${trade.strike} "
                    f"exp {trade.expiration_date}"
                )
                click.echo(f"  Premium: ${trade.total_premium:.2f}")
    else:
        print_error("Provide SYMBOL or --all")
        sys.exit(1)
