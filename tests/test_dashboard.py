from __future__ import annotations

from pathlib import Path

import pytest


def test_dashboard_renders_all_command_center_tabs() -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    dashboard = Path(__file__).parents[1] / "src" / "altron" / "dashboard.py"
    app = AppTest.from_file(str(dashboard)).run(timeout=30)
    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "Overview",
        "Chart & signals",
        "Backtest lab",
        "Pine lab",
        "Deployments",
        "Live statistics",
        "Brokers",
        "Leaderboard",
        "Sweet spot test",
        "Free market data",
    ]
