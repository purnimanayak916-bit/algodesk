"""
brokers/upstox.py
Upstox (RKSV) API v2 adapter.
Docs: https://upstox.com/developer

NOTE: Upstox endpoint paths and auth flow have changed between API
versions in the past. Verify all endpoints against the current Upstox
developer docs before going live. The structure here is correct; specifics
may need adjustment.

Login flow: browser redirect → auth code → exchange for access_token.
Requires: api_key, api_secret, redirect_uri in secrets.
"""

import requests
import pandas as pd
from brokers.base import BaseBroker


class UpstoxBroker(BaseBroker):
    BASE_URL = "https://api.upstox.com/v2"

    def __init__(self, api_key: str, api_secret: str, redirect_uri: str = "http://localhost:8501"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.redirect_uri = redirect_uri
        self._access_token = None

    @property
    def name(self) -> str:
        return "Upstox"

    @property
    def is_connected(self) -> bool:
        return self._access_token is not None

    def get_login_url(self) -> str:
        return (
            f"{self.BASE_URL}/login/authorization/dialog"
            f"?response_type=code&client_id={self.api_key}"
            f"&redirect_uri={self.redirect_uri}"
        )

    def complete_login(self, auth_code: str, **kwargs) -> bool:
        try:
            import base64
            creds = base64.b64encode(f"{self.api_key}:{self.api_secret}".encode()).decode()
            resp = requests.post(
                f"{self.BASE_URL}/login/authorization/token",
                headers={
                    "Authorization": f"Basic {creds}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "redirect_uri": self.redirect_uri,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                self._access_token = resp.json().get("access_token")
                return self._access_token is not None
            return False
        except Exception as e:
            print(f"Upstox login error: {e}")
            return False

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }

    def _ensure_token(self):
        if not self._access_token:
            raise RuntimeError("Not logged in. Call get_login_url() then complete_login().")

    def get_historical(self, symbol: str, interval: str, days: int = 365) -> pd.DataFrame:
        self._ensure_token()
        from datetime import datetime, timedelta

        # Map our interval to Upstox interval strings
        interval_map = {
            "5minute": "5minute",
            "15minute": "15minute",
            "60minute": "1hour",
            "day": "1day",
        }
        upstox_interval = interval_map.get(interval, "1day")

        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)

        resp = requests.get(
            f"{self.BASE_URL}/historical-candle",
            headers=self._headers(),
            params={
                "instrument_key": f"NSE_EQ|{symbol}",
                "interval": upstox_interval,
                "to_date": to_date.isoformat(),
                "from_date": from_date.isoformat(),
            },
            timeout=30,
        )

        if resp.status_code != 200:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        data = resp.json().get("data", [])
        if not data:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(data)
        # Upstox returns candles as [timestamp, open, high, low, close, volume]
        if "candles" in df.columns:
            candles = df["candles"].tolist()
            df = pd.DataFrame(candles, columns=["date", "open", "high", "low", "close", "volume"])
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
            return df[["open", "high", "low", "close", "volume"]]

        return df

    def get_quote(self, symbol: str) -> dict:
        self._ensure_token()
        resp = requests.get(
            f"{self.BASE_URL}/market-quote/quotes",
            headers=self._headers(),
            params={"instrument_key": f"NSE_EQ|{symbol}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return {"symbol": symbol, "ltp": 0, "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}

        data = resp.json().get("data", {})
        q = data.get(f"NSE_EQ|{symbol}", {})
        ohlc = q.get("ohlc", {})
        return {
            "symbol": symbol,
            "ltp": q.get("last_price", 0),
            "open": ohlc.get("open", 0),
            "high": ohlc.get("high", 0),
            "low": ohlc.get("low", 0),
            "close": ohlc.get("close", 0),
            "volume": q.get("volume", 0),
        }

    def place_order(self, symbol: str, qty: int, side: str,
                    order_type: str = "MARKET", price: float = 0.0) -> dict:
        self._ensure_token()
        try:
            payload = {
                "quantity": qty,
                "product": "D",
                "validity": "DAY",
                "instrument_token": f"NSE_EQ|{symbol}",
                "order_type": order_type,
                "transaction_type": side,
                "disclosed_quantity": 0,
                "trigger_price": 0,
                "is_amo": False,
                "slice": False,
            }
            if order_type == "LIMIT":
                payload["price"] = price

            resp = requests.post(
                f"{self.BASE_URL}/order/place",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=15,
            )
            if resp.status_code == 200:
                order_id = resp.json().get("data", {}).get("order_id", "")
                return {"success": True, "order_id": str(order_id), "message": "Order placed"}
            return {"success": False, "order_id": "", "message": resp.text}
        except Exception as e:
            return {"success": False, "order_id": "", "message": str(e)}

    def get_positions(self) -> list:
        self._ensure_token()
        resp = requests.get(f"{self.BASE_URL}/portfolio/short-term-positions",
                            headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            return []
        positions = resp.json().get("data", [])
        return [
            {
                "symbol": p.get("tradingsymbol", p.get("instrument_token", "")),
                "qty": p.get("quantity", 0),
                "avg_price": p.get("average_price", 0),
                "pnl": p.get("pnl", 0),
                "product": p.get("product", ""),
            }
            for p in positions
            if p.get("quantity", 0) != 0
        ]

    def get_order_history(self) -> list:
        self._ensure_token()
        resp = requests.get(f"{self.BASE_URL}/order/retrieve-all",
                            headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            return []
        orders = resp.json().get("data", [])
        return [
            {
                "order_id": o.get("order_id", ""),
                "symbol": o.get("tradingsymbol", o.get("instrument_token", "")),
                "side": o.get("transaction_type", ""),
                "qty": o.get("quantity", 0),
                "status": o.get("status", ""),
                "price": o.get("average_price", 0) or o.get("price", 0),
            }
            for o in orders
        ]
