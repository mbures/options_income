#!/usr/bin/env python3
"""
Finnhub Options Chain CLI Application.

This application retrieves options chain data from Finnhub API
and displays it in various formats.
"""

import sys
import json
import argparse
import logging
from typing import NoReturn

from .config import FinnhubConfig
from .finnhub_client import FinnhubClient, FinnhubAPIError
from .options_service import OptionsChainService, DataValidationError
from .models import OptionsChain


# Configure logging
logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def main() -> None:
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        description="Retrieve options chain data from Finnhub API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s F                           # Fetch options for Ford (F)
  %(prog)s AAPL --output summary       # Show summary instead of full JSON
  %(prog)s TSLA --output-file out.json # Save to file
  %(prog)s MSFT --verbose              # Enable debug logging

Configuration:
  API key can be provided in two ways (checked in this order):
  1. File: config/finhub_api_key.txt (format: finhub_api_key = 'your_key')
  2. Environment variable: FINNHUB_API_KEY

  Get your API key from https://finnhub.io/register
        """,
    )

    parser.add_argument("symbol", type=str, help="Stock ticker symbol (e.g., F, AAPL, TSLA)")

    parser.add_argument(
        "--output",
        type=str,
        default="json",
        choices=["json", "summary", "minimal"],
        help="Output format (default: json)",
    )

    parser.add_argument("--output-file", type=str, help="Save output to file instead of stdout")

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    try:
        # Load configuration - try file first, then environment variable
        try:
            config = FinnhubConfig.from_file()
        except FileNotFoundError:
            config = FinnhubConfig.from_env()

        # Initialize client and service
        with FinnhubClient(config) as client:
            service = OptionsChainService(client)

            # Retrieve options chain
            print(f"Fetching options chain for {args.symbol}...", file=sys.stderr)
            options_chain = service.get_options_chain(args.symbol)

            # Format output
            if args.output == "json":
                output = json.dumps(options_chain.to_dict(), indent=2)
            elif args.output == "summary":
                output = format_summary(options_chain)
            else:  # minimal
                output = format_minimal(options_chain)

            # Write output
            if args.output_file:
                with open(args.output_file, "w", encoding="utf-8") as f:
                    f.write(output)
                print(f"✓ Output written to {args.output_file}", file=sys.stderr)
            else:
                print(output)

    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("\nPlease provide your API key in one of these ways:", file=sys.stderr)
        print("  1. Create config/finhub_api_key.txt with: finhub_api_key = 'your_key'", file=sys.stderr)
        print("  2. Set FINNHUB_API_KEY environment variable", file=sys.stderr)
        print("\nGet a free API key at https://finnhub.io/register", file=sys.stderr)
        sys.exit(1)

    except FinnhubAPIError as e:
        print(f"API error: {e}", file=sys.stderr)
        sys.exit(2)

    except DataValidationError as e:
        print(f"Data validation error: {e}", file=sys.stderr)
        print("\nThis may indicate:", file=sys.stderr)
        print("  - Symbol does not have options available", file=sys.stderr)
        print("  - API response format has changed", file=sys.stderr)
        print("  - Temporary API issue", file=sys.stderr)
        sys.exit(3)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user", file=sys.stderr)
        sys.exit(130)

    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(4)


def format_summary(options_chain: OptionsChain) -> str:
    """
    Format options chain as human-readable summary.

    Args:
        options_chain: OptionsChain object to format

    Returns:
        Formatted string with summary information
    """
    lines = [
        "=" * 70,
        f"Options Chain for {options_chain.symbol}",
        "=" * 70,
        f"Retrieved at: {options_chain.retrieved_at}",
        f"Total contracts: {len(options_chain.contracts)}",
        f"  Calls: {len(options_chain.get_calls())}",
        f"  Puts: {len(options_chain.get_puts())}",
        f"Expirations: {len(options_chain.get_expirations())}",
        "",
    ]

    # Show expirations
    expirations = options_chain.get_expirations()
    if expirations:
        lines.append("Available Expirations:")
        for exp in expirations[:10]:  # Show first 10
            count = len(options_chain.get_by_expiration(exp))
            lines.append(f"  {exp}: {count} contracts")
        if len(expirations) > 10:
            lines.append(f"  ... and {len(expirations) - 10} more")
        lines.append("")

    # Show sample calls
    calls = options_chain.get_calls()[:5]
    if calls:
        lines.append("Sample Call Options:")
        lines.append(
            f"  {'Expiration':<12} {'Strike':>8} {'Bid':>8} {'Ask':>8} {'Last':>8} {'Volume':>8}"
        )
        lines.append("  " + "-" * 60)
        for contract in calls:
            lines.append(
                f"  {contract.expiration_date:<12} "
                f"${contract.strike:>7.2f} "
                f"${contract.bid or 0:>7.2f} "
                f"${contract.ask or 0:>7.2f} "
                f"${contract.last or 0:>7.2f} "
                f"{contract.volume or 0:>8}"
            )
        lines.append("")

    # Show sample puts
    puts = options_chain.get_puts()[:5]
    if puts:
        lines.append("Sample Put Options:")
        lines.append(
            f"  {'Expiration':<12} {'Strike':>8} {'Bid':>8} {'Ask':>8} {'Last':>8} {'Volume':>8}"
        )
        lines.append("  " + "-" * 60)
        for contract in puts:
            lines.append(
                f"  {contract.expiration_date:<12} "
                f"${contract.strike:>7.2f} "
                f"${contract.bid or 0:>7.2f} "
                f"${contract.ask or 0:>7.2f} "
                f"${contract.last or 0:>7.2f} "
                f"{contract.volume or 0:>8}"
            )
        lines.append("")

    lines.append("=" * 70)
    lines.append(
        "Note: Finnhub options data may have accuracy limitations. " "Verify before trading."
    )
    lines.append("=" * 70)

    return "\n".join(lines)


def format_minimal(options_chain: OptionsChain) -> str:
    """
    Format options chain in minimal format.

    Args:
        options_chain: OptionsChain object to format

    Returns:
        Minimal formatted string
    """
    return (
        f"{options_chain.symbol}: {len(options_chain.contracts)} contracts "
        f"({len(options_chain.get_calls())} calls, {len(options_chain.get_puts())} puts), "
        f"{len(options_chain.get_expirations())} expirations"
    )


if __name__ == "__main__":
    main()
