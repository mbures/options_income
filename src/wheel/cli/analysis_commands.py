"""
Analysis and reporting commands for the wheel CLI.

This module provides commands for getting recommendations, viewing performance,
and displaying trade history.
"""

import sys
from typing import Optional

import click

from ..api_client import APIConnectionError, APIError
from ..exceptions import InvalidStateError, SymbolNotFoundError, WheelError
from .utils import (
    get_cli_context,
    get_manager,
    get_status_icon,
    print_error,
    print_performance,
    print_recommendation,
    print_success,
)


@click.command()
@click.argument("symbol", required=False)
@click.option("--all", "all_symbols", is_flag=True, help="All active wheels")
@click.option("--max-dte", type=int, default=None, help="Max days to expiration (default: from config)")
@click.pass_context
def recommend(ctx: click.Context, symbol: Optional[str], all_symbols: bool, max_dte: Optional[int]) -> None:
    """
    Get recommendation for next option to sell.

    Example: wheel recommend AAPL
    Example: wheel recommend AAPL --max-dte 30
    """
    cli_ctx = get_cli_context(ctx)
    manager = get_manager(ctx)
    verbose = cli_ctx.verbose

    # Use CLI override or config value
    effective_max_dte = max_dte if max_dte is not None else cli_ctx.config.max_dte

    # Try API mode first, fall back to direct mode
    if cli_ctx.mode == "api" and cli_ctx.api_client:
        try:
            if all_symbols:
                # Get all recommendations - would need to iterate wheels
                # For now, fall back to direct mode for --all
                click.echo("Note: --all flag not fully supported in API mode yet")
                click.echo("Falling back to direct mode...")
                _recommend_direct_mode(manager, symbol, all_symbols, verbose, effective_max_dte)
            elif symbol:
                # Get wheel by symbol
                wheel = cli_ctx.api_client.get_wheel_by_symbol(symbol.upper())
                if not wheel:
                    print_error(f"No wheel found for {symbol.upper()}")
                    sys.exit(1)

                # Get recommendation via API
                rec_resp = cli_ctx.api_client.get_recommendation(
                    wheel.id, use_cache=True, max_dte=effective_max_dte
                )

                # Convert API response to WheelRecommendation for display
                from ..models import WheelRecommendation

                rec = WheelRecommendation(
                    symbol=rec_resp.symbol,
                    direction=rec_resp.direction,
                    strike=rec_resp.strike,
                    expiration_date=rec_resp.expiration_date,
                    premium_per_share=rec_resp.premium_per_share,
                    contracts=rec_resp.contracts,
                    total_premium=rec_resp.total_premium,
                    current_price=rec_resp.current_price,
                    bid=rec_resp.bid,
                    ask=rec_resp.ask,
                    dte=rec_resp.dte,
                    sigma_distance=rec_resp.sigma_distance,
                    p_itm=rec_resp.p_itm,
                    annualized_yield_pct=rec_resp.annualized_yield_pct,
                    effective_yield_if_assigned=rec_resp.effective_yield_if_assigned,
                    bias_score=rec_resp.bias_score,
                    warnings=rec_resp.warnings or [],
                )

                print_recommendation(rec, verbose)
            else:
                print_error("Provide SYMBOL or --all")
                sys.exit(1)

        except APIConnectionError as e:
            # Fall back to direct mode
            if cli_ctx.verbose:
                click.echo(f"! API unavailable, using direct mode: {e}", err=True)
            _recommend_direct_mode(manager, symbol, all_symbols, verbose, effective_max_dte)
        except APIError as e:
            print_error(str(e))
            sys.exit(1)
    else:
        # Direct mode
        _recommend_direct_mode(manager, symbol, all_symbols, verbose, effective_max_dte)


def _recommend_direct_mode(
    manager, symbol: Optional[str], all_symbols: bool, verbose: bool, max_dte: int = 14
):
    """Handle recommendations in direct mode.

    Args:
        manager: WheelManager instance
        symbol: Optional symbol
        all_symbols: Get all recommendations
        verbose: Verbose output
        max_dte: Maximum days to expiration search window
    """
    if all_symbols:
        recs = manager.get_all_recommendations(max_dte=max_dte)
        if not recs:
            click.echo("No recommendations available. All wheels have open positions.")
            return
        for rec in recs:
            print_recommendation(rec, verbose)
    elif symbol:
        try:
            rec = manager.get_recommendation(symbol.upper(), max_dte=max_dte)
            print_recommendation(rec, verbose)
        except SymbolNotFoundError as e:
            print_error(str(e))
            sys.exit(1)
        except InvalidStateError as e:
            print_error(str(e))
            sys.exit(1)
        except WheelError as e:
            print_error(str(e))
            sys.exit(1)
    else:
        print_error("Provide SYMBOL or --all")
        sys.exit(1)


@click.command()
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
    cli_ctx = get_cli_context(ctx)
    manager = get_manager(ctx)
    verbose = cli_ctx.verbose

    # Performance calculation is complex and not fully supported in API yet
    # Fall back to direct mode for now
    if cli_ctx.mode == "api" and cli_ctx.api_client:
        if cli_ctx.verbose:
            click.echo("Note: Performance metrics via API not yet fully implemented")
            click.echo("Falling back to direct mode...")

    # Direct mode
    if export:
        # Export mode
        data = manager.export_trades(symbol if not all_symbols else None, format=export)
        click.echo(data)
    elif all_symbols:
        perf = manager.get_portfolio_performance()
        print_performance(perf, verbose)
    elif symbol:
        perf = manager.get_performance(symbol.upper())
        print_performance(perf, verbose)
    else:
        print_error("Provide SYMBOL or --all")
        sys.exit(1)


@click.command()
@click.argument("symbol")
@click.pass_context
def history(ctx: click.Context, symbol: str) -> None:
    """
    View trade history for a symbol.

    Example: wheel history AAPL
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

            # Get all trades via API
            trades_resp = cli_ctx.api_client.list_trades(wheel.id)

            if not trades_resp:
                click.echo(f"No trades found for {symbol_upper}")
                return

            click.echo()
            click.secho(f"=== Trade History: {symbol_upper} ===", bold=True)
            click.echo()

            # Convert API response to TradeRecord for display
            from ..models import TradeRecord
            from ..state import TradeOutcome
            from datetime import datetime

            for trade_resp in trades_resp:
                # Create minimal TradeRecord for display
                trade = TradeRecord(
                    id=trade_resp.id,
                    wheel_id=trade_resp.wheel_id,
                    symbol=symbol_upper,
                    direction=trade_resp.direction,
                    strike=trade_resp.strike,
                    expiration_date=trade_resp.expiration_date,
                    premium_per_share=trade_resp.premium_per_share,
                    contracts=trade_resp.contracts,
                    total_premium=trade_resp.total_premium,
                    opened_at=datetime.fromisoformat(trade_resp.opened_at.replace('Z', '+00:00')),
                    outcome=TradeOutcome(trade_resp.outcome),
                )

                status_icon = get_status_icon(trade)

                click.echo(
                    f"{trade.opened_at.strftime('%Y-%m-%d')} "
                    f"{trade.direction.upper():4} ${trade.strike:7.2f} "
                    f"exp {trade.expiration_date} "
                    f"${trade.total_premium:7.2f} "
                    f"{status_icon}"
                )

        except APIConnectionError as e:
            # Fall back to direct mode
            if cli_ctx.verbose:
                click.echo(f"! API unavailable, using direct mode: {e}", err=True)
            _history_direct_mode(manager, symbol_upper)
        except APIError as e:
            print_error(str(e))
            sys.exit(1)
    else:
        # Direct mode
        _history_direct_mode(manager, symbol_upper)


def _history_direct_mode(manager, symbol: str):
    """Handle trade history in direct mode.

    Args:
        manager: WheelManager instance
        symbol: Stock symbol
    """
    trades = manager.get_trade_history(symbol)

    if not trades:
        click.echo(f"No trades found for {symbol}")
        return

    click.echo()
    click.secho(f"=== Trade History: {symbol} ===", bold=True)
    click.echo()

    for trade in trades:
        status_icon = get_status_icon(trade)

        click.echo(
            f"{trade.opened_at.strftime('%Y-%m-%d')} "
            f"{trade.direction.upper():4} ${trade.strike:7.2f} "
            f"exp {trade.expiration_date} "
            f"${trade.total_premium:7.2f} "
            f"{status_icon}"
        )


@click.command()
@click.argument("symbol")
@click.option(
    "--profile",
    required=True,
    type=click.Choice(["aggressive", "moderate", "conservative", "defensive"]),
    help="New risk profile",
)
@click.pass_context
def update(ctx: click.Context, symbol: str, profile: str) -> None:
    """
    Update wheel settings.

    Example: wheel update AAPL --profile moderate
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

            # Update wheel via API
            cli_ctx.api_client.update_wheel(wheel.id, {"profile": profile})
            print_success(f"Updated {symbol_upper} profile to {profile}")

        except APIConnectionError as e:
            # Fall back to direct mode
            if cli_ctx.verbose:
                click.echo(f"! API unavailable, using direct mode: {e}", err=True)
            _update_direct_mode(manager, symbol_upper, profile)
        except APIError as e:
            print_error(str(e))
            sys.exit(1)
    else:
        # Direct mode
        _update_direct_mode(manager, symbol_upper, profile)


def _update_direct_mode(manager, symbol: str, profile: str):
    """Handle wheel update in direct mode.

    Args:
        manager: WheelManager instance
        symbol: Stock symbol
        profile: New profile
    """
    try:
        wheel = manager.update_profile(symbol, profile)
        print_success(f"Updated {symbol} profile to {profile}")
    except (SymbolNotFoundError, ValueError) as e:
        print_error(str(e))
        sys.exit(1)


@click.command()
@click.pass_context
def refresh(ctx: click.Context) -> None:
    """
    Refresh all position snapshots and create daily historical records.

    This command:
    - Fetches fresh quotes for all open positions
    - Creates daily snapshots for historical tracking
    - Should be run once per day (typically after market close)

    The snapshots enable tracking position evolution over time. You can
    schedule this command via cron to run automatically:

        # Daily at 4:15 PM ET (after market close)
        15 16 * * 1-5 cd /path/to/project && wheel refresh

    Example: wheel refresh
    """
    cli_ctx = get_cli_context(ctx)
    manager = get_manager(ctx)

    # Refresh is a direct-mode operation for now
    # API doesn't have a refresh endpoint yet
    if cli_ctx.mode == "api" and cli_ctx.api_client:
        if cli_ctx.verbose:
            click.echo("Note: Refresh via API not yet implemented")
            click.echo("Falling back to direct mode...")

    click.echo("Refreshing all open positions...")

    count = manager.refresh_snapshots(force=False)

    if count == 0:
        click.echo("No new snapshots created (already up-to-date for today)")
    else:
        print_success(f"Created {count} position snapshot(s) for today")
