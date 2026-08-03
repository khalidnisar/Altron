"""Tiny shared types for notification channels."""

from __future__ import annotations

from typing import Protocol


class NotificationSink(Protocol):
    name: str

    def send(self, *, monitor: str, url: str, kind: str, summary: str, urgent: bool) -> bool:
        """Send one alert. Return True on success, False on failure."""
        ...


def render_text(monitor: str, url: str, kind: str, summary: str, urgent: bool) -> str:
    head = "🚨 URGENT " if urgent else ""
    return f"{head}[{kind}] {monitor}\n{url}\n\n{summary}\n"


def render_telegram(monitor: str, url: str, kind: str, summary: str, urgent: bool) -> str:
    head = "🚨 *URGENT* " if urgent else ""
    safe_url = url.replace(")", "%29")
    return f"{head}*{kind}* — `{monitor}`\n{summary}\n[Open page]({safe_url})"
