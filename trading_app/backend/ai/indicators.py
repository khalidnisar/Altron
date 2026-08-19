"""Technical indicators (numpy). Blueprint 1B: trend, momentum, volatility, volume."""
from __future__ import annotations

import numpy as np


def ema(values: np.ndarray, period: int) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return values
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(values)
    out[0] = values[0]
    for i in range(1, values.size):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def sma(values: np.ndarray, period: int) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.size < period:
        return np.full_like(values, np.nan)
    cum = np.cumsum(np.insert(values, 0, 0.0))
    out = np.full_like(values, np.nan)
    out[period - 1:] = (cum[period:] - cum[:-period]) / period
    return out


def rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    closes = np.asarray(closes, dtype=float)
    if closes.size < period + 1:
        return np.full_like(closes, 50.0)
    diff = np.diff(closes, prepend=closes[0])
    gain = np.where(diff > 0, diff, 0.0)
    loss = np.where(diff < 0, -diff, 0.0)
    avg_gain = ema(gain, period)
    avg_loss = ema(loss, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = np.divide(avg_gain, avg_loss, out=np.full_like(closes, np.inf), where=avg_loss != 0)
    return 100.0 - 100.0 / (1.0 + rs)


def macd(closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    closes = np.asarray(closes, dtype=float)
    line = ema(closes, fast) - ema(closes, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    return np.maximum(high - low,
                      np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    return ema(true_range(np.asarray(high), np.asarray(low), np.asarray(close)), period)


def bollinger(closes: np.ndarray, period: int = 20, mult: float = 2.0):
    mid = sma(closes, period)
    std = np.full_like(closes, np.nan)
    if closes.size >= period:
        for i in range(period - 1, closes.size):
            std[i] = np.std(closes[i - period + 1: i + 1], ddof=0)
    return mid, mid + mult * std, mid - mult * std


def stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray, k: int = 14, d: int = 3):
    n = close.size
    k_line = np.full(n, 50.0)
    for i in range(k - 1, n):
        hh = np.max(high[i - k + 1: i + 1])
        ll = np.min(low[i - k + 1: i + 1])
        k_line[i] = 100.0 * (close[i] - ll) / (hh - ll) if hh > ll else 50.0
    return k_line, ema(k_line, d)


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = close.size
    if n < 2:
        return np.zeros(n)
    up = np.diff(high, prepend=high[0])
    dn = -np.diff(low, prepend=low[0])
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = true_range(high, low, close)
    atr_v = ema(tr, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100 * np.divide(ema(plus_dm, period), atr_v, out=np.zeros(n), where=atr_v != 0)
        mdi = 100 * np.divide(ema(minus_dm, period), atr_v, out=np.zeros(n), where=atr_v != 0)
        dx = 100 * np.divide(np.abs(pdi - mdi), pdi + mdi, out=np.zeros(n), where=(pdi + mdi) != 0)
    return ema(dx, period)


def donchian(high: np.ndarray, low: np.ndarray, period: int = 20):
    n = high.size
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    for i in range(period, n):  # exclude current bar: channels from previous `period` bars
        upper[i] = np.max(high[i - period: i])
        lower[i] = np.min(low[i - period: i])
    return upper, lower
