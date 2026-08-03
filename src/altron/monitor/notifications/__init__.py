"""Notification channel implementations."""

from altron.monitor.notifications.base import NotificationSink
from altron.monitor.notifications.email import EmailSink
from altron.monitor.notifications.log import LogSink
from altron.monitor.notifications.telegram import TelegramSink

__all__ = [
    "EmailSink",
    "LogSink",
    "NotificationSink",
    "TelegramSink",
    "build_sink",
]


def build_sink(channel: str) -> NotificationSink:
    channel = channel.strip().lower()
    if channel == "log":
        return LogSink()
    if channel == "telegram":
        return TelegramSink.from_env()
    if channel == "email":
        return EmailSink.from_env()
    raise ValueError(f"unknown notification channel: {channel!r}")
