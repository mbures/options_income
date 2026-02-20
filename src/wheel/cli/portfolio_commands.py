"""
Portfolio management commands for the wheel CLI.

This module provides commands for creating, listing, and managing
portfolios in API mode.
"""

import sys

import click

from ..api_client import APIConnectionError, APIError, APIValidationError
from .utils import get_cli_context, print_error, print_success


@click.command("create")
@click.argument("name")
@click.option("--description", help="Portfolio description")
@click.option("--capital", type=float, help="Default capital allocation ($)")
@click.pass_context
def create_portfolio(
    ctx: click.Context,
    name: str,
    description: str,
    capital: float,
) -> None:
    """
    Create a new portfolio.

    Example: wheel portfolio create "Trading Portfolio" --capital 50000
    """
    cli_ctx = get_cli_context(ctx)

    # Portfolio management requires API mode
    if cli_ctx.mode != "api" or not cli_ctx.api_client:
        print_error("Portfolio management requires API mode")
        click.echo("Please start the API server and configure API URL")
        sys.exit(1)

    try:
        portfolio = cli_ctx.api_client.create_portfolio(
            name=name,
            description=description,
            default_capital=capital,
        )

        print_success(f"Created portfolio: {portfolio.name}")
        click.echo(f"ID: {portfolio.id}")
        if portfolio.description:
            click.echo(f"Description: {portfolio.description}")
        if portfolio.default_capital:
            click.echo(f"Default Capital: ${portfolio.default_capital:,.2f}")

    except APIConnectionError as e:
        print_error(f"API unavailable: {e}")
        sys.exit(1)
    except APIValidationError as e:
        print_error(f"Validation error: {e.detail}")
        sys.exit(1)
    except APIError as e:
        print_error(str(e))
        sys.exit(1)


@click.command("list")
@click.pass_context
def list_portfolios(ctx: click.Context) -> None:
    """
    List all portfolios.

    Example: wheel portfolio list
    """
    cli_ctx = get_cli_context(ctx)

    # Portfolio management requires API mode
    if cli_ctx.mode != "api" or not cli_ctx.api_client:
        print_error("Portfolio management requires API mode")
        click.echo("Please start the API server and configure API URL")
        sys.exit(1)

    try:
        portfolios = cli_ctx.api_client.list_portfolios()

        if not portfolios:
            click.echo("No portfolios found. Use 'wheel portfolio create' to start.")
            return

        # Table header
        click.echo()
        click.echo(
            f"{'ID':<38} {'Name':<25} {'Wheels':>8} {'Status':<10}"
        )
        click.echo("=" * 85)

        # Get default portfolio ID
        default_id = cli_ctx.config.default_portfolio_id

        for portfolio in portfolios:
            # Mark default portfolio
            marker = "*" if portfolio.id == default_id else " "

            row = (
                f"{marker}{portfolio.id:<37} "
                f"{portfolio.name:<25} "
                f"{portfolio.wheel_count:>8} "
                f"{'Active' if portfolio.is_active else 'Inactive':<10}"
            )
            click.echo(row)

        # Summary
        click.echo()
        click.echo(f"Total portfolios: {len(portfolios)}")
        if default_id:
            click.echo(f"Default portfolio: {default_id} (marked with *)")

    except APIConnectionError as e:
        print_error(f"API unavailable: {e}")
        sys.exit(1)
    except APIError as e:
        print_error(str(e))
        sys.exit(1)


@click.command("show")
@click.argument("portfolio_id")
@click.pass_context
def show_portfolio(ctx: click.Context, portfolio_id: str) -> None:
    """
    Show detailed portfolio information.

    Example: wheel portfolio show <ID>
    """
    cli_ctx = get_cli_context(ctx)

    # Portfolio management requires API mode
    if cli_ctx.mode != "api" or not cli_ctx.api_client:
        print_error("Portfolio management requires API mode")
        click.echo("Please start the API server and configure API URL")
        sys.exit(1)

    try:
        # Get portfolio summary
        summary = cli_ctx.api_client.get_portfolio_summary(portfolio_id)

        click.echo()
        click.secho(f"=== Portfolio: {summary.name} ===", bold=True)
        click.echo()
        click.echo(f"ID: {summary.id}")
        if summary.description:
            click.echo(f"Description: {summary.description}")
        if summary.default_capital:
            click.echo(f"Default Capital: ${summary.default_capital:,.2f}")

        click.echo()
        click.echo(f"Total Wheels: {summary.total_wheels}")
        click.echo(f"Active Wheels: {summary.active_wheels}")

        if summary.total_premium is not None:
            click.echo()
            click.echo(f"Total Premium Collected: ${summary.total_premium:,.2f}")
        if summary.total_trades is not None:
            click.echo(f"Total Trades: {summary.total_trades}")
        if summary.open_positions is not None:
            click.echo(f"Open Positions: {summary.open_positions}")

        click.echo()
        click.echo(f"Status: {'Active' if summary.is_active else 'Inactive'}")
        click.echo(f"Created: {summary.created_at}")

    except APIConnectionError as e:
        print_error(f"API unavailable: {e}")
        sys.exit(1)
    except APIError as e:
        print_error(str(e))
        sys.exit(1)


@click.command("set-default")
@click.argument("portfolio_id")
@click.pass_context
def set_default_portfolio(ctx: click.Context, portfolio_id: str) -> None:
    """
    Set default portfolio for CLI operations.

    Example: wheel portfolio set-default <ID>
    """
    cli_ctx = get_cli_context(ctx)

    # Portfolio management requires API mode
    if cli_ctx.mode != "api" or not cli_ctx.api_client:
        print_error("Portfolio management requires API mode")
        click.echo("Please start the API server and configure API URL")
        sys.exit(1)

    try:
        # Verify portfolio exists
        portfolio = cli_ctx.api_client.get_portfolio(portfolio_id)

        # Update configuration
        cli_ctx.config.default_portfolio_id = portfolio_id

        # Save configuration to file
        cli_ctx.config.save_to_file()

        print_success(f"Set default portfolio to: {portfolio.name}")
        click.echo(f"ID: {portfolio_id}")

    except APIConnectionError as e:
        print_error(f"API unavailable: {e}")
        sys.exit(1)
    except APIError as e:
        print_error(str(e))
        sys.exit(1)


@click.command("delete")
@click.argument("portfolio_id")
@click.option(
    "--confirm",
    is_flag=True,
    help="Confirm deletion (required for safety)",
)
@click.pass_context
def delete_portfolio(
    ctx: click.Context,
    portfolio_id: str,
    confirm: bool,
) -> None:
    """
    Delete a portfolio and all associated wheels.

    WARNING: This will permanently delete all wheels and trades in the portfolio.

    Example: wheel portfolio delete <ID> --confirm
    """
    cli_ctx = get_cli_context(ctx)

    # Portfolio management requires API mode
    if cli_ctx.mode != "api" or not cli_ctx.api_client:
        print_error("Portfolio management requires API mode")
        click.echo("Please start the API server and configure API URL")
        sys.exit(1)

    if not confirm:
        print_error("Deletion requires --confirm flag for safety")
        click.echo("This will permanently delete all wheels and trades in the portfolio")
        sys.exit(1)

    try:
        # Get portfolio info before deletion
        portfolio = cli_ctx.api_client.get_portfolio(portfolio_id)

        # Delete portfolio
        cli_ctx.api_client.delete_portfolio(portfolio_id)

        print_success(f"Deleted portfolio: {portfolio.name}")
        click.echo(f"ID: {portfolio_id}")

        # If this was the default portfolio, clear it
        if cli_ctx.config.default_portfolio_id == portfolio_id:
            cli_ctx.config.default_portfolio_id = None
            cli_ctx.config.save_to_file()
            click.echo("Cleared default portfolio setting")

    except APIConnectionError as e:
        print_error(f"API unavailable: {e}")
        sys.exit(1)
    except APIError as e:
        print_error(str(e))
        sys.exit(1)


# Create portfolio command group
@click.group("portfolio")
def portfolio():
    """
    Manage portfolios (API mode only).

    Portfolios organize wheels and allow managing multiple strategies.
    """
    pass


# Register subcommands
portfolio.add_command(create_portfolio, name="create")
portfolio.add_command(list_portfolios, name="list")
portfolio.add_command(show_portfolio, name="show")
portfolio.add_command(set_default_portfolio, name="set-default")
portfolio.add_command(delete_portfolio, name="delete")
