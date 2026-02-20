"""
Position management commands for the wheel CLI.

This module provides commands for initializing, importing, and viewing
wheel positions.
"""

import sys
from typing import Optional

import click

from ..api_client import APIConnectionError, APIError, APIValidationError
from ..exceptions import DuplicateSymbolError
from .utils import (
    get_cli_context,
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
@click.option(
    "--portfolio",
    help="Portfolio ID (uses default from config if not specified)",
)
@click.pass_context
def init(
    ctx: click.Context,
    symbol: str,
    capital: float,
    shares: int,
    cost_basis: float,
    profile: str,
    portfolio: Optional[str],
) -> None:
    """
    Initialize a new wheel position.

    Start with CASH (to sell puts) or SHARES (to sell calls).

    \b
    Examples:
      wheel init AAPL --capital 15000           # Start with cash, sell puts
      wheel init AAPL --shares 200 --cost-basis 150  # Start with shares, sell calls
      wheel init AAPL --capital 10000 --shares 100 --cost-basis 145  # Both
      wheel init AAPL --capital 15000 --portfolio <ID>  # Specify portfolio
    """
    cli_ctx = get_cli_context(ctx)
    manager = get_manager(ctx)

    # Validate inputs
    if shares is not None and cost_basis is None:
        print_error("--cost-basis is required when --shares is specified")
        sys.exit(1)

    if shares is None and capital is None:
        print_error("Must specify --capital and/or --shares")
        sys.exit(1)

    symbol_upper = symbol.upper()

    # Try API mode first, fall back to direct mode
    if cli_ctx.mode == "api" and cli_ctx.api_client:
        try:
            # Determine portfolio ID
            portfolio_id = portfolio or cli_ctx.config.default_portfolio_id

            if not portfolio_id:
                # Need to get or create a default portfolio
                portfolios = cli_ctx.api_client.list_portfolios()
                if portfolios:
                    portfolio_id = portfolios[0].id
                    if cli_ctx.verbose:
                        click.echo(f"+ Using portfolio: {portfolios[0].name}")
                else:
                    # Create default portfolio
                    new_portfolio = cli_ctx.api_client.create_portfolio(
                        name="Default Portfolio",
                        description="Auto-created default portfolio"
                    )
                    portfolio_id = new_portfolio.id
                    if cli_ctx.verbose:
                        click.echo(f"+ Created default portfolio: {new_portfolio.name}")

            # Create wheel via API
            # Note: API doesn't support importing shares in create_wheel yet
            # So we'll create and then handle shares if needed
            wheel_response = cli_ctx.api_client.create_wheel(
                portfolio_id=portfolio_id,
                symbol=symbol_upper,
                capital=capital or 0.0,
                profile=profile,
            )

            # If shares were specified, we need to update the wheel
            # This is a limitation - the API should support this in create
            # For now, display success for cash-only creation
            if shares is not None and shares > 0:
                print_success(
                    f"Created wheel for {symbol_upper} with ${capital or 0.0:,.2f} capital"
                )
                click.echo(f"Profile: {profile}")
                click.echo(f"Note: Share import via API not yet implemented")
                click.echo(f"Use direct mode or API update to add shares")
            else:
                print_success(
                    f"Created wheel for {symbol_upper} with ${capital:,.2f} capital"
                )
                click.echo(f"Profile: {profile}")
                click.echo(f"State: {wheel_response.state}")
                click.echo(f"Ready to sell puts (use 'wheel recommend {symbol_upper}')")

        except APIConnectionError as e:
            # Fall back to direct mode
            if cli_ctx.verbose:
                click.echo(f"! API unavailable, using direct mode: {e}", err=True)
            _init_direct_mode(manager, symbol_upper, capital, shares, cost_basis, profile)
        except APIValidationError as e:
            print_error(f"Validation error: {e.detail}")
            sys.exit(1)
        except APIError as e:
            print_error(str(e))
            sys.exit(1)
    else:
        # Direct mode
        _init_direct_mode(manager, symbol_upper, capital, shares, cost_basis, profile)


def _init_direct_mode(manager, symbol: str, capital: float, shares: int, cost_basis: float, profile: str):
    """Handle wheel initialization in direct mode.

    Args:
        manager: WheelManager instance
        symbol: Stock symbol
        capital: Capital allocation
        shares: Number of shares
        cost_basis: Cost basis per share
        profile: Risk profile
    """
    try:
        if shares is not None and shares > 0:
            # Start with shares (SHARES state) - can sell calls
            wheel = manager.import_shares(
                symbol=symbol,
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
                symbol=symbol,
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
@click.option(
    "--portfolio",
    help="Portfolio ID (uses default from config if not specified)",
)
@click.pass_context
def import_shares(
    ctx: click.Context,
    symbol: str,
    shares: int,
    cost_basis: float,
    capital: float,
    profile: str,
    portfolio: Optional[str],
) -> None:
    """
    Import existing shares to start selling calls.

    Starts in SHARES state, ready to sell covered calls.

    Example: wheel import AAPL --shares 200 --cost-basis 150.00 --portfolio <ID>
    """
    cli_ctx = get_cli_context(ctx)
    manager = get_manager(ctx)

    symbol_upper = symbol.upper()

    # Try API mode first, fall back to direct mode
    if cli_ctx.mode == "api" and cli_ctx.api_client:
        try:
            # Determine portfolio ID
            portfolio_id = portfolio or cli_ctx.config.default_portfolio_id

            if not portfolio_id:
                # Need to get or create a default portfolio
                portfolios = cli_ctx.api_client.list_portfolios()
                if portfolios:
                    portfolio_id = portfolios[0].id
                    if cli_ctx.verbose:
                        click.echo(f"+ Using portfolio: {portfolios[0].name}")
                else:
                    # Create default portfolio
                    new_portfolio = cli_ctx.api_client.create_portfolio(
                        name="Default Portfolio",
                        description="Auto-created default portfolio"
                    )
                    portfolio_id = new_portfolio.id
                    if cli_ctx.verbose:
                        click.echo(f"+ Created default portfolio: {new_portfolio.name}")

            # Note: API doesn't support importing shares in create_wheel yet
            # We'll create a cash position and then update it
            # This is a temporary workaround - API should be enhanced
            click.echo("Note: Share import via API not yet fully implemented")
            click.echo("Falling back to direct mode for share import...")
            _import_shares_direct_mode(manager, symbol_upper, shares, cost_basis, capital, profile)

        except APIConnectionError as e:
            # Fall back to direct mode
            if cli_ctx.verbose:
                click.echo(f"! API unavailable, using direct mode: {e}", err=True)
            _import_shares_direct_mode(manager, symbol_upper, shares, cost_basis, capital, profile)
        except (APIValidationError, APIError) as e:
            print_error(str(e))
            sys.exit(1)
    else:
        # Direct mode
        _import_shares_direct_mode(manager, symbol_upper, shares, cost_basis, capital, profile)


def _import_shares_direct_mode(manager, symbol: str, shares: int, cost_basis: float, capital: float, profile: str):
    """Handle share import in direct mode.

    Args:
        manager: WheelManager instance
        symbol: Stock symbol
        shares: Number of shares
        cost_basis: Cost basis per share
        capital: Additional capital
        profile: Risk profile
    """
    try:
        wheel = manager.import_shares(
            symbol=symbol,
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
@click.option(
    "--portfolio",
    help="Filter by portfolio ID",
)
@click.option(
    "--all-portfolios",
    is_flag=True,
    help="List wheels across all portfolios",
)
@click.pass_context
def list_wheels(ctx: click.Context, refresh: bool, portfolio: Optional[str], all_portfolios: bool) -> None:
    """
    List all wheel positions with live monitoring data.

    Shows DTE, moneyness, and risk for open positions.

    Example: wheel list --refresh
    Example: wheel list --portfolio <ID>
    Example: wheel list --all-portfolios
    """
    cli_ctx = get_cli_context(ctx)
    manager = get_manager(ctx)

    # Try API mode first, fall back to direct mode
    if cli_ctx.mode == "api" and cli_ctx.api_client:
        try:
            # Determine which portfolios to query
            if all_portfolios:
                # Get all portfolios and their wheels
                portfolios = cli_ctx.api_client.list_portfolios()
                all_wheels_data = []
                for p in portfolios:
                    wheels = cli_ctx.api_client.list_wheels(p.id, active_only=True)
                    all_wheels_data.extend([(w, p.name) for w in wheels])
            else:
                # Get specific portfolio or default
                portfolio_id = portfolio or cli_ctx.config.default_portfolio_id
                if not portfolio_id:
                    portfolios = cli_ctx.api_client.list_portfolios()
                    if portfolios:
                        portfolio_id = portfolios[0].id
                    else:
                        click.echo("No portfolios found. Use 'wheel portfolio create' to start.")
                        return

                wheels = cli_ctx.api_client.list_wheels(portfolio_id, active_only=True)
                # Get portfolio name for display
                portfolio_obj = cli_ctx.api_client.get_portfolio(portfolio_id)
                all_wheels_data = [(w, portfolio_obj.name) for w in wheels]

            if not all_wheels_data:
                click.echo("No active wheels. Use 'wheel init SYMBOL --capital N' to start.")
                return

            # Table header
            click.echo()
            header = f"{'Symbol':<8} {'Portfolio':<20} {'State':<20}"
            if not all_portfolios:
                # Don't show portfolio column if only one portfolio
                header = f"{'Symbol':<8} {'State':<20} {'Strike':>8} {'Current':>8} {'DTE':>12} {'Moneyness':>12} {'Risk':>6}"
            click.echo(header)
            click.echo("=" * 85)

            # Note: For API mode, position monitoring might not be available in list view
            # This would require batch position status endpoint
            for wheel_resp, portfolio_name in all_wheels_data:
                if all_portfolios:
                    row = f"{wheel_resp.symbol:<8} {portfolio_name:<20} {wheel_resp.state:<20}"
                else:
                    row = f"{wheel_resp.symbol:<8} {wheel_resp.state:<20}"
                    # Try to get position status if wheel has open position
                    # This is inefficient - should use batch endpoint
                    row += f" {'---':>8} {'---':>8} {'---':>12} {'---':>12} {'---':>6}"
                click.echo(row)

            # Summary
            click.echo()
            click.echo(f"Total wheels: {len(all_wheels_data)}")

        except APIConnectionError as e:
            # Fall back to direct mode
            if cli_ctx.verbose:
                click.echo(f"! API unavailable, using direct mode: {e}", err=True)
            _list_wheels_direct_mode(manager, refresh)
        except APIError as e:
            print_error(str(e))
            sys.exit(1)
    else:
        # Direct mode
        _list_wheels_direct_mode(manager, refresh)


def _list_wheels_direct_mode(manager, refresh: bool):
    """Handle wheel listing in direct mode.

    Args:
        manager: WheelManager instance
        refresh: Force refresh of data
    """
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
@click.option(
    "--portfolio",
    help="Portfolio ID to filter (for --all)",
)
@click.pass_context
def status(
    ctx: click.Context, symbol: Optional[str], all_symbols: bool, refresh: bool, portfolio: Optional[str]
) -> None:
    """
    View current wheel status with live monitoring data.

    Shows real-time data including DTE, moneyness, and risk level for open positions.

    Example: wheel status AAPL --refresh
    Example: wheel status --all
    Example: wheel status --all --portfolio <ID>
    """
    cli_ctx = get_cli_context(ctx)
    manager = get_manager(ctx)
    verbose = cli_ctx.verbose

    # Try API mode first, fall back to direct mode
    if cli_ctx.mode == "api" and cli_ctx.api_client:
        try:
            if all_symbols:
                # Get all wheels and their statuses
                portfolio_id = portfolio or cli_ctx.config.default_portfolio_id
                if not portfolio_id:
                    portfolios = cli_ctx.api_client.list_portfolios()
                    if portfolios:
                        portfolio_id = portfolios[0].id
                    else:
                        click.echo("No portfolios found.")
                        return

                wheels = cli_ctx.api_client.list_wheels(portfolio_id, active_only=True)
                if not wheels:
                    click.echo("No active wheels.")
                    return

                for wheel_resp in wheels:
                    # Convert API response to WheelPosition for display
                    from ..models import WheelPosition
                    from ..state import WheelState
                    from src.models.profiles import StrikeProfile

                    wheel = WheelPosition(
                        id=wheel_resp.id,
                        symbol=wheel_resp.symbol,
                        state=WheelState(wheel_resp.state),
                        capital_allocated=wheel_resp.capital_allocated,
                        shares_held=wheel_resp.shares_held or 0,
                        cost_basis=wheel_resp.cost_basis,
                        profile=StrikeProfile(wheel_resp.profile),
                        is_active=wheel_resp.is_active,
                    )

                    # Try to get position status if open
                    try:
                        if wheel.has_open_position:
                            status_resp = cli_ctx.api_client.get_position_status(wheel_resp.id, force_refresh=refresh)
                            # Would need to convert to PositionStatus and TradeRecord for display
                            # For now, show basic status
                            print_status(wheel, verbose)
                        else:
                            print_status(wheel, verbose)
                    except APIError:
                        # No open position or error
                        print_status(wheel, verbose)
                    click.echo()

            elif symbol:
                # Get specific wheel by symbol
                wheel_resp = cli_ctx.api_client.get_wheel_by_symbol(symbol.upper(), portfolio)
                if not wheel_resp:
                    print_error(f"No wheel found for {symbol.upper()}")
                    sys.exit(1)

                # Convert to WheelPosition
                from ..models import WheelPosition
                from ..state import WheelState
                from src.models.profiles import StrikeProfile

                wheel = WheelPosition(
                    id=wheel_resp.id,
                    symbol=wheel_resp.symbol,
                    state=WheelState(wheel_resp.state),
                    capital_allocated=wheel_resp.capital_allocated,
                    shares_held=wheel_resp.shares_held or 0,
                    cost_basis=wheel_resp.cost_basis,
                    profile=StrikeProfile(wheel_resp.profile),
                    is_active=wheel_resp.is_active,
                )

                # Try to get position status
                try:
                    if wheel.has_open_position:
                        status_resp = cli_ctx.api_client.get_position_status(wheel_resp.id, force_refresh=refresh)
                        # Would need full conversion - for now show basic
                        print_status(wheel, verbose)
                    else:
                        print_status(wheel, verbose)
                except APIError:
                    print_status(wheel, verbose)
            else:
                print_error("Provide SYMBOL or --all")
                sys.exit(1)

        except APIConnectionError as e:
            # Fall back to direct mode
            if cli_ctx.verbose:
                click.echo(f"! API unavailable, using direct mode: {e}", err=True)
            _status_direct_mode(manager, symbol, all_symbols, refresh, verbose)
        except APIError as e:
            print_error(str(e))
            sys.exit(1)
    else:
        # Direct mode
        _status_direct_mode(manager, symbol, all_symbols, refresh, verbose)


def _status_direct_mode(manager, symbol: Optional[str], all_symbols: bool, refresh: bool, verbose: bool):
    """Handle status display in direct mode.

    Args:
        manager: WheelManager instance
        symbol: Optional symbol to query
        all_symbols: Show all symbols
        refresh: Force refresh
        verbose: Verbose output
    """
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
