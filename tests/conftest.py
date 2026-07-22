from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def candles() -> pd.DataFrame:
    generator = np.random.default_rng(7)
    count = 500
    close = 100 * np.exp(np.cumsum(generator.normal(0.0003, 0.01, count)))
    open_ = np.r_[close[0], close[:-1]]
    spread = generator.uniform(0.001, 0.01, count)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=count, freq="h", tz="UTC"),
            "open": open_,
            "high": np.maximum(open_, close) * (1 + spread),
            "low": np.minimum(open_, close) * (1 - spread),
            "close": close,
            "volume": generator.uniform(10, 1000, count),
        }
    )
