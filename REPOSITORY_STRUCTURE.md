# Repository structure

```text
Altron/
├── src/altron/
│   ├── data_layer/       # normalization, cache, vendors, public/free stream manager
│   ├── strategies/       # plugin contract, indicators, built-ins, rules, Pine subset
│   ├── backtest/         # execution model, metrics, Monte Carlo, vectorbt adapter
│   ├── optimization/     # Optuna, fast scenario sweet spots, walk-forward, leaderboard
│   ├── portfolio/        # correlation, allocation, rotation, circuit breaker
│   ├── brokers/          # gated Tradovate and MT5 connectivity / execution routing
│   ├── live_trading/     # engine, virtual broker, demo-mode toggle, telemetry, deployments
│   ├── api/              # signals, charts, statistics, deployments, broker connectivity
│   ├── desktop/          # native PySide6 Windows application and local runtime
│   ├── cli.py            # research, translation, service, and paper commands
│   └── dashboard.py      # optional Streamlit research and signal view
├── packaging/windows/    # PyInstaller specification and PowerShell build
├── tests/                # deterministic unit/integration tests
├── docs/                 # architecture, Pine mapping, strategy schema guide
├── schemas/              # canonical JSON Schema
├── examples/             # Pine and YAML examples
├── notebooks/            # research quickstart
├── monitoring/           # Grafana provisioning
├── Dockerfile
├── docker-compose.yml
├── optimizer.py          # requested compatibility CLI
└── pyproject.toml
```

Runtime candles, leaderboards, logs, Optuna databases, credentials, virtual environments, and
build output are excluded from version control. SQLite uses `data/` by default. Source code follows
a `src` package layout and third-party strategies can register through the `altron.strategies`
entry-point group.
