"""Argparse entry point for ``altron monitor …``."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from altron.config import Settings
from altron.logging_config import configure_logging, get_logger
from altron.monitor.config import (
    dump_monitor_yaml,
    list_monitor_files,
    load_monitor_file,
    load_monitors_from_directory,
)
from altron.monitor.models import Monitor
from altron.monitor.notifications import build_sink
from altron.monitor.runner import run_monitor
from altron.monitor.storage import MonitorStore

logger = get_logger(__name__)

DEFAULT_MONITORS_DIR = "examples/monitors"
DEFAULT_DB_PATH = "data/monitor.sqlite"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="altron monitor",
        description="Watch websites for changes and notify you via Telegram or email.",
    )
    parser.add_argument(
        "--monitors-dir",
        default=os.environ.get("ALTRON_MONITORS_DIR", DEFAULT_MONITORS_DIR),
        help=f"Directory of monitor YAML files (default: {DEFAULT_MONITORS_DIR})",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("ALTRON_MONITOR_DB", DEFAULT_DB_PATH),
        help=f"SQLite path for state and history (default: {DEFAULT_DB_PATH})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List every monitor in the monitors dir")
    show = sub.add_parser("show", help="Show a single monitor's resolved config")
    show.add_argument("name")

    add = sub.add_parser("add", help="Scaffold a new monitor YAML")
    add.add_argument("--name", required=True)
    add.add_argument("--url", required=True)
    add.add_argument("--interval", default="15m")
    add.add_argument("--selector", action="append", default=[])
    add.add_argument("--keyword", action="append", default=[])
    add.add_argument("--regex", default=None)
    add.add_argument("--days", help="Comma-separated: mon,tue,wed,thu,fri,sat,sun")
    add.add_argument("--hours", help="HH:MM-HH:MM, e.g. 09:00-21:00")
    add.add_argument("--tz", default="UTC")
    add.add_argument("--active-from")
    add.add_argument("--active-until")
    add.add_argument(
        "--notify",
        default="log",
        help="Comma-separated channels: log,telegram,email",
    )
    add.add_argument("--overwrite", action="store_true")

    rm = sub.add_parser("remove", help="Delete a monitor YAML (and clear its state)")
    rm.add_argument("name")
    rm.add_argument("--keep-state", action="store_true")

    run = sub.add_parser("run", help="Run a single monitor once")
    run.add_argument("name")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--quiet", action="store_true")

    sub.add_parser("run-all", help="Run every active monitor once and exit")

    hist = sub.add_parser("history", help="Show recent alerts for a monitor")
    hist.add_argument("name")
    hist.add_argument("--limit", type=int, default=20)

    test = sub.add_parser("test-notify", help="Send a test message through a single channel")
    test.add_argument("channel", help="log | telegram | email")
    test.add_argument("--monitor", default="manual-test")
    return parser


def _monitor_path(directory: str, name: str) -> Path:
    return Path(directory) / f"{name}.yaml"


def _cmd_list(args: argparse.Namespace) -> int:
    files = list_monitor_files(args.monitors_dir)
    if not files:
        print(f"No monitor YAML files found in {args.monitors_dir}")
        return 0
    for path in files:
        try:
            monitor = load_monitor_file(path)
        except Exception as exc:  # noqa: BLE001
            print(f"⚠ {path.name}: {exc}")
            continue
        print(f"• {monitor.name}  ({monitor.interval})  {monitor.url}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    for path in list_monitor_files(args.monitors_dir):
        try:
            monitor = load_monitor_file(path)
        except Exception:  # noqa: BLE001
            continue
        if monitor.name == args.name:
            print(
                yaml.safe_dump(
                    monitor.model_dump(mode="json"), sort_keys=False, allow_unicode=True
                )
            )
            return 0
    print(f"No monitor named {args.name!r} in {args.monitors_dir}")
    return 1


def _cmd_add(args: argparse.Namespace) -> int:
    path = _monitor_path(args.monitors_dir, args.name)
    if path.exists() and not args.overwrite:
        print(f"Refusing to overwrite {path} (use --overwrite to force)")
        return 2
    monitor = Monitor(
        name=args.name,
        url=args.url,
        interval=args.interval,
        selectors=list(args.selector or []),
        keywords=list(args.keyword or []),
        regex=args.regex,
        days_of_week=args.days,
        hours_of_day=args.hours,
        timezone=args.tz,
        active_from=args.active_from,
        active_until=args.active_until,
    )
    if args.notify:
        monitor.notify.channels = [c.strip() for c in args.notify.split(",") if c.strip()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_monitor_yaml(monitor))
    print(f"Wrote {path}")
    return 0


def _cmd_remove(args: argparse.Namespace) -> int:
    path = _monitor_path(args.monitors_dir, args.name)
    if not path.exists():
        print(f"No monitor named {args.name!r}")
        return 1
    path.unlink()
    if not args.keep_state:
        MonitorStore(args.db).clear_monitor(args.name)
        print(f"Deleted {path} and cleared its state from {args.db}")
    else:
        print(f"Deleted {path}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    store = MonitorStore(args.db)
    monitor = _find_monitor(args.monitors_dir, args.name)
    if monitor is None:
        print(f"No monitor named {args.name!r}")
        return 1
    outcome = run_monitor(monitor, store=store, dry_run=args.dry_run)
    return 0 if _print_outcome(outcome, quiet=args.quiet) else 1


def _cmd_run_all(args: argparse.Namespace) -> int:
    store = MonitorStore(args.db)
    monitors = load_monitors_from_directory(args.monitors_dir)
    if not monitors:
        print(f"No monitors in {args.monitors_dir}")
        return 0
    failures = 0
    for monitor in monitors:
        outcome = run_monitor(monitor, store=store)
        if not _print_outcome(outcome):
            failures += 1
    if failures:
        print(f"{failures} monitor(s) reported an error", file=sys.stderr)
        return 1
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    rows = MonitorStore(args.db).recent_alerts(args.name, limit=args.limit)
    if not rows:
        print(f"No alerts recorded for {args.name!r}")
        return 0
    for row in rows:
        flag = "URGENT" if row["urgent"] else "     "
        print(f"{row['detected_at']}  {flag}  [{row['kind']}]  {row['summary']}")
    return 0


def _cmd_test_notify(args: argparse.Namespace) -> int:
    try:
        sink = build_sink(args.channel)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not build {args.channel!r} sink: {exc}")
        return 1
    ok = sink.send(
        monitor=args.monitor,
        url="https://example.com",
        kind="test",
        summary="This is a test alert from `altron monitor test-notify`.",
        urgent=False,
    )
    print(f"{args.channel}: {'OK' if ok else 'FAILED'}")
    return 0 if ok else 2


def _find_monitor(directory: str, name: str) -> Monitor | None:
    for path in list_monitor_files(directory):
        try:
            monitor = load_monitor_file(path)
        except Exception:  # noqa: BLE001
            continue
        if monitor.name == name:
            return monitor
    return None


def _print_outcome(outcome, *, quiet: bool = False) -> bool:
    """Print a one-line summary. Returns True if the run was healthy."""
    if not outcome.ran:
        print(f"⏭  {outcome.name}: {outcome.reason or 'skipped'}")
        return True
    if outcome.error:
        print(f"✖  {outcome.name}: {outcome.error}")
        return False
    if not outcome.alerts:
        if not quiet:
            tag = outcome.change_summary or "no change"
            print(f"· {outcome.name}: {tag}")
        return True
    flags = ",".join(outcome.dispatched) or "no-channel"
    print(f"✦ {outcome.name}: {len(outcome.alerts)} alert(s) -> [{flags}]")
    for alert in outcome.alerts:
        print(f"    - [{alert.kind}] {alert.summary}")
    return True


def main(argv: list[str] | None = None) -> int:
    Settings().ensure_directories()
    configure_logging(Settings().log_level)
    args = build_parser().parse_args(argv)
    handlers = {
        "list": _cmd_list,
        "show": _cmd_show,
        "add": _cmd_add,
        "remove": _cmd_remove,
        "run": _cmd_run,
        "run-all": _cmd_run_all,
        "history": _cmd_history,
        "test-notify": _cmd_test_notify,
    }
    return handlers[args.command](args)
