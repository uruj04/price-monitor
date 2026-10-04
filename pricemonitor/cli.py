"""Command line interface."""

from __future__ import annotations

import argparse
import dataclasses
import logging
import time

from . import __version__
from .alerts import EmailNotifier
from .config import Settings, load_products
from .exceptions import PriceMonitorError
from .logger_config import setup_logging
from .monitor import PriceMonitor
from .storage import PriceHistory

logger = logging.getLogger("pricemonitor")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="price-monitor", description="Track product prices with Playwright."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Check every product's price.")
    run.add_argument("--headed", action="store_true", help="Show the browser window.")
    run.add_argument("--watch", action="store_true", help="Keep checking on a schedule.")
    run.add_argument(
        "--interval", type=int, default=300, help="Seconds between checks in watch mode."
    )

    history = commands.add_parser("history", help="Show recorded prices.")
    history.add_argument("--name", help="Only show one product.")
    history.add_argument("--limit", type=int, default=20, help="Most recent rows to show.")
    return parser


def command_run(args: argparse.Namespace, settings: Settings) -> int:
    if args.headed:
        settings = dataclasses.replace(settings, headless=False)
    if args.interval < 1:
        raise PriceMonitorError("--interval must be at least 1 second.")

    monitor = PriceMonitor(
        settings=settings,
        products=load_products(settings.products_file),
        history=PriceHistory(settings.data_file),
        notifier=EmailNotifier(settings),
    )

    exit_code = 0
    while True:
        summary = monitor.run_once()
        print(
            f"\nChecked {summary.checked} | OK {summary.succeeded} | "
            f"Failed {summary.failed} | Alerts {len(summary.alerts)}"
        )
        if summary.failed:
            exit_code = 2
        if not args.watch:
            return exit_code
        print(f"Next check in {args.interval}s. Press Ctrl+C to stop.")
        time.sleep(args.interval)


def command_history(args: argparse.Namespace, settings: Settings) -> int:
    rows = PriceHistory(settings.data_file).load(args.name)
    if not rows:
        print("No price history yet. Run 'python main.py run' first.")
        return 0

    rows = rows[-max(args.limit, 1):]
    header = f"{'Timestamp':<21}{'Product':<34}{'Price':>10}"
    print(f"\n{header}\n{'-' * len(header)}")
    for row in rows:
        name = row["name"] if len(row["name"]) <= 32 else row["name"][:29] + "..."
        print(f"{row['timestamp']:<21}{name:<34}{float(row['price']):>10.2f}")
    print(f"\n{len(rows)} reading(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        setup_logging(settings.log_file)
        if args.command == "run":
            return command_run(args, settings)
        return command_history(args, settings)
    except PriceMonitorError as exc:
        print(f"Error: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
