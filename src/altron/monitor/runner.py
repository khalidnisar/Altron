"""One-shot monitor execution: fetch -> diff -> alert -> notify.

A single call to :func:`run_monitor` performs a complete pass for a monitor:
load state, check the active window, fetch, extract, diff, build alerts, and
dispatch them through every configured channel (unless the alert is inside
quiet hours and not urgent).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from altron.logging_config import get_logger
from altron.monitor.diff import diff_pages, hash_text, values_changed
from altron.monitor.extractors import (
    extract_keywords,
    extract_regex,
    extract_selectors,
    visible_text,
)
from altron.monitor.fetcher import fetch_url
from altron.monitor.models import Alert, Monitor
from altron.monitor.notifications import build_sink
from altron.monitor.storage import MonitorStore

logger = get_logger(__name__)


@dataclass
class MonitorOutcome:
    name: str
    ran: bool
    reason: str = ""
    alerts: list[Alert] = field(default_factory=list)
    dispatched: list[str] = field(default_factory=list)
    error: str | None = None
    change_summary: str = ""


def _in_quiet_hours(monitor: Monitor, moment: datetime) -> bool:
    qh = monitor.notify.quiet_hours
    if qh is None:
        return False
    from altron.monitor.models import _to_local, _time_in_window

    local = _to_local(moment, monitor.timezone)
    return _time_in_window(local.time(), qh.start, qh.end)


def _is_urgent(monitor: Monitor, kind: str, summary: str) -> bool:
    if not (monitor.notify.urgent_keywords or monitor.notify.urgent_regex):
        return False
    text = summary.lower()
    for kw in monitor.notify.urgent_keywords:
        if kw.lower() and kw.lower() in text:
            return True
    for pattern in monitor.notify.urgent_regex:
        if re.search(pattern, summary, flags=re.IGNORECASE):
            return True
    return False


def _is_cooldown(store: MonitorStore, monitor: Monitor, kind: str) -> bool:
    last = store.last_alert_at(monitor.name, kind)
    if last is None:
        return False
    return (datetime.now(UTC) - last).total_seconds() < monitor.notify.cooldown_seconds


def run_monitor(
    monitor: Monitor,
    *,
    store: MonitorStore,
    dry_run: bool = False,
    now: datetime | None = None,
) -> MonitorOutcome:
    now = now or datetime.now(UTC)
    outcome = MonitorOutcome(name=monitor.name, ran=True)

    if not monitor.is_active(now):
        outcome.reason = "outside active window"
        store.record_run(name=monitor.name, ok=True, message=outcome.reason, alert_count=0)
        return outcome

    # --- fetch ----------------------------------------------------------
    result = fetch_url(
        monitor.url,
        method=monitor.method,
        headers=monitor.headers,
        timeout=monitor.timeout_seconds,
    )
    if not result.ok:
        outcome.error = result.error or f"HTTP {result.status_code}"
        store.save_state(
            name=monitor.name,
            url=monitor.url,
            last_hash=None,
            last_text=None,
            last_status=result.status_code,
            last_error=outcome.error,
        )
        store.record_run(name=monitor.name, ok=False, message=outcome.error, alert_count=0)
        return outcome

    # --- normalize ------------------------------------------------------
    text = visible_text(result.text, monitor.diff.ignore_selectors)
    new_hash = hash_text(text)
    state = store.get_state(monitor.name)
    old_hash = state["last_hash"] if state else None
    old_text = state["last_text"] if state else None
    old_values: dict[str, Any] = {}
    if state and state.get("last_values_json"):
        try:
            old_values = json.loads(state["last_values_json"])
        except (json.JSONDecodeError, TypeError):
            old_values = {}

    # --- page diff ------------------------------------------------------
    alerts: list[Alert] = []
    if old_hash is None:
        outcome.change_summary = "baseline recorded"
    else:
        diff = diff_pages(
            old_text or "",
            text,
            min_change_chars=monitor.diff.min_change_chars,
        )
        if diff.changed:
            outcome.change_summary = "page changed"
            alerts.append(
                Alert(
                    monitor=monitor.name,
                    url=monitor.url,
                    kind="page_change",
                    summary=diff.new_excerpt,
                )
            )

    # --- selectors ------------------------------------------------------
    new_values: dict[str, Any] = {}
    if monitor.selectors:
        extraction = extract_selectors(result.text, monitor.selectors)
        for selector, payload in extraction.items():
            new_values[selector] = payload.values
            old = old_values.get(selector, [])
            if old and values_changed(old, payload.values):
                alerts.append(
                    Alert(
                        monitor=monitor.name,
                        url=monitor.url,
                        kind="selector_change",
                        summary=f"{selector}: {payload.values}",
                        details={"selector": selector, "old": old, "new": payload.values},
                    )
                )

    # --- keywords -------------------------------------------------------
    if monitor.keywords:
        presence = extract_keywords(result.text, monitor.keywords)
        old_presence: dict[str, int] = {}
        stored = old_values.get("__keywords__", {})
        if isinstance(stored, dict):
            old_presence = {k: int(v) for k, v in stored.items()}
        for kw, is_present in presence.items():
            if kw in old_presence:
                was_present = bool(old_presence[kw])
                if is_present != was_present:
                    alerts.append(
                        Alert(
                            monitor=monitor.name,
                            url=monitor.url,
                            kind="keyword_match",
                            summary=f"{'appeared' if is_present else 'disappeared'}: {kw}",
                            details={"keyword": kw, "present": is_present},
                        )
                    )
        new_values["__keywords__"] = {k: int(v) for k, v in presence.items()}

    # --- regex ----------------------------------------------------------
    if monitor.regex:
        match = extract_regex(result.text, monitor.regex)
        old_match = old_values.get("__regex__")
        if match.found and old_match is not None and old_match != match.values:
            alerts.append(
                Alert(
                    monitor=monitor.name,
                    url=monitor.url,
                    kind="regex_match",
                    summary=f"regex matched: {match.values}",
                    details={"regex": monitor.regex, "matches": match.values},
                )
            )
        new_values["__regex__"] = match.values

    outcome.alerts = alerts

    # --- state ----------------------------------------------------------
    page_changed = bool(alerts and any(a.kind == "page_change" for a in alerts))
    store.save_state(
        name=monitor.name,
        url=monitor.url,
        last_hash=new_hash,
        last_text=text[:500],  # keep the row small; we only need it for excerpts
        last_status=result.status_code,
        last_error=None,
        last_values=new_values,
        changed=page_changed,
    )

    # --- notify ---------------------------------------------------------
    if not alerts:
        store.record_run(
            name=monitor.name,
            ok=True,
            message=outcome.change_summary or "no change",
            alert_count=0,
        )
        return outcome

    quiet = _in_quiet_hours(monitor, now)
    for alert in alerts:
        urgent = _is_urgent(monitor, alert.kind, alert.summary)
        if quiet and not urgent and not monitor.notify.digest_on_quiet:
            continue
        if _is_cooldown(store, monitor, alert.kind) and not urgent:
            continue
        alert.urgent = urgent
        if dry_run:
            continue
        store.record_alert(
            name=alert.monitor,
            kind=alert.kind,
            summary=alert.summary,
            details=alert.details,
            urgent=urgent,
        )
        for channel in monitor.notify.channels:
            try:
                sink = build_sink(channel)
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not build sink %s: %s", channel, exc)
                continue
            if sink.send(
                monitor=alert.monitor,
                url=alert.url,
                kind=alert.kind,
                summary=alert.summary,
                urgent=urgent,
            ):
                outcome.dispatched.append(channel)
            else:
                logger.warning("channel %s failed for %s", channel, monitor.name)

    store.record_run(
        name=monitor.name,
        ok=True,
        message=outcome.change_summary or "alerts dispatched",
        alert_count=len(alerts),
    )
    return outcome
