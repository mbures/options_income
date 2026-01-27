"""
Click CLI implementation for the wheel strategy tool.

This module provides command-line interface commands for managing
wheel strategy positions.
"""

import logging
import sys
from typing import Optional

import click

from src.config import FinnhubConfig
from src.finnhub_client import FinnhubClient
from src.oauth.config import SchwabOAuthConfig
from src.oauth.coordinator import OAuthCoordinator
from src.price_fetcher import SchwabPriceDataFetcher
from src.schwab.client import SchwabClient

from .exceptions import (
    DuplicateSymbolError,
    InsufficientCapitalError,
    InvalidStateError,
    SymbolNotFoundError,
    TradeNotFoundError,
    WheelError,
)
from .manager import WheelManager
from .models import WheelPerformance, WheelPosition, WheelRecommendation
from .state import TradeOutcome

logger = logging.getLogger(__name__)


# Profile choices for CLI
PROFILE_CHOICES = ["aggressive", "moderate", "conservative", "defensive"]


def _get_manager(ctx: click.Context) -> WheelManager:
    """Get the WheelManager from context."""
    return ctx.obj["manager"]


def _print_error(message: str) -> None:
    """Print error message to stderr."""
    click.secho(f"Error: {message}", fg="red", err=True)


def _print_success(message: str) -> None:
    """Print success message."""
    click.secho(message, fg="green")


def _print_warning(message: str) -> None:
    """Print warning message."""
    click.secho(f"Warning: {message}", fg="yellow")


def _print_recommendation(rec: WheelRecommendation, verbose: bool = False) -> None:
    """Print a recommendation in a formatted way."""
    click.echo()
    click.secho(f"=== Recommendation for {rec.symbol} ===", bold=True)
    click.echo(f"Direction: SELL {rec.direction.upper()}")
    click.echo(f"Strike:    ${rec.strike:.2f}")
    click.echo(f"Expiration: {rec.expiration_date} ({rec.dte} DTE)")
    click.echo(f"Premium:   ${rec.premium_per_share:.2f}/share")
    click.echo(f"Contracts: {rec.contracts}")
    click.echo(f"Total:     ${rec.total_premium:.2f}")
    click.echo()
    click.echo(f"Sigma:     {rec.sigma_distance:.2f} sigma OTM")
    click.echo(f"P(ITM):    {rec.p_itm * 100:.1f}%")
    click.echo(f"Ann Yield: {rec.annualized_yield_pct:.1f}%")
    click.echo(f"Bias Score: {rec.bias_score:.2f}")

    if verbose:
        click.echo(f"Current Price: ${rec.current_price:.2f}")
        click.echo(f"Bid/Ask: ${rec.bid:.2f} / ${rec.ask:.2f}")
        click.echo(
            f"Effective {'cost' if rec.direction == 'put' else 'sale'}: "
            f"${rec.effective_yield_if_assigned:.2f}"
        )

    if rec.warnings:
        click.echo()
        click.secho("Warnings:", fg="yellow")
        for warning in rec.warnings:
            click.echo(f"  - {warning}")


def _print_status(wheel: WheelPosition, verbose: bool = False) -> None:
    """Print wheel status in a formatted way."""
    click.echo()
    click.secho(f"=== {wheel.symbol} ===", bold=True)
    click.echo(f"State:   {wheel.state.value}")
    click.echo(f"Profile: {wheel.profile.value}")
    click.echo(f"Capital: ${wheel.capital_allocated:,.2f}")

    if wheel.shares_held > 0:
        click.echo(f"Shares:  {wheel.shares_held}")
        if wheel.cost_basis:
            click.echo(f"Cost Basis: ${wheel.cost_basis:.2f}")

    if verbose:
        click.echo(f"Created: {wheel.created_at.strftime('%Y-%m-%d %H:%M')}")
        click.echo(f"Updated: {wheel.updated_at.strftime('%Y-%m-%d %H:%M')}")

    # Show available actions
    if wheel.can_sell_put:
        click.echo("Action: Ready to sell puts")
    elif wheel.can_sell_call:
        click.echo("Action: Ready to sell calls")
    elif wheel.has_open_position:
        click.echo("Action: Awaiting expiration")


def _print_performance(perf: WheelPerformance, verbose: bool = False) -> None:
    """Print performance metrics in a formatted way."""
    click.echo()
    click.secho(f"=== Performance: {perf.symbol} ===", bold=True)
    click.echo(f"Total Premium:    ${perf.total_premium:,.2f}")
    click.echo(f"Total Trades:     {perf.total_trades}")
    click.echo(f"Win Rate:         {perf.win_rate_pct:.1f}%")
    click.echo()
    click.echo(f"Puts Sold:        {perf.puts_sold}")
    click.echo(f"Calls Sold:       {perf.calls_sold}")
    click.echo(f"Assignments:      {perf.assignment_events}")
    click.echo(f"Called Away:      {perf.called_away_events}")

    if verbose:
        click.echo()
        click.echo(f"Open Trades:      {perf.open_trades}")
        click.echo(f"Avg Days Held:    {perf.average_days_held:.1f}")
        click.echo(f"Ann. Yield:       {perf.annualized_yield_pct:.1f}%")
        click.echo(f"Current State:    {perf.current_state.value}")
        if perf.current_shares > 0:
            click.echo(f"Current Shares:   {perf.current_shares}")
            if perf.current_cost_basis:
                click.echo(f"Cost Basis:       ${perf.current_cost_basis:.2f}")


@click.group()
@click.option(
    "--db",
    default="~/.wheel_strategy/trades.db",
    help="Database file path",
    envvar="WHEEL_DB_PATH",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--json", "output_json", is_flag=True, help="JSON output (where supported)")
@click.pass_context
def cli(ctx: click.Context, db: str, verbose: bool, output_json: bool) -> None:
    """
    Wheel Strategy Tool - Manage options wheel positions.

    Track and optimize your wheel strategy across multiple symbols.
    Biases toward premium collection over assignment.
    """
    ctx.ensure_object(dict)

    # Load API configurations
    finnhub_client = None
    price_fetcher = None
    schwab_client = None

    # Initialize Schwab client (required for price and options data)
    try:
        # Try loading credentials from file first, then environment
        try:
            oauth_config = SchwabOAuthConfig.from_file()
            if verbose:
                click.echo("+ Schwab credentials loaded from config/charles_schwab_key.txt")
        except FileNotFoundError:
            oauth_config = SchwabOAuthConfig.from_env()
            if verbose:
                click.echo("+ Schwab credentials loaded from environment")

        oauth = OAuthCoordinator(config=oauth_config)
        schwab_client = SchwabClient(oauth_coordinator=oauth)
        price_fetcher = SchwabPriceDataFetcher(schwab_client, enable_cache=True)
        if verbose:
            click.echo("+ Schwab client configured for price and options data")
    except Exception as e:
        click.echo(f"Error: Schwab client initialization failed: {e}", err=True)
        click.echo("Please run: python scripts/authorize_schwab_host.py", err=True)
        sys.exit(1)

    # Initialize Finnhub client for earnings calendar (optional)
    try:
        finnhub_config = FinnhubConfig.from_file()
        finnhub_client = FinnhubClient(finnhub_config)
        if verbose:
            click.echo("+ Finnhub client configured (earnings calendar)")
    except (FileNotFoundError, ValueError) as e:
        if verbose:
            click.echo(f"! Finnhub not configured: {e}", err=True)
            click.echo("  Earnings calendar features will be disabled")

    # Initialize WheelManager with configured clients
    ctx.obj["manager"] = WheelManager(
        db_path=db,
        finnhub_client=finnhub_client,
        price_fetcher=price_fetcher,
        schwab_client=schwab_client,
    )
    ctx.obj["verbose"] = verbose
    ctx.obj["json"] = output_json


@cli.command()
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
    manager = _get_manager(ctx)

    # Validate inputs
    if shares is not None and cost_basis is None:
        _print_error("--cost-basis is required when --shares is specified")
        sys.exit(1)

    if shares is None and capital is None:
        _print_error("Must specify --capital and/or --shares")
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
            _print_success(
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
            _print_success(
                f"Created wheel for {wheel.symbol} with ${capital:,.2f} capital"
            )
            click.echo(f"Profile: {profile}")
            click.echo(f"State: {wheel.state.value}")
            click.echo(f"Ready to sell puts (use 'wheel recommend {wheel.symbol}')")
    except DuplicateSymbolError as e:
        _print_error(str(e))
        sys.exit(1)
    except ValueError as e:
        _print_error(str(e))
        sys.exit(1)


@cli.command("import")
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
    manager = _get_manager(ctx)

    try:
        wheel = manager.import_shares(
            symbol=symbol.upper(),
            shares=shares,
            cost_basis=cost_basis,
            capital=capital,
            profile=profile,
        )
        _print_success(f"Imported {shares} shares of {wheel.symbol} @ ${cost_basis:.2f}")
        click.echo(f"State: {wheel.state.value}")
        click.echo(f"Ready to sell calls (use 'wheel recommend {wheel.symbol}')")
    except (DuplicateSymbolError, ValueError) as e:
        _print_error(str(e))
        sys.exit(1)


@cli.command()
@click.argument("symbol", required=False)
@click.option("--all", "all_symbols", is_flag=True, help="All active wheels")
@click.pass_context
def recommend(ctx: click.Context, symbol: Optional[str], all_symbols: bool) -> None:
    """
    Get recommendation for next option to sell.

    Example: wheel recommend AAPL
    """
    manager = _get_manager(ctx)
    verbose = ctx.obj["verbose"]

    if all_symbols:
        recs = manager.get_all_recommendations()
        if not recs:
            click.echo("No recommendations available. All wheels have open positions.")
            return
        for rec in recs:
            _print_recommendation(rec, verbose)
    elif symbol:
        try:
            rec = manager.get_recommendation(symbol.upper())
            _print_recommendation(rec, verbose)
        except SymbolNotFoundError as e:
            _print_error(str(e))
            sys.exit(1)
        except InvalidStateError as e:
            _print_error(str(e))
            sys.exit(1)
        except WheelError as e:
            _print_error(str(e))
            sys.exit(1)
    else:
        _print_error("Provide SYMBOL or --all")
        sys.exit(1)


@cli.command()
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
    manager = _get_manager(ctx)

    try:
        trade = manager.record_trade(
            symbol=symbol.upper(),
            direction=direction,
            strike=strike,
            expiration_date=expiration,
            premium=premium,
            contracts=contracts,
        )
        _print_success(
            f"Recorded: SELL {contracts}x {symbol.upper()} ${strike} {direction.upper()}"
        )
        click.echo(f"Premium collected: ${trade.total_premium:.2f} (${premium:.2f}/share)")
        click.echo(f"Expiration: {expiration}")
    except (SymbolNotFoundError, InvalidStateError, InsufficientCapitalError) as e:
        _print_error(str(e))
        sys.exit(1)


@cli.command()
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
    manager = _get_manager(ctx)

    try:
        outcome = manager.record_expiration(symbol.upper(), price)
        wheel = manager.get_wheel(symbol.upper())

        if outcome == TradeOutcome.EXPIRED_WORTHLESS:
            _print_success("Option EXPIRED WORTHLESS - premium kept!")
        elif outcome == TradeOutcome.ASSIGNED:
            _print_warning(
                f"PUT ASSIGNED - bought {wheel.shares_held} shares @ ${wheel.cost_basis:.2f}"
            )
        elif outcome == TradeOutcome.CALLED_AWAY:
            _print_warning("CALL EXERCISED - sold shares, received cash")

        click.echo(f"New state: {wheel.state.value}")
    except (SymbolNotFoundError, TradeNotFoundError, InvalidStateError) as e:
        _print_error(str(e))
        sys.exit(1)


@cli.command()
@click.argument("symbol")
@click.option("--price", required=True, type=float, help="Price to buy back ($)")
@click.pass_context
def close(ctx: click.Context, symbol: str, price: float) -> None:
    """
    Close an open trade early (buy back the option).

    Example: wheel close AAPL --price 0.50
    """
    manager = _get_manager(ctx)

    try:
        trade = manager.close_trade_early(symbol.upper(), price)
        net = trade.net_premium
        _print_success(f"Closed {symbol.upper()} trade early")
        click.echo(f"Buy-back price: ${price:.2f}/share")
        click.echo(f"Net premium: ${net:.2f}")
    except (SymbolNotFoundError, TradeNotFoundError) as e:
        _print_error(str(e))
        sys.exit(1)


@cli.command()
@click.argument("symbol", required=False)
@click.option("--all", "all_symbols", is_flag=True, help="All active wheels")
@click.pass_context
def status(ctx: click.Context, symbol: Optional[str], all_symbols: bool) -> None:
    """
    View current wheel status.

    Example: wheel status AAPL
    """
    manager = _get_manager(ctx)
    verbose = ctx.obj["verbose"]

    if all_symbols:
        wheels = manager.list_wheels()
        if not wheels:
            click.echo("No active wheels. Use 'wheel init SYMBOL --capital N' to start.")
            return
        for wheel in wheels:
            _print_status(wheel, verbose)
    elif symbol:
        wheel = manager.get_wheel(symbol.upper())
        if wheel:
            _print_status(wheel, verbose)

            # Show open trade if any
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
            _print_error(f"No wheel found for {symbol.upper()}")
            sys.exit(1)
    else:
        _print_error("Provide SYMBOL or --all")
        sys.exit(1)


@cli.command()
@click.argument("symbol", required=False)
@click.option("--all", "all_symbols", is_flag=True, help="All wheels")
@click.option("--export", type=click.Choice(["csv", "json"]), help="Export format")
@click.pass_context
def performance(
    ctx: click.Context, symbol: Optional[str], all_symbols: bool, export: Optional[str]
) -> None:
    """
    View performance metrics.

    Example: wheel performance AAPL --export csv
    """
    manager = _get_manager(ctx)
    verbose = ctx.obj["verbose"]

    if export:
        # Export mode
        data = manager.export_trades(symbol if not all_symbols else None, format=export)
        click.echo(data)
    elif all_symbols:
        perf = manager.get_portfolio_performance()
        _print_performance(perf, verbose)
    elif symbol:
        perf = manager.get_performance(symbol.upper())
        _print_performance(perf, verbose)
    else:
        _print_error("Provide SYMBOL or --all")
        sys.exit(1)


@cli.command("list")
@click.pass_context
def list_wheels(ctx: click.Context) -> None:
    """
    List all wheel positions.

    Example: wheel list
    """
    manager = _get_manager(ctx)
    wheels = manager.list_wheels()

    if not wheels:
        click.echo("No active wheels. Use 'wheel init SYMBOL --capital N' to start.")
        return

    # Print header
    click.echo()
    click.echo(
        f"{'Symbol':<8} {'State':<20} {'Capital':>12} {'Shares':>8} {'Profile':<12}"
    )
    click.echo("-" * 70)

    # Print each wheel
    for w in wheels:
        click.echo(
            f"{w.symbol:<8} {w.state.value:<20} "
            f"${w.capital_allocated:>10,.2f} {w.shares_held:>8} "
            f"{w.profile.value:<12}"
        )


@cli.command()
@click.argument("symbol")
@click.pass_context
def archive(ctx: click.Context, symbol: str) -> None:
    """
    Archive/close a wheel position.

    Cannot archive if there's an open trade.

    Example: wheel archive AAPL
    """
    manager = _get_manager(ctx)

    try:
        manager.close_wheel(symbol.upper())
        _print_success(f"Archived wheel for {symbol.upper()}")
    except (SymbolNotFoundError, InvalidStateError) as e:
        _print_error(str(e))
        sys.exit(1)


@cli.command()
@click.argument("symbol")
@click.option(
    "--profile",
    required=True,
    type=click.Choice(PROFILE_CHOICES),
    help="New risk profile",
)
@click.pass_context
def update(ctx: click.Context, symbol: str, profile: str) -> None:
    """
    Update wheel settings.

    Example: wheel update AAPL --profile moderate
    """
    manager = _get_manager(ctx)

    try:
        wheel = manager.update_profile(symbol.upper(), profile)
        _print_success(f"Updated {symbol.upper()} profile to {profile}")
    except (SymbolNotFoundError, ValueError) as e:
        _print_error(str(e))
        sys.exit(1)


@cli.command()
@click.argument("symbol")
@click.pass_context
def history(ctx: click.Context, symbol: str) -> None:
    """
    View trade history for a symbol.

    Example: wheel history AAPL
    """
    manager = _get_manager(ctx)

    trades = manager.get_trade_history(symbol.upper())

    if not trades:
        click.echo(f"No trades found for {symbol.upper()}")
        return

    click.echo()
    click.secho(f"=== Trade History: {symbol.upper()} ===", bold=True)
    click.echo()

    for trade in trades:
        status_icon = {
            TradeOutcome.OPEN: "[OPEN]",
            TradeOutcome.EXPIRED_WORTHLESS: "[WIN]",
            TradeOutcome.ASSIGNED: "[ASSIGNED]",
            TradeOutcome.CALLED_AWAY: "[CALLED]",
            TradeOutcome.CLOSED_EARLY: "[CLOSED]",
        }.get(trade.outcome, "[?]")

        click.echo(
            f"{trade.opened_at.strftime('%Y-%m-%d')} "
            f"{trade.direction.upper():4} ${trade.strike:7.2f} "
            f"exp {trade.expiration_date} "
            f"${trade.total_premium:7.2f} "
            f"{status_icon}"
        )


def main() -> None:
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
