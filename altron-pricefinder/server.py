#!/usr/bin/env python3
"""Altron PriceFinder - local static server + privacy proxy.

Serves the web app and proxies live-web search (SerpAPI) and currency
rates server-side, so API keys and geo-spoofing parameters never have to
leave your machine.

Usage:
    python3 server.py [port]            # default 8000
    PORT=8000 SERPAPI_KEY=... python3 server.py

Environment:
    SERPAPI_KEY   optional SerpAPI key (https://serpapi.com). Without it
                  the app runs in demo mode, which is fully functional.

Endpoints:
    GET /                 the app (static files)
    GET /api/search?...   proxy to SerpAPI (engine, q, gl, hl, currency, ...)
    GET /api/fx           proxy to free FX rate APIs (USD base)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERPAPI_URL = "https://serpapi.com/search.json"
FX_ENDPOINTS = [
    "https://open.er-api.com/v6/latest/USD",
    "https://api.frankfurter.app/latest?from=USD",
    "https://api.frankfurter.dev/v1/latest?base=USD",
]
UA = "Altron-PriceFinder/1.0 (local privacy proxy)"


def fetch_json(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    # ---- helpers -------------------------------------------------------
    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:  # permissive CORS for local tooling
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    # ---- routes ---------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/search":
            return self.api_search(urllib.parse.parse_qs(parsed.query))
        if parsed.path == "/api/fx":
            return self.api_fx()
        if parsed.path == "/api/health":
            return self._send(200, {"ok": True, "serpapi_key_set": bool(self._key())})
        return super().do_GET()

    def api_search(self, qs) -> None:
        api_key = self._key(qs)
        if not api_key:
            return self._send(400, {
                "error": "no_api_key",
                "hint": "Set SERPAPI_KEY in your environment, or add your key in the app's Settings panel.",
            })
        engine = (qs.get("engine") or ["google_shopping"])[0]
        query = (qs.get("q") or [""])[0]
        params = {"engine": engine, "q": query, "api_key": api_key}
        for key in ("gl", "hl", "location", "google_domain", "num", "start", "currency", "max_price", "min_price"):
            if qs.get(key):
                params[key] = qs[key][0]
        url = SERPAPI_URL + "?" + urllib.parse.urlencode(params)
        try:
            data = fetch_json(url)
            data["_proxied_by"] = "altron-pricefinder"
            return self._send(200, data)
        except Exception as exc:  # sandbox/offline or upstream failure
            return self._send(502, {"error": "proxy_upstream_failed", "detail": str(exc)[:300]})

    def api_fx(self) -> None:
        for url in FX_ENDPOINTS:
            try:
                return self._send(200, fetch_json(url, timeout=15))
            except Exception:
                continue
        return self._send(502, {"error": "fx_unavailable"})

    def _key(self, qs=None) -> str:
        env_key = os.environ.get("SERPAPI_KEY", "").strip()
        if env_key:
            return env_key
        if qs and (qs.get("api_key") or [""])[0]:
            return qs["api_key"][0].strip()
        return ""

    def log_message(self, fmt: str, *args) -> None:  # quieter logs
        if "/api/" not in (fmt % args):
            print("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), fmt % args))


def main() -> None:
    port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8000))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"\n  Altron PriceFinder running at http://0.0.0.0:{port}")
    print("  Live web search: " + ("ON (SERPAPI_KEY set)" if os.environ.get("SERPAPI_KEY") else "OFF - demo mode (set SERPAPI_KEY for live web)"))
    print("  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        server.server_close()


if __name__ == "__main__":
    main()
