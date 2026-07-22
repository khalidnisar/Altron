from __future__ import annotations

import json
from typing import Any, Literal, cast

import pandas as pd
import yaml
from PySide6.QtCharts import (
    QCandlestickSeries,
    QCandlestickSet,
    QChart,
    QChartView,
    QDateTimeAxis,
    QValueAxis,
)
from PySide6.QtCore import QDateTime, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from altron.data_layer.free_streams import FreeStreamRequest
from altron.desktop.runtime import DesktopRuntime
from altron.desktop.settings import DesktopSettings
from altron.strategies.registry import get_strategy, list_strategies

APP_STYLE = """
QMainWindow, QWidget { background: #07101f; color: #e6edf7; font-family: 'Segoe UI'; font-size: 10pt; }
QListWidget { background: #091426; border: 0; padding: 10px; min-width: 185px; }
QListWidget::item { padding: 12px; border-radius: 7px; margin: 2px; }
QListWidget::item:selected { background: #12345a; color: #6ee7f9; }
QFrame#card { background: #0d1b31; border: 1px solid #203a5f; border-radius: 12px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QTableWidget {
  background: #091426; border: 1px solid #203a5f; border-radius: 6px; padding: 6px;
}
QPushButton { background: #12345a; border: 1px solid #2e628f; border-radius: 7px; padding: 8px 14px; }
QPushButton:hover { background: #18507c; }
QPushButton#primary { background: #157a78; border-color: #35e6a5; font-weight: 600; }
QPushButton#danger { background: #6e2539; border-color: #ff6685; }
QHeaderView::section { background: #10213a; color: #b9c7da; padding: 7px; border: 0; }
QTabBar::tab { background:#0d1b31; padding:9px 14px; margin:2px; border-radius:6px; }
QTabBar::tab:selected { color:#6ee7f9; border:1px solid #6ee7f9; }
"""


class MetricCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        label = QLabel(title.upper())
        label.setStyleSheet("color:#8fa4c1;font-size:8pt")
        self.value = QLabel("—")
        self.value.setStyleSheet("color:#6ee7f9;font-size:19pt;font-weight:600")
        layout.addWidget(label)
        layout.addWidget(self.value)


class CandleChart(QChartView):
    def __init__(self) -> None:
        super().__init__()
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(430)
        self.set_candles(pd.DataFrame())

    def set_candles(self, frame: pd.DataFrame) -> None:
        chart = QChart()
        chart.setBackgroundBrush(QColor("#091426"))
        chart.setPlotAreaBackgroundBrush(QColor("#091426"))
        chart.setPlotAreaBackgroundVisible(True)
        chart.legend().setLabelColor(QColor("#b9c7da"))
        chart.setTitleBrush(QColor("#e6edf7"))
        chart.setTitle("Market candles")
        series = QCandlestickSeries()
        series.setIncreasingColor(QColor("#35e6a5"))
        series.setDecreasingColor(QColor("#ff6685"))
        if not frame.empty:
            for row in frame.tail(500).itertuples(index=False):
                stamp = pd.Timestamp(row.timestamp)
                candle = QCandlestickSet(
                    float(row.open),
                    float(row.high),
                    float(row.low),
                    float(row.close),
                    int(stamp.timestamp() * 1000),
                )
                series.append(candle)
        chart.addSeries(series)
        time_axis = QDateTimeAxis()
        time_axis.setFormat("dd MMM\nHH:mm")
        time_axis.setLabelsColor(QColor("#9eb0ca"))
        price_axis = QValueAxis()
        price_axis.setLabelFormat("%.5g")
        price_axis.setLabelsColor(QColor("#9eb0ca"))
        chart.addAxis(time_axis, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(price_axis, Qt.AlignmentFlag.AlignRight)
        series.attachAxis(time_axis)
        series.attachAxis(price_axis)
        if not frame.empty:
            timestamps = pd.to_datetime(frame["timestamp"], utc=True)
            time_axis.setRange(
                QDateTime.fromMSecsSinceEpoch(
                    int(timestamps.iloc[-min(500, len(frame))].timestamp() * 1000)
                ),
                QDateTime.fromMSecsSinceEpoch(int(timestamps.iloc[-1].timestamp() * 1000)),
            )
            low, high = float(frame.tail(500)["low"].min()), float(frame.tail(500)["high"].max())
            padding = max((high - low) * 0.05, abs(high) * 0.001)
            price_axis.setRange(low - padding, high + padding)
        self.setChart(chart)


class MainWindow(QMainWindow):
    def __init__(self, settings: DesktopSettings, runtime: DesktopRuntime) -> None:
        super().__init__()
        self.settings = settings
        self.runtime = runtime
        self.setWindowTitle("Altron Quant Desktop")
        self.resize(1500, 930)
        self.setStyleSheet(APP_STYLE)
        self._build_ui()
        self._connect_runtime()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_overview)
        self.timer.start(2000)
        self.refresh_overview()

    def _build_ui(self) -> None:
        toolbar = self.addToolBar("Status")
        toolbar.setMovable(False)
        self.mode_label = QLabel("  ● VIRTUAL  ")
        self.mode_label.setStyleSheet("color:#35e6a5;font-weight:700")
        toolbar.addWidget(self.mode_label)
        toolbar.addSeparator()
        self.session_label = QLabel("Live strategy: stopped")
        toolbar.addWidget(self.session_label)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        toolbar.addAction(exit_action)

        root = QSplitter()
        self.navigation = QListWidget()
        self.navigation.addItems(
            [
                "Overview",
                "Market Chart",
                "Backtest",
                "Sweet Spot",
                "Live Session",
                "Brokers & Mode",
                "Logs",
            ]
        )
        self.navigation.setCurrentRow(0)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._overview_page())
        self.pages.addWidget(self._chart_page())
        self.pages.addWidget(self._backtest_page())
        self.pages.addWidget(self._optimizer_page())
        self.pages.addWidget(self._live_page())
        self.pages.addWidget(self._brokers_page())
        self.pages.addWidget(self._logs_page())
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        root.addWidget(self.navigation)
        root.addWidget(self.pages)
        root.setStretchFactor(1, 1)
        self.setCentralWidget(root)

    def _page(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel(title)
        heading.setStyleSheet("font-size:22pt;font-weight:650;color:#f2f7ff")
        caption = QLabel(subtitle)
        caption.setWordWrap(True)
        caption.setStyleSheet("color:#8fa4c1")
        layout.addWidget(heading)
        layout.addWidget(caption)
        return page, layout

    def _overview_page(self) -> QWidget:
        page, layout = self._page("Command Center", "Local portfolio, risk and execution status")
        cards = QGridLayout()
        self.cards = {
            name: MetricCard(name)
            for name in ["Equity", "Net P&L", "Drawdown", "Open Positions", "Win Rate", "Fills"]
        }
        for index, card in enumerate(self.cards.values()):
            cards.addWidget(card, index // 3, index % 3)
        layout.addLayout(cards)
        self.positions_table = QTableWidget(0, 7)
        self.positions_table.setHorizontalHeaderLabels(
            ["Strategy", "Symbol", "Side", "Quantity", "Average", "Mark", "Unrealized P&L"]
        )
        self.positions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(QLabel("Open virtual positions"))
        layout.addWidget(self.positions_table)
        return page

    def _chart_page(self) -> QWidget:
        page, layout = self._page(
            "Market Chart", "Closed candles from local public or broker feeds"
        )
        controls = QHBoxLayout()
        self.chart_symbol = QLineEdit("BTC/USDT")
        self.chart_timeframe = QComboBox()
        self.chart_timeframe.addItems(["1m", "5m", "15m", "1h", "4h", "1d"])
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_chart)
        controls.addWidget(QLabel("Symbol"))
        controls.addWidget(self.chart_symbol)
        controls.addWidget(QLabel("Timeframe"))
        controls.addWidget(self.chart_timeframe)
        controls.addWidget(refresh)
        self.chart = CandleChart()
        layout.addLayout(controls)
        layout.addWidget(self.chart)
        return page

    def _file_row(self, field: QLineEdit) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(field)
        button = QPushButton("Browse…")
        button.clicked.connect(lambda: self._browse(field))
        row.addWidget(button)
        return row

    def _backtest_page(self) -> QWidget:
        page, layout = self._page(
            "Backtest Lab", "Cost-aware local research with corrected fill timing"
        )
        form = QFormLayout()
        self.bt_file = QLineEdit()
        form.addRow("OHLCV file", self._wrap(self._file_row(self.bt_file)))
        self.bt_strategy = QComboBox()
        self.bt_strategy.addItems(list_strategies())
        form.addRow("Strategy", self.bt_strategy)
        self.bt_params = QTextEdit("{}")
        self.bt_params.setMaximumHeight(100)
        form.addRow("Parameters", self.bt_params)
        self.bt_commission = QDoubleSpinBox()
        self.bt_commission.setValue(5)
        form.addRow("Commission bps", self.bt_commission)
        self.bt_slippage = QDoubleSpinBox()
        self.bt_slippage.setValue(2)
        form.addRow("Slippage bps", self.bt_slippage)
        run = QPushButton("Run backtest")
        run.setObjectName("primary")
        run.clicked.connect(self._run_backtest)
        self.bt_metrics = QLabel("No result")
        self.bt_table = QTableWidget(0, 8)
        self.bt_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addLayout(form)
        layout.addWidget(run)
        layout.addWidget(self.bt_metrics)
        layout.addWidget(self.bt_table)
        return page

    def _optimizer_page(self) -> QWidget:
        page, layout = self._page(
            "Sweet Spot Optimizer", "Parallel scenario search with risk and stability penalties"
        )
        form = QFormLayout()
        self.opt_file = QLineEdit()
        form.addRow("OHLCV file", self._wrap(self._file_row(self.opt_file)))
        self.opt_strategy = QComboBox()
        self.opt_strategy.addItems(list_strategies())
        self.opt_strategy.currentTextChanged.connect(self._set_default_space)
        form.addRow("Strategy", self.opt_strategy)
        self.opt_space = QTextEdit()
        self.opt_space.setMaximumHeight(150)
        form.addRow("Search space", self.opt_space)
        self.opt_trials = QSpinBox()
        self.opt_trials.setRange(10, 5000)
        self.opt_trials.setValue(100)
        form.addRow("Candidates", self.opt_trials)
        self.opt_workers = QSpinBox()
        self.opt_workers.setRange(1, 32)
        self.opt_workers.setValue(4)
        form.addRow("Workers", self.opt_workers)
        run = QPushButton("Find robust sweet spot")
        run.setObjectName("primary")
        run.clicked.connect(self._run_optimizer)
        self.opt_result = QTextEdit()
        self.opt_result.setReadOnly(True)
        layout.addLayout(form)
        layout.addWidget(run)
        layout.addWidget(self.opt_result)
        self._set_default_space(self.opt_strategy.currentText())
        return page

    def _live_page(self) -> QWidget:
        page, layout = self._page(
            "Live Strategy Session", "One local closed-candle feed and strategy engine"
        )
        form = QFormLayout()
        self.live_asset = QComboBox()
        self.live_asset.addItems(["crypto", "stocks", "forex"])
        form.addRow("Asset class", self.live_asset)
        self.live_symbol = QLineEdit("BTC/USDT")
        form.addRow("Symbol", self.live_symbol)
        self.live_tf = QComboBox()
        self.live_tf.addItems(["1m", "5m", "15m", "1h", "4h", "1d"])
        form.addRow("Timeframe", self.live_tf)
        self.live_provider = QComboBox()
        self.live_provider.addItems(["auto", "binance", "yahoo", "alpaca"])
        form.addRow("Provider", self.live_provider)
        self.live_strategy = QComboBox()
        self.live_strategy.addItems(list_strategies())
        form.addRow("Strategy", self.live_strategy)
        self.live_params = QTextEdit("{}")
        self.live_params.setMaximumHeight(90)
        form.addRow("Parameters", self.live_params)
        self.live_allocation = QDoubleSpinBox()
        self.live_allocation.setRange(0.01, 1)
        self.live_allocation.setSingleStep(0.01)
        self.live_allocation.setValue(0.05)
        form.addRow("Allocation", self.live_allocation)
        buttons = QHBoxLayout()
        start = QPushButton("Start")
        start.setObjectName("primary")
        start.clicked.connect(self._start_live)
        stop = QPushButton("Stop")
        stop.setObjectName("danger")
        stop.clicked.connect(self.runtime.stop_live)
        buttons.addWidget(start)
        buttons.addWidget(stop)
        layout.addLayout(form)
        layout.addLayout(buttons)
        return page

    def _brokers_page(self) -> QWidget:
        page, layout = self._page(
            "Brokers & Trading Mode",
            "Secrets use Windows Credential Manager; live mode has independent hard gates",
        )
        tabs = QTabWidget()
        tabs.addTab(self._tradovate_form(), "Tradovate")
        tabs.addTab(self._mt5_form(), "MetaTrader 5")
        tabs.addTab(self._mode_form(), "Execution mode")
        self.broker_table = QTableWidget(0, 6)
        self.broker_table.setHorizontalHeaderLabels(
            ["Backend", "Connected", "Environment", "Execution", "Account", "Message"]
        )
        self.broker_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(tabs)
        layout.addWidget(self.broker_table)
        return page

    def _tradovate_form(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        self.tv_env = QComboBox()
        self.tv_env.addItems(["demo", "live"])
        self.tv_user = QLineEdit(self.settings.get("tradovate_username", ""))
        self.tv_password = QLineEdit()
        self.tv_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.tv_password.setText(self.settings.get_secret("tradovate_password") or "")
        self.tv_token = QLineEdit()
        self.tv_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.tv_app = QLineEdit(self.settings.get("tradovate_app_id", ""))
        self.tv_save = QCheckBox("Store password in Windows Credential Manager")
        button = QPushButton("Link account")
        button.clicked.connect(self._link_tradovate)
        for label, control in [
            ("Environment", self.tv_env),
            ("Username", self.tv_user),
            ("Password", self.tv_password),
            ("Access token", self.tv_token),
            ("App ID", self.tv_app),
        ]:
            form.addRow(label, control)
        form.addRow(self.tv_save)
        form.addRow(button)
        return widget

    def _mt5_form(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        self.mt_path = QLineEdit(self.settings.get("mt5_path", ""))
        self.mt_login = QLineEdit(self.settings.get("mt5_login", ""))
        self.mt_server = QLineEdit(self.settings.get("mt5_server", ""))
        self.mt_password = QLineEdit()
        self.mt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.mt_password.setText(self.settings.get_secret("mt5_password") or "")
        self.mt_save = QCheckBox("Store password in Windows Credential Manager")
        button = QPushButton("Link local terminal")
        button.clicked.connect(self._link_mt5)
        for label, control in [
            ("Terminal path", self.mt_path),
            ("Login", self.mt_login),
            ("Server", self.mt_server),
            ("Password", self.mt_password),
        ]:
            form.addRow(label, control)
        form.addRow(self.mt_save)
        form.addRow(button)
        return widget

    def _mode_form(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        self.mode_choice = QComboBox()
        self.mode_choice.addItems(["Virtual", "Broker demo", "LIVE (guarded)"])
        self.mode_backend = QComboBox()
        self.mode_symbol = QLineEdit("BTC/USDT")
        self.mode_broker_symbol = QLineEdit("BTC/USDT")
        self.mode_quantity = QDoubleSpinBox()
        self.mode_quantity.setRange(0.0001, 1_000_000)
        self.mode_quantity.setValue(1)
        self.mode_rate = QSpinBox()
        self.mode_rate.setRange(1, 60)
        self.mode_rate.setValue(5)
        self.mode_loss = QDoubleSpinBox()
        self.mode_loss.setRange(1, 1_000_000)
        self.mode_loss.setValue(100)
        self.mode_phrase = QLineEdit()
        self.mode_phrase.setPlaceholderText("ENABLE_LIVE_ORDERS for live mode")
        self.mode_ack = QCheckBox("I understand live orders can lose real money")
        apply = QPushButton("Apply mode")
        apply.setObjectName("danger")
        apply.clicked.connect(self._apply_mode)
        for label, control in [
            ("Mode", self.mode_choice),
            ("Backend", self.mode_backend),
            ("Strategy symbol", self.mode_symbol),
            ("Broker symbol", self.mode_broker_symbol),
            ("Quantity per strategy", self.mode_quantity),
            ("Max orders/min", self.mode_rate),
            ("Max daily loss", self.mode_loss),
            ("Typed confirmation", self.mode_phrase),
        ]:
            form.addRow(label, control)
        form.addRow(self.mode_ack)
        form.addRow(apply)
        return widget

    def _logs_page(self) -> QWidget:
        page, layout = self._page("Event Log", "Local runtime diagnostics with no secret values")
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)
        return page

    @staticmethod
    def _wrap(layout: QHBoxLayout) -> QWidget:
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _connect_runtime(self) -> None:
        self.runtime.task_failed.connect(lambda text: self._error(text))
        self.runtime.log.connect(self._log)
        self.runtime.backtest_ready.connect(self._show_backtest)
        self.runtime.optimization_ready.connect(self._show_optimization)
        self.runtime.brokers_changed.connect(self._brokers_changed)
        self.runtime.mode_changed.connect(self._mode_changed)
        self.runtime.live_changed.connect(self._live_changed)

    def _browse(self, field: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select OHLCV", "", "Market data (*.csv *.parquet *.pq)"
        )
        if path:
            field.setText(path)

    def _run_backtest(self) -> None:
        self.runtime.run_backtest(
            self.bt_file.text(),
            self.bt_strategy.currentText(),
            self.bt_params.toPlainText(),
            self.bt_commission.value(),
            self.bt_slippage.value(),
        )

    def _show_backtest(self, result: Any, frame: pd.DataFrame, name: str) -> None:
        m = result.metrics
        self.bt_metrics.setText(
            f"{name}  |  Return {m['total_return']:.2%}  |  Sharpe {m['sharpe']:.2f}  |  Max DD {m['max_drawdown']:.2%}  |  Trades {len(result.trades)}"
        )
        rows = [trade.as_dict() for trade in result.trades]
        headers = [
            "entry_time",
            "exit_time",
            "direction",
            "entry_price",
            "exit_price",
            "return_pct",
            "pnl",
            "bars",
        ]
        self.bt_table.setColumnCount(len(headers))
        self.bt_table.setHorizontalHeaderLabels(headers)
        self.bt_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, key in enumerate(headers):
                self.bt_table.setItem(r, c, QTableWidgetItem(str(row[key])))
        self.chart.set_candles(frame)

    def _set_default_space(self, name: str) -> None:
        mapped = {}
        for key, value in get_strategy(name).parameter_space.items():
            if isinstance(value, tuple):
                mapped[key] = {
                    "type": "int" if all(isinstance(x, int) for x in value) else "float",
                    "low": value[0],
                    "high": value[1],
                }
            else:
                mapped[key] = value
        self.opt_space.setPlainText(yaml.safe_dump(mapped, sort_keys=False))

    def _run_optimizer(self) -> None:
        self.runtime.run_strategy_test(
            self.opt_file.text(),
            self.opt_strategy.currentText(),
            self.opt_space.toPlainText(),
            self.opt_trials.value(),
            self.opt_workers.value(),
        )

    def _show_optimization(self, result: Any) -> None:
        self.opt_result.setPlainText(json.dumps(result.summary(), indent=2, default=str))

    def _start_live(self) -> None:
        try:
            self.runtime.start_live(
                FreeStreamRequest(
                    asset_class=cast(
                        Literal["stocks", "forex", "crypto"],
                        self.live_asset.currentText(),
                    ),
                    symbol=self.live_symbol.text(),
                    timeframe=cast(
                        Literal["1m", "5m", "15m", "1h", "4h", "1d"],
                        self.live_tf.currentText(),
                    ),
                    provider=cast(
                        Literal["auto", "yahoo", "binance", "alpaca"],
                        self.live_provider.currentText(),
                    ),
                ),
                self.live_strategy.currentText(),
                self.live_params.toPlainText(),
                self.live_allocation.value(),
            )
        except Exception as exc:
            self._error(str(exc))

    def _link_tradovate(self) -> None:
        self.settings.set("tradovate_username", self.tv_user.text())
        self.settings.set("tradovate_app_id", self.tv_app.text())
        if self.tv_save.isChecked():
            self.settings.set_secret("tradovate_password", self.tv_password.text())
        self.runtime.link_tradovate(
            {
                "environment": self.tv_env.currentText(),
                "access_token": self.tv_token.text() or None,
                "username": self.tv_user.text() or None,
                "password": self.tv_password.text() or None,
                "app_id": self.tv_app.text() or None,
            }
        )

    def _link_mt5(self) -> None:
        self.settings.set("mt5_path", self.mt_path.text())
        self.settings.set("mt5_login", self.mt_login.text())
        self.settings.set("mt5_server", self.mt_server.text())
        if self.mt_save.isChecked():
            self.settings.set_secret("mt5_password", self.mt_password.text())
        self.runtime.link_mt5(
            {
                "terminal_path": self.mt_path.text() or None,
                "login": int(self.mt_login.text()) if self.mt_login.text() else None,
                "password": self.mt_password.text() or None,
                "server": self.mt_server.text() or None,
            }
        )

    def _apply_mode(self) -> None:
        choice = self.mode_choice.currentIndex()
        if choice == 0:
            self.runtime.switch_virtual()
            return
        backend = self.mode_backend.currentText()
        if not backend:
            self._error("Link a broker first")
            return
        if choice == 1:
            self.runtime.switch_demo(
                backend,
                self.mode_symbol.text(),
                self.mode_broker_symbol.text(),
                self.mode_quantity.value(),
            )
        else:
            if self.mode_phrase.text() != "ENABLE_LIVE_ORDERS" or not self.mode_ack.isChecked():
                self._error("Live mode confirmation is incomplete")
                return
            self.runtime.switch_live(
                backend,
                self.mode_symbol.text(),
                self.mode_broker_symbol.text(),
                self.mode_quantity.value(),
                self.mode_rate.value(),
                self.mode_loss.value(),
                True,
            )

    def _brokers_changed(self, status: dict[str, Any]) -> None:
        self._log(f"Broker: {status}")
        self.refresh_brokers()

    def refresh_brokers(self) -> None:
        statuses = self.runtime.brokers.statuses()
        self.broker_table.setRowCount(len(statuses))
        self.mode_backend.clear()
        for r, status in enumerate(statuses):
            self.mode_backend.addItem(status.backend)
            values = [
                status.backend,
                status.connected,
                status.environment,
                status.execution_enabled,
                status.account_id,
                status.message,
            ]
            for c, value in enumerate(values):
                self.broker_table.setItem(r, c, QTableWidgetItem(str(value)))

    def _mode_changed(self, status: Any) -> None:
        self.mode_label.setText(f"  ● {status.mode.upper()}  ")
        self.mode_label.setStyleSheet(
            "color:#ff6685;font-weight:700"
            if status.mode == "live"
            else "color:#35e6a5;font-weight:700"
        )
        self._log(status.message)

    def _live_changed(self, status: str) -> None:
        self.session_label.setText(f"Live strategy: {status}")

    def refresh_overview(self) -> None:
        p = self.runtime.portfolio()
        values = {
            "Equity": money(p.get("equity")),
            "Net P&L": money(p.get("net_pnl")),
            "Drawdown": percent(p.get("drawdown")),
            "Open Positions": str(p.get("open_positions", 0)),
            "Win Rate": percent(p.get("win_rate")),
            "Fills": str(p.get("fills", 0)),
        }
        for name, value in values.items():
            self.cards[name].value.setText(value)
        positions = p.get("positions", [])
        self.positions_table.setRowCount(len(positions))
        keys = [
            "strategy",
            "symbol",
            "side",
            "quantity",
            "average_price",
            "mark_price",
            "unrealized_pnl",
        ]
        for r, position in enumerate(positions):
            for c, key in enumerate(keys):
                self.positions_table.setItem(r, c, QTableWidgetItem(str(position.get(key, ""))))

    def refresh_chart(self) -> None:
        self.chart.set_candles(
            self.runtime.candles(self.chart_symbol.text(), self.chart_timeframe.currentText())
        )

    def _log(self, text: str) -> None:
        self.log_view.append(text)

    def _error(self, text: str) -> None:
        self._log(text)
        QMessageBox.critical(self, "Altron", text)

    def closeEvent(self, event) -> None:
        self.runtime.close()
        event.accept()


def money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def percent(value: Any) -> str:
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "—"
