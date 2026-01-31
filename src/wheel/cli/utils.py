"""
CLI utility functions for the wheel strategy tool.

This module provides helper functions for formatting output,
displaying data, and managing CLI context.
"""

import click

from ..models import WheelPerformance, WheelPosition, WheelRecommendation
from ..state import TradeOutcome
from ..models import TradeRecord, PositionStatus


def get_manager(ctx: click.Context):
    """Get the WheelManager from context."""
    return ctx.obj["manager"]


def print_error(message: str) -> None:
    """Print error message to stderr."""
    click.secho(f"Error: {message}", fg="red", err=True)


def print_success(message: str) -> None:
    """Print success message."""
    click.secho(message, fg="green")


def print_warning(message: str) -> None:
    """Print warning message."""
    click.secho(f"Warning: {message}", fg="yellow")


def print_recommendation(rec: WheelRecommendation, verbose: bool = False) -> None:
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


def print_status(wheel: WheelPosition, verbose: bool = False) -> None:
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


def print_performance(perf: WheelPerformance, verbose: bool = False) -> None:
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


def format_dte(dte_calendar: int, dte_trading: int) -> str:
    """Format days to expiration with both calendar and trading days."""
    return f"{dte_calendar} days ({dte_trading} trading)"


def print_status_with_monitoring(
    wheel: WheelPosition,
    trade: TradeRecord,
    status: PositionStatus,
    verbose: bool = False,
) -> None:
    """Print wheel status with live monitoring data."""
    click.echo()
    click.secho(f"{'='*70}", bold=True)
    click.secho(f"  {wheel.symbol} - {wheel.state.value.upper()}", bold=True)
    click.secho(f"{'='*70}", bold=True)

    # Position basics
    click.echo(f"\nPosition:")
    click.echo(f"  Profile: {wheel.profile.value}")
    click.echo(f"  Capital: ${wheel.capital_allocated:,.2f}")
    if wheel.shares_held > 0:
        click.echo(f"  Shares: {wheel.shares_held} @ ${wheel.cost_basis:.2f}")

    # Open trade details
    click.echo(f"\nOpen {trade.direction.upper()}:")
    click.echo(f"  Strike: ${trade.strike:.2f}")
    click.echo(f"  Expiration: {trade.expiration_date}")
    click.echo(f"  Premium: ${trade.total_premium:.2f} (${trade.premium_per_share:.2f}/share)")
    click.echo(f"  Contracts: {trade.contracts}")

    # LIVE MONITORING DATA
    click.echo(
        f"\nLive Status (as of {status.last_updated.strftime('%Y-%m-%d %H:%M:%S')}):"
    )
    click.echo(f"  Current Price: ${status.current_price:.2f}")
    click.echo(f"  DTE: {format_dte(status.dte_calendar, status.dte_trading)}")
    click.echo(f"  Moneyness: {status.moneyness_label}")
    click.echo(f"  Risk Level: {status.risk_icon} {status.risk_level}")

    if verbose:
        click.echo(f"\n  {status.risk_description}")
        click.echo(f"  Price vs Strike: ${status.price_vs_strike:+.2f}")

    # Risk warning for HIGH risk positions
    if status.risk_level == "HIGH":
        click.echo()
        click.secho(f"{'!'*70}", fg="red", bold=True)
        click.secho(f"  ⚠️  WARNING: Position is ITM - ASSIGNMENT RISK", fg="red", bold=True)
        click.secho(f"{'!'*70}", fg="red", bold=True)


def get_status_icon(trade: TradeRecord) -> str:
    """Get status icon for trade outcome."""
    return {
        TradeOutcome.OPEN: "[OPEN]",
        TradeOutcome.EXPIRED_WORTHLESS: "[WIN]",
        TradeOutcome.ASSIGNED: "[ASSIGNED]",
        TradeOutcome.CALLED_AWAY: "[CALLED]",
        TradeOutcome.CLOSED_EARLY: "[CLOSED]",
    }.get(trade.outcome, "[?]")
