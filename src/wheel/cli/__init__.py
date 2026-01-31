"""
Click CLI implementation for the wheel strategy tool.

This module provides command-line interface commands for managing
wheel strategy positions, split into logical command groups.
"""

import logging
import sys

import click

from src.config import FinnhubConfig
from src.finnhub_client import FinnhubClient
from src.oauth.config import SchwabOAuthConfig
from src.oauth.coordinator import OAuthCoordinator
from src.price_fetcher import SchwabPriceDataFetcher
from src.schwab.client import SchwabClient

from ..manager import WheelManager

# Import command groups
from .analysis_commands import history, performance, recommend, refresh, update
from .position_commands import import_shares, init, list_wheels, status
from .trade_commands import archive, close, expire, record

logger = logging.getLogger(__name__)


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


# Register position commands
cli.add_command(init)
cli.add_command(import_shares, name="import")
cli.add_command(list_wheels, name="list")
cli.add_command(status)

# Register trade commands
cli.add_command(record)
cli.add_command(expire)
cli.add_command(close)
cli.add_command(archive)

# Register analysis commands
cli.add_command(recommend)
cli.add_command(performance)
cli.add_command(history)
cli.add_command(update)
cli.add_command(refresh)


def main() -> None:
    """Main entry point for the CLI."""
    cli()


__all__ = ["cli", "main"]
