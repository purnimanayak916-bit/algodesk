"""
brokers/angelone.py
Angel One (SmartAPI) adapter.
Docs: https://smartapi.angelbroking.com/

Login flow: direct login with client_code + password + TOTP.
No browser redirect needed — generates TOTP from a shared secret.
Enable TOTP-based API login in the Angel One mobile app first.
Requires: api_key, client_code, password, totp_secret in secrets.
"""

import requests
import pandas as pd
from brokers.base import BaseBroker


class AngelOneBroker(BaseBroker):
    BASE_URL = "https://apiconnect.angelbroking.com"
    SMART_API_URL = "https://smartapi.angelbroking.com"

    def __init__(self, api_key: str, client_code: str, password: str, totp_secret: str):
        self.api_key = api_key
        self.client_code = client_code
        self.password = password
        self.totp_secret = totp_secret
        self._access_token = None
        self._jwt_token = None
        self._feed_token = None
        self._obj = None

    @property
    def name(self) -> str:
        return "Angel One"

    @property
    def is_connected(self) -> bool:
        return self._jwt_token is not None

    def get_login_url(self) -> str:
        # Angel One uses direct login, not browser redirect
        return "Direct login — enter client code, password, and TOTP in the form."

    def complete_login(self, totp: str = None, **kwargs) -> bool:
        try:
            from SmartApi import SmartConnect
            import pyotp

            # Generate TOTP from secret if not provided manually
            if totp is None and self.totp_secret:
                totp = pyotp.TOTP(self.totp_secret).now()

            self._obj = SmartConnect(api_key=self.api_key)
            data = self._obj.generateSession(
                self.client_code, self.password, totp
            )

            if data and data.get("status"):
                self._jwt_token = data["data"]["jwtToken"]
                self._feed_token = self._obj.getFeedToken()
                self._refresh_token = data["data"]["refreshToken"]
                return True
            return False
        except Exception as e:
            print(f"Angel One login error: {e}")
            return False

    def _ensure_session(self):
        if not self._obj:
            raise RuntimeError("Not logged in. Call complete_login() first.")

    def get_historical(self, symbol: str, interval: str, days: int = 365) -> pd.DataFrame:
        self._ensure_session()
        from datetime import datetime, timedelta

        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)

        # Angel One interval mapping
        interval_map = {
            "5minute": "FIVE_MINUTE",
            "15minute": "FIFTEEN_MINUTE",
            "60minute": "ONE_HOUR",
            "day": "ONE_DAY",
        }
        ao_interval = interval_map.get(interval, "ONE_DAY")

        # Get instrument token — Angel One requires exchange + symbol token
        # For NSE stocks, we search for the token
        try:
            exchange = "NSE"
            # Try to get the token via search
            search_resp = self._obj.searchScrip(exchange, symbol)
            token = None
            if search_resp and search_resp.get("data"):
                for item in search_resp["data"]:
                    if item["tradingsymbol"] == symbol:
                        token = item["symboltoken"]
                        break
            if token is None:
                # Fallback: use the first result
                if search_resp.get("data"):
                    token = search_resp["data"][0]["symboltoken"]
        except Exception:
            token = symbol  # Last resort

        params = {
            "exchange": "NSE",
            "symboltoken": str(token),
            "interval": ao_interval,
            "fromdate": from_date.strftime("%Y-%m-%d %H:%M:%S"),
            "todate": to_date.strftime("%Y-%m-%d %H:%M:%S"),
        }

        data = self._obj.candleData(params)

        if not data or not data.get("data"):
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        candles = data["data"]
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        df = df.astype({"open": float, "high": float, "low": float, "close": float, "volume": float})
        return df[["open", "high", "low", "close", "volume"]]

    def get_quote(self, symbol: str) -> dict:
        self._ensure_session()
        try:
            # Get LTP quote
            resp = self._obj.ltpData("NSE", symbol, "3045")
            data = resp.get("data", {})
            return {
                "symbol": symbol,
                "ltp": data.get("ltp", 0),
                "open": data.get("open", 0),
                "high": data.get("high", 0),
                "low": data.get("low", 0),
                "close": data.get("close", 0),
                "volume": 0,
            }
        except Exception:
            return {"symbol": symbol, "ltp": 0, "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}

    def place_order(self, symbol: str, qty: int, side: str,
                    order_type: str = "MARKET", price: float = 0.0) -> dict:
        self._ensure_session()
        try:
            # Get the symbol token for the order
            search_resp = self._obj.searchScrip("NSE", symbol)
            token = None
            if search_resp and search_resp.get("data"):
                for item in search_resp["data"]:
                    if item["tradingsymbol"] == symbol:
                        token = item["symboltoken"]
                        break
                if token is None and search_resp["data"]:
                    token = search_resp["data"][0]["symboltoken"]

            order_params = {
                "variety": "NORMAL",
                "tradingsymbol": symbol,
                "symboltoken": str(token),
                "transactiontype": side,
                "exchange": "NSE",
                "ordertype": order_type,
                "producttype": "DELIVERY",
                "duration": "DAY",
                "quantity": qty,
            }
            if order_type == "LIMIT":
                order_params["price"] = str(price)

            order_id = self._obj.placeOrder(order_params)
            return {"success": True, "order_id": str(order_id), "message": "Order placed"}
        except Exception as e:
            return {"success": False, "order_id": "", "message": str(e)}

    def get_positions(self) -> list:
        self._ensure_session()
        try:
            resp = self._obj.position()
            if resp and resp.get("data"):
                return [
                    {
                        "symbol": p.get("tradingsymbol", ""),
                        "qty": p.get("netqty", 0),
                        "avg_price": p.get("avgnetprice", 0),
                        "pnl": p.get("unrealised", 0),
                        "product": p.get("producttype", ""),
                    }
                    for p in resp["data"]
                    if p.get("netqty") != 0
                ]
        except Exception:
            pass
        return []

    def get_order_history(self) -> list:
        self._ensure_session()
        try:
            resp = self._obj.orderBook()
            if resp and resp.get("data"):
                return [
                    {
                        "order_id": o.get("orderid", ""),
                        "symbol": o.get("tradingsymbol", ""),
                        "side": o.get("transactiontype", ""),
                        "qty": o.get("quantity", 0),
                        "status": o.get("orderstatus", ""),
                        "price": o.get("averageprice", 0) or o.get("price", 0),
                    }
                    for o in resp["data"]
                ]
        except Exception:
            pass
        return []
