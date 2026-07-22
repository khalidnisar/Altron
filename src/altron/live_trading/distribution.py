from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
import urllib.request
from collections import deque
from typing import Protocol

from altron.live_trading.models import SignalEvent

logger = logging.getLogger(__name__)


class SignalSink(Protocol):
    async def publish(self, event: SignalEvent) -> None: ...


class SignalHub:
    """Bounded in-memory feed consumed by the REST API and dashboard."""

    def __init__(self, capacity: int = 1000) -> None:
        self.events: deque[SignalEvent] = deque(maxlen=capacity)
        self._subscribers: set[asyncio.Queue[SignalEvent]] = set()

    async def publish(self, event: SignalEvent) -> None:
        self.events.append(event)
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Dropping live signal for a slow subscriber")

    def recent(self, limit: int = 100) -> list[SignalEvent]:
        return list(self.events)[-limit:]

    def subscribe(self, maxsize: int = 100) -> asyncio.Queue[SignalEvent]:
        queue: asyncio.Queue[SignalEvent] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[SignalEvent]) -> None:
        self._subscribers.discard(queue)


class LoggingSink:
    async def publish(self, event: SignalEvent) -> None:
        logger.info("signal=%s", event.model_dump_json())


def _post_json(url: str, payload: dict[str, object]) -> None:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=10):  # noqa: S310 - operator-provided webhook
        pass


class DiscordSink:
    def __init__(self, webhook_url: str) -> None:
        if not webhook_url.startswith("https://"):
            raise ValueError("Discord webhook must use HTTPS")
        self.webhook_url = webhook_url

    async def publish(self, event: SignalEvent) -> None:
        text = (
            f"{event.timestamp.isoformat()} | {event.strategy} | {event.symbol} "
            f"{event.timeframe} | signal={event.signal:+d} | price={event.entry_price:g} "
            f"| confidence={event.confidence:.0%}"
        )
        try:
            await asyncio.to_thread(_post_json, self.webhook_url, {"content": text})
        except Exception as exc:
            raise RuntimeError(f"Discord delivery failed ({type(exc).__name__})") from None


class TelegramSink:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.url = f"https://api.telegram.org/bot{urllib.parse.quote(bot_token, safe='')}/sendMessage"
        self.chat_id = chat_id

    async def publish(self, event: SignalEvent) -> None:
        text = (
            f"{event.strategy} {event.symbol} {event.timeframe}\n"
            f"Signal: {event.signal:+d} @ {event.entry_price:g}\n"
            f"Confidence: {event.confidence:.0%}"
        )
        try:
            await asyncio.to_thread(
                _post_json, self.url, {"chat_id": self.chat_id, "text": text}
            )
        except Exception as exc:
            raise RuntimeError(f"Telegram delivery failed ({type(exc).__name__})") from None


class CompositeSink:
    def __init__(self, *sinks: SignalSink) -> None:
        self.sinks = sinks

    async def publish(self, event: SignalEvent) -> None:
        results = await asyncio.gather(
            *(sink.publish(event) for sink in self.sinks), return_exceptions=True
        )
        for result in results:
            if isinstance(result, Exception):
                logger.error("Signal sink failed: %s", result)
