"""Telegram Bot API sink. Pure stdlib."""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request

from altron.monitor.notifications.base import render_telegram


class TelegramSink:
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str, *, timeout: float = 15.0) -> None:
        if not bot_token or not chat_id:
            raise ValueError("Telegram sink requires bot_token and chat_id")
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._timeout = timeout

    @classmethod
    def from_env(cls) -> "TelegramSink":
        return cls(
            os.environ.get("ALTRON_TELEGRAM_BOT_TOKEN", "").strip(),
            os.environ.get("ALTRON_TELEGRAM_CHAT_ID", "").strip(),
        )

    def send(self, *, monitor: str, url: str, kind: str, summary: str, urgent: bool) -> bool:
        endpoint = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        body = json.dumps(
            {
                "chat_id": self._chat_id,
                "text": render_telegram(monitor, url, kind, summary, urgent),
                "parse_mode": "Markdown",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                return 200 <= response.status < 300
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
            return False
