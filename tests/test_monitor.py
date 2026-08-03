"""Tests for the website monitor.

The monitor is intentionally small: a few extractors, a hash-based
diff, a state store, three notification channels, and a runner. These
tests cover each layer in isolation plus a couple of end-to-end passes
with a fake fetcher.
"""

from __future__ import annotations

import textwrap
from datetime import UTC, datetime, time
from pathlib import Path

import pytest

from altron.monitor.config import (
    dump_monitor_yaml,
    load_monitor_file,
    load_monitors_from_directory,
)
from altron.monitor.diff import diff_pages, hash_text, values_changed
from altron.monitor.extractors import (
    extract_keywords,
    extract_regex,
    extract_selectors,
    strip_ignored,
    visible_text,
)
from altron.monitor.models import Monitor, _time_in_window
from altron.monitor.notifications.email import EmailSink
from altron.monitor.notifications.log import LogSink
from altron.monitor.notifications.telegram import TelegramSink
from altron.monitor.runner import run_monitor
from altron.monitor.storage import MonitorStore


# --------------------------------------------------------------------------- #
# models
# --------------------------------------------------------------------------- #


def test_monitor_validation():
    m = Monitor(name="price", url="https://example.com", interval="15m")
    assert m.interval == "15m"
    with pytest.raises(ValueError):
        Monitor(name="price", url="https://example.com", interval="forever")
    with pytest.raises(ValueError):
        Monitor(name="bad name!", url="https://example.com")
    with pytest.raises(ValueError):
        Monitor(name="x", url="ftp://example.com")


def test_hours_of_day_parsing():
    m = Monitor(name="x", url="https://example.com", hours_of_day="09:00-21:00")
    assert m.hours_of_day is not None
    assert m.hours_of_day[0].hour == 9
    assert m.hours_of_day[1].hour == 21


def test_time_in_window_wrap_midnight():
    assert _time_in_window(time(23, 0), time(22, 0), time(6, 0))
    assert _time_in_window(time(5, 0), time(22, 0), time(6, 0))
    assert not _time_in_window(time(7, 0), time(22, 0), time(6, 0))


def test_active_window():
    m = Monitor(
        name="x",
        url="https://example.com",
        days_of_week="sat,sun",
        hours_of_day="10:00-20:00",
        timezone="UTC",
    )
    sat_midday = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    sun_morning = datetime(2026, 8, 2, 9, 0, tzinfo=UTC)
    fri_morning = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
    assert m.is_active(sat_midday)
    assert not m.is_active(sun_morning)
    assert not m.is_active(fri_morning)


# --------------------------------------------------------------------------- #
# extractors (stdlib HTMLParser)
# --------------------------------------------------------------------------- #


def test_extract_selectors_basic():
    html = '<html><body><span class="price">$19.99</span><span class="price">was $29.99</span></body></html>'
    result = extract_selectors(html, [".price"])
    assert result[".price"].values == ["$19.99", "was $29.99"]


def test_extract_selectors_by_id():
    html = '<html><body><div id="main"><span>hello</span></div></body></html>'
    result = extract_selectors(html, ["#main"])
    assert result["#main"].values == ["hello"]


def test_extract_selectors_unsupported():
    result = extract_selectors("<html></html>", ["div > span"])  # combinator not supported
    assert "unsupported" in result["div > span"].error


def test_extract_keywords():
    html = "<html><body>Welcome to our SALE. Limited time only!</body></html>"
    presence = extract_keywords(html, ["sale", "out of stock", "launch"])
    assert presence == {"sale": True, "out of stock": False, "launch": False}


def test_extract_regex():
    html = "Today only: $199.99 (was $249.00)"
    result = extract_regex(html, r"\$\s?[0-9]+(?:\.[0-9]{2})?")
    assert result.found
    assert len(result.values) == 2


def test_strip_ignored():
    html = "<html><body><nav>noise</nav><main>real content</main><footer>more noise</footer></body></html>"
    cleaned = strip_ignored(html, ["nav", "footer"])
    assert "noise" not in cleaned
    assert "real content" in cleaned


def test_strip_ignored_by_id():
    html = '<html><body><div id="cookie">accept cookies</div><p>real content</p></body></html>'
    cleaned = strip_ignored(html, ["#cookie"])
    assert "accept cookies" not in cleaned
    assert "real content" in cleaned


def test_visible_text():
    html = "<html><head><style>body{}</style></head><body><h1>Hello</h1><script>var x=1</script></body></html>"
    text = visible_text(html)
    assert text == "Hello"


# --------------------------------------------------------------------------- #
# diff
# --------------------------------------------------------------------------- #


def test_diff_identical():
    same = "the quick brown fox jumps over the lazy dog"
    d = diff_pages(same, same)
    assert not d.changed
    assert d.reason == "identical"


def test_diff_below_threshold_is_unchanged():
    old = "the quick brown fox jumps over the lazy dog"
    new = "the quick brown FOX jumps over the lazy dog"  # 1-char change
    d = diff_pages(old, new, min_change_chars=20)
    assert not d.changed
    assert "below threshold" in d.reason


def test_diff_above_threshold_is_changed():
    old = "the quick brown fox jumps over the lazy dog"
    new = old + "  and the cat ran away" * 5
    d = diff_pages(old, new, min_change_chars=20)
    assert d.changed
    assert d.new_excerpt  # an excerpt is provided


def test_values_changed():
    # Order / whitespace changes are normalized away
    assert not values_changed(["a", "b"], ["b", "a"])
    assert not values_changed(["$19.99"], ["  $19.99  "])
    # Real changes are detected
    assert values_changed(["a"], ["a", "c"])
    assert values_changed(["$19.99", "in stock"], ["$9.99", "in stock"])


def test_hash_text_stable_and_short():
    assert hash_text("hello") == hash_text("hello")
    assert hash_text("hello") != hash_text("Hello")
    assert len(hash_text("hello")) == 16  # truncated sha256 prefix


# --------------------------------------------------------------------------- #
# config load / dump
# --------------------------------------------------------------------------- #


def test_load_short_notify_form(tmp_path: Path):
    path = tmp_path / "demo.yaml"
    path.write_text(
        textwrap.dedent(
            """
            name: demo
            url: https://example.com
            interval: 5m
            selectors: [".price"]
            keywords: [sale]
            notify: [log, telegram]
            """
        ).strip()
    )
    monitor = load_monitor_file(path)
    assert monitor.name == "demo"
    assert monitor.selectors == [".price"]
    assert monitor.notify.channels == ["log", "telegram"]


def test_load_long_notify_form(tmp_path: Path):
    path = tmp_path / "demo.yaml"
    path.write_text(
        textwrap.dedent(
            """
            name: demo
            url: https://example.com
            notify:
              channels: [telegram]
              cooldown_seconds: 120
              urgent_keywords: [sale]
            """
        ).strip()
    )
    monitor = load_monitor_file(path)
    assert monitor.notify.cooldown_seconds == 120
    assert monitor.notify.urgent_keywords == ["sale"]


def test_load_and_dump_roundtrip(tmp_path: Path):
    path = tmp_path / "demo.yaml"
    monitor = Monitor(name="demo", url="https://example.com", interval="5m")
    path.write_text(dump_monitor_yaml(monitor))
    reloaded = load_monitor_file(path)
    assert reloaded.name == "demo"
    assert reloaded.interval == "5m"


def test_load_monitors_from_directory_skips_bad(tmp_path: Path):
    (tmp_path / "good.yaml").write_text("name: a\nurl: https://example.com\n")
    (tmp_path / "bad.yaml").write_text("name: bad name!\nurl: https://example.com\n")
    monitors = load_monitors_from_directory(tmp_path)
    assert [m.name for m in monitors] == ["a"]


# --------------------------------------------------------------------------- #
# storage
# --------------------------------------------------------------------------- #


def test_storage_save_and_get(tmp_path: Path):
    store = MonitorStore(tmp_path / "m.sqlite")
    store.save_state(
        name="demo",
        url="https://example.com",
        last_hash="abc",
        last_text="hello",
        last_status=200,
        last_error=None,
        last_values={".price": ["$9.99"]},
        changed=True,
    )
    state = store.get_state("demo")
    assert state is not None
    assert state["last_hash"] == "abc"
    assert state["last_text"] == "hello"


def test_storage_alerts_and_runs_and_clear(tmp_path: Path):
    store = MonitorStore(tmp_path / "m.sqlite")
    store.record_alert(
        name="demo", kind="page_change", summary="page changed",
        details={"added_chars": 5, "removed_chars": 2},
    )
    store.record_run(name="demo", ok=True, message="ok", alert_count=1)
    assert len(store.recent_alerts("demo")) == 1
    store.clear_monitor("demo")
    assert store.get_state("demo") is None
    assert store.recent_alerts("demo") == []


# --------------------------------------------------------------------------- #
# notifications
# --------------------------------------------------------------------------- #


def test_log_sink(caplog):
    sink = LogSink()
    assert sink.send(
        monitor="m", url="https://x", kind="test", summary="hello", urgent=False
    ) is True


def test_telegram_sink_build_from_env(monkeypatch):
    monkeypatch.setenv("ALTRON_TELEGRAM_BOT_TOKEN", "abc")
    monkeypatch.setenv("ALTRON_TELEGRAM_CHAT_ID", "123")
    sink = TelegramSink.from_env()
    assert sink._bot_token == "abc"  # noqa: SLF001
    assert sink._chat_id == "123"  # noqa: SLF001


def test_email_sink_build_from_env(monkeypatch):
    monkeypatch.setenv("ALTRON_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("ALTRON_SMTP_PORT", "587")
    monkeypatch.setenv("ALTRON_SMTP_USER", "u")
    monkeypatch.setenv("ALTRON_SMTP_PASSWORD", "p")
    monkeypatch.setenv("ALTRON_EMAIL_FROM", "from@example.com")
    monkeypatch.setenv("ALTRON_EMAIL_TO", "to1@example.com, to2@example.com")
    sink = EmailSink.from_env()
    assert sink._recipients == ["to1@example.com", "to2@example.com"]  # noqa: SLF001


# --------------------------------------------------------------------------- #
# runner — with a fake fetcher so we don't hit the network
# --------------------------------------------------------------------------- #


class _FakeResult:
    def __init__(self, ok=True, text="", status=200, error=None):
        self.ok = ok
        self.text = text
        self.status_code = status
        self.error = error
        self.headers = {}
        self.elapsed_ms = 12


def test_runner_baseline_then_change(tmp_path: Path, monkeypatch):
    store = MonitorStore(tmp_path / "m.sqlite")
    monitor = Monitor(
        name="demo",
        url="https://example.com",
        interval="15m",
        selectors=[".price"],
    )

    html1 = "<html><body><h1>Hello</h1><span class='price'>$19.99</span></body></html>"
    monkeypatch.setattr(
        "altron.monitor.runner.fetch_url", lambda *a, **k: _FakeResult(ok=True, text=html1)
    )
    outcome = run_monitor(monitor, store=store)
    assert outcome.ran
    assert outcome.alerts == []  # baseline
    assert store.get_state("demo")["last_hash"] is not None

    html2 = "<html><body><h1>Hello</h1><span class='price'>$9.99</span></body></html>"
    monkeypatch.setattr(
        "altron.monitor.runner.fetch_url", lambda *a, **k: _FakeResult(ok=True, text=html2)
    )
    outcome = run_monitor(monitor, store=store)
    assert outcome.alerts, "expected at least one alert on price change"
    assert any(a.kind == "selector_change" for a in outcome.alerts)


def test_runner_keyword_appearance(tmp_path: Path, monkeypatch):
    store = MonitorStore(tmp_path / "m.sqlite")
    monitor = Monitor(
        name="demo",
        url="https://example.com",
        interval="15m",
        keywords=["promo"],
    )
    monkeypatch.setattr(
        "altron.monitor.runner.fetch_url",
        lambda *a, **k: _FakeResult(ok=True, text="<html><body>nothing here</body></html>"),
    )
    run_monitor(monitor, store=store)
    monkeypatch.setattr(
        "altron.monitor.runner.fetch_url",
        lambda *a, **k: _FakeResult(ok=True, text="<html><body>flash PROMO today</body></html>"),
    )
    outcome = run_monitor(monitor, store=store)
    assert any(a.kind == "keyword_match" and "appeared" in a.summary for a in outcome.alerts)


def test_runner_respects_inactive_window(tmp_path: Path, monkeypatch):
    store = MonitorStore(tmp_path / "m.sqlite")
    monitor = Monitor(
        name="demo",
        url="https://example.com",
        interval="15m",
        days_of_week=["sat"],
    )
    called = {"n": 0}

    def fake_fetch(*a, **k):
        called["n"] += 1
        return _FakeResult(ok=True, text="<html><body>x</body></html>")

    monkeypatch.setattr("altron.monitor.runner.fetch_url", fake_fetch)
    monday = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    outcome = run_monitor(monitor, store=store, now=monday)
    assert outcome.reason == "outside active window"
    assert called["n"] == 0


def test_runner_cooldown_suppresses(tmp_path: Path, monkeypatch):
    store = MonitorStore(tmp_path / "m.sqlite")
    monitor = Monitor(
        name="demo",
        url="https://example.com",
        interval="15m",
        keywords=["promo"],
        cooldown_seconds=3600,
    )
    monkeypatch.setattr(
        "altron.monitor.runner.fetch_url",
        lambda *a, **k: _FakeResult(ok=True, text="<html><body>nothing</body></html>"),
    )
    run_monitor(monitor, store=store)
    monkeypatch.setattr(
        "altron.monitor.runner.fetch_url",
        lambda *a, **k: _FakeResult(ok=True, text="<html><body>PROMO now</body></html>"),
    )
    first = run_monitor(monitor, store=store)
    assert first.alerts
    # Same state again: cooldown should suppress the duplicate alert
    second = run_monitor(monitor, store=store)
    assert all(a.urgent for a in second.alerts) or not second.alerts


def test_runner_fetch_failure_recorded(tmp_path: Path, monkeypatch):
    store = MonitorStore(tmp_path / "m.sqlite")
    monitor = Monitor(name="demo", url="https://example.com", interval="15m")
    monkeypatch.setattr(
        "altron.monitor.runner.fetch_url",
        lambda *a, **k: _FakeResult(ok=False, error="connection refused"),
    )
    outcome = run_monitor(monitor, store=store)
    assert outcome.error == "connection refused"
    assert store.get_state("demo")["last_error"] == "connection refused"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def test_cli_add_list_run(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "examples" / "monitors").mkdir(parents=True)
    (tmp_path / "data").mkdir()

    from altron.monitor.cli import main as monitor_main

    rc = monitor_main(
        [
            "--monitors-dir", "examples/monitors",
            "--db", "data/m.sqlite",
            "add",
            "--name", "demo",
            "--url", "https://example.com",
            "--interval", "5m",
            "--selector", ".price",
            "--notify", "log",
        ]
    )
    assert rc == 0
    assert (tmp_path / "examples" / "monitors" / "demo.yaml").exists()

    rc = monitor_main(
        ["--monitors-dir", "examples/monitors", "--db", "data/m.sqlite", "list"]
    )
    assert rc == 0

    def fake_fetch(*a, **k):
        return _FakeResult(ok=True, text="<html><body><span class='price'>$1.00</span></body></html>")

    monkeypatch.setattr("altron.monitor.runner.fetch_url", fake_fetch)
    rc = monitor_main(
        [
            "--monitors-dir", "examples/monitors",
            "--db", "data/m.sqlite",
            "run", "demo", "--dry-run", "--quiet",
        ]
    )
    assert rc == 0
