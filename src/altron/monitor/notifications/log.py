"""Plain log sink — always available, useful for tests and cron output."""

from __future__ import annotations

from altron.logging_config import get_logger
from altron.monitor.notifications.base import render_text


class LogSink:
    name = "log"

    def __init__(self, logger_name: str = "altron.monitor") -> None:
        self._logger = get_logger(logger_name)

    def send(self, *, monitor: str, url: str, kind: str, summary: str, urgent: bool) -> bool:
        self._logger.info(
            "alert monitor=%s kind=%s urgent=%s summary=%s", monitor, kind, urgent, summary
        )
        return True
