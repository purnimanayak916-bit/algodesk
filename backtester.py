"""
backtester.py
No-lookahead backtesting engine with metrics.
Iterates candle-by-candle, only using data available up to each point.
"""

import pandas as pd
import numpy as np
from strategy import generate_signals


class Backtester:
    def __init__(self, risk_config: dict = None):
        if risk_config is None:
            risk_config = {
                "max_capital_per_trade_pct": 5.0,
                "stop_loss_pct": 2.0,
                "take_profit_pct": 4.0,
                "max_open_positions": 5,
                "daily_loss_limit_pct": 6.0,
            }
        self.risk = risk_config

    def run(self, df: pd.DataFrame, starting_cash: float = 100000.0,
            strategy_params: dict = None) -> dict:
        """
        Run a backtest on OHLCV data.
        Returns a dict with trades, equity curve, and metrics.
        """
        signals_df = generate_signals(df, strategy_params)

        cash = starting_cash
        position = 0  # shares held
        entry_price = 0.0
        trades = []
        equity_curve = []

        max_trade_capital = starting_cash * (self.risk["max_capital_per_trade_pct"] / 100)
        sl_pct = self.risk["stop_loss_pct"] / 100
        tp_pct = self.risk["take_profit_pct"] / 100

        for i in range(len(signals_df)):
            row = signals_df.iloc[i]
            close = row["close"]
            signal = row["signal"]

            # Check stop-loss / take-profit for open position
            if position > 0 and entry_price > 0:
                if close <= entry_price * (1 - sl_pct):
                    # Stop-loss hit
                    proceeds = position * close
                    cash += proceeds
                    pnl = (close - entry_price) * position
                    trades.append({
                        "entry_time": entry_time, "exit_time": row.name,
                        "entry_price": entry_price, "exit_price": close,
                        "qty": position, "pnl": pnl, "reason": "Stop Loss",
                    })
                    position = 0
                    entry_price = 0.0
                    continue
                elif close >= entry_price * (1 + tp_pct):
                    # Take-profit hit
                    proceeds = position * close
                    cash += proceeds
                    pnl = (close - entry_price) * position
                    trades.append({
                        "entry_time": entry_time, "exit_time": row.name,
                        "entry_price": entry_price, "exit_price": close,
                        "qty": position, "pnl": pnl, "reason": "Take Profit",
                    })
                    position = 0
                    entry_price = 0.0
                    continue

            # Process signals
            if signal == 1 and position == 0:
                # BUY
                qty = int(max_trade_capital / close)
                if qty > 0:
                    cost = qty * close
                    if cost <= cash:
                        cash -= cost
                        position = qty
                        entry_price = close
                        entry_time = row.name
            elif signal == -1 and position > 0:
                # SELL
                proceeds = position * close
                cash += proceeds
                pnl = (close - entry_price) * position
                trades.append({
                    "entry_time": entry_time, "exit_time": row.name,
                    "entry_price": entry_price, "exit_price": close,
                    "qty": position, "pnl": pnl, "reason": "Signal",
                })
                position = 0
                entry_price = 0.0

            # Record equity
            equity = cash + (position * close)
            equity_curve.append({"time": row.name, "equity": equity})

        # Close any remaining position at the last close
        if position > 0:
            close = signals_df.iloc[-1]["close"]
            proceeds = position * close
            cash += proceeds
            pnl = (close - entry_price) * position
            trades.append({
                "entry_time": entry_time, "exit_time": signals_df.index[-1],
                "entry_price": entry_price, "exit_price": close,
                "qty": position, "pnl": pnl, "reason": "End of Data",
            })
            position = 0

        # Build metrics
        trades_df = pd.DataFrame(trades)
        equity_df = pd.DataFrame(equity_curve)

        metrics = self._compute_metrics(trades_df, equity_df, starting_cash, cash)
        return {
            "trades": trades_df,
            "equity_curve": equity_df,
            "metrics": metrics,
            "final_cash": cash,
        }

    def _compute_metrics(self, trades_df: pd.DataFrame, equity_df: pd.DataFrame,
                         starting_cash: float, final_cash: float) -> dict:
        if trades_df.empty:
            return {
                "total_return_pct": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate_pct": 0.0,
                "avg_pnl": 0.0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
                "final_equity": final_cash,
            }

        total_pnl = trades_df["pnl"].sum()
        total_return_pct = (total_pnl / starting_cash) * 100

        wins = trades_df[trades_df["pnl"] > 0]
        losses = trades_df[trades_df["pnl"] <= 0]
        win_rate = len(wins) / len(trades_df) * 100 if len(trades_df) > 0 else 0

        # Max drawdown from equity curve
        if not equity_df.empty:
            equity = equity_df["equity"]
            running_max = equity.cummax()
            drawdown = (equity - running_max) / running_max * 100
            max_dd = drawdown.min()
        else:
            max_dd = 0.0

        # Sharpe ratio (simplified, using trade returns)
        if len(trades_df) > 1:
            returns = trades_df["pnl"] / starting_cash
            sharpe = (returns.mean() / returns.std()) * np.sqrt(len(returns)) if returns.std() > 0 else 0.0
        else:
            sharpe = 0.0

        return {
            "total_return_pct": round(total_return_pct, 2),
            "total_trades": len(trades_df),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": round(win_rate, 2),
            "avg_pnl": round(trades_df["pnl"].mean(), 2),
            "max_drawdown_pct": round(abs(max_dd), 2),
            "sharpe_ratio": round(sharpe, 4),
            "final_equity": round(final_cash, 2),
        }
