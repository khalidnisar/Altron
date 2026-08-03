"""HTTP fetch with retries. Pure stdlib — no third-party dependencies."""

from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; AltronMonitor/1.0)"
DEFAULT_TIMEOUT = 20.0


class FetchResult:
    __slots__ = ("ok", "status_code", "text", "headers", "error", "elapsed_ms")

    def __init__(
        self,
        ok: bool,
        status_code: int = 0,
        text: str = "",
        headers: dict[str, str] | None = None,
        error: str | None = None,
        elapsed_ms: int = 0,
    ) -> None:
        self.ok = ok
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.error = error
        self.elapsed_ms = elapsed_ms


def _request(url: str, headers: dict[str, str], method: str, timeout: float) -> urllib.request.Request:
    return urllib.request.Request(url, method=method, headers=headers)


def fetch_url(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = 2,
) -> FetchResult:
    """Fetch ``url`` with simple retries on transient errors."""
    merged = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "*/*"}
    if headers:
        merged.update(headers)
    last_error: str | None = None
    for attempt in range(max_retries + 1):
        started = time.monotonic()
        req = _request(url, merged, method, timeout)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read()
                # Decode lazily; most pages are utf-8, fall back to latin-1
                charset = response.headers.get_content_charset() or "utf-8"
                try:
                    text = body.decode(charset, errors="replace")
                except LookupError:
                    text = body.decode("utf-8", errors="replace")
                return FetchResult(
                    ok=True,
                    status_code=response.status,
                    text=text,
                    headers=dict(response.headers.items()),
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
        except urllib.error.HTTPError as exc:
            # 5xx → retryable, 4xx → permanent
            if 500 <= exc.code < 600 and attempt < max_retries:
                last_error = f"HTTP {exc.code}"
                time.sleep(1.5 ** attempt)
                continue
            return FetchResult(ok=False, status_code=exc.code, error=f"HTTP {exc.code}")
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            last_error = str(exc) or exc.__class__.__name__
            if attempt < max_retries:
                time.sleep(1.5 ** attempt)
                continue
            return FetchResult(ok=False, error=last_error)
    return FetchResult(ok=False, error=last_error or "max retries exceeded")
