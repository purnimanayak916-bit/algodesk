"""
brokers/groww.py
Groww Trading API adapter.
Docs: https://groww.in/trade-api/docs

Login flow: API Key + TOTP → access token (expires daily at 6:00 AM).
Requires: api_key, totp_secret (or manual TOTP entry) in secrets.

Groww API supports equity (CASH) and derivatives (FNO) only.
All requests need headers: Authorization, Accept, X-API-VERSION.
"""

import requests
import pandas as pd
import time
import hashlib
from datetime import datetime, timedelta
from brokers.base import BaseBroker


class GrowwBroker(BaseBroker):
    BASE_URL = "https://api.groww.in/v1"

    def __init__(self, api_key: str, totp_secret: str = ""):
        self.api_key = api_key
        self.totp_secret = totp_secret
        self._access_token = None

    @property
    def name(self) -> str:
        return "Groww"

    @property
    def is_connected(self) -> bool:
        return self._access_token is not None

    def get_login_url(self) -> str:
        return "https://groww.in/trade-api/api-keys"

    def complete_login(self, totp: str = "", **kwargs) -> bool:
        if not totp:
            return False
        try:
            resp = requests.post(
                f"{self.BASE_URL}/token/api/access",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "key_type": "totp",
                    "totp": totp,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._access_token = data.get("token")
                return self._access_token is not None
            return False
        except Exception as e:
            print(f"Groww login error: {e}")
            return False

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "X-API-VERSION": "1.0",
        }

    def _ensure_token(self):
        if not self._access_token:
            raise RuntimeError("Not logged in. Go to Connect page and enter TOTP.")

    def get_historical(self, symbol: str, interval: str, days: int = 365) -> pd.DataFrame:
        self._ensure_token()

        # Map our interval to Groww interval_in_minutes
        interval_map = {
            "5minute": 5,
            "15minute": 15,
            "60minute": 60,
            "day": 1440,
        }
        minutes = interval_map.get(interval, 1440)

        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)

        # Format: yyyy-MM-dd HH:mm:ss
        start = from_date.strftime("%Y-%m-%d %H:%M:%S")
        end = to_date.strftime("%Y-%m-%d %H:%M:%S")

        try:
            resp = requests.get(
                f"{self.BASE_URL}/historical/candle/range",
                headers=self._headers(),
                params={
                    "exchange": "NSE",
                    "segment": "CASH",
                    "trading_symbol": symbol,
                    "start_time": start,
                    "end_time": end,
                    "interval_in_minutes": minutes,
                },
                timeout=30,
            )

            if resp.status_code != 200:
                return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

            payload = resp.json().get("payload", {})
            candles = payload.get("candles", [])

            if not candles:
                return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

            # Each candle: [epoch_second, open, high, low, close, volume]
            df = pd.DataFrame(candles, columns=["date", "open", "high", "low", "close", "volume"])
            df["date"] = pd.to_datetime(df["date"], unit="s")
            df.set_index("date", inplace=True)
            return df[["open", "high", "low", "close", "volume"]]

        except Exception as e:
            print(f"Groww historical error: {e}")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def get_quote(self, symbol: str) -> dict:
        self._ensure_token()
        try:
            resp = requests.get(
                f"{self.BASE_URL}/live-data/quote",
                headers=self._headers(),
                params={
                    "exchange": "NSE",
                    "segment": "CASH",
                    "trading_symbol": symbol,
                },
                timeout=10,
            )

            if resp.status_code != 200:
                return {"symbol": symbol, "ltp": 0, "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}

            payload = resp.json().get("payload", {})
            ohlc_str = payload.get("ohlc", "")

            # Parse OHLC from string format: "{open: 149.50,high: 150.50,low: 148.50,close: 149.50}"
            ohlc = {"open": 0, "high": 0, "low": 0, "close": 0}
            if ohlc_str:
                import re
                for key in ["open", "high", "low", "close"]:
                    match = re.search(rf"{key}:\s*([\d.]+)", ohlc_str)
                    if match:
                        ohlc[key] = float(match.group(1))

            return {
                "symbol": symbol,
                "ltp": payload.get("last_price", 0),
                "open": ohlc["open"],
                "high": ohlc["high"],
                "low": ohlc["low"],
                "close": ohlc["close"],
                "volume": payload.get("volume", 0),
            }

        except Exception as e:
            print(f"Groww quote error: {e}")
            return {"symbol": symbol, "ltp": 0, "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}

    def place_order(self, symbol: str, qty: int, side: str,
                    order_type: str = "MARKET", price: float = 0.0) -> dict:
        self._ensure_token()
        try:
            payload = {
                "trading_symbol": symbol,
                "quantity": qty,
                "validity": "DAY",
                "exchange": "NSE",
                "segment": "CASH",
                "product": "CNC",
                "order_type": order_type,
                "transaction_type": side,
            }
            if order_type == "LIMIT":
                payload["price"] = price
            else:
                payload["price"] = 0

            resp = requests.post(
                f"{self.BASE_URL}/order/create",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=15,
            )

            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "SUCCESS":
                    order_id = data.get("payload", {}).get("groww_order_id", "")
                    return {"success": True, "order_id": str(order_id), "message": "Order placed"}
                else:
                    err = data.get("error", {})
                    return {"success": False, "order_id": "", "message": err.get("message", "Order failed")}
            return {"success": False, "order_id": "", "message": resp.text}
        except Exception as e:
            return {"success": False, "order_id": "", "message": str(e)}

    def get_positions(self) -> list:
        self._ensure_token()
        try:
            resp = requests.get(
                f"{self.BASE_URL}/positions/user",
                headers=self._headers(),
                params={"segment": "CASH"},
                timeout=10,
            )
            if resp.status_code != 200:
                return []

            positions = resp.json().get("payload", {}).get("positions", [])
            return [
                {
                    "symbol": p.get("trading_symbol", ""),
                    "qty": p.get("quantity", 0),
                    "avg_price": p.get("net_price", 0),
                    "pnl": p.get("realised_pnl", 0),
                    "product": p.get("product", ""),
                }
                for p in positions
                if p.get("quantity", 0) != 0
            ]
        except Exception as e:
            print(f"Groww positions error: {e}")
            return []

    def get_order_history(self) -> list:
        self._ensure_token()
        try:
            resp = requests.get(
                f"{self.BASE_URL}/order/list",
                headers=self._headers(),
                params={"segment": "CASH", "page": 0, "page_size": 50},
                timeout=10,
            )
            if resp.status_code != 200:
                return []

            orders = resp.json().get("payload", {}).get("orders", [])
            return [
                {
                    "order_id": o.get("groww_order_id", ""),
                    "symbol": o.get("trading_symbol", ""),
                    "side": o.get("transaction_type", ""),
                    "qty": o.get("quantity", 0),
                    "status": o.get("order_status", ""),
                    "price": o.get("price", 0) or o.get("average_fill_price", 0),
                }
                for o in orders
            ]
        except Exception as e:
            print(f"Groww order history error: {e}")
            return []
