"""
strategy.py
Rule-based BUY/SELL/HOLD signal engine.
Combines RSI, MACD, and SMA crossover to produce signals.
"""

import pandas as pd
from indicators import rsi, macd, sma, ema


def generate_signals(df: pd.DataFrame, params: dict = None) -> pd.DataFrame:
    """
    Add a 'signal' column to the OHLCV DataFrame.
    Signals: 1 = BUY, -1 = SELL, 0 = HOLD

    Logic:
    - BUY when: RSI < oversold AND MACD histogram > 0 (bullish momentum)
               OR SMA fast crosses above SMA slow (golden cross)
    - SELL when: RSI > overbought AND MACD histogram < 0 (bearish momentum)
                OR SMA fast crosses below SMA slow (death cross)
    - HOLD otherwise
    """
    if params is None:
        params = {
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "sma_fast": 20,
            "sma_slow": 50,
        }

    out = df.copy()

    # Compute indicators
    out["rsi"] = rsi(out["close"], 14)
    out["macd_line"], out["macd_signal"], out["macd_hist"] = macd(out["close"])
    out["sma_fast"] = sma(out["close"], params["sma_fast"])
    out["sma_slow"] = sma(out["close"], params["sma_slow"])

    # SMA crossover detection
    out["sma_cross"] = 0
    out.loc[out["sma_fast"] > out["sma_slow"], "sma_cross"] = 1
    out["sma_cross_prev"] = out["sma_cross"].shift(1)
    golden_cross = (out["sma_cross"] == 1) & (out["sma_cross_prev"] == 0)
    death_cross = (out["sma_cross"] == 0) & (out["sma_cross_prev"] == 1)

    # Build signal
    out["signal"] = 0

    buy_cond = (
        (out["rsi"] < params["rsi_oversold"]) & (out["macd_hist"] > 0)
    ) | golden_cross

    sell_cond = (
        (out["rsi"] > params["rsi_overbought"]) & (out["macd_hist"] < 0)
    ) | death_cross

    out.loc[buy_cond, "signal"] = 1
    out.loc[sell_cond, "signal"] = -1

    # Add a human-readable signal label
    out["signal_label"] = out["signal"].map({1: "BUY", -1: "SELL", 0: "HOLD"})

    return out


def latest_signal(df: pd.DataFrame) -> str:
    """Return the most recent signal label."""
    if "signal_label" not in df.columns:
        df = generate_signals(df)
    return df["signal_label"].iloc[-1] if len(df) > 0 else "HOLD"
