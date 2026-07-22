#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Altron Quant development setup"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.11+ is required." >&2
  exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit(f"Python 3.11+ is required; found {sys.version.split()[0]}")
PY

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[all,dev]'
mkdir -p data

cat <<'TXT'

Setup complete.

Activate:       source .venv/bin/activate
Run tests:      pytest
List plugins:   altron list-strategies
Backtest:       python optimizer.py --input candles.csv --strategy ma_crossover
Strategy test:  altron strategy-test --input candles.csv --strategy supertrend --trials 250
Walk-forward:   altron --input candles.csv --strategy supertrend --walk-forward
Paper worker:   altron paper --symbol BTC/USDT --timeframe 1h --source binance

Credentials are optional and belong in environment variables; see .env.example.
On Windows, install the desktop extra and launch `altron-desktop`.
TXT
