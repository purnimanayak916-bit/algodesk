"""
indicators.py
Technical indicators: RSI, MACD, SMA/EMA, Bollinger Bands, ATR.
All functions take a pandas Series (typically 'close' or 'high'/'low')
and return a pandas Series aligned to the input index.
"""

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD line, signal line, and histogram."""
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    """Bollinger Bands: upper, middle (SMA), lower."""
    middle = sma(series, period)
    std = series.rolling(window=period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return upper, middle, lower


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range."""
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def add_all_indicators(df: pd.DataFrame, strategy_params: dict = None) -> pd.DataFrame:
    """
    Add all indicators to an OHLCV DataFrame.
    Returns a new DataFrame with indicator columns appended.
    """
    if strategy_params is None:
        strategy_params = {"sma_fast": 20, "sma_slow": 50}

    out = df.copy()
    out["sma_fast"] = sma(out["close"], strategy_params["sma_fast"])
    out["sma_slow"] = sma(out["close"], strategy_params["sma_slow"])
    out["rsi"] = rsi(out["close"], 14)
    out["macd"], out["macd_signal"], out["macd_hist"] = macd(out["close"])
    out["bb_upper"], out["bb_middle"], out["bb_lower"] = bollinger_bands(out["close"])
    out["atr"] = atr(out["high"], out["low"], out["close"])
    return out
