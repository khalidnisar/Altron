# Declarative strategy schema

The canonical JSON Schema is [`schemas/strategy.schema.json`](../schemas/strategy.schema.json).
YAML and JSON decode to the same object. Rules are evaluated without Python `eval` or `exec`.

A comparison has `left`, `operator`, and `right`. Operands are an OHLCV column, a named indicator,
or a number. Conditions can be nested under `all`, `any`, and `not`.

```yaml
name: trend_filtered_rsi
indicators:
  - {name: rsi14, indicator: rsi, period: 14}
  - {name: daily_sma, indicator: sma, period: 50, timeframe: 1d}
long_entry:
  all:
    - {left: rsi14, operator: "<", right: 30}
    - {left: close, operator: ">", right: daily_sma}
long_exit: {left: rsi14, operator: ">=", right: 50}
```

Load it with:

```python
import yaml
from altron.strategies.rules import strategy_from_definition

strategy = strategy_from_definition(yaml.safe_load(open("strategy.yaml")))
signals = strategy(candles, {})
```

The compact form `{"indicator":"rsi","period":14,"overbought":70,"oversold":30}` is also
accepted. Multi-timeframe indicators are resampled from base candles and shifted by one completed
higher-timeframe bar to prevent look-ahead.
