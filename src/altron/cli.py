from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from altron.backtest.engine import BacktestEngine
from altron.backtest.models import BacktestConfig
from altron.backtest.monte_carlo import block_bootstrap
from altron.config import Settings
from altron.data_layer.cache import MarketDataCache
from altron.data_layer.fetchers import AlpacaFetcher, CCXTFetcher, PolygonFetcher, YFinanceFetcher
from altron.data_layer.normalization import normalize_ohlcv
from altron.data_layer.service import MarketDataService
from altron.data_layer.timeframes import timeframe_to_seconds
from altron.optimization.leaderboard import Leaderboard
from altron.optimization.search import StrategyOptimizer, composite_score
from altron.optimization.walk_forward import WalkForwardAnalyzer, WalkForwardConfig
from altron.strategies.base import Strategy
from altron.strategies.pine import PineTranspiler
from altron.strategies.registry import get_strategy, list_strategies


def _parameters(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    path = Path(value)
    payload = path.read_text() if path.exists() else value
    loaded = yaml.safe_load(payload)
    if not isinstance(loaded, dict):
        raise ValueError("Parameters must decode to an object")
    return loaded


def _date(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _source(name: str):
    if name == "yfinance":
        return YFinanceFetcher()
    if name == "alpaca":
        return AlpacaFetcher(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_API_SECRET"])
    if name == "polygon":
        return PolygonFetcher(os.environ["POLYGON_API_KEY"])
    return CCXTFetcher(name)


async def _load_data(args: argparse.Namespace) -> pd.DataFrame:
    if args.input:
        path = Path(args.input)
        if path.suffix.lower() in {".parquet", ".pq"}:
            return normalize_ohlcv(pd.read_parquet(path))
        return normalize_ohlcv(pd.read_csv(path))
    cache = MarketDataCache(args.cache)
    service = MarketDataService(_source(args.source), cache)
    return await service.get_ohlcv(
        args.symbol,
        args.timeframe,
        start=_date(args.start),
        end=_date(args.end),
        limit=args.limit,
        refresh=args.refresh,
    )


def _json_print(payload: object) -> None:
    print(json.dumps(payload, indent=2, default=str, allow_nan=True))


def _research_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Altron strategy backtester and optimizer")
    parser.add_argument("--strategy", default="ma_crossover", choices=list_strategies())
    parser.add_argument("--strategy-file", help="Declarative strategy YAML/JSON file")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--source", default="binance", help="binance/bybit/coinbase/yfinance/alpaca/polygon")
    parser.add_argument("--input", help="Offline CSV or Parquet OHLCV file")
    parser.add_argument("--start", help="ISO-8601 start time")
    parser.add_argument("--end", help="ISO-8601 end time")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache", default="data/market_data.sqlite")
    parser.add_argument("--params", help="Fixed parameter JSON/YAML object or path")
    parser.add_argument("--space", help="Optimization-space JSON/YAML object or path")
    parser.add_argument("--optimize", action="store_true", help="Bayesian parameter search")
    parser.add_argument("--walk-forward", action="store_true", help="Rolling train/test optimization")
    parser.add_argument("--trials", type=int, default=50)
    parser.add_argument("--train-bars", type=int, default=1000)
    parser.add_argument("--test-bars", type=int, default=250)
    parser.add_argument("--commission-bps", type=float, default=5)
    parser.add_argument("--slippage-bps", type=float, default=2)
    parser.add_argument("--position-fraction", type=float, default=1)
    parser.add_argument("--monte-carlo", type=int, default=0, metavar="SIMULATIONS")
    parser.add_argument("--leaderboard", default="data/leaderboard.sqlite")
    parser.add_argument("--output", help="Write JSON result to this path")
    return parser


async def _research(argv: list[str]) -> int:
    args = _research_parser().parse_args(argv)
    data = await _load_data(args)
    if data.empty:
        raise RuntimeError("The data source returned no candles")
    rule_definition: dict[str, Any] | None = None
    strategy: Strategy
    if args.strategy_file:
        from altron.strategies.rules import strategy_from_definition

        rule_definition = _parameters(args.strategy_file)
        strategy = strategy_from_definition(rule_definition)
    else:
        strategy = get_strategy(args.strategy)
    params = _parameters(args.params)
    parameter_space = _parameters(args.space)
    if params and (args.optimize or args.walk_forward):
        raise ValueError("--params is for a fixed backtest; use --space to override a search space")
    engine = BacktestEngine(
        BacktestConfig(
            commission_bps=args.commission_bps,
            slippage_bps=args.slippage_bps,
            position_fraction=args.position_fraction,
        )
    )
    robust = False
    if args.walk_forward:
        analyzer = WalkForwardAnalyzer(
            engine,
            WalkForwardConfig(
                train_bars=args.train_bars,
                test_bars=args.test_bars,
                trials=args.trials,
            ),
        )
        walk = analyzer.run(data, strategy, parameter_space=parameter_space or None)
        selected_params = walk.best_parameters
        payload: dict[str, Any] = {
            "mode": "walk_forward",
            "strategy": strategy.name,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "robust": walk.robust,
            "rejection_reasons": walk.rejection_reasons,
            "best_parameters": selected_params,
            "metrics": walk.aggregate_metrics,
            "folds": [
                {
                    "fold": fold.fold,
                    "train_start": fold.train_start,
                    "train_end": fold.train_end,
                    "test_start": fold.test_start,
                    "test_end": fold.test_end,
                    "params": fold.params,
                    "train_score": fold.train_score,
                    "test_score": fold.test_score,
                    "test_metrics": fold.test_metrics,
                }
                for fold in walk.folds
            ],
        }
        score = walk.aggregate_metrics.get("mean_oos_score", -1e12)
        robust = walk.robust
    elif args.optimize:
        search = StrategyOptimizer(engine).optimize(
            data, strategy, parameter_space=parameter_space or None, trials=args.trials
        )
        selected_params = search.best.params
        payload = {
            "mode": "optimization",
            "strategy": strategy.name,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "best_parameters": selected_params,
            "score": search.best.score,
            "metrics": search.best.metrics,
            "trials": len(search.trials),
            "robust": False,
            "warning": "A single in-sample optimization is not eligible for live-paper promotion; run --walk-forward.",
        }
        score = search.best.score
    else:
        result = engine.run(data, strategy, params)
        selected_params = params
        payload = {
            "mode": "backtest",
            "strategy": strategy.name,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "params": params,
            "metrics": result.metrics,
            "trades": len(result.trades),
        }
        score = composite_score(result.metrics)
        if args.monte_carlo:
            payload["monte_carlo"] = block_bootstrap(
                result.returns, simulations=args.monte_carlo, seed=42
            ).percentiles()
    persisted_params = (
        {"__rule_definition__": rule_definition, "__params__": selected_params}
        if rule_definition is not None
        else selected_params
    )
    Leaderboard(args.leaderboard).add(
        source=args.source,
        symbol=args.symbol,
        timeframe=args.timeframe,
        strategy=strategy.name,
        params=persisted_params,
        metrics=payload.get("metrics", {}),
        score=float(score),
        robust=robust,
    )
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2, default=str))
    _json_print(payload)
    return 0


def _strategy_test(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Fast multi-scenario parameter sweet-spot and risk optimization"
    )
    parser.add_argument("--input", required=True, help="Canonical OHLCV CSV or Parquet")
    parser.add_argument("--strategy", default="ma_crossover", choices=list_strategies())
    parser.add_argument("--strategy-file", help="Declarative strategy YAML/JSON")
    parser.add_argument("--space", help="YAML/JSON search-space override or path")
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--workers", type=int, default=0, help="0 selects available CPU workers")
    parser.add_argument("--retention", type=float, default=0.25)
    parser.add_argument("--regime-splits", type=int, default=3)
    parser.add_argument("--commission-bps", type=float, default=5)
    parser.add_argument("--slippage-bps", type=float, default=2)
    parser.add_argument("--position-fraction", type=float, default=1)
    parser.add_argument("--cost-multiplier", type=float, default=2)
    parser.add_argument("--latency-bars", type=int, default=1)
    parser.add_argument("--profit-weight", type=float, default=2)
    parser.add_argument("--drawdown-penalty", type=float, default=2.75)
    parser.add_argument("--maximum-scenario-drawdown", type=float, default=0.30)
    parser.add_argument("--minimum-scenario-return", type=float, default=-0.15)
    parser.add_argument("--minimum-positive-scenarios", type=float, default=0.60)
    parser.add_argument("--symbol", default="UNKNOWN")
    parser.add_argument("--timeframe", default="unknown")
    parser.add_argument("--source", default="offline")
    parser.add_argument("--leaderboard", default="data/leaderboard.sqlite")
    parser.add_argument("--output", help="Write complete result JSON")
    parser.add_argument("--candidates-output", help="Write tested candidate leaderboard CSV")
    args = parser.parse_args(argv)

    from altron.optimization.robust import (
        RobustParameterOptimizer,
        RobustScoreWeights,
        RobustTestConfig,
    )

    path = Path(args.input)
    data = normalize_ohlcv(
        pd.read_parquet(path) if path.suffix.lower() in {".parquet", ".pq"} else pd.read_csv(path)
    )
    strategy: Strategy
    if args.strategy_file:
        from altron.strategies.rules import strategy_from_definition

        strategy = strategy_from_definition(_parameters(args.strategy_file))
    else:
        strategy = get_strategy(args.strategy)
    parameter_space = _parameters(args.space)
    workers = args.workers or max(1, min(32, (os.cpu_count() or 2) - 1))
    test_config = RobustTestConfig(
        trials=args.trials,
        retention_ratio=args.retention,
        regime_splits=args.regime_splits,
        workers=workers,
        cost_multiplier=args.cost_multiplier,
        latency_bars=args.latency_bars,
        maximum_scenario_drawdown=args.maximum_scenario_drawdown,
        minimum_scenario_return=args.minimum_scenario_return,
        minimum_positive_scenario_ratio=args.minimum_positive_scenarios,
        score=RobustScoreWeights(
            total_return=args.profit_weight,
            drawdown_penalty=args.drawdown_penalty,
        ),
    )
    result = RobustParameterOptimizer(
        BacktestConfig(
            commission_bps=args.commission_bps,
            slippage_bps=args.slippage_bps,
            position_fraction=args.position_fraction,
        ),
        test_config,
    ).optimize(data, strategy, parameter_space=parameter_space or None)
    payload = {
        **result.summary(),
        "strategy": strategy.name,
        "top_candidates": [candidate.summary() for candidate in result.candidates[:25]],
        "best_scenarios": result.best.scenario_metrics,
    }
    if args.candidates_output:
        pd.DataFrame([candidate.summary() for candidate in result.candidates]).drop(
            columns=["params"], errors="ignore"
        ).assign(params=[json.dumps(candidate.params, sort_keys=True) for candidate in result.candidates]).to_csv(
            args.candidates_output, index=False
        )
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2, default=str))
    Leaderboard(args.leaderboard).add(
        source=args.source,
        symbol=args.symbol,
        timeframe=args.timeframe,
        strategy=strategy.name,
        params=result.best.params,
        metrics={**result.best.summary(), "validation_stage": "multi_scenario_in_sample"},
        score=result.best.robust_score,
        # Scenario robustness is not unseen OOS validation. Only walk-forward runs
        # receive leaderboard promotion eligibility.
        robust=False,
    )
    _json_print(payload)
    return 0


def _pine_backtest(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Backtest translated Pine subset or externally exported Pine target signals"
    )
    parser.add_argument("--input", required=True, help="Canonical OHLCV CSV or Parquet")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pine", help="Pine v5 source file for the supported translator subset")
    source.add_argument("--signals", help="CSV exported from any Pine strategy: timestamp,signal")
    parser.add_argument("--commission-bps", type=float, default=5)
    parser.add_argument("--slippage-bps", type=float, default=2)
    parser.add_argument("--position-fraction", type=float, default=1)
    parser.add_argument("--trades-output", help="Optional trade-ledger CSV path")
    args = parser.parse_args(argv)

    from altron.backtest.pine_runner import PineBacktestRunner

    path = Path(args.input)
    data = normalize_ohlcv(
        pd.read_parquet(path) if path.suffix.lower() in {".parquet", ".pq"} else pd.read_csv(path)
    )
    runner = PineBacktestRunner(
        BacktestEngine(
            BacktestConfig(
                commission_bps=args.commission_bps,
                slippage_bps=args.slippage_bps,
                position_fraction=args.position_fraction,
            )
        )
    )
    result = (
        runner.run_source(data, Path(args.pine).read_text())
        if args.pine
        else runner.run_external(data, pd.read_csv(args.signals))
    )
    if args.trades_output:
        pd.DataFrame([trade.as_dict() for trade in result.backtest.trades]).to_csv(
            args.trades_output, index=False
        )
    _json_print(
        {
            "mode": result.mode,
            "metrics": result.backtest.metrics,
            "trades": len(result.backtest.trades),
            "warnings": result.warnings,
            "translated_schema": result.translation.schema if result.translation else None,
        }
    )
    return 0


def _pine(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Translate the supported Pine v5 subset")
    parser.add_argument("input")
    parser.add_argument("--output", "-o")
    parser.add_argument("--format", choices=["schema", "python"], default="schema")
    args = parser.parse_args(argv)
    translation = PineTranspiler().transpile(Path(args.input).read_text())
    output = (
        translation.to_python()
        if args.format == "python"
        else yaml.safe_dump(translation.schema, sort_keys=False)
    )
    if args.output:
        Path(args.output).write_text(output)
    else:
        print(output)
    for warning in translation.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


async def _paper(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run robust leaderboard strategies against closed live candles in paper mode"
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--source", default="binance")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--leaderboard", default="data/leaderboard.sqlite")
    parser.add_argument("--deployments", default="data/deployments.sqlite")
    parser.add_argument(
        "--use-deployments",
        action="store_true",
        help="Run enabled paper deployment records before falling back to leaderboard top-N",
    )
    parser.add_argument("--cache", default="data/market_data.sqlite")
    parser.add_argument("--history-bars", type=int, default=1000)
    parser.add_argument("--initial-cash", type=float, default=100_000)
    parser.add_argument("--allocation", type=float, default=0.05)
    parser.add_argument("--max-position-fraction", type=float, default=0.10)
    parser.add_argument("--max-drawdown", type=float, default=0.20)
    parser.add_argument("--commission-bps", type=float, default=5)
    parser.add_argument("--slippage-bps", type=float, default=2)
    parser.add_argument("--api-host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--no-api", action="store_true")
    args = parser.parse_args(argv)
    if args.top < 1 or args.history_bars < 2:
        raise ValueError("--top must be positive and --history-bars must be at least two")
    if args.source in {"yfinance", "polygon"}:
        raise ValueError("Live paper streaming supports ccxt exchanges or Alpaca")

    from altron.api.app import create_app
    from altron.brokers.registry import registry_from_environment
    from altron.data_layer.free_streams import FreeStreamManager
    from altron.data_layer.stream import (
        AlpacaBarStream,
        CCXTProCandleStream,
        ClosedCandleAggregator,
    )
    from altron.live_trading.deployments import DeploymentStore
    from altron.live_trading.distribution import (
        CompositeSink,
        DiscordSink,
        LoggingSink,
        SignalHub,
        TelegramSink,
    )
    from altron.live_trading.engine import LivePaperEngine, LiveStrategy
    from altron.live_trading.modes import TradingModeController
    from altron.live_trading.paper import PaperBroker
    from altron.live_trading.telemetry import RuntimeTelemetry
    from altron.logging_config import configure_logging
    from altron.strategies.rules import strategy_from_definition

    settings = Settings()
    configure_logging(settings.log_level)
    deployment_store = DeploymentStore(args.deployments)
    specifications: list[LiveStrategy] = []
    if args.use_deployments:
        selected_deployments = [
            record
            for record in deployment_store.list()
            if record.enabled
            and record.execution_backend == "paper"
            and record.symbol == args.symbol
            and record.timeframe == args.timeframe
            and record.data_source == args.source
        ][: args.top]
        for record in selected_deployments:
            specifications.append(
                LiveStrategy(
                    strategy=get_strategy(record.strategy),
                    params=record.params,
                    allocation=record.allocation,
                    instance_name=f"deployment:{record.id}:{record.name}",
                )
            )

    if not specifications:
        leaders = Leaderboard(args.leaderboard).top(
            symbol=args.symbol, timeframe=args.timeframe, limit=max(100, args.top * 10)
        )
        if not leaders.empty:
            leaders = leaders.loc[leaders["source"] == args.source].head(args.top)
        if leaders.empty:
            raise RuntimeError(
                "No enabled paper deployments or robust walk-forward leaderboard entries match "
                "source/symbol/timeframe. Run --walk-forward first."
            )
        for row in leaders.to_dict("records"):
            selected_strategy: Strategy
            stored_params = json.loads(row["params_json"])
            if "__rule_definition__" in stored_params:
                selected_strategy = strategy_from_definition(stored_params["__rule_definition__"])
                selected_params = stored_params.get("__params__", {})
            else:
                selected_strategy = get_strategy(str(row["strategy"]))
                selected_params = stored_params
            specifications.append(
                LiveStrategy(
                    strategy=selected_strategy,
                    params=selected_params,
                    allocation=args.allocation,
                    instance_name=f"{row['strategy']}#{row['id']}",
                )
            )
    hub = SignalHub()
    sinks: list[Any] = [LoggingSink(), hub]
    if settings.telegram_bot_token and settings.telegram_chat_id:
        sinks.append(TelegramSink(settings.telegram_bot_token, settings.telegram_chat_id))
    if settings.discord_webhook_url:
        sinks.append(DiscordSink(settings.discord_webhook_url))
    broker = PaperBroker(
        initial_cash=args.initial_cash,
        commission_bps=args.commission_bps,
        slippage_bps=args.slippage_bps,
        max_position_fraction=args.max_position_fraction,
        max_drawdown=args.max_drawdown,
    )
    telemetry = RuntimeTelemetry()
    broker_registry = registry_from_environment(execution_enabled=False)
    mode_controller = TradingModeController(broker_registry)
    market_streams = FreeStreamManager(telemetry)
    paper = LivePaperEngine(
        specifications,
        broker,
        CompositeSink(*sinks),
        telemetry=telemetry,
        execution_router=mode_controller,
    )

    data_service = MarketDataService(_source(args.source), MarketDataCache(args.cache))
    history = await data_service.get_ohlcv(
        args.symbol, args.timeframe, limit=args.history_bars, refresh=True
    )
    closed_before = pd.Timestamp.now(tz=UTC) - pd.Timedelta(
        seconds=timeframe_to_seconds(args.timeframe)
    )
    history = history.loc[history["timestamp"] <= closed_before]
    if history.empty:
        raise RuntimeError("No closed historical candles were available for live strategy warm-up")
    history = history.tail(args.history_bars).reset_index(drop=True)
    paper.history[(args.symbol, args.timeframe)] = history
    for row in history.itertuples(index=False):
        telemetry.record_candle(args.symbol, args.timeframe, pd.Series(row._asdict()))

    aggregator: ClosedCandleAggregator | None = None
    stream: AlpacaBarStream | CCXTProCandleStream
    if args.source == "alpaca":
        stream = AlpacaBarStream(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_API_SECRET"])
        stream_timeframe = "1m"
        if args.timeframe != "1m":
            aggregator = ClosedCandleAggregator(args.timeframe)
    else:
        stream = CCXTProCandleStream(args.source)
        stream_timeframe = args.timeframe

    server = None
    server_task: asyncio.Task[Any] | None = None
    if not args.no_api:
        try:
            import uvicorn
        except ImportError as exc:
            raise RuntimeError("Install API dependencies with: pip install '.[api]'") from exc
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(
                    hub,
                    webhook_secret=os.getenv("TRADINGVIEW_WEBHOOK_SECRET"),
                    telemetry=telemetry,
                    brokers=broker_registry,
                    deployment_store=deployment_store,
                    mode_controller=mode_controller,
                    market_streams=market_streams,
                    operator_token=os.getenv("ALTRON_OPERATOR_TOKEN"),
                ),
                host=args.api_host,
                port=args.api_port,
                log_level="info",
            )
        )
        server_task = asyncio.create_task(server.serve())

    try:
        async for candle in stream.stream_ohlcv(args.symbol, stream_timeframe):
            if aggregator is not None:
                aggregated = aggregator.update(candle)
                if aggregated is None:
                    continue
                candle = aggregated
            await paper.process_candle(args.symbol, args.timeframe, candle, closed=True)
    finally:
        if server is not None:
            server.should_exit = True
        if server_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await server_task
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "list-strategies":
        print("\n".join(list_strategies()))
        return 0
    if argv and argv[0] == "pine":
        return _pine(argv[1:])
    if argv and argv[0] == "pine-backtest":
        return _pine_backtest(argv[1:])
    if argv and argv[0] == "strategy-test":
        return _strategy_test(argv[1:])
    if argv and argv[0] == "paper":
        return asyncio.run(_paper(argv[1:]))
    if argv and argv[0] == "serve":
        try:
            import uvicorn
        except ImportError as exc:
            raise RuntimeError("Install API dependencies with: pip install '.[api]'") from exc
        uvicorn.run(
            "altron.api.server:app",
            host=os.getenv("ALTRON_API_HOST", "127.0.0.1"),
            port=int(os.getenv("ALTRON_API_PORT", "8000")),
        )
        return 0
    if argv and argv[0] == "dashboard":
        try:
            from streamlit.web import cli as streamlit_cli
        except ImportError as exc:
            raise RuntimeError(
                "Install dashboard dependencies with: pip install '.[dashboard]'"
            ) from exc
        dashboard_path = Path(__file__).with_name("dashboard.py")
        sys.argv = ["streamlit", "run", str(dashboard_path), *argv[1:]]
        return int(streamlit_cli.main() or 0)
    Settings().ensure_directories()
    return asyncio.run(_research(argv))


if __name__ == "__main__":
    raise SystemExit(main())
