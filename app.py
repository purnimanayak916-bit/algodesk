"""
app.py
AlgoDesk — Multi-Broker Stock Trading Dashboard
Main Streamlit application with broker selector and all pages.
Now includes Social Trading Hub (groups, signal sharing, social feed).
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta, datetime

from config import (
    APP_TITLE, DEFAULT_WATCHLIST, DEFAULT_RISK,
    STRATEGY_PARAMS, INTERVAL_CHOICES,
)
from broker_factory import create_broker, SUPPORTED_BROKERS
from indicators import add_all_indicators
from strategy import generate_signals, latest_signal
from backtester import Backtester
from paper_trader import PaperTrader
from telegram_alert import send_telegram_message
from social import (
    init_social_state, ensure_username, create_group, join_group,
    get_my_groups, update_risk_settings, post_signal, get_group_signals,
    respond_to_signal, get_social_feed, get_signal_stats,
)


# ── Page config ─────────────────────────────────────────────────────
st.set_page_config(page_title=APP_TITLE, page_icon="📈", layout="wide")

# ── Session state init ───────────────────────────────────────────────
def init_state():
    defaults = {
        "broker": None,
        "broker_name": None,
        "watchlist": DEFAULT_WATCHLIST.copy(),
        "risk": DEFAULT_RISK.copy(),
        "strategy_params": STRATEGY_PARAMS.copy(),
        "paper_trader": PaperTrader(),
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val
    init_social_state()

init_state()


# ── Custom CSS for cyber + Instagram styling ─────────────────────────
st.markdown("""
<style>
/* Cyber electric blue theme */
.stApp {
    background: linear-gradient(135deg, #0A0E1A 0%, #06080F 100%);
}
.stSidebar {
    background: linear-gradient(180deg, #06080F 0%, #0A0E1A 100%);
    border-right: 1px solid rgba(0, 212, 255, 0.15);
}
.stSidebar .stRadio > div {
    gap: 4px;
}
/* Metric cards glow */
.stMetric {
    border-radius: 14px;
    padding: 20px;
    background: rgba(15, 20, 35, 0.7);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.06);
}
/* Instagram gradient text for headers */
.ig-gradient {
    background: linear-gradient(135deg, #F58529, #DD2A7B, #8134AF, #515BD4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-weight: 800;
}
/* Electric gradient */
.electric-gradient {
    background: linear-gradient(135deg, #00D4FF, #B026FF);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-weight: 800;
}
/* Signal cards */
.signal-buy {
    border-left: 4px solid #00FF9F;
    padding: 16px 20px;
    border-radius: 8px;
    background: rgba(0, 255, 159, 0.05);
    margin-bottom: 12px;
}
.signal-sell {
    border-left: 4px solid #FF3B5C;
    padding: 16px 20px;
    border-radius: 8px;
    background: rgba(255, 59, 92, 0.05);
    margin-bottom: 12px;
}
/* Group card Instagram border */
.group-card {
    padding: 3px;
    background: linear-gradient(135deg, #F58529, #DD2A7B, #8134AF, #515BD4);
    border-radius: 16px;
    margin-bottom: 12px;
}
.group-card-inner {
    background: rgba(15, 20, 35, 0.9);
    backdrop-filter: blur(20px);
    border-radius: 14px;
    padding: 20px;
}
/* Feed items */
.feed-item {
    padding: 12px 16px;
    border-left: 2px solid rgba(0, 212, 255, 0.3);
    margin-bottom: 8px;
    background: rgba(255, 255, 255, 0.02);
    border-radius: 0 8px 8px 0;
    font-size: 14px;
}
/* Demo badge */
.demo-badge {
    display: inline-block;
    padding: 6px 16px;
    background: rgba(255, 59, 92, 0.1);
    border: 1px solid rgba(255, 59, 92, 0.2);
    border-radius: 20px;
    font-size: 12px;
    color: #FF6B7A;
}
</style>
""", unsafe_allow_html=True)


# ── Sidebar: broker selector ─────────────────────────────────────────
st.sidebar.title(APP_TITLE)
st.sidebar.markdown("---")

broker_choice = st.sidebar.selectbox(
    "Select Broker",
    options=SUPPORTED_BROKERS,
    index=0,
    help="Switch brokers anytime — all pages work the same way."
)

st.sidebar.markdown("---")

# Navigation
pages = [
    "📊 Dashboard", "📈 Charts", "🔬 Backtest",
    "📝 Paper Trading", "⚡ Live Orders",
    "👥 Social Hub", "📡 Signal Share", "📰 Feed",
    "⚙️ Settings", "🔗 Connect",
]
page = st.sidebar.radio("Navigate", pages)

st.sidebar.markdown("---")
username = ensure_username()
st.sidebar.markdown(f"👤 **{username}**")
st.sidebar.markdown('<span class="demo-badge">🔒 Demo Mode</span>', unsafe_allow_html=True)


# ── Helper: get broker connection ────────────────────────────────────
def get_broker():
    """Return the current broker instance from session state."""
    return st.session_state.get("broker")


def require_broker():
    """Show a warning if not connected, return False."""
    b = get_broker()
    if b is None or not b.is_connected:
        st.warning("⚠️ Not connected. Go to the **Connect** page to log in.")
        return False
    return True


def try_create_broker():
    """Try to instantiate the selected broker from secrets."""
    if st.session_state.get("broker_name") != broker_choice:
        try:
            secrets = st.secrets
            b = create_broker(broker_choice, dict(secrets))
            st.session_state["broker"] = b
            st.session_state["broker_name"] = broker_choice
            return b
        except Exception as e:
            st.session_state["broker"] = None
            return None
    return st.session_state.get("broker")


broker = try_create_broker()


# ═══════════════════════════════════════════════════════════════════════
# CONNECT PAGE
# ═══════════════════════════════════════════════════════════════════════
if "Connect" in page:
    st.title("🔗 Connect to Broker")
    st.markdown(f"**Selected broker:** {broker_choice}")

    if broker is None:
        st.error(
            f"No secrets found for **{broker_choice}**. "
            f"Add your API keys to `.streamlit/secrets.toml` and restart."
        )
        st.info("See `secrets.toml.example` for the required fields.")
        st.stop()

    if broker.is_connected:
        st.success(f"✅ Connected to {broker.name}!")
        st.markdown("You're all set. Head to the **Dashboard** to start trading.")
        if st.button("Disconnect"):
            st.session_state["broker"] = None
            st.session_state["broker_name"] = None
            st.rerun()
        st.stop()

    # ── Zerodha login ──
    if broker_choice == "Zerodha":
        st.markdown("### Zerodha Login")
        st.markdown("1. Click the login URL below.\n2. Authorize on Kite.\n3. Copy the `request_token` from the redirect URL.")
        if st.button("Get Login URL"):
            url = broker.get_login_url()
            st.code(url)
            st.markdown(f"[Open Login URL]({url})")
        request_token = st.text_input("Paste request_token here:")
        if st.button("Complete Login") and request_token:
            with st.spinner("Logging in..."):
                if broker.complete_login(request_token=request_token):
                    st.success("✅ Logged in to Zerodha!")
                    st.rerun()
                else:
                    st.error("Login failed. Check your request_token and API keys.")

    # ── Upstox login ──
    elif broker_choice == "Upstox":
        st.markdown("### Upstox Login")
        st.markdown("1. Click the login URL below.\n2. Authorize on Upstox.\n3. Copy the `auth_code` from the redirect URL.")
        if st.button("Get Login URL"):
            url = broker.get_login_url()
            st.code(url)
            st.markdown(f"[Open Login URL]({url})")
        auth_code = st.text_input("Paste auth code here:")
        if st.button("Complete Login") and auth_code:
            with st.spinner("Logging in..."):
                if broker.complete_login(auth_code=auth_code):
                    st.success("✅ Logged in to Upstox!")
                    st.rerun()
                else:
                    st.error("Login failed. Check your auth code and API keys.")

    # ── Angel One login ──
    elif broker_choice == "Angel One":
        st.markdown("### Angel One Login")
        st.markdown("Direct login — enter your TOTP below. Make sure TOTP-based API login is enabled in the Angel One app.")
        totp_input = st.text_input("Enter 6-digit TOTP:", max_chars=6)
        if st.button("Complete Login") and totp_input:
            with st.spinner("Logging in..."):
                if broker.complete_login(totp=totp_input):
                    st.success("✅ Logged in to Angel One!")
                    st.rerun()
                else:
                    st.error("Login failed. Check your TOTP and credentials.")


# ═══════════════════════════════════════════════════════════════════════
# DASHBOARD PAGE
# ═══════════════════════════════════════════════════════════════════════
elif "Dashboard" in page:
    st.title("📊 Dashboard")

    if not require_broker():
        st.stop()

    broker = get_broker()

    # Watchlist editor
    with st.expander("Watchlist (click to edit)"):
        new_list = st.text_area(
            "Symbols (comma-separated)",
            value=", ".join(st.session_state["watchlist"]),
        )
        if st.button("Update Watchlist"):
            symbols = [s.strip().upper() for s in new_list.split(",") if s.strip()]
            st.session_state["watchlist"] = symbols
            st.rerun()

    interval_label = st.selectbox(
        "Interval", list(INTERVAL_CHOICES.keys()), index=1
    )
    interval = INTERVAL_CHOICES[interval_label]

    st.markdown("---")

    # Signal scan
    st.subheader("Live Signals")
    watchlist = st.session_state["watchlist"]

    if st.button("🔄 Scan Watchlist"):
        signal_data = []
        progress = st.progress(0)
        for i, symbol in enumerate(watchlist):
            try:
                df = broker.get_historical(symbol, interval=interval, days=120)
                if df.empty or len(df) < 60:
                    signal_data.append({
                        "Symbol": symbol, "Signal": "N/A",
                        "RSI": None, "Price": None, "Error": "Insufficient data"
                    })
                    continue
                df = generate_signals(df, st.session_state["strategy_params"])
                last_row = df.iloc[-1]
                signal_data.append({
                    "Symbol": symbol,
                    "Signal": last_row["signal_label"],
                    "RSI": round(last_row["rsi"], 2),
                    "Price": round(last_row["close"], 2),
                    "MACD Hist": round(last_row["macd_hist"], 4),
                    "SMA Fast": round(last_row["sma_fast"], 2),
                    "SMA Slow": round(last_row["sma_slow"], 2),
                })
            except Exception as e:
                signal_data.append({
                    "Symbol": symbol, "Signal": "ERROR",
                    "RSI": None, "Price": None, "Error": str(e)
                })
            progress.progress((i + 1) / len(watchlist))

        if signal_data:
            sig_df = pd.DataFrame(signal_data)
            st.dataframe(sig_df, use_container_width=True)

            # Telegram alert for BUY/SELL signals
            tg = dict(st.secrets.get("telegram", {})) if "telegram" in st.secrets else {}
            bot_token = tg.get("bot_token", "")
            chat_id = tg.get("chat_id", "")
            buy_signals = [d for d in signal_data if d.get("Signal") == "BUY"]
            sell_signals = [d for d in signal_data if d.get("Signal") == "SELL"]
            if (buy_signals or sell_signals) and bot_token and chat_id:
                alerts = []
                if buy_signals:
                    alerts.append("🟢 BUY: " + ", ".join(d["Symbol"] for d in buy_signals))
                if sell_signals:
                    alerts.append("🔴 SELL: " + ", ".join(d["Symbol"] for d in sell_signals))
                send_telegram_message(bot_token, chat_id, "\n".join(alerts))
                st.toast("Telegram alerts sent!")

    # Quick quote
    st.markdown("---")
    st.subheader("Quick Quote")
    symbol = st.selectbox("Symbol", st.session_state["watchlist"])
    if st.button("Get Quote"):
        try:
            q = broker.get_quote(symbol)
            cols = st.columns(5)
            cols[0].metric("LTP", f"₹{q['ltp']}")
            cols[1].metric("Open", f"₹{q['open']}")
            cols[2].metric("High", f"₹{q['high']}")
            cols[3].metric("Low", f"₹{q['low']}")
            cols[4].metric("Close", f"₹{q['close']}")
        except Exception as e:
            st.error(f"Error fetching quote: {e}")


# ═══════════════════════════════════════════════════════════════════════
# CHARTS PAGE
# ═══════════════════════════════════════════════════════════════════════
elif "Charts" in page:
    st.title("📈 Charts")

    if not require_broker():
        st.stop()

    broker = get_broker()

    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.text_input("Symbol", value=st.session_state["watchlist"][0])
    with col2:
        interval_label = st.selectbox("Interval", list(INTERVAL_CHOICES.keys()), index=3)
        interval = INTERVAL_CHOICES[interval_label]
    with col3:
        days = st.number_input("Lookback (days)", value=180, min_value=30, max_value=730)

    if st.button("Load Chart"):
        with st.spinner("Fetching data..."):
            try:
                df = broker.get_historical(symbol.upper(), interval=interval, days=days)
                if df.empty:
                    st.warning("No data returned.")
                    st.stop()
            except Exception as e:
                st.error(f"Error fetching data: {e}")
                st.stop()

        df = generate_signals(df, st.session_state["strategy_params"])
        df = add_all_indicators(df, st.session_state["strategy_params"])

        # Candlestick + volume chart
        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True,
            row_heights=[0.6, 0.2, 0.2],
            vertical_spacing=0.03,
            subplot_titles=("Price & SMA", "Volume", "RSI")
        )

        fig.add_trace(go.Candlestick(
            x=df.index, open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name="OHLC"
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["sma_fast"], name="SMA Fast",
            line=dict(color="blue", width=1.5)
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["sma_slow"], name="SMA Slow",
            line=dict(color="orange", width=1.5)
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["bb_upper"], name="BB Upper",
            line=dict(color="gray", dash="dash", width=1), opacity=0.5
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["bb_lower"], name="BB Lower",
            line=dict(color="gray", dash="dash", width=1), opacity=0.5
        ), row=1, col=1)

        colors = ["green" if c >= o else "red" for c, o in zip(df["close"], df["open"])]
        fig.add_trace(go.Bar(
            x=df.index, y=df["volume"], name="Volume",
            marker_color=colors, opacity=0.7
        ), row=2, col=1)

        fig.add_trace(go.Scatter(
            x=df.index, y=df["rsi"], name="RSI",
            line=dict(color="purple", width=1.5)
        ), row=3, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)

        fig.update_layout(
            height=800, xaxis_rangeslider_visible=False,
            title_text=f"{symbol.upper()} — {interval_label}"
        )
        st.plotly_chart(fig, use_container_width=True)

        buys = df[df["signal"] == 1]
        sells = df[df["signal"] == -1]
        if not buys.empty:
            st.markdown(f"🟢 **{len(buys)} BUY signals**")
            st.dataframe(buys[["close", "rsi", "macd_hist", "sma_fast", "sma_slow"]].tail(10))
        if not sells.empty:
            st.markdown(f"🔴 **{len(sells)} SELL signals**")
            st.dataframe(sells[["close", "rsi", "macd_hist", "sma_fast", "sma_slow"]].tail(10))


# ═══════════════════════════════════════════════════════════════════════
# BACKTEST PAGE
# ═══════════════════════════════════════════════════════════════════════
elif "Backtest" in page:
    st.title("🔬 Backtest")

    if not require_broker():
        st.stop()

    broker = get_broker()

    col1, col2 = st.columns(2)
    with col1:
        bt_symbol = st.text_input("Symbol", value=st.session_state["watchlist"][0], key="bt_symbol")
        bt_interval_label = st.selectbox("Interval", list(INTERVAL_CHOICES.keys()), index=3, key="bt_interval")
        bt_days = st.number_input("Lookback (days)", value=365, min_value=60, max_value=730, key="bt_days")
    with col2:
        bt_capital = st.number_input("Starting Capital (₹)", value=100000, min_value=10000, key="bt_capital")

    if st.button("Run Backtest"):
        with st.spinner("Running backtest..."):
            try:
                interval = INTERVAL_CHOICES[bt_interval_label]
                df = broker.get_historical(bt_symbol.upper(), interval=interval, days=int(bt_days))
                if df.empty or len(df) < 60:
                    st.warning("Not enough data for backtesting.")
                    st.stop()
            except Exception as e:
                st.error(f"Error fetching data: {e}")
                st.stop()

            bt = Backtester(st.session_state["risk"])
            results = bt.run(df, starting_cash=bt_capital, strategy_params=st.session_state["strategy_params"])

            m = results["metrics"]
            st.markdown("### Results")
            cols = st.columns(4)
            cols[0].metric("Total Return", f"{m['total_return_pct']}%")
            cols[1].metric("Win Rate", f"{m['win_rate_pct']}%")
            cols[2].metric("Total Trades", m["total_trades"])
            cols[3].metric("Max Drawdown", f"{m['max_drawdown_pct']}%")

            cols2 = st.columns(3)
            cols2[0].metric("Final Equity", f"₹{m['final_equity']:,.2f}")
            cols2[1].metric("Avg P&L/Trade", f"₹{m['avg_pnl']:,.2f}")
            cols2[2].metric("Sharpe Ratio", m["sharpe_ratio"])

            if not results["equity_curve"].empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=results["equity_curve"]["time"],
                    y=results["equity_curve"]["equity"],
                    name="Equity", fill="tozeroy",
                    line=dict(color="royalblue", width=2)
                ))
                fig.update_layout(title="Equity Curve", height=400)
                st.plotly_chart(fig, use_container_width=True)

            if not results["trades"].empty:
                st.markdown("### Trade Log")
                st.dataframe(results["trades"], use_container_width=True)
            else:
                st.info("No trades generated. Try adjusting strategy parameters in Settings.")


# ═══════════════════════════════════════════════════════════════════════
# PAPER TRADING PAGE
# ═══════════════════════════════════════════════════════════════════════
elif "Paper Trading" in page:
    st.title("📝 Paper Trading")

    if not require_broker():
        st.stop()

    broker = get_broker()
    pt = st.session_state["paper_trader"]

    st.markdown("### Portfolio")
    try:
        prices = {}
        for sym in st.session_state["watchlist"][:10]:
            try:
                q = broker.get_quote(sym)
                prices[sym] = q["ltp"]
            except Exception:
                pass
    except Exception:
        prices = {}

    portfolio_val = pt.portfolio_value(prices)
    cols = st.columns(3)
    cols[0].metric("Cash", f"₹{pt.cash:,.2f}")
    cols[1].metric("Portfolio Value", f"₹{portfolio_val:,.2f}")
    pnl_pct = (portfolio_val / pt.starting_cash - 1) * 100
    cols[2].metric("Return", f"{pnl_pct:.2f}%")

    st.markdown("---")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        pt_symbol = st.selectbox("Symbol", st.session_state["watchlist"], key="pt_symbol")
    with col2:
        pt_qty = st.number_input("Qty", min_value=1, value=10, key="pt_qty")
    with col3:
        pt_price = st.number_input("Price (0 = live LTP)", min_value=0.0, value=0.0, key="pt_price")
    with col4:
        pt_action = st.selectbox("Action", ["BUY", "SELL"], key="pt_action")

    if st.button("Execute Paper Trade"):
        price = pt_price
        if price == 0:
            try:
                q = broker.get_quote(pt_symbol)
                price = q["ltp"]
            except Exception as e:
                st.error(f"Couldn't get live price: {e}")
                st.stop()

        if pt_action == "BUY":
            ok, msg = pt.buy(pt_symbol, pt_qty, price, "Manual")
        else:
            ok, msg = pt.sell(pt_symbol, pt_qty, price, "Manual")

        if ok:
            st.success(f"✅ {pt_action} {pt_qty} {pt_symbol} @ ₹{price:.2f}")
        else:
            st.error(f"❌ {msg}")

    st.markdown("---")

    st.markdown("### Open Positions")
    pos_df = pt.positions_df(prices)
    if pos_df.empty:
        st.info("No open positions.")
    else:
        st.dataframe(pos_df, use_container_width=True)

    st.markdown("### Trade History")
    log_df = pt.trade_log_df()
    if log_df.empty:
        st.info("No trades yet.")
    else:
        st.dataframe(log_df, use_container_width=True)

    if st.button("Reset Paper Portfolio"):
        st.session_state["paper_trader"] = PaperTrader()
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# LIVE ORDERS PAGE
# ═══════════════════════════════════════════════════════════════════════
elif "Live Orders" in page:
    st.title("⚡ Live Orders")

    if not require_broker():
        st.stop()

    broker = get_broker()

    st.warning(
        "⚠️ **This page places REAL orders with real money.** "
        "Test everything in Paper Trading and Backtest first."
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        lo_symbol = st.selectbox("Symbol", st.session_state["watchlist"], key="lo_symbol")
    with col2:
        lo_qty = st.number_input("Qty", min_value=1, value=1, key="lo_qty")
    with col3:
        lo_type = st.selectbox("Order Type", ["MARKET", "LIMIT"], key="lo_type")
    with col4:
        lo_side = st.selectbox("Side", ["BUY", "SELL"], key="lo_side")

    lo_price = 0.0
    if lo_type == "LIMIT":
        lo_price = st.number_input("Limit Price (₹)", min_value=0.0, value=0.0, key="lo_price")

    st.markdown("---")
    st.markdown("**Type `CONFIRM` below to place this order.**")
    confirm = st.text_input("Confirmation", key="lo_confirm", placeholder="CONFIRM")

    if st.button("Place Live Order", type="primary"):
        if confirm != "CONFIRM":
            st.error("❌ You must type CONFIRM to place a live order.")
        else:
            with st.spinner("Placing order..."):
                result = broker.place_order(
                    symbol=lo_symbol.upper(),
                    qty=lo_qty,
                    side=lo_side,
                    order_type=lo_type,
                    price=lo_price,
                )
                if result["success"]:
                    st.success(f"✅ Order placed! ID: {result['order_id']}")
                    tg = dict(st.secrets.get("telegram", {})) if "telegram" in st.secrets else {}
                    if tg.get("bot_token") and tg.get("chat_id"):
                        msg = f"🚨 LIVE ORDER\n{lo_side} {lo_qty} {lo_symbol}\nType: {lo_type}\nID: {result['order_id']}"
                        send_telegram_message(tg["bot_token"], tg["chat_id"], msg)
                else:
                    st.error(f"❌ Order failed: {result['message']}")

    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("### Current Positions")
        try:
            positions = broker.get_positions()
            if positions:
                st.dataframe(pd.DataFrame(positions), use_container_width=True)
            else:
                st.info("No open positions.")
        except Exception as e:
            st.error(f"Error: {e}")
    with col_b:
        st.markdown("### Recent Orders")
        try:
            orders = broker.get_order_history()
            if orders:
                st.dataframe(pd.DataFrame(orders), use_container_width=True)
            else:
                st.info("No recent orders.")
        except Exception as e:
            st.error(f"Error: {e}")


# ═══════════════════════════════════════════════════════════════════════
# SOCIAL HUB PAGE (Instagram-inspired groups)
# ═══════════════════════════════════════════════════════════════════════
elif "Social Hub" in page:
    st.markdown('<h1 class="ig-gradient">👥 Social Hub</h1>', unsafe_allow_html=True)
    st.markdown("Create or join trading groups. Share signals. Demo mode — no real money.")
    st.markdown("---")

    username = ensure_username()

    # ── Create / Join ──
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🏠 Create Group")
        with st.form("create_group_form"):
            grp_name = st.text_input("Group Name", key="cg_name")
            grp_pass = st.text_input("Group Password", type="password", key="cg_pass")
            submitted = st.form_submit_button("Create Group")
            if submitted and grp_name and grp_pass:
                result = create_group(grp_name, grp_pass, username)
                st.success(f"Group created! ID: `{result['group_id']}`")
                st.info("Share this Group ID + password with others to let them join.")

    with col2:
        st.markdown("#### 🚪 Join Group")
        with st.form("join_group_form"):
            join_id = st.text_input("Group ID", key="jg_id")
            join_pass = st.text_input("Group Password", type="password", key="jg_pass")
            submitted2 = st.form_submit_button("Join Group")
            if submitted2 and join_id and join_pass:
                result = join_group(join_id, join_pass, username)
                if result["success"]:
                    st.success(result["message"])
                else:
                    st.error(result["message"])

    st.markdown("---")

    # ── My Groups ──
    st.markdown("#### My Groups")
    my_groups = get_my_groups(username)

    if not my_groups:
        st.info("No groups yet. Create one or join with a Group ID above.")
    else:
        for g in my_groups:
            # Instagram-style gradient card
            st.markdown(f"""
            <div class="group-card">
                <div class="group-card-inner">
                    <h4 style="margin:0;">🚀 {g['name']}</h4>
                    <p style="color:#8892B0; font-size:12px; margin:4px 0;">ID: <code>{g['group_id']}</code></p>
                </div>
            </div>
            """, unsafe_allow_html=True)

            cols = st.columns(4)
            cols[0].metric("Members", g["member_count"])
            cols[1].metric("Capital Alloc", f"₹{g['capital_allocation']:,.0f}")
            cols[2].metric("Max Loss", f"₹{g['max_loss_limit']:,.0f}")
            cols[3].metric("Owner", g["owner"])

            # Member list
            with st.expander(f"Members ({g['member_count']})"):
                for m in g["members"]:
                    role = "👑 Owner" if m == g["owner"] else "👤 Member"
                    st.markdown(f"- {role} **{m}**")

            # Risk settings
            with st.expander("Risk Settings"):
                new_capital = st.number_input(
                    "Capital Allocation (₹)", value=g["capital_allocation"],
                    min_value=100, key=f"rs_cap_{g['group_id']}"
                )
                new_loss = st.number_input(
                    "Max Loss Limit (₹)", value=g["max_loss_limit"],
                    min_value=10, key=f"rs_loss_{g['group_id']}"
                )
                if st.button("Update Risk Settings", key=f"rs_btn_{g['group_id']}"):
                    update_risk_settings(g["group_id"], username, new_capital, new_loss)
                    st.success("Risk settings updated!")
                    st.rerun()

            # Signal stats
            stats = get_signal_stats(g["group_id"])
            st.markdown(f"📊 {stats['total_signals']} signals | 🟢 {stats['buy_signals']} BUY | 🔴 {stats['sell_signals']} SELL | ✓ {stats['yes_responses']} Yes | ✗ {stats['no_responses']} No")

            st.markdown("---")


# ═══════════════════════════════════════════════════════════════════════
# SIGNAL SHARE PAGE (Cyber terminal style)
# ═══════════════════════════════════════════════════════════════════════
elif "Signal Share" in page:
    st.markdown('<h1 class="electric-gradient">📡 Signal Share</h1>', unsafe_allow_html=True)
    st.markdown("Share AI signals to your groups. Members respond yes/no → demo trades.")
    st.markdown("---")

    username = ensure_username()
    my_groups = get_my_groups(username)

    if not my_groups:
        st.warning("Join a group first in the **Social Hub** to share signals.")
        st.stop()

    # ── Post Signal ──
    st.markdown("#### 📤 Post Signal")
    col1, col2, col3 = st.columns(3)
    with col1:
        sig_group = st.selectbox(
            "Group", [f"{g['name']}|{g['group_id']}" for g in my_groups],
            key="sig_group_sel"
        )
    with col2:
        sig_symbol = st.text_input("Symbol", value="RELIANCE", key="sig_symbol")
    with col3:
        sig_direction = st.selectbox("Direction", ["BUY 🟢", "SELL 🔴"], key="sig_dir")

    sig_analysis = st.text_area("Analysis (optional)", placeholder="RSI oversold + MACD bullish crossover...", key="sig_analysis")

    # Optional: pull live signal data from broker
    if st.checkbox("Auto-fill from live signal scan", key="sig_autofill"):
        if require_broker():
            broker = get_broker()
            try:
                df = broker.get_historical(sig_symbol.upper(), interval="day", days=120)
                if not df.empty and len(df) >= 60:
                    df = generate_signals(df, st.session_state["strategy_params"])
                    last = df.iloc[-1]
                    auto_analysis = f"Auto: RSI={last['rsi']:.1f}, MACD Hist={last['macd_hist']:.4f}, Signal={last['signal_label']}"
                    st.info(auto_analysis)
                    sig_analysis = auto_analysis
                    if last["signal_label"] == "BUY":
                        sig_direction = "BUY 🟢"
                    elif last["signal_label"] == "SELL":
                        sig_direction = "SELL 🔴"
            except Exception as e:
                st.error(f"Could not fetch live data: {e}")

    if st.button("📡 Post Signal to Group", type="primary"):
        grp_id = sig_group.split("|")[1]
        direction = "BUY" if "BUY" in sig_direction else "SELL"
        result = post_signal(
            grp_id, sig_symbol.upper(), direction, sig_analysis, username
        )
        if result["success"]:
            st.success(f"Signal posted to group!")
            # Telegram alert
            tg = dict(st.secrets.get("telegram", {})) if "telegram" in st.secrets else {}
            if tg.get("bot_token") and tg.get("chat_id"):
                msg = f"📡 Signal in {sig_group.split('|')[0]}\n{direction} {sig_symbol.upper()}\n{sig_analysis}"
                send_telegram_message(tg["bot_token"], tg["chat_id"], msg)
        else:
            st.error(result.get("message", "Failed to post"))

    st.markdown("---")

    # ── View Signals & Respond ──
    st.markdown("#### 📥 Group Signals")

    # Select group to view
    view_group = st.selectbox(
        "View signals for", [f"{g['name']}|{g['group_id']}" for g in my_groups],
        key="view_sig_group"
    )
    grp_id = view_group.split("|")[1]
    signals = get_group_signals(grp_id)

    if not signals:
        st.info("No signals posted in this group yet. Post one above!")
    else:
        for sig in reversed(signals):
            css_class = "signal-buy" if sig["direction"] == "BUY" else "signal-sell"
            dir_emoji = "🟢 BUY" if sig["direction"] == "BUY" else "🔴 SELL"
            time_str = sig["created_at"].strftime("%d %b, %H:%M")

            responses = sig.get("responses", {})
            yes_count = sum(1 for r in responses.values() if r == "yes")
            no_count = sum(1 for r in responses.values() if r == "no")

            st.markdown(f"""
            <div class="{css_class}">
                <strong>{sig['symbol']}</strong> — {dir_emoji} <span style="color:#8892B0; font-size:12px;">by {sig['posted_by']} · {time_str}</span><br>
                <span style="color:#8892B0; font-size:13px;">{sig['analysis']}</span><br>
                <span style="font-size:12px;">✓ {yes_count} Yes · ✗ {no_count} No</span>
            </div>
            """, unsafe_allow_html=True)

            # Response buttons
            user_response = responses.get(username)
            col_y, col_n = st.columns(2)
            with col_y:
                if st.button("✓ Yes (Demo Trade)", key=f"yes_{sig['id']}",
                              disabled=(user_response is not None)):
                    result = respond_to_signal(sig["id"], "yes", username, st.session_state["paper_trader"])
                    if result["success"]:
                        dt = result.get("demo_trade", {})
                        if dt and dt.get("status") == "executed":
                            st.success(f"Demo trade created! Qty: {dt.get('qty', 0)} @ ₹{dt.get('price', 0):.2f}")
                        else:
                            st.warning(f"Response recorded. Trade: {dt}")
                        st.rerun()
                    else:
                        st.error(result.get("message", "Failed"))
            with col_n:
                if st.button("✕ No", key=f"no_{sig['id']}",
                              disabled=(user_response is not None)):
                    result = respond_to_signal(sig["id"], "no", username, st.session_state["paper_trader"])
                    if result["success"]:
                        st.info("Signal rejected.")
                        st.rerun()
                    else:
                        st.error(result.get("message", "Failed"))

            if user_response:
                st.markdown(f"*You responded: **{user_response.upper()}***")
            st.markdown("---")


# ═══════════════════════════════════════════════════════════════════════
# FEED PAGE (Social activity)
# ═══════════════════════════════════════════════════════════════════════
elif "Feed" in page:
    st.markdown('<h1 class="electric-gradient">📰 Social Feed</h1>', unsafe_allow_html=True)
    st.markdown("Recent activity across your trading groups.")
    st.markdown("---")

    feed = get_social_feed(limit=30)

    if not feed:
        st.info("No activity yet. Create groups, post signals, and invite others to see the feed come alive!")
    else:
        for item in feed:
            time_str = item["time"].strftime("%d %b %H:%M")
            st.markdown(f"""
            <div class="feed-item">
                {item['text']}<br>
                <span style="color:#495670; font-size:11px;">{time_str}</span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # Quick stats
    st.markdown("#### Quick Stats")
    all_stats = get_signal_stats()
    cols = st.columns(4)
    cols[0].metric("Total Signals", all_stats["total_signals"])
    cols[1].metric("Buy Signals", all_stats["buy_signals"])
    cols[2].metric("Sell Signals", all_stats["sell_signals"])
    cols[3].metric("Total Groups", len(st.session_state.get("social_groups", {})))

    cols2 = st.columns(2)
    cols2[0].metric("Yes Responses", all_stats["yes_responses"])
    cols2[1].metric("No Responses", all_stats["no_responses"])


# ═══════════════════════════════════════════════════════════════════════
# SETTINGS PAGE
# ═══════════════════════════════════════════════════════════════════════
elif "Settings" in page:
    st.title("⚙️ Settings")

    st.markdown("### Risk Management")
    risk = st.session_state["risk"]
    col1, col2 = st.columns(2)
    with col1:
        risk["max_capital_per_trade_pct"] = st.slider(
            "Max Capital per Trade (%)", 1.0, 100.0, risk["max_capital_per_trade_pct"]
        )
        risk["stop_loss_pct"] = st.slider(
            "Stop Loss (%)", 0.5, 20.0, risk["stop_loss_pct"]
        )
        risk["max_open_positions"] = st.slider(
            "Max Open Positions", 1, 20, risk["max_open_positions"]
        )
    with col2:
        risk["take_profit_pct"] = st.slider(
            "Take Profit (%)", 0.5, 50.0, risk["take_profit_pct"]
        )
        risk["daily_loss_limit_pct"] = st.slider(
            "Daily Loss Limit (%)", 1.0, 30.0, risk["daily_loss_limit_pct"]
        )

    st.session_state["risk"] = risk

    st.markdown("---")
    st.markdown("### Strategy Parameters")
    params = st.session_state["strategy_params"]
    col3, col4 = st.columns(2)
    with col3:
        params["rsi_oversold"] = st.slider("RSI Oversold", 10, 40, params["rsi_oversold"])
        params["rsi_overbought"] = st.slider("RSI Overbought", 60, 90, params["rsi_overbought"])
    with col4:
        params["sma_fast"] = st.slider("SMA Fast Period", 5, 50, params["sma_fast"])
        params["sma_slow"] = st.slider("SMA Slow Period", 20, 200, params["sma_slow"])

    st.session_state["strategy_params"] = params

    st.markdown("---")
    st.markdown("### Telegram Alerts")
    tg = dict(st.secrets.get("telegram", {})) if "telegram" in st.secrets else {}
    st.text_input("Bot Token", value=tg.get("bot_token", ""), key="tg_token", type="password")
    st.text_input("Chat ID", value=tg.get("chat_id", ""), key="tg_chat")
    if st.button("Send Test Alert"):
        token = st.session_state.get("tg_token", "")
        chat = st.session_state.get("tg_chat", "")
        ok = send_telegram_message(token, chat, "✅ AlgoDesk test alert — your bot is configured!")
        if ok:
            st.success("Test alert sent!")
        else:
            st.error("Failed to send. Check your bot token and chat ID.")

    st.markdown("---")
    st.markdown("### Social Username")
    new_name = st.text_input("Your display name", value=st.session_state.get("social_username", ""))
    if st.button("Update Name"):
        st.session_state["social_username"] = new_name
        st.success("Name updated!")
        st.rerun()

    st.markdown("---")
    st.markdown("### About")
    st.info(
        f"**{APP_TITLE}**\n\n"
        "A technical/analytical tool — not financial advice. "
        "Test thoroughly in Paper Trading and Backtest before using Live Orders.\n\n"
        "Social features are demo/sandbox mode — no real money, no real broker execution."
    )
