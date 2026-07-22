from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from PySide6.QtCore import QObject, Signal

from altron.backtest.engine import BacktestEngine
from altron.backtest.models import BacktestConfig
from altron.brokers.mt5 import MT5Backend
from altron.brokers.registry import BrokerRegistry
from altron.brokers.tradovate import TradovateBackend
from altron.config import Settings
from altron.data_layer.fetchers import CCXTFetcher, YFinanceFetcher
from altron.data_layer.free_streams import FreeStreamManager, FreeStreamRequest
from altron.data_layer.normalization import normalize_ohlcv
from altron.live_trading.distribution import LoggingSink, SignalHub
from altron.live_trading.engine import LivePaperEngine, LiveStrategy
from altron.live_trading.modes import TradingModeController
from altron.live_trading.paper import PaperBroker
from altron.live_trading.telemetry import RuntimeTelemetry
from altron.optimization.robust import RobustParameterOptimizer, RobustTestConfig
from altron.strategies.registry import get_strategy


class DesktopRuntime(QObject):
    log = Signal(str)
    task_failed = Signal(str)
    backtest_ready = Signal(object, object, str)
    optimization_ready = Signal(object)
    brokers_changed = Signal(object)
    mode_changed = Signal(object)
    feeds_changed = Signal(object)
    live_changed = Signal(str)

    def __init__(self, data_dir: Path) -> None:
        super().__init__()
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=max(2, min(8, (os_cpu_count() - 1))))
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._run_loop, daemon=True, name="altron-async")
        self.loop_thread.start()
        self.telemetry = RuntimeTelemetry()
        self.paper_broker = PaperBroker()
        self.brokers = BrokerRegistry()
        self.mode = TradingModeController(self.brokers)
        self.feeds = FreeStreamManager(self.telemetry)
        self.signal_hub = SignalHub()
        self.live_task: Future[None] | None = None
        self.live_engine: LivePaperEngine | None = None

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coroutine: Coroutine[Any, Any, Any], success: Any | None = None) -> None:
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)

        def complete(done):
            try:
                result = done.result()
            except Exception as exc:
                self.task_failed.emit(f"{type(exc).__name__}: {exc}")
            else:
                if success is not None:
                    success.emit(result)

        future.add_done_callback(complete)

    def run_backtest(
        self,
        path: str,
        strategy_name: str,
        params_text: str,
        commission: float,
        slippage: float,
    ) -> None:
        def work() -> tuple[Any, pd.DataFrame, str]:
            source = Path(path)
            frame = normalize_ohlcv(
                pd.read_parquet(source)
                if source.suffix.lower() in {".parquet", ".pq"}
                else pd.read_csv(source)
            )
            params = yaml.safe_load(params_text) or {}
            strategy = get_strategy(strategy_name)
            result = BacktestEngine(
                BacktestConfig(
                    commission_bps=commission,
                    slippage_bps=slippage,
                    position_fraction=0.25,
                )
            ).run(frame, strategy, params)
            return result, frame, strategy_name

        future = self.executor.submit(work)
        future.add_done_callback(self._emit_backtest)

    def _emit_backtest(self, future) -> None:
        try:
            result, frame, name = future.result()
        except Exception as exc:
            self.task_failed.emit(f"Backtest failed: {exc}")
        else:
            self.backtest_ready.emit(result, frame, name)

    def run_strategy_test(
        self, path: str, strategy_name: str, space_text: str, trials: int, workers: int
    ) -> None:
        def work():
            source = Path(path)
            frame = normalize_ohlcv(
                pd.read_parquet(source)
                if source.suffix.lower() in {".parquet", ".pq"}
                else pd.read_csv(source)
            )
            space = yaml.safe_load(space_text) or {}
            return RobustParameterOptimizer(
                BacktestConfig(position_fraction=0.25),
                RobustTestConfig(trials=trials, workers=workers),
            ).optimize(frame, get_strategy(strategy_name), parameter_space=space)

        future = self.executor.submit(work)
        future.add_done_callback(self._emit_optimization)

    def _emit_optimization(self, future) -> None:
        try:
            self.optimization_ready.emit(future.result())
        except Exception as exc:
            self.task_failed.emit(f"Strategy test failed: {exc}")

    async def _link_tradovate(self, config: dict[str, Any]) -> dict[str, Any]:
        if self.mode.status.mode != "virtual":
            raise RuntimeError("Return to virtual mode before relinking a broker")
        backend = TradovateBackend(**config)
        status = await backend.connect()
        if not status.connected:
            return status.model_dump(mode="json")
        try:
            old = self.brokers.get("tradovate")
        except KeyError:
            pass
        else:
            await old.disconnect()
        self.brokers.register(backend, replace=True)
        return status.model_dump(mode="json")

    def link_tradovate(self, config: dict[str, Any]) -> None:
        self.submit(self._link_tradovate(config), self.brokers_changed)

    async def _link_mt5(self, config: dict[str, Any]) -> dict[str, Any]:
        if self.mode.status.mode != "virtual":
            raise RuntimeError("Return to virtual mode before relinking a broker")
        backend = MT5Backend(**config)
        status = await backend.connect()
        if status.connected:
            try:
                old = self.brokers.get("mt5")
            except KeyError:
                pass
            else:
                await old.disconnect()
            self.brokers.register(backend, replace=True)
        return status.model_dump(mode="json")

    def link_mt5(self, config: dict[str, Any]) -> None:
        self.submit(self._link_mt5(config), self.brokers_changed)

    def switch_virtual(self) -> None:
        self.submit(self.mode.return_to_virtual(), self.mode_changed)

    def switch_demo(self, backend: str, symbol: str, broker_symbol: str, quantity: float) -> None:
        self.submit(
            self.mode.use_broker_paper(
                backend=backend,
                symbol=symbol,
                broker_symbol=broker_symbol,
                quantity=quantity,
                confirmation="ENABLE_DEMO_ORDERS",
            ),
            self.mode_changed,
        )

    def switch_live(
        self,
        backend: str,
        symbol: str,
        broker_symbol: str,
        quantity: float,
        max_orders: int,
        max_loss: float,
        authorized: bool,
    ) -> None:
        settings = Settings()
        settings.authorize_live_trading(authorized)
        self.submit(
            self.mode.use_live(
                backend=backend,
                symbol=symbol,
                broker_symbol=broker_symbol,
                quantity=quantity,
                max_orders_per_minute=max_orders,
                max_daily_loss=max_loss,
                confirmation="ENABLE_LIVE_ORDERS",
                authorized=not settings.paper_trading,
            ),
            self.mode_changed,
        )

    async def _start_live(
        self,
        request: FreeStreamRequest,
        strategy_name: str,
        params: dict[str, Any],
        allocation: float,
    ) -> None:
        if self.live_engine is not None:
            raise RuntimeError("A live strategy session is already running")
        source, source_timeframe, aggregator = self.feeds._source(  # internal local composition
            request,
            "binance"
            if request.provider == "auto" and request.asset_class == "crypto"
            else "yahoo"
            if request.provider == "auto"
            else request.provider,
        )
        fetcher = CCXTFetcher("binance") if request.asset_class == "crypto" else YFinanceFetcher()
        history = await fetcher.fetch_ohlcv(request.symbol, request.timeframe, limit=1000)
        if history.empty:
            raise RuntimeError("No historical warm-up candles were available")
        engine = LivePaperEngine(
            [LiveStrategy(get_strategy(strategy_name), params, allocation=allocation)],
            self.paper_broker,
            LoggingSink(),
            telemetry=self.telemetry,
            execution_router=self.mode,
        )
        engine.history[(request.symbol, request.timeframe)] = history.tail(1000).reset_index(
            drop=True
        )
        self.live_engine = engine
        self.live_changed.emit("running")
        try:
            async for candle in source.stream_ohlcv(request.symbol, source_timeframe):
                if aggregator is not None:
                    candle = aggregator.update(candle)
                    if candle is None:
                        continue
                await engine.process_candle(request.symbol, request.timeframe, candle, closed=True)
        finally:
            self.live_engine = None
            self.live_changed.emit("stopped")

    def start_live(
        self,
        request: FreeStreamRequest,
        strategy_name: str,
        params_text: str,
        allocation: float,
    ) -> None:
        if self.live_task and not self.live_task.done():
            raise RuntimeError("A live strategy session is already running")
        params = yaml.safe_load(params_text) or {}
        self.live_task = asyncio.run_coroutine_threadsafe(
            self._start_live(request, strategy_name, params, allocation), self.loop
        )

        def completed(done: Future[None]) -> None:
            try:
                error = done.exception()
            except CancelledError:
                return
            if error is not None:
                self.task_failed.emit(str(error))

        self.live_task.add_done_callback(completed)

    def stop_live(self) -> None:
        if self.live_task and not self.live_task.done():
            self.live_task.cancel()

    def candles(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        return pd.DataFrame(self.telemetry.candles(symbol, timeframe, limit))

    def portfolio(self) -> dict[str, Any]:
        return self.telemetry.portfolio()

    def close(self) -> None:
        self.stop_live()
        future = asyncio.run_coroutine_threadsafe(self.feeds.close(), self.loop)
        try:
            future.result(timeout=5)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop_thread.join(timeout=5)
        self.executor.shutdown(wait=False, cancel_futures=True)


def os_cpu_count() -> int:
    import os

    return os.cpu_count() or 2
