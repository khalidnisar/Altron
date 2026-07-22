from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ACCENT = "#6ee7f9"
GREEN = "#35e6a5"
RED = "#ff6685"
PANEL = "rgba(14, 25, 45, .82)"


def _api(
    base: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    parsed_base = urllib.parse.urlsplit(base)
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.hostname:
        raise ValueError("Dashboard API URL must be an http(s) URL with a hostname")
    if parsed_base.username or parsed_base.password:
        raise ValueError("Credentials are not permitted in the dashboard API URL")
    allowed = {
        host.strip().lower()
        for host in os.getenv(
            "ALTRON_ALLOWED_API_HOSTS", "localhost,127.0.0.1,api,host.docker.internal"
        ).split(",")
        if host.strip()
    }
    if parsed_base.hostname.lower() not in allowed:
        raise ValueError(
            f"Dashboard API host {parsed_base.hostname!r} is not in ALTRON_ALLOWED_API_HOSTS"
        )
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    operator_token = os.getenv("ALTRON_OPERATOR_TOKEN")
    if operator_token:
        headers["X-Altron-Operator-Token"] = operator_token
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=8) as response:  # noqa: S310 - operator endpoint
            content = response.read().decode("utf-8")
            return json.loads(content) if content else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API {exc.code}: {detail}") from None


def _style(st: Any) -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{
          background:
            radial-gradient(circle at 10% 0%, rgba(21,92,130,.24), transparent 32%),
            radial-gradient(circle at 95% 15%, rgba(56,38,116,.20), transparent 30%),
            #07101f;
          color: #e7edf8;
        }}
        [data-testid="stSidebar"] {{ background: #091426; border-right: 1px solid #1d3150; }}
        [data-testid="stMetric"] {{
          background: {PANEL}; border: 1px solid #203a5f; border-radius: 14px;
          padding: 14px 16px; box-shadow: 0 10px 30px rgba(0,0,0,.18);
        }}
        [data-testid="stMetricValue"] {{ color: {ACCENT}; font-size: 1.65rem; }}
        .altron-hero {{
          background: linear-gradient(115deg, rgba(15,39,68,.95), rgba(20,28,58,.90));
          border: 1px solid #24466d; border-radius: 18px; padding: 20px 24px; margin-bottom: 18px;
          box-shadow: 0 18px 55px rgba(0,0,0,.25);
        }}
        .altron-hero h1 {{ margin:0; letter-spacing:.02em; font-size:2rem; }}
        .altron-hero p {{ color:#9eb0ca; margin:.45rem 0 0; }}
        .status-dot {{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px}}
        .status-ok {{background:{GREEN};box-shadow:0 0 12px {GREEN}}}
        .status-bad {{background:{RED};box-shadow:0 0 12px {RED}}}
        .small-muted {{ color:#8fa4c1; font-size:.82rem; }}
        div[data-baseweb="tab-list"] {{ gap: 7px; }}
        button[data-baseweb="tab"] {{
          background:#0d1b31; border:1px solid #1d3555; border-radius:10px; padding:8px 13px;
        }}
        button[data-baseweb="tab"][aria-selected="true"] {{ border-color:{ACCENT}; color:{ACCENT}; }}
        .stDataFrame {{ border: 1px solid #203a5f; border-radius: 12px; overflow: hidden; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _percent(value: Any) -> str:
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "—"


def _market_figure(candles: pd.DataFrame, signals: pd.DataFrame | None = None):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    frame = candles.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.78, 0.22],
        vertical_spacing=0.03,
    )
    figure.add_trace(
        go.Candlestick(
            x=frame["timestamp"],
            open=frame["open"],
            high=frame["high"],
            low=frame["low"],
            close=frame["close"],
            increasing_line_color=GREEN,
            decreasing_line_color=RED,
            name="OHLC",
        ),
        row=1,
        col=1,
    )
    if signals is not None and not signals.empty:
        events = signals.copy()
        events["timestamp"] = pd.to_datetime(events["timestamp"], utc=True)
        buys = events.loc[events["signal"].astype(int) > 0]
        sells = events.loc[events["signal"].astype(int) < 0]
        flat = events.loc[events["signal"].astype(int) == 0]
        for selected, color, symbol, label in [
            (buys, GREEN, "triangle-up", "Buy / Long"),
            (sells, RED, "triangle-down", "Sell / Short"),
            (flat, "#f5c451", "x", "Flat"),
        ]:
            if not selected.empty:
                figure.add_trace(
                    go.Scatter(
                        x=selected["timestamp"],
                        y=selected["entry_price"],
                        mode="markers",
                        marker={"size": 13, "color": color, "symbol": symbol, "line": {"width": 1}},
                        text=selected.get("strategy"),
                        name=label,
                    ),
                    row=1,
                    col=1,
                )
    colors = [GREEN if close >= open_ else RED for open_, close in zip(frame["open"], frame["close"], strict=False)]
    figure.add_trace(
        go.Bar(x=frame["timestamp"], y=frame["volume"], marker_color=colors, name="Volume"),
        row=2,
        col=1,
    )
    figure.update_layout(
        height=690,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#091426",
        font={"color": "#b9c7da"},
        margin={"l": 12, "r": 12, "t": 28, "b": 12},
        xaxis_rangeslider_visible=False,
        legend={"orientation": "h", "y": 1.02, "x": 0},
        hovermode="x unified",
    )
    figure.update_xaxes(gridcolor="#162945", showgrid=True)
    figure.update_yaxes(gridcolor="#162945", showgrid=True, side="right")
    return figure


def _backtest_results(st: Any, result: Any, candles: pd.DataFrame, title: str) -> None:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    metrics = result.metrics
    st.subheader(title)
    columns = st.columns(6)
    values = [
        ("Net return", _percent(metrics.get("total_return"))),
        ("Sharpe", f"{metrics.get('sharpe', 0):.2f}"),
        ("Sortino", f"{metrics.get('sortino', 0):.2f}"),
        ("Max drawdown", _percent(metrics.get("max_drawdown"))),
        ("Win rate", _percent(metrics.get("win_rate"))),
        ("Profit factor", f"{metrics.get('profit_factor', 0):.2f}"),
    ]
    for column, (label, value) in zip(columns, values, strict=False):
        column.metric(label, value)

    equity = result.equity
    drawdown = equity / equity.cummax() - 1
    timestamp = pd.to_datetime(candles["timestamp"], utc=True)
    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28])
    figure.add_trace(
        go.Scatter(x=timestamp, y=equity, line={"color": ACCENT, "width": 2}, fill="tozeroy", name="Equity"),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Scatter(x=timestamp, y=drawdown, line={"color": RED}, fill="tozeroy", name="Drawdown"),
        row=2,
        col=1,
    )
    figure.update_layout(
        height=500,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#091426",
        font={"color": "#b9c7da"},
        margin={"l": 10, "r": 10, "t": 24, "b": 10},
        hovermode="x unified",
    )
    figure.update_xaxes(gridcolor="#162945")
    figure.update_yaxes(gridcolor="#162945", side="right")
    st.plotly_chart(figure, use_container_width=True)

    signal_events = result.signals.ne(result.signals.shift(1).fillna(0))
    events = pd.DataFrame(
        {
            "timestamp": timestamp.loc[signal_events],
            "signal": result.signals.loc[signal_events].astype(int),
            "entry_price": candles.loc[signal_events, "close"],
            "strategy": title,
        }
    )
    st.plotly_chart(_market_figure(candles, events), use_container_width=True)
    trades = pd.DataFrame([trade.as_dict() for trade in result.trades])
    if not trades.empty:
        st.markdown("#### Trade ledger")
        st.dataframe(trades, use_container_width=True, hide_index=True)
        st.download_button(
            "Download trades CSV",
            trades.to_csv(index=False),
            file_name="altron-trades.csv",
            mime="text/csv",
        )


def _yaml_parameter_space(space: dict[str, Any]) -> str:
    mapped: dict[str, Any] = {}
    for name, specification in space.items():
        if isinstance(specification, tuple) and len(specification) == 2:
            low, high = specification
            mapped[name] = {
                "type": "int" if isinstance(low, int) and isinstance(high, int) else "float",
                "low": low,
                "high": high,
            }
        else:
            mapped[name] = specification
    return yaml.safe_dump(mapped, sort_keys=False)


def _leaderboard_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    with sqlite3.connect(path) as connection:
        return pd.read_sql_query(
            "SELECT id, created_at, source, symbol, timeframe, strategy, score, robust, "
            "params_json, metrics_json FROM leaderboard ORDER BY robust DESC, score DESC LIMIT 500",
            connection,
        )


def run() -> None:
    try:
        import streamlit as st
    except ImportError as exc:
        raise RuntimeError("Install dashboard dependencies with: pip install '.[dashboard]'") from exc

    st.set_page_config(
        page_title="Altron Quant Command Center",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _style(st)
    st.markdown(
        """
        <div class="altron-hero">
          <h1>⚡ ALTRON <span style="color:#6ee7f9">Quant Command Center</span></h1>
          <p>Research, Pine parity, chart signals, deployment control and paper execution telemetry.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("### Runtime")
        api_base = st.text_input(
            "Signal API",
            os.getenv("ALTRON_SIGNAL_API", "http://localhost:8000"),
            help="Use http://api:8000 from the dashboard Docker service.",
        )
        try:
            health = _api(api_base, "/health")
            online = health.get("status") == "ok"
        except Exception:
            health, online = {}, False
        dot = "status-ok" if online else "status-bad"
        st.markdown(
            f'<span class="status-dot {dot}"></span>{"API connected" if online else "API offline"}',
            unsafe_allow_html=True,
        )
        if online:
            current_mode = _api(api_base, "/runtime/mode")
            st.markdown("### Trading mode")
            broker_paper = st.toggle(
                "Broker paper/demo",
                value=current_mode.get("mode") == "broker_paper",
                help="Off uses local virtual fills. On can route signals only to a connected demo account.",
            )
            if broker_paper:
                broker_states = _api(api_base, "/brokers")
                demo_backends = [
                    item["backend"]
                    for item in broker_states
                    if item["backend"] != "paper"
                    and item["connected"]
                    and item.get("environment") == "demo"
                ]
                if demo_backends:
                    selected_demo = st.selectbox(
                        "Connected demo account",
                        demo_backends,
                        index=(
                            demo_backends.index(current_mode["backend"])
                            if current_mode.get("backend") in demo_backends
                            else 0
                        ),
                    )
                    route_symbol = st.text_input(
                        "Strategy symbol", current_mode.get("symbol") or "BTC/USDT"
                    )
                    broker_symbol = st.text_input(
                        "Broker symbol", current_mode.get("broker_symbol") or route_symbol
                    )
                    demo_quantity = st.number_input(
                        "Demo quantity per strategy",
                        min_value=0.0001,
                        value=float(current_mode.get("quantity") or 1.0),
                        format="%.4f",
                    )
                    acknowledged = st.checkbox("I confirm this is a demo account")
                    if st.button("Apply broker-paper mode", use_container_width=True):
                        try:
                            _api(
                                api_base,
                                "/runtime/mode",
                                method="PATCH",
                                payload={
                                    "mode": "broker_paper",
                                    "backend": selected_demo,
                                    "symbol": route_symbol,
                                    "broker_symbol": broker_symbol,
                                    "quantity": demo_quantity,
                                    "confirmation": (
                                        "ENABLE_DEMO_ORDERS" if acknowledged else ""
                                    ),
                                },
                            )
                            st.success("Broker-paper routing enabled")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                else:
                    st.warning("Link and connect a verified demo account first.")
            elif current_mode.get("mode") != "virtual":
                if st.button("Switch to virtual fills", use_container_width=True):
                    _api(
                        api_base,
                        "/runtime/mode",
                        method="PATCH",
                        payload={"mode": "virtual"},
                    )
                    st.rerun()
            st.caption(
                "Mode: virtual simulator"
                if current_mode.get("mode") == "virtual"
                else f"Mode: {current_mode.get('backend')} demo"
            )
        st.divider()
        st.markdown("### Safety")
        st.info("Virtual mode is default. Broker-paper routing rejects live accounts.")
        leaderboard_path = Path(os.getenv("ALTRON_LEADERBOARD", "data/leaderboard.sqlite"))

    tabs = st.tabs(
        [
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
    )

    with tabs[0]:
        st.subheader("System overview")
        if not online:
            st.warning("Start `altron serve` or `altron paper ...` to populate live telemetry.")
        else:
            overview = _api(api_base, "/overview")
            portfolio = overview.get("portfolio", {})
            metrics = st.columns(6)
            metrics[0].metric("Equity", _money(portfolio.get("equity")))
            metrics[1].metric("Net P&L", _money(portfolio.get("net_pnl")), _percent(portfolio.get("return_pct")))
            metrics[2].metric("Drawdown", _percent(portfolio.get("drawdown")))
            metrics[3].metric("Open positions", portfolio.get("open_positions", 0))
            metrics[4].metric("Signals", overview.get("signal_count", 0))
            metrics[5].metric("Win rate", _percent(portfolio.get("win_rate")))
            equity = pd.DataFrame(_api(api_base, "/equity", params={"limit": 1500}))
            if not equity.empty:
                equity["timestamp"] = pd.to_datetime(equity["timestamp"], utc=True)
                st.line_chart(equity.set_index("timestamp")[["equity"]], color=ACCENT)
            markets = pd.DataFrame(overview.get("tracked_markets", []))
            if not markets.empty:
                st.markdown("#### Tracked markets")
                st.dataframe(markets, use_container_width=True, hide_index=True)

    with tabs[1]:
        header, refresh = st.columns([5, 1])
        header.subheader("TradingView-style market chart")
        refresh.button("↻ Refresh", use_container_width=True)
        controls = st.columns([2, 1, 1, 1])
        symbol = controls[0].text_input("Symbol", "BTC/USDT", key="chart_symbol")
        timeframe = controls[1].selectbox("Timeframe", ["1m", "5m", "15m", "1h", "4h", "1d"], index=3)
        bars = controls[2].selectbox("Bars", [100, 250, 500, 1000], index=2)
        source_filter = controls[3].selectbox("Signals", ["all", "python", "tradingview"])
        if online:
            candles = pd.DataFrame(
                _api(api_base, "/candles", params={"symbol": symbol, "timeframe": timeframe, "limit": bars})
            )
            signals = pd.DataFrame(_api(api_base, "/signals", params={"limit": 1000}))
            if not signals.empty:
                signals = signals.loc[
                    (signals["symbol"] == symbol) & (signals["timeframe"] == timeframe)
                ]
                if source_filter != "all":
                    signals = signals.loc[signals["source"] == source_filter]
            if candles.empty:
                st.info("No live candles for this market yet. Run the matching paper worker.")
            else:
                st.plotly_chart(_market_figure(candles, signals), use_container_width=True)
                if not signals.empty:
                    st.dataframe(
                        signals.sort_values("timestamp", ascending=False),
                        use_container_width=True,
                        hide_index=True,
                    )
        else:
            st.info("Connect the runtime API to display live candles and signal markers.")

    with tabs[2]:
        st.subheader("Backtest laboratory")
        st.caption("Upload normalized OHLCV and evaluate built-in or declarative target-position strategies.")
        uploaded = st.file_uploader("OHLCV CSV or Parquet", type=["csv", "parquet", "pq"], key="bt_data")
        strategy_mode = st.radio("Strategy source", ["Built-in plugin", "Declarative YAML/JSON"], horizontal=True)
        left, right = st.columns(2)
        if strategy_mode == "Built-in plugin":
            from altron.strategies.registry import list_strategies

            strategy_name = left.selectbox("Strategy", list_strategies())
            strategy_definition = None
        else:
            strategy_name = "declarative"
            strategy_definition = left.text_area(
                "Strategy definition",
                Path("examples/rsi_strategy.yaml").read_text() if Path("examples/rsi_strategy.yaml").exists() else "",
                height=220,
            )
        params_text = right.text_area("Parameters (YAML/JSON)", "{}", height=110)
        commission = right.number_input("Commission (bps)", 0.0, 100.0, 5.0, 0.5)
        slippage = right.number_input("Slippage (bps)", 0.0, 100.0, 2.0, 0.5)
        position_fraction = right.slider("Position fraction", 0.01, 1.0, 0.25, 0.01)
        if st.button("Run rigorous backtest", type="primary", disabled=uploaded is None):
            try:
                from altron.backtest.engine import BacktestEngine
                from altron.backtest.models import BacktestConfig
                from altron.data_layer.normalization import normalize_ohlcv
                from altron.strategies.registry import get_strategy
                from altron.strategies.rules import strategy_from_definition

                data = (
                    pd.read_parquet(uploaded)
                    if uploaded.name.lower().endswith((".parquet", ".pq"))
                    else pd.read_csv(uploaded)
                )
                data = normalize_ohlcv(data)
                params = yaml.safe_load(params_text) or {}
                strategy = (
                    get_strategy(strategy_name)
                    if strategy_definition is None
                    else strategy_from_definition(yaml.safe_load(strategy_definition))
                )
                result = BacktestEngine(
                    BacktestConfig(
                        commission_bps=commission,
                        slippage_bps=slippage,
                        position_fraction=position_fraction,
                    )
                ).run(data, strategy, params)
                st.session_state["backtest"] = (result, data, strategy.name)
            except Exception as exc:
                st.error(f"Backtest failed: {exc}")
        if "backtest" in st.session_state:
            result, data, name = st.session_state["backtest"]
            _backtest_results(st, result, data, name)

    with tabs[3]:
        st.subheader("Pine strategy parity lab")
        st.warning(
            "Arbitrary Pine executes only on TradingView. Altron translates a reviewed subset; for any "
            "other Pine strategy, export timestamped target signals and use External Signal mode."
        )
        pine_mode = st.radio("Test mode", ["Translate supported Pine", "External TradingView signals"], horizontal=True)
        pine_data = st.file_uploader("OHLCV CSV", type=["csv"], key="pine_data")
        source = ""
        exported = None
        if pine_mode == "Translate supported Pine":
            source = st.text_area(
                "Pine v5 source",
                Path("examples/ma_crossover.pine").read_text() if Path("examples/ma_crossover.pine").exists() else "",
                height=300,
            )
        else:
            exported = st.file_uploader(
                "Exported signal CSV (`timestamp,signal`)", type=["csv"], key="pine_signals"
            )
            st.caption("Signals may be -1/0/+1 or buy/sell/flat. Sparse targets are carried forward.")
        pcols = st.columns(3)
        pine_commission = pcols[0].number_input("Pine commission (bps)", 0.0, 100.0, 5.0)
        pine_slippage = pcols[1].number_input("Pine slippage (bps)", 0.0, 100.0, 2.0)
        pine_fraction = pcols[2].slider("Pine position fraction", 0.01, 1.0, 0.25)
        disabled = pine_data is None or (pine_mode != "Translate supported Pine" and exported is None)
        if st.button("Run Pine parity backtest", type="primary", disabled=disabled):
            try:
                from altron.backtest.engine import BacktestEngine
                from altron.backtest.models import BacktestConfig
                from altron.backtest.pine_runner import PineBacktestRunner
                from altron.data_layer.normalization import normalize_ohlcv

                data = normalize_ohlcv(pd.read_csv(pine_data))
                runner = PineBacktestRunner(
                    BacktestEngine(
                        BacktestConfig(
                            commission_bps=pine_commission,
                            slippage_bps=pine_slippage,
                            position_fraction=pine_fraction,
                        )
                    )
                )
                pine_result = (
                    runner.run_source(data, source)
                    if pine_mode == "Translate supported Pine"
                    else runner.run_external(data, pd.read_csv(exported))
                )
                st.session_state["pine_result"] = (pine_result, data)
            except Exception as exc:
                st.error(f"Pine parity test failed: {exc}")
        if "pine_result" in st.session_state:
            pine_result, data = st.session_state["pine_result"]
            for warning in pine_result.warnings:
                st.warning(warning)
            if pine_result.translation:
                with st.expander("Translated rule schema"):
                    st.code(yaml.safe_dump(pine_result.translation.schema, sort_keys=False), language="yaml")
            _backtest_results(st, pine_result.backtest, data, f"Pine · {pine_result.mode}")

    with tabs[4]:
        st.subheader("Signal deployments")
        st.caption("A deployment is configuration, not an order. The paper worker loads enabled paper records.")
        if not online:
            st.info("Connect the API to create and manage deployments.")
        else:
            from altron.strategies.registry import list_strategies

            with st.expander("Create deployment", expanded=True):
                dcols = st.columns(3)
                dep_name = dcols[0].text_input("Deployment name")
                dep_strategy = dcols[1].selectbox("Plugin", list_strategies(), key="dep_strategy")
                dep_symbol = dcols[2].text_input("Market", "BTC/USDT", key="dep_symbol")
                dcols2 = st.columns(4)
                dep_timeframe = dcols2[0].selectbox("Bar interval", ["1m", "5m", "15m", "1h", "4h", "1d"], index=3)
                dep_source = dcols2[1].text_input("Data source", "binance")
                dep_backend = dcols2[2].selectbox("Backend", ["paper", "tradovate", "mt5"])
                dep_environment = dcols2[3].selectbox("Environment", ["paper", "demo", "live"])
                dep_params = st.text_area("Deployment parameters", "{}", height=90)
                dep_allocation = st.slider("Capital allocation", 0.01, 1.0, 0.05, 0.01)
                enable_now = st.checkbox("Enable immediately", value=dep_backend == "paper" and dep_environment == "paper")
                if st.button("Create deployment", type="primary"):
                    try:
                        created = _api(
                            api_base,
                            "/deployments",
                            method="POST",
                            payload={
                                "name": dep_name,
                                "strategy": dep_strategy,
                                "params": yaml.safe_load(dep_params) or {},
                                "symbol": dep_symbol,
                                "timeframe": dep_timeframe,
                                "data_source": dep_source,
                                "execution_backend": dep_backend,
                                "environment": dep_environment,
                                "allocation": dep_allocation,
                                "enabled": enable_now,
                            },
                        )
                        st.success(f"Created deployment #{created['id']}")
                    except Exception as exc:
                        st.error(str(exc))
            records = _api(api_base, "/deployments")
            if records:
                deployments = pd.DataFrame(records)
                st.dataframe(deployments, use_container_width=True, hide_index=True)
                selected_id = st.selectbox(
                    "Manage deployment",
                    [record["id"] for record in records],
                    format_func=lambda value: next(
                        f"#{item['id']} · {item['name']} · {'enabled' if item['enabled'] else 'disabled'}"
                        for item in records
                        if item["id"] == value
                    ),
                )
                selected_record = next(item for item in records if item["id"] == selected_id)
                b1, b2 = st.columns(2)
                if b1.button("Enable" if not selected_record["enabled"] else "Disable"):
                    try:
                        _api(
                            api_base,
                            f"/deployments/{selected_id}",
                            method="PATCH",
                            payload={"enabled": not selected_record["enabled"]},
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
                if b2.button("Delete", type="secondary"):
                    _api(api_base, f"/deployments/{selected_id}", method="DELETE")
                    st.rerun()
            else:
                st.info("No deployment records yet.")

    with tabs[5]:
        st.subheader("Live paper-trade statistics")
        if not online:
            st.info("Connect the paper worker API to see portfolio telemetry.")
        else:
            portfolio = _api(api_base, "/portfolio")
            cards = st.columns(7)
            card_values = [
                ("Equity", _money(portfolio.get("equity"))),
                ("Cash", _money(portfolio.get("cash"))),
                ("Net P&L", _money(portfolio.get("net_pnl"))),
                ("Return", _percent(portfolio.get("return_pct"))),
                ("Drawdown", _percent(portfolio.get("drawdown"))),
                ("Win rate", _percent(portfolio.get("win_rate"))),
                ("Profit factor", portfolio.get("profit_factor") or "—"),
            ]
            for card, (label, value) in zip(cards, card_values, strict=False):
                card.metric(label, value)
            if portfolio.get("halted"):
                st.error("CIRCUIT BREAKER ACTIVE — virtual positions have been liquidated.")
            equity = pd.DataFrame(_api(api_base, "/equity", params={"limit": 5000}))
            if not equity.empty:
                equity["timestamp"] = pd.to_datetime(equity["timestamp"], utc=True)
                st.area_chart(equity.set_index("timestamp")[["equity"]], color=ACCENT)
            positions = pd.DataFrame(portfolio.get("positions", []))
            fills = pd.DataFrame(_api(api_base, "/fills", params={"limit": 1000}))
            ptab, ftab = st.tabs(["Open positions", "Fills"])
            with ptab:
                st.dataframe(positions, use_container_width=True, hide_index=True)
            with ftab:
                st.dataframe(fills, use_container_width=True, hide_index=True)

    with tabs[6]:
        st.subheader("Broker connectivity")
        st.caption(
            "Link credentials in process memory, discover accounts, and read positions. "
            "Broker-paper routing only accepts accounts verified as demo."
        )
        if online:
            with st.expander("Link Tradovate or MetaTrader 5 account", expanded=False):
                st.warning(
                    "Use HTTPS when the dashboard and API are on different hosts. Credentials are "
                    "sent once to the API process and are never written to SQLite."
                )
                tradovate_link, mt5_link = st.tabs(["Tradovate", "MetaTrader 5"])
                with tradovate_link:
                    tv_cols = st.columns(3)
                    tv_environment = tv_cols[0].selectbox(
                        "Tradovate environment", ["demo", "live"], key="tv_link_env"
                    )
                    tv_username = tv_cols[1].text_input("Username", key="tv_link_user")
                    tv_password = tv_cols[2].text_input(
                        "Password", type="password", key="tv_link_password"
                    )
                    tv_cols2 = st.columns(3)
                    tv_token = tv_cols2[0].text_input(
                        "Existing access token (optional)", type="password", key="tv_link_token"
                    )
                    tv_app_id = tv_cols2[1].text_input("App ID", key="tv_link_app")
                    tv_account = tv_cols2[2].text_input(
                        "Account ID (optional)", key="tv_link_account"
                    )
                    if st.button("Link Tradovate account", key="link_tradovate"):
                        try:
                            status = _api(
                                api_base,
                                "/brokers/tradovate/link",
                                method="POST",
                                payload={
                                    "environment": tv_environment,
                                    "access_token": tv_token or None,
                                    "username": tv_username or None,
                                    "password": tv_password or None,
                                    "app_id": tv_app_id or None,
                                    "account_id": int(tv_account) if tv_account else None,
                                },
                            )
                            if status["connected"]:
                                st.success("Tradovate account linked")
                            else:
                                st.error(status["message"])
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                with mt5_link:
                    mt_cols = st.columns(2)
                    mt_path = mt_cols[0].text_input(
                        "Terminal executable path", key="mt5_link_path"
                    )
                    mt_server = mt_cols[1].text_input("Broker server", key="mt5_link_server")
                    mt_cols2 = st.columns(2)
                    mt_login = mt_cols2[0].text_input("Account login", key="mt5_link_login")
                    mt_password = mt_cols2[1].text_input(
                        "Account password", type="password", key="mt5_link_password"
                    )
                    if st.button("Link local MT5 terminal", key="link_mt5"):
                        try:
                            status = _api(
                                api_base,
                                "/brokers/mt5/link",
                                method="POST",
                                payload={
                                    "terminal_path": mt_path or None,
                                    "login": int(mt_login) if mt_login else None,
                                    "password": mt_password or None,
                                    "server": mt_server or None,
                                },
                            )
                            if status["connected"]:
                                st.success(
                                    f"MT5 linked and identified as {status['environment']}"
                                )
                            else:
                                st.error(status["message"])
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
            statuses = _api(api_base, "/brokers")
            for status in statuses:
                cols = st.columns([2, 1, 1, 3])
                cols[0].markdown(f"**{status['backend'].upper()}** · {status.get('environment', '')}")
                cols[1].markdown("🟢 connected" if status["connected"] else "🔴 offline")
                cols[2].markdown("execution on" if status.get("execution_enabled") else "read-only")
                cols[3].caption(status.get("message", ""))
                if status["backend"] != "paper":
                    a, b, c = st.columns(3)
                    if a.button("Connect", key=f"connect_{status['backend']}"):
                        _api(api_base, f"/brokers/{status['backend']}/connect", method="POST")
                        st.rerun()
                    if b.button("Disconnect", key=f"disconnect_{status['backend']}"):
                        _api(api_base, f"/brokers/{status['backend']}/disconnect", method="POST")
                        st.rerun()
                    if c.button("Read account", key=f"account_{status['backend']}"):
                        try:
                            st.json(_api(api_base, f"/brokers/{status['backend']}/account"))
                        except Exception as exc:
                            st.error(str(exc))
                st.divider()
            if len(statuses) == 1:
                st.info("Configure Tradovate or MT5 environment variables, then restart the API.")
        else:
            st.info("Broker connectivity status is provided by the runtime API.")

    with tabs[7]:
        st.subheader("Optimization leaderboard")
        leaders = _leaderboard_frame(leaderboard_path)
        if leaders.empty:
            st.info("No leaderboard database yet. Run an optimization or walk-forward analysis.")
        else:
            filters = st.columns(3)
            only_robust = filters[0].toggle("Robust only", value=True)
            selected_symbol = filters[1].selectbox("Asset", ["all", *sorted(leaders["symbol"].unique())])
            selected_tf = filters[2].selectbox("Timeframe", ["all", *sorted(leaders["timeframe"].unique())])
            shown = leaders.copy()
            if only_robust:
                shown = shown.loc[shown["robust"] == 1]
            if selected_symbol != "all":
                shown = shown.loc[shown["symbol"] == selected_symbol]
            if selected_tf != "all":
                shown = shown.loc[shown["timeframe"] == selected_tf]
            st.dataframe(shown.drop(columns=["params_json", "metrics_json"]), use_container_width=True, hide_index=True)
            if not shown.empty:
                selected = st.selectbox(
                    "Inspect run",
                    shown.index,
                    format_func=lambda index: f"#{shown.loc[index, 'id']} · {shown.loc[index, 'strategy']} · {shown.loc[index, 'symbol']}",
                )
                metrics = json.loads(shown.loc[selected, "metrics_json"])
                params = json.loads(shown.loc[selected, "params_json"])
                left, right = st.columns(2)
                left.json(metrics)
                right.json(params)

    with tabs[8]:
        st.subheader("Fast multi-scenario strategy parameter test")
        st.caption(
            "Search a broad parameter space, screen every candidate quickly, then stress the best "
            "across costs, latency, long-only constraints, chronological regimes, high volatility, "
            "and the worst market window. Selection rewards profit while penalizing drawdown, "
            "worst-case behavior, and unstable settings."
        )
        from altron.strategies.registry import get_strategy, list_strategies

        sweet_data = st.file_uploader(
            "Optimization OHLCV CSV or Parquet", type=["csv", "parquet", "pq"], key="sweet_data"
        )
        sleft, sright = st.columns([1, 2])
        sweet_strategy_name = sleft.selectbox(
            "Selected strategy", list_strategies(), key="sweet_strategy"
        )
        default_space = _yaml_parameter_space(get_strategy(sweet_strategy_name).parameter_space)
        sweet_space = sright.text_area(
            "Parameter search space",
            default_space,
            height=180,
            key=f"sweet_space_{sweet_strategy_name}",
            help="Numeric ranges use type/low/high. Lists are categorical choices.",
        )
        fast = st.columns(5)
        sweet_trials = fast[0].number_input("Candidates", 10, 5000, 100, 10)
        sweet_workers = fast[1].number_input(
            "Parallel workers", 1, max(1, min(64, os.cpu_count() or 2)), max(1, min(8, (os.cpu_count() or 2) - 1))
        )
        sweet_retention = fast[2].slider("Full-test retention", 0.10, 1.0, 0.25, 0.05)
        sweet_regimes = fast[3].number_input("Market regimes", 1, 10, 3)
        sweet_cost_stress = fast[4].number_input("Cost stress ×", 1.0, 10.0, 2.0, 0.25)
        risk = st.columns(5)
        sweet_commission = risk[0].number_input("Base commission bps", 0.0, 100.0, 5.0, key="sweet_fee")
        sweet_slippage = risk[1].number_input("Base slippage bps", 0.0, 100.0, 2.0, key="sweet_slip")
        sweet_profit_weight = risk[2].slider("Profit priority", 0.25, 5.0, 2.0, 0.25)
        sweet_risk_penalty = risk[3].slider("Drawdown penalty", 0.5, 8.0, 2.75, 0.25)
        sweet_max_dd = risk[4].slider("Maximum scenario DD", 0.05, 0.80, 0.30, 0.05)
        if st.button(
            "Find robust sweet spot",
            type="primary",
            disabled=sweet_data is None,
            use_container_width=True,
        ):
            try:
                from altron.backtest.models import BacktestConfig
                from altron.data_layer.normalization import normalize_ohlcv
                from altron.optimization.robust import (
                    RobustParameterOptimizer,
                    RobustScoreWeights,
                    RobustTestConfig,
                )

                frame = normalize_ohlcv(
                    pd.read_parquet(sweet_data)
                    if sweet_data.name.lower().endswith((".parquet", ".pq"))
                    else pd.read_csv(sweet_data)
                )
                parameter_space = yaml.safe_load(sweet_space) or {}
                with st.spinner(
                    f"Screening {sweet_trials} combinations with {sweet_workers} workers…"
                ):
                    optimized = RobustParameterOptimizer(
                        BacktestConfig(
                            commission_bps=sweet_commission,
                            slippage_bps=sweet_slippage,
                            position_fraction=0.25,
                        ),
                        RobustTestConfig(
                            trials=int(sweet_trials),
                            workers=int(sweet_workers),
                            retention_ratio=float(sweet_retention),
                            regime_splits=int(sweet_regimes),
                            cost_multiplier=float(sweet_cost_stress),
                            maximum_scenario_drawdown=float(sweet_max_dd),
                            score=RobustScoreWeights(
                                total_return=float(sweet_profit_weight),
                                drawdown_penalty=float(sweet_risk_penalty),
                            ),
                        ),
                    ).optimize(
                        frame,
                        get_strategy(sweet_strategy_name),
                        parameter_space=parameter_space,
                    )
                st.session_state["sweet_result"] = optimized
            except Exception as exc:
                st.error(f"Strategy parameter test failed: {exc}")

        if "sweet_result" in st.session_state:
            optimized = st.session_state["sweet_result"]
            best = optimized.best
            for warning in optimized.warnings:
                st.warning(warning)
            summary_cards = st.columns(7)
            sweet_values = [
                ("Robust score", f"{best.robust_score:.3f}"),
                ("Mean return", _percent(best.mean_return)),
                ("Worst return", _percent(best.worst_return)),
                ("Mean Sharpe", f"{best.mean_sharpe:.2f}"),
                ("Worst drawdown", _percent(best.worst_drawdown)),
                ("Positive scenarios", _percent(best.positive_scenario_ratio)),
                ("Runtime", f"{optimized.elapsed_seconds:.2f}s"),
            ]
            for card, (label, value) in zip(summary_cards, sweet_values, strict=False):
                card.metric(label, value)
            if best.robust:
                st.success("This parameter set passed every configured robustness gate.")
            else:
                st.error("No fully robust set was found. Do not promote this fallback automatically.")
            recommended, ranges = st.columns([1, 2])
            recommended.markdown("#### Recommended settings")
            recommended.json(optimized.sweet_spot["recommended_params"])
            ranges.markdown("#### Stable parameter neighborhood")
            ranges.json(optimized.sweet_spot["stable_ranges"])

            candidate_rows = pd.DataFrame(
                [candidate.summary() for candidate in optimized.candidates]
            )
            candidate_rows["params"] = candidate_rows["params"].map(
                lambda value: json.dumps(value, sort_keys=True)
            )
            st.markdown("#### Candidate ranking")
            st.dataframe(candidate_rows, use_container_width=True, hide_index=True)
            import plotly.express as px

            plot = px.scatter(
                candidate_rows,
                x="worst_drawdown",
                y="mean_return",
                color="robust_score",
                symbol="robust",
                size="positive_scenario_ratio",
                hover_data=["params", "mean_sharpe", "worst_return"],
                color_continuous_scale="Turbo",
                title="Profit / risk candidate map — upper-left is preferred",
            )
            plot.update_layout(
                height=520,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="#091426",
                font={"color": "#b9c7da"},
            )
            st.plotly_chart(plot, use_container_width=True)

            scenario_lookup = {scenario.name: scenario for scenario in optimized.scenarios}
            scenario_rows = []
            for name, metrics in best.scenario_metrics.items():
                scenario_rows.append(
                    {
                        "scenario": name,
                        "category": scenario_lookup[name].category,
                        "bars": scenario_lookup[name].bars,
                        "return": metrics.get("total_return"),
                        "sharpe": metrics.get("sharpe"),
                        "sortino": metrics.get("sortino"),
                        "max_drawdown": metrics.get("max_drawdown"),
                        "profit_factor": metrics.get("profit_factor"),
                    }
                )
            st.markdown("#### Best settings in every scenario")
            st.dataframe(pd.DataFrame(scenario_rows), use_container_width=True, hide_index=True)
            downloadable = {
                **optimized.summary(),
                "top_candidates": [candidate.summary() for candidate in optimized.candidates],
                "best_scenarios": best.scenario_metrics,
            }
            st.download_button(
                "Download complete strategy-test JSON",
                json.dumps(downloadable, indent=2, default=str),
                file_name="altron-sweet-spot.json",
                mime="application/json",
            )

    with tabs[9]:
        st.subheader("Free and public market-data streams")
        st.caption(
            "Start no-key public crypto websockets or delayed no-key stock/forex polling. "
            "Alpaca IEX streaming is also available with free-account API keys."
        )
        if not online:
            st.info("Connect the runtime API before starting a market-data subscription.")
        else:
            catalog = _api(api_base, "/market/catalog")
            feed_controls = st.columns(5)
            asset_class = feed_controls[0].selectbox(
                "Asset class", ["stocks", "forex", "crypto"], key="free_asset"
            )
            market_entries = catalog["markets"][asset_class]
            market_label = feed_controls[1].selectbox(
                "Common symbol",
                [f"{entry['symbol']} · {entry['name']}" for entry in market_entries],
                key="free_market",
            )
            default_symbol = market_label.split(" · ", 1)[0]
            free_symbol = feed_controls[2].text_input(
                "Symbol override", default_symbol, key=f"free_symbol_{asset_class}_{default_symbol}"
            )
            free_timeframe = feed_controls[3].selectbox(
                "Stream timeframe",
                ["1m", "5m", "15m", "1h", "4h", "1d"],
                key="free_tf",
            )
            provider_options = (
                ["auto", "binance"]
                if asset_class == "crypto"
                else (["auto", "yahoo", "alpaca"] if asset_class == "stocks" else ["auto", "yahoo"])
            )
            free_provider = feed_controls[4].selectbox(
                "Provider", provider_options, key="free_provider"
            )
            if free_provider in {"auto", "yahoo"} and asset_class != "crypto":
                st.warning(
                    "Yahoo mode is delayed polling for research and chart display. It has no "
                    "streaming SLA and must not drive execution."
                )
            elif free_provider in {"auto", "binance"} and asset_class == "crypto":
                st.success("Binance public websocket: no API key required for public candles.")
            else:
                st.info("Alpaca IEX requires API keys from a free account in the API environment.")
            if st.button("Start data stream", type="primary", use_container_width=True):
                try:
                    started = _api(
                        api_base,
                        "/market/subscriptions",
                        method="POST",
                        payload={
                            "asset_class": asset_class,
                            "symbol": free_symbol,
                            "timeframe": free_timeframe,
                            "provider": free_provider,
                        },
                    )
                    st.success(f"Started {started['provider']} subscription {started['id']}")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

            subscriptions = _api(api_base, "/market/subscriptions")
            if subscriptions:
                status_frame = pd.DataFrame(subscriptions)
                st.markdown("#### Active subscriptions")
                st.dataframe(status_frame, use_container_width=True, hide_index=True)
                active_ids = [
                    item["id"] for item in subscriptions if item["state"] not in {"stopped"}
                ]
                if active_ids:
                    selected_subscription = st.selectbox(
                        "Stop subscription",
                        active_ids,
                        format_func=lambda value: next(
                            f"{item['symbol']} · {item['timeframe']} · {item['provider']}"
                            for item in subscriptions
                            if item["id"] == value
                        ),
                    )
                    if st.button("Stop selected stream"):
                        _api(
                            api_base,
                            f"/market/subscriptions/{selected_subscription}",
                            method="DELETE",
                        )
                        st.rerun()
                chart_subscription = st.selectbox(
                    "Preview subscription",
                    [item["id"] for item in subscriptions],
                    format_func=lambda value: next(
                        f"{item['symbol']} · {item['timeframe']}"
                        for item in subscriptions
                        if item["id"] == value
                    ),
                )
                preview = next(item for item in subscriptions if item["id"] == chart_subscription)
                preview_candles = pd.DataFrame(
                    _api(
                        api_base,
                        "/candles",
                        params={
                            "symbol": preview["symbol"],
                            "timeframe": preview["timeframe"],
                            "limit": 500,
                        },
                    )
                )
                if not preview_candles.empty:
                    st.plotly_chart(
                        _market_figure(preview_candles), use_container_width=True
                    )
                else:
                    st.info("Waiting for the first closed candle from this feed.")
            else:
                st.info("No free-data streams are active in this API process.")


if __name__ == "__main__":
    run()
