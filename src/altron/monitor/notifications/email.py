"""SMTP email sink. Standard library only — no extra dependencies."""

from __future__ import annotations

import os
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime

from altron.monitor.notifications.base import render_text


class EmailSink:
    name = "email"

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        sender: str,
        recipients: list[str],
        *,
        use_tls: bool = True,
        timeout: float = 20.0,
    ) -> None:
        if not (host and port and sender and recipients):
            raise ValueError("Email sink requires host, port, sender, and recipients")
        self._host = host
        self._port = int(port)
        self._user = user
        self._password = password
        self._sender = sender
        self._recipients = recipients
        self._use_tls = use_tls
        self._timeout = timeout

    @classmethod
    def from_env(cls) -> "EmailSink":
        recipients = [
            r.strip() for r in os.environ.get("ALTRON_EMAIL_TO", "").split(",") if r.strip()
        ]
        return cls(
            host=os.environ.get("ALTRON_SMTP_HOST", "").strip(),
            port=int(os.environ.get("ALTRON_SMTP_PORT", "587")),
            user=os.environ.get("ALTRON_SMTP_USER", "").strip(),
            password=os.environ.get("ALTRON_SMTP_PASSWORD", "").strip(),
            sender=os.environ.get("ALTRON_EMAIL_FROM", "").strip(),
            recipients=recipients,
            use_tls=os.environ.get("ALTRON_SMTP_TLS", "1") not in {"0", "false", "False"},
        )

    def send(self, *, monitor: str, url: str, kind: str, summary: str, urgent: bool) -> bool:
        message = EmailMessage()
        message["Subject"] = f"[Altron {'URGENT ' if urgent else ''}monitor] {monitor}: {kind}"
        message["From"] = self._sender
        message["To"] = ", ".join(self._recipients)
        message["Date"] = format_datetime(datetime.now(UTC))
        message.set_content(render_text(monitor, url, kind, summary, urgent))
        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                smtp.ehlo()
                if self._use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                if self._user:
                    smtp.login(self._user, self._password)
                smtp.sendmail(self._sender, self._recipients, message.as_string())
            return True
        except (smtplib.SMTPException, OSError):
            return False
