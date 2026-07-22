"""
brokers/zerodha.py
Zerodha Kite Connect adapter.
Docs: https://kite.trade/docs/connect/v3/

Login flow: browser redirect → request_token → exchange for access_token.
Tokens expire daily (~7:30 AM IST) and require a fresh login.
Requires: api_key, api_secret in secrets.
"""

import pandas as pd
from brokers.base import BaseBroker


class ZerodhaBroker(BaseBroker):
    def __init__(self, api_key: str, api_secret: str, redirect_uri: str = "http://localhost:8501"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.redirect_uri = redirect_uri
        self._kite = None

    @property
    def name(self) -> str:
        return "Zerodha"

    @property
    def is_connected(self) -> bool:
        return self._kite is not None

    def get_login_url(self) -> str:
        from kiteconnect import KiteConnect
        self._kite = KiteConnect(api_key=self.api_key)
        return self._kite.login_url()

    def complete_login(self, request_token: str, **kwargs) -> bool:
        try:
            from kiteconnect import KiteConnect
            self._kite = KiteConnect(api_key=self.api_key)
            data = self._kite.generate_session(request_token, api_secret=self.api_secret)
            self._kite.set_access_token(data["access_token"])
            return True
        except Exception as e:
            print(f"Zerodha login error: {e}")
            return False

    def _ensure_kite(self):
        if not self._kite:
            raise RuntimeError("Not logged in. Call get_login_url() then complete_login().")

    def get_historical(self, symbol: str, interval: str, days: int = 365) -> pd.DataFrame:
        self._ensure_kite()
        from datetime import datetime, timedelta
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)

        # Kite needs instrument token — try symbol first, fallback to NSE exchange
        try:
            instruments = self._kite.ltp([f"NSE:{symbol}"])
            token = list(instruments.values())[0]["instrument_token"]
        except Exception:
            # Try NFO or other exchanges
            token = symbol

        data = self._kite.historical_data(token, from_date, to_date, interval)

        df = pd.DataFrame(data)
        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df = df[["open", "high", "low", "close", "volume"]]
        return df

    def get_quote(self, symbol: str) -> dict:
        self._ensure_kite()
        quote = self._kite.quote([f"NSE:{symbol}"])
        q = quote[f"NSE:{symbol}"]
        return {
            "symbol": symbol,
            "ltp": q.get("last_price", 0),
            "open": q.get("ohlc", {}).get("open", 0),
            "high": q.get("ohlc", {}).get("high", 0),
            "low": q.get("ohlc", {}).get("low", 0),
            "close": q.get("ohlc", {}).get("close", 0),
            "volume": q.get("volume", 0),
        }

    def place_order(self, symbol: str, qty: int, side: str,
                    order_type: str = "MARKET", price: float = 0.0) -> dict:
        self._ensure_kite()
        try:
            variety = self._kite.VARIETY_REGULAR
            product = self._kite.PRODUCT_CNC
            otype = self._kite.ORDER_TYPE_MARKET if order_type == "MARKET" else self._kite.ORDER_TYPE_LIMIT

            order_id = self._kite.place_order(
                variety=variety,
                exchange=self._kite.EXCHANGE_NSE,
                tradingsymbol=symbol,
                transaction_type=side,
                quantity=qty,
                product=product,
                order_type=otype,
                price=price if order_type == "LIMIT" else None,
            )
            return {"success": True, "order_id": str(order_id), "message": "Order placed"}
        except Exception as e:
            return {"success": False, "order_id": "", "message": str(e)}

    def get_positions(self) -> list:
        self._ensure_kite()
        positions = self._kite.positions()
        net_positions = positions.get("net", [])
        return [
            {
                "symbol": p["tradingsymbol"],
                "qty": p["quantity"],
                "avg_price": p["average_price"],
                "pnl": p["pnl"],
                "product": p["product"],
            }
            for p in net_positions
            if p["quantity"] != 0
        ]

    def get_order_history(self) -> list:
        self._ensure_kite()
        orders = self._kite.orders()
        return [
            {
                "order_id": o["order_id"],
                "symbol": o["tradingsymbol"],
                "side": o["transaction_type"],
                "qty": o["quantity"],
                "status": o["status"],
                "price": o["average_price"] or o["price"],
            }
            for o in orders
        ]
