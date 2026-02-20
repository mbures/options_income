"""
Click CLI implementation for the wheel strategy tool.

This module provides command-line interface commands for managing
wheel strategy positions, split into logical command groups.
"""

import logging
import sys
from dataclasses import dataclass
from typing import Optional

import click

from src.config import FinnhubConfig
from src.finnhub_client import FinnhubClient
from src.oauth.config import SchwabOAuthConfig
from src.oauth.coordinator import OAuthCoordinator
from src.price_fetcher import SchwabPriceDataFetcher
from src.schwab.client import SchwabClient

from ..api_client import APIConnectionError, WheelStrategyAPIClient
from ..config import WheelStrategyConfig
from ..manager import WheelManager

# Import command groups
from .analysis_commands import history, performance, recommend, refresh, update
from .position_commands import import_shares, init, list_wheels, status
from .trade_commands import archive, close, expire, record
from .portfolio_commands import portfolio

logger = logging.getLogger(__name__)


@dataclass
class CLIContext:
    """Context object passed to all CLI commands.

    Attributes:
        config: Configuration settings
        api_client: API client instance (None if using direct mode)
        wheel_manager: WheelManager instance for direct mode
        mode: Current mode ("api" or "direct")
        verbose: Verbose output enabled
        json: JSON output enabled
    """
    config: WheelStrategyConfig
    api_client: Optional[WheelStrategyAPIClient]
    wheel_manager: WheelManager
    mode: str
    verbose: bool
    json: bool


@click.group()
@click.option(
    "--db",
    default="~/.wheel_strategy/trades.db",
    help="Database file path",
    envvar="WHEEL_DB_PATH",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--json", "output_json", is_flag=True, help="JSON output (where supported)")
@click.option(
    "--api-url",
    help="API server URL (overrides config)",
    envvar="WHEEL_API_URL",
)
@click.option(
    "--api-mode/--direct-mode",
    default=None,
    help="Force API mode or direct database mode",
)
@click.option(
    "--config-file",
    type=click.Path(exists=True),
    help="Path to configuration file",
)
@click.pass_context
def cli(
    ctx: click.Context,
    db: str,
    verbose: bool,
    output_json: bool,
    api_url: Optional[str],
    api_mode: Optional[bool],
    config_file: Optional[str],
) -> None:
    """
    Wheel Strategy Tool - Manage options wheel positions.

    Track and optimize your wheel strategy across multiple symbols.
    Biases toward premium collection over assignment.
    """
    ctx.ensure_object(dict)

    # Load configuration
    try:
        if config_file:
            from pathlib import Path
            config = WheelStrategyConfig.load_from_file(Path(config_file))
        else:
            config = WheelStrategyConfig.load_from_file()
    except Exception as e:
        if verbose:
            click.echo(f"! Could not load config file: {e}", err=True)
            click.echo("  Using default configuration")
        config = WheelStrategyConfig()

    # Apply command-line overrides
    if api_url:
        config.api_url = api_url
    if verbose:
        config.verbose = True
    if output_json:
        config.json_output = True
    if api_mode is not None:
        config.use_api_mode = api_mode

    # Load API configurations for direct mode
    finnhub_client = None
    price_fetcher = None
    schwab_client = None

    # Initialize Schwab client (required for price and options data)
    try:
        # Try loading credentials from file first, then environment
        try:
            oauth_config = SchwabOAuthConfig.from_file()
            if config.verbose:
                click.echo("+ Schwab credentials loaded from config/charles_schwab_key.txt")
        except FileNotFoundError:
            oauth_config = SchwabOAuthConfig.from_env()
            if config.verbose:
                click.echo("+ Schwab credentials loaded from environment")

        oauth = OAuthCoordinator(config=oauth_config)
        schwab_client = SchwabClient(oauth_coordinator=oauth)
        price_fetcher = SchwabPriceDataFetcher(schwab_client, enable_cache=True)
        if config.verbose:
            click.echo("+ Schwab client configured for price and options data")
    except Exception as e:
        click.echo(f"Error: Schwab client initialization failed: {e}", err=True)
        click.echo("Please run: python scripts/authorize_schwab_host.py", err=True)
        sys.exit(1)

    # Initialize Finnhub client for earnings calendar (optional)
    try:
        finnhub_config = FinnhubConfig.from_file()
        finnhub_client = FinnhubClient(finnhub_config)
        if config.verbose:
            click.echo("+ Finnhub client configured (earnings calendar)")
    except (FileNotFoundError, ValueError) as e:
        if config.verbose:
            click.echo(f"! Finnhub not configured: {e}", err=True)
            click.echo("  Earnings calendar features will be disabled")

    # Initialize WheelManager (always needed for fallback)
    wheel_manager = WheelManager(
        db_path=db,
        finnhub_client=finnhub_client,
        price_fetcher=price_fetcher,
        schwab_client=schwab_client,
    )

    # Initialize API client if API mode is enabled
    api_client = None
    mode = "direct"

    if config.use_api_mode:
        try:
            api_client = WheelStrategyAPIClient.create_with_fallback(
                api_url=config.api_url,
                timeout=config.api_timeout
            )
            if api_client:
                mode = "api"
                if config.verbose:
                    click.echo(f"+ API mode enabled (server: {config.api_url})")
            else:
                if config.verbose:
                    click.echo("! API server not available, using direct mode")
        except Exception as e:
            if config.verbose:
                click.echo(f"! Failed to initialize API client: {e}", err=True)
                click.echo("  Using direct mode")

    # Create CLI context
    cli_ctx = CLIContext(
        config=config,
        api_client=api_client,
        wheel_manager=wheel_manager,
        mode=mode,
        verbose=config.verbose,
        json=config.json_output,
    )

    # Store context for commands
    ctx.obj = cli_ctx

    # Also maintain backward compatibility with old dict-based access
    ctx.obj = {
        "manager": wheel_manager,
        "verbose": config.verbose,
        "json": config.json_output,
        "cli_context": cli_ctx,
    }


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

# Register portfolio commands
cli.add_command(portfolio)


def main() -> None:
    """Main entry point for the CLI."""
    cli()


__all__ = ["cli", "main"]
