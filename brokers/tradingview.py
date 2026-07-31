"""
brokers/tradingview.py
TradingView adapter — display-only data source.
No API key required. Uses TradingView's free embeddable widgets.
Trading is NOT supported through TradingView. This is for charting and
market data visualization only.

When selected, the dashboard shows TradingView widgets (charts, market
overview, technical analysis). For trading, connect a real broker
(Zerodha, Upstox, Angel One, Groww).
"""

import pandas as pd
from brokers.base import BaseBroker


class TradingViewBroker(BaseBroker):
    """Display-only broker using TradingView free widgets."""

    def __init__(self, **kwargs):
        self._connected = True  # No auth needed — always "connected"

    @property
    def name(self) -> str:
        return "TradingView"

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_login_url(self) -> str:
        return "https://www.tradingview.com"

    def complete_login(self, **kwargs) -> bool:
        self._connected = True
        return True

    def get_historical(self, symbol: str, interval: str, days: int = 365) -> pd.DataFrame:
        # TradingView handles charts via widgets — no REST API for historical data
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def get_quote(self, symbol: str) -> dict:
        return {"symbol": symbol, "ltp": 0, "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}

    def place_order(self, symbol: str, qty: int, side: str,
                    order_type: str = "MARKET", price: float = 0.0) -> dict:
        return {"success": False, "order_id": "", "message": "Trading not supported with TradingView. Connect a broker."}

    def get_positions(self) -> list:
        return []

    def get_order_history(self) -> list:
        return []
