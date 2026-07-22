"""
config.py
Central constants + default risk settings for the multi-broker app.
"""

DEFAULT_WATCHLIST = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "SBIN", "TATAMOTORS", "ITC", "BHARTIARTL", "LT",
]

DEFAULT_RISK = {
    "max_capital_per_trade_pct": 5.0,
    "stop_loss_pct": 2.0,
    "take_profit_pct": 4.0,
    "max_open_positions": 5,
    "daily_loss_limit_pct": 6.0,
}

STRATEGY_PARAMS = {
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "sma_fast": 20,
    "sma_slow": 50,
}

INTERVAL_CHOICES = {
    "5 minute": "5minute",
    "15 minute": "15minute",
    "1 hour": "60minute",
    "1 day": "day",
}

APP_TITLE = "AlgoDesk — Multi-Broker Stock Trading Dashboard"
