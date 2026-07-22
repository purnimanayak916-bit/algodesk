"""
paper_trader.py
In-memory simulated portfolio for risk-free strategy testing.
State lives in st.session_state (persists for the browser session only —
by design, since Streamlit Cloud free tier has no reliable persistent DB
attached out of the box). See README for how to wire up a real database
if you want trade history to survive restarts.
"""

import pandas as pd


class PaperTrader:
    def __init__(self, starting_cash: float = 100000.0):
        self.cash = starting_cash
        self.starting_cash = starting_cash
        self.positions = {}   # symbol -> {qty, avg_price}
        self.trade_log = []   # list of dicts

    def buy(self, symbol: str, qty: int, price: float, reason: str = ""):
        cost = qty * price
        if cost > self.cash:
            return False, "Insufficient paper cash"
        self.cash -= cost
        pos = self.positions.get(symbol, {"qty": 0, "avg_price": 0.0})
        new_qty = pos["qty"] + qty
        pos["avg_price"] = ((pos["avg_price"] * pos["qty"]) + cost) / new_qty
        pos["qty"] = new_qty
        self.positions[symbol] = pos
        self.trade_log.append({
            "time": pd.Timestamp.now(), "symbol": symbol, "side": "BUY",
            "qty": qty, "price": price, "reason": reason,
        })
        return True, "OK"

    def sell(self, symbol: str, qty: int, price: float, reason: str = ""):
        pos = self.positions.get(symbol)
        if not pos or pos["qty"] < qty:
            return False, "Not enough paper shares held"
        proceeds = qty * price
        self.cash += proceeds
        pnl = (price - pos["avg_price"]) * qty
        pos["qty"] -= qty
        if pos["qty"] == 0:
            del self.positions[symbol]
        else:
            self.positions[symbol] = pos
        self.trade_log.append({
            "time": pd.Timestamp.now(), "symbol": symbol, "side": "SELL",
            "qty": qty, "price": price, "pnl": pnl, "reason": reason,
        })
        return True, "OK"

    def portfolio_value(self, current_prices: dict) -> float:
        holdings_value = sum(
            pos["qty"] * current_prices.get(sym, pos["avg_price"])
            for sym, pos in self.positions.items()
        )
        return self.cash + holdings_value

    def positions_df(self, current_prices: dict) -> pd.DataFrame:
        rows = []
        for sym, pos in self.positions.items():
            ltp = current_prices.get(sym, pos["avg_price"])
            pnl = (ltp - pos["avg_price"]) * pos["qty"]
            pnl_pct = (ltp / pos["avg_price"] - 1) * 100 if pos["avg_price"] else 0
            rows.append({
                "Symbol": sym, "Qty": pos["qty"], "Avg Price": round(pos["avg_price"], 2),
                "LTP": round(ltp, 2), "P&L": round(pnl, 2), "P&L %": round(pnl_pct, 2),
            })
        return pd.DataFrame(rows)

    def trade_log_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.trade_log)
