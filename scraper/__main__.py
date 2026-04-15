"""CLI entry point for the scraper package.

Usage
-----
    python -m scraper --list
    python -m scraper hapoalim --start-date 2024-01-01
    python -m scraper max --days 30 --output json
    python -m scraper onezero --headless false
"""

import argparse
import asyncio
import dataclasses
import getpass
import json
import os
import sys
from datetime import date, timedelta
from typing import TYPE_CHECKING

from scraper.models.credentials import PROVIDER_CONFIGS

if TYPE_CHECKING:
    from scraper.models.result import ScrapingResult


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the scraper CLI.

    Returns
    -------
    argparse.ArgumentParser
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="python -m scraper",
        description="Scrape financial data from Israeli institutions.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available providers and exit.",
    )
    parser.add_argument(
        "provider",
        nargs="?",
        help="Provider key (e.g., hapoalim, max, visa cal).",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Number of days back to scrape (default: 90).",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--headless",
        choices=["true", "false"],
        default="true",
        help="Run browser in headless mode (default: true).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser


def list_providers() -> None:
    """Print all available providers with their configuration."""
    print("Available providers:\n")
    for key, config in PROVIDER_CONFIGS.items():
        tfa_marker = " [2FA]" if config.requires_2fa else ""
        fields = ", ".join(config.required_fields)
        print(f"  {key:<22} {config.name}{tfa_marker}")
        print(f"  {'':<22} Fields: {fields}")
        print()


def gather_credentials(provider: str) -> dict:
    """Gather credentials from environment variables or interactive prompts.

    Environment variables are checked first with the naming convention
    ``SCRAPER_{FIELD_NAME_UPPERCASE}``. If not found, the user is prompted
    interactively (using getpass for password fields).

    Parameters
    ----------
    provider : str
        Provider key to look up required fields.

    Returns
    -------
    dict
        Credential key-value pairs.
    """
    config = PROVIDER_CONFIGS[provider]
    credentials = {}
    for field_name in config.required_fields:
        env_key = f"SCRAPER_{field_name.upper()}"
        env_value = os.environ.get(env_key)
        if env_value is not None:
            credentials[field_name] = env_value
        elif "password" in field_name.lower():
            credentials[field_name] = getpass.getpass(f"{field_name}: ")
        else:
            credentials[field_name] = input(f"{field_name}: ")
    return credentials


async def handle_otp() -> str:
    """Prompt user for OTP code via stdin.

    Returns
    -------
    str
        The OTP code entered by the user.
    """
    loop = asyncio.get_event_loop()
    code = await loop.run_in_executor(None, lambda: input("Enter OTP code: "))
    return code


def format_text_output(result: "ScrapingResult") -> str:
    """Format scraping result as human-readable text.

    Parameters
    ----------
    result : ScrapingResult
        The scraping result to format.

    Returns
    -------
    str
        Formatted text output.
    """
    lines = []
    for account in result.accounts:
        lines.append(f"Account: {account.account_number}")
        if account.balance is not None:
            lines.append(f"Balance: {account.balance:,.2f}")
        lines.append(f"Transactions: {len(account.transactions)}")
        lines.append("")
        for txn in sorted(account.transactions, key=lambda t: t.date):
            lines.append(
                f"  {txn.date} | {txn.charged_amount:>10.2f} "
                f"{txn.original_currency} | {txn.description}"
            )
        lines.append("")
    return "\n".join(lines)


def format_json_output(result: "ScrapingResult") -> str:
    """Serialize scraping result to JSON.

    Parameters
    ----------
    result : ScrapingResult
        The scraping result to serialize.

    Returns
    -------
    str
        JSON string.
    """
    return json.dumps(dataclasses.asdict(result), indent=2, ensure_ascii=False)


async def run_scraper(args: argparse.Namespace) -> int:
    """Run the scraper with the given CLI arguments.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments.

    Returns
    -------
    int
        Exit code (0 for success, 1 for failure).
    """
    # Lazy import to avoid import errors before provider modules exist
    from scraper import create_scraper, is_2fa_required
    from scraper.base import ScraperOptions

    provider = args.provider

    if provider not in PROVIDER_CONFIGS:
        print(f"Error: Unknown provider '{provider}'", file=sys.stderr)
        print(
            "Use --list to see available providers.",
            file=sys.stderr,
        )
        return 1

    # Resolve start date
    if args.start_date:
        start_date = date.fromisoformat(args.start_date)
    elif args.days:
        start_date = date.today() - timedelta(days=args.days)
    else:
        start_date = date.today() - timedelta(days=90)

    show_browser = args.headless == "false"

    credentials = gather_credentials(provider)
    options = ScraperOptions(
        start_date=start_date,
        show_browser=show_browser,
        verbose=args.verbose,
    )

    scraper = create_scraper(provider, credentials, options)

    # Set up progress callback
    def on_progress(message: str) -> None:
        print(f"[{provider}] {message}", file=sys.stderr)

    scraper.on_progress = on_progress

    # Set up 2FA callback if needed
    if is_2fa_required(provider):
        scraper.on_otp_request = handle_otp

    result = await scraper.scrape()

    if not result.success:
        print(
            f"Error: {result.error_type} - {result.error_message}",
            file=sys.stderr,
        )
        return 1

    if args.output == "json":
        print(format_json_output(result))
    else:
        print(format_text_output(result))

    return 0


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.list:
        list_providers()
        return

    if not args.provider:
        parser.error("provider is required (or use --list)")

    exit_code = asyncio.run(run_scraper(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
