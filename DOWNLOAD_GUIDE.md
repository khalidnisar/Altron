# Download and setup

## Clone

```bash
git clone https://github.com/khalidnisar/Altron.git
cd Altron
./setup.sh
source .venv/bin/activate
pytest
```

The setup script requires Python 3.11+ and installs the research, data, API, dashboard, and
development extras into a local virtual environment. For a smaller environment, install selected
extras manually:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[data,optimize]'
```

## Configure optional vendors

Copy `.env.example` to `.env` for Docker Compose, or export only the credentials needed by your
chosen vendor. Do not commit `.env`, exchange credentials, bot tokens, or webhook secrets.
Public ccxt OHLCV generally needs no key. Alpaca uses `ALPACA_API_KEY` and
`ALPACA_API_SECRET`; Polygon uses `POLYGON_API_KEY`.

## Verify

```bash
altron list-strategies
altron pine examples/ma_crossover.pine --format schema
pytest
```

## First offline run

Provide a CSV or Parquet file with `timestamp,open,high,low,close,volume`:

```bash
altron --input candles.csv --strategy ma_crossover \
  --params '{fast_period: 20, slow_period: 50, ma_type: ema}'

altron --input candles.csv --strategy supertrend \
  --walk-forward --train-bars 1000 --test-bars 250 --trials 50
```

Only robust walk-forward entries are automatically eligible for leaderboard-driven `altron paper`.
Start the command center with `altron dashboard`; its sidebar switches between local virtual fills
and verified broker-demo routing, while **Free market data** starts public crypto or delayed
stock/forex feeds. Use `altron pine-backtest --signals` for arbitrary Pine exports. See
[`docs/BROKER_CONNECTIVITY.md`](docs/BROKER_CONNECTIVITY.md) and
[`docs/MARKET_DATA_STREAMS.md`](docs/MARKET_DATA_STREAMS.md).

## Windows desktop

```powershell
.\.venv\Scripts\pip.exe install -e ".[desktop,data,optimize,mt5]"
.\.venv\Scripts\altron-desktop.exe
```

Use `packaging\windows\build.ps1` to produce `dist\AltronQuant.exe`. Broker passwords are stored
through Windows Credential Manager rather than the settings JSON file.
