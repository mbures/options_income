"""
Analysis and reporting commands for the wheel CLI.

This module provides commands for getting recommendations, viewing performance,
and displaying trade history.
"""

import sys
from typing import Optional

import click

from ..exceptions import InvalidStateError, SymbolNotFoundError, WheelError
from .utils import (
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
@click.pass_context
def recommend(ctx: click.Context, symbol: Optional[str], all_symbols: bool) -> None:
    """
    Get recommendation for next option to sell.

    Example: wheel recommend AAPL
    """
    manager = get_manager(ctx)
    verbose = ctx.obj["verbose"]

    if all_symbols:
        recs = manager.get_all_recommendations()
        if not recs:
            click.echo("No recommendations available. All wheels have open positions.")
            return
        for rec in recs:
            print_recommendation(rec, verbose)
    elif symbol:
        try:
            rec = manager.get_recommendation(symbol.upper())
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
    manager = get_manager(ctx)
    verbose = ctx.obj["verbose"]

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
    manager = get_manager(ctx)

    trades = manager.get_trade_history(symbol.upper())

    if not trades:
        click.echo(f"No trades found for {symbol.upper()}")
        return

    click.echo()
    click.secho(f"=== Trade History: {symbol.upper()} ===", bold=True)
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
    manager = get_manager(ctx)

    try:
        wheel = manager.update_profile(symbol.upper(), profile)
        print_success(f"Updated {symbol.upper()} profile to {profile}")
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
    manager = get_manager(ctx)

    click.echo("Refreshing all open positions...")

    count = manager.refresh_snapshots(force=False)

    if count == 0:
        click.echo("No new snapshots created (already up-to-date for today)")
    else:
        print_success(f"Created {count} position snapshot(s) for today")
