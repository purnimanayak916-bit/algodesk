"""
app.py
AlgoDesk — Multi-Broker Stock Trading Dashboard
Main Streamlit application with broker selector and all pages.
Supports: Zerodha, Upstox, Angel One, Groww, TradingView (charts only).
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta

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
from tradingview import (
    advanced_chart, symbol_info, technical_analysis,
    market_overview, ticker_tape, mini_chart, render as render_tv
)


# ── Page config ─────────────────────────────────────────────────────
st.set_page_config(page_title=APP_TITLE, layout="wide")

# ── Session state init ───────────────────────────────────────────────
def init_state():
    defaults = {
        "broker": None,
        "broker_name": None,
        "watchlist": DEFAULT_WATCHLIST.copy(),
        "risk": DEFAULT_RISK.copy(),
        "strategy_params": STRATEGY_PARAMS.copy(),
        "paper_trader": PaperTrader(),
        "tv_enabled": True,       # TradingView widgets on by default
        "auto_loaded": False,      # Dashboard auto-load flag
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

init_state()


# ── Sidebar ─────────────────────────────────────────────────────────
st.sidebar.title(APP_TITLE)
st.sidebar.markdown("---")

broker_choice = st.sidebar.selectbox(
    "Select Broker",
    options=SUPPORTED_BROKERS,
    index=0,
    help="Switch brokers anytime — all pages work the same way."
)

st.sidebar.markdown("---")

# TradingView toggle
st.session_state["tv_enabled"] = st.sidebar.checkbox(
    "TradingView Charts", value=st.session_state.get("tv_enabled", True),
    help="Enable TradingView chart widgets on Dashboard and Charts pages"
)

st.sidebar.markdown("---")

# Navigation
pages = ["Dashboard", "Charts", "Backtest",
         "Paper Trading", "Live Orders", "Settings", "Connect"]
page = st.sidebar.radio("Navigate", pages)


# ── Helpers ──────────────────────────────────────────────────────────
def get_broker():
    return st.session_state.get("broker")


def require_broker():
    b = get_broker()
    if b is None or not b.is_connected:
        st.warning("Not connected. Go to the Connect page to log in.")
        return False
    return True


def is_tradingview():
    """Check if current broker is TradingView (display-only)."""
    b = get_broker()
    return b is not None and b.name == "TradingView"


def try_create_broker():
    if st.session_state.get("broker_name") != broker_choice:
        try:
            secrets = st.secrets
            b = create_broker(broker_choice, dict(secrets))
            st.session_state["broker"] = b
            st.session_state["broker_name"] = broker_choice
            st.session_state["auto_loaded"] = False
            return b
        except Exception:
            st.session_state["broker"] = None
            return None
    return st.session_state.get("broker")


broker = try_create_broker()


def interval_to_tv(interval_label: str) -> str:
    """Map our interval labels to TradingView interval codes."""
    return {
        "5 minute": "5",
        "15 minute": "15",
        "1 hour": "60",
        "1 day": "D",
    }.get(interval_label, "D")


# ═══════════════════════════════════════════════════════════════════════
# CONNECT PAGE
# ═══════════════════════════════════════════════════════════════════════
if "Connect" in page:
    st.title("Connect")

    # ── Broker connection section ──
    st.markdown("### Broker Connection")
    st.markdown(f"**Selected broker:** {broker_choice}")

    # TradingView — no API key needed
    if broker_choice == "TradingView":
        st.success("TradingView is ready — no API key needed!")
        st.markdown(
            "TradingView provides free chart widgets and market data. "
            "No login or API key required. "
            "Go to the **Dashboard** to see live charts and market overview."
        )
        st.markdown(
            "For trading (live orders), connect a real broker: "
            "**Zerodha**, **Upstox**, **Angel One**, or **Groww**."
        )
        st.stop()

    # Real brokers
    if broker is None:
        st.error(
            f"No secrets found for **{broker_choice}**. "
            f"Add your API keys to `.streamlit/secrets.toml` and restart."
        )
        with st.expander("Required fields"):
            st.code(
                f"[{broker_choice.lower().replace(' ', '')}]\n"
                f"api_key = \"your_api_key\"\n"
                f"# See secrets.toml.example for full details",
                language="toml"
            )
        st.stop()

    if broker.is_connected:
        st.success(f"Connected to {broker.name}!")
        st.markdown("Head to the **Dashboard** to see live data and signals.")
        if st.button("Disconnect"):
            st.session_state["broker"] = None
            st.session_state["broker_name"] = None
            st.session_state["auto_loaded"] = False
            st.rerun()
        st.stop()

    # ── Zerodha ──
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
                    st.success("Logged in to Zerodha!")
                    st.rerun()
                else:
                    st.error("Login failed. Check your request_token and API keys.")

    # ── Upstox ──
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
                    st.success("Logged in to Upstox!")
                    st.rerun()
                else:
                    st.error("Login failed. Check your auth code and API keys.")

    # ── Angel One ──
    elif broker_choice == "Angel One":
        st.markdown("### Angel One Login")
        st.markdown("Direct login — enter your TOTP below. Make sure TOTP-based API login is enabled in the Angel One app.")
        totp_input = st.text_input("Enter 6-digit TOTP:", max_chars=6)
        if st.button("Complete Login") and totp_input:
            with st.spinner("Logging in..."):
                if broker.complete_login(totp=totp_input):
                    st.success("Logged in to Angel One!")
                    st.rerun()
                else:
                    st.error("Login failed. Check your TOTP and credentials.")

    # ── Groww ──
    elif broker_choice == "Groww":
        st.markdown("### Groww Login")
        st.markdown("Direct login — enter your TOTP below. Generate your API key from groww.in/trade-api/api-keys")
        totp_input = st.text_input("Enter 6-digit TOTP:", max_chars=6, key="groww_totp")
        if st.button("Complete Login", key="groww_login") and totp_input:
            with st.spinner("Logging in..."):
                if broker.complete_login(totp=totp_input):
                    st.success("Logged in to Groww!")
                    st.rerun()
                else:
                    st.error("Login failed. Check your TOTP and API key.")

    # ── API key info section ──
    st.markdown("---")
    st.markdown("### How to get API keys")

    with st.expander("Zerodha"):
        st.markdown(
            "1. Go to developers.kite.trade\n"
            "2. Create an app (Rs 2,000/month subscription)\n"
            "3. Note API key and secret\n"
            "4. Set redirect URL to your deployed app's URL"
        )

    with st.expander("Upstox"):
        st.markdown(
            "1. Go to upstox.com/developer\n"
            "2. Create an app (free)\n"
            "3. Note API key and secret\n"
            "4. Set redirect URI to match UPSTOX_REDIRECT_URI"
        )

    with st.expander("Angel One"):
        st.markdown(
            "1. Go to smartapi.angelbroking.com\n"
            "2. Create an app (free)\n"
            "3. Note API key\n"
            "4. Enable TOTP-based login in Angel One app under API settings"
        )

    with st.expander("Groww"):
        st.markdown(
            "1. Go to groww.in/trade-api/api-keys\n"
            "2. Log in to your Groww account\n"
            "3. Click 'Generate API Key'\n"
            "4. Copy API Key and Secret\n"
            "5. Set up TOTP in Google Authenticator"
        )

    with st.expander("TradingView (free, no API key)"):
        st.markdown(
            "TradingView widgets are free to embed. No API key, no login.\n"
            "Provides live charts, technical analysis, and market overview.\n"
            "Trading is NOT supported — connect a real broker for that."
        )


# ═══════════════════════════════════════════════════════════════════════
# DASHBOARD PAGE
# ═══════════════════════════════════════════════════════════════════════
elif "Dashboard" in page:
    st.title("Dashboard")

    watchlist = st.session_state["watchlist"]

    # ── TradingView ticker tape (always shows if enabled) ──
    if st.session_state.get("tv_enabled"):
        tv_symbols = [(s, "NSE") for s in watchlist]
        render_tv(ticker_tape(tv_symbols), height=50)

    st.markdown("---")

    # ── TradingView mode ──
    if is_tradingview():
        st.markdown("### Market Overview")
        render_tv(market_overview([(s, "NSE") for s in watchlist], height=400), height=420)

        st.markdown("---")
        st.markdown("### Technical Analysis")

        tv_sym = st.selectbox("Select Symbol", watchlist, key="tv_dash_sym")
        col1, col2 = st.columns([2, 1])
        with col1:
            render_tv(advanced_chart(tv_sym, "NSE", "D", height=400), height=420)
        with col2:
            render_tv(technical_analysis(tv_sym, "NSE", height=400), height=420)

        st.markdown("---")
        st.markdown("### Mini Charts — Watchlist")
        cols = st.columns(3)
        for i, sym in enumerate(watchlist[:6]):
            with cols[i % 3]:
                st.markdown(f"**{sym}**")
                render_tv(mini_chart(sym, "NSE", height=180), height=200)

        st.markdown("---")
        st.info(
            "TradingView mode shows live charts and market data. "
            "To place trades, connect a broker (Zerodha, Upstox, Angel One, Groww) "
            "from the Connect page."
        )
        st.stop()

    # ── Broker mode (real brokers) ──
    if not require_broker():
        # Still show TradingView widgets if enabled
        if st.session_state.get("tv_enabled"):
            st.markdown("---")
            st.markdown("### Market Overview (TradingView)")
            render_tv(market_overview([(s, "NSE") for s in watchlist], height=400), height=420)
        st.stop()

    broker = get_broker()

    # Watchlist editor
    with st.expander("Watchlist (click to edit)"):
        new_list = st.text_area(
            "Symbols (comma-separated)",
            value=", ".join(watchlist),
        )
        if st.button("Update Watchlist"):
            symbols = [s.strip().upper() for s in new_list.split(",") if s.strip()]
            st.session_state["watchlist"] = symbols
            st.session_state["auto_loaded"] = False
            st.rerun()

    interval_label = st.selectbox(
        "Interval", list(INTERVAL_CHOICES.keys()), index=1
    )
    interval = INTERVAL_CHOICES[interval_label]

    st.markdown("---")

    # ── Auto-load: fetch quotes on first visit ──
    if not st.session_state.get("auto_loaded", False):
        with st.spinner("Loading market data..."):
            quote_data = []
            for symbol in watchlist:
                try:
                    q = broker.get_quote(symbol)
                    quote_data.append({
                        "Symbol": symbol,
                        "LTP": q["ltp"],
                        "Open": q["open"],
                        "High": q["high"],
                        "Low": q["low"],
                        "Close": q["close"],
                    })
                except Exception:
                    quote_data.append({
                        "Symbol": symbol, "LTP": "—",
                        "Open": "—", "High": "—", "Low": "—", "Close": "—",
                    })
            if quote_data:
                st.session_state["auto_quotes"] = pd.DataFrame(quote_data)
            st.session_state["auto_loaded"] = True

    # Show auto-loaded quotes
    if st.session_state.get("auto_quotes") is not None and not st.session_state["auto_quotes"].empty:
        st.markdown("### Live Quotes (auto-loaded)")
        st.dataframe(st.session_state["auto_quotes"], use_container_width=True, hide_index=True)

    # TradingView mini charts alongside broker data
    if st.session_state.get("tv_enabled"):
        st.markdown("---")
        st.markdown("### TradingView Charts")
        tv_sym = st.selectbox("Select Symbol for Chart", watchlist, key="tv_dash_chart")
        render_tv(advanced_chart(tv_sym, "NSE", interval_to_tv(interval_label), height=450), height=470)

    st.markdown("---")

    # ── Signal scan ──
    st.subheader("Live Signals")

    if st.button("Scan Watchlist"):
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

            tg = dict(st.secrets.get("telegram", {})) if "telegram" in st.secrets else {}
            bot_token = tg.get("bot_token", "")
            chat_id = tg.get("chat_id", "")
            buy_signals = [d for d in signal_data if d.get("Signal") == "BUY"]
            sell_signals = [d for d in signal_data if d.get("Signal") == "SELL"]
            if (buy_signals or sell_signals) and bot_token and chat_id:
                alerts = []
                if buy_signals:
                    alerts.append("BUY: " + ", ".join(d["Symbol"] for d in buy_signals))
                if sell_signals:
                    alerts.append("SELL: " + ", ".join(d["Symbol"] for d in sell_signals))
                send_telegram_message(bot_token, chat_id, "\n".join(alerts))
                st.toast("Telegram alerts sent!")

    # Quick quote
    st.markdown("---")
    st.subheader("Quick Quote")
    symbol = st.selectbox("Symbol", watchlist, key="dq_sym")
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

    # TradingView technical analysis widget
    if st.session_state.get("tv_enabled"):
        st.markdown("---")
        st.markdown("### Technical Analysis (TradingView)")
        render_tv(technical_analysis(symbol, "NSE", height=400), height=420)


# ═══════════════════════════════════════════════════════════════════════
# CHARTS PAGE
# ═══════════════════════════════════════════════════════════════════════
elif "Charts" in page:
    st.title("Charts")

    watchlist = st.session_state["watchlist"]
    col1, col2, col3 = st.columns(3)
    with col1:
        chart_symbol = st.text_input("Symbol", value=watchlist[0])
    with col2:
        chart_interval = st.selectbox("Interval", list(INTERVAL_CHOICES.keys()), index=3)
    with col3:
        days = st.number_input("Lookback (days)", value=180, min_value=30, max_value=730)

    # ── TradingView chart (always available if enabled) ──
    if st.session_state.get("tv_enabled"):
        st.markdown("### TradingView Live Chart")
        render_tv(advanced_chart(
            chart_symbol.upper(), "NSE",
            interval_to_tv(chart_interval), height=500
        ), height=520)

        st.markdown("---")
        col_t1, col_t2 = st.columns([2, 1])
        with col_t1:
            st.markdown("### Technical Analysis")
            render_tv(technical_analysis(chart_symbol.upper(), "NSE", height=400), height=420)
        with col_t2:
            st.markdown("### Symbol Info")
            render_tv(symbol_info(chart_symbol.upper(), "NSE"), height=420)

        st.markdown("---")

    # ── Broker-based Plotly chart (requires broker connection) ──
    if is_tradingview():
        st.info("Broker-based charts require a real broker connection. TradingView charts are shown above.")
        st.stop()

    if not require_broker():
        st.stop()

    broker = get_broker()

    st.markdown("### Broker Chart (Plotly)")
    if st.button("Load Plotly Chart"):
        with st.spinner("Fetching data..."):
            try:
                df = broker.get_historical(chart_symbol.upper(),
                                            interval=INTERVAL_CHOICES[chart_interval],
                                            days=days)
                if df.empty:
                    st.warning("No data returned.")
                    st.stop()
            except Exception as e:
                st.error(f"Error fetching data: {e}")
                st.stop()

            df = generate_signals(df, st.session_state["strategy_params"])
            df = add_all_indicators(df, st.session_state["strategy_params"])

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
                title_text=f"{chart_symbol.upper()} — {chart_interval}"
            )
            st.plotly_chart(fig, use_container_width=True)

            buys = df[df["signal"] == 1]
            sells = df[df["signal"] == -1]
            if not buys.empty:
                st.markdown(f"**{len(buys)} BUY signals**")
                st.dataframe(buys[["close", "rsi", "macd_hist", "sma_fast", "sma_slow"]].tail(10))
            if not sells.empty:
                st.markdown(f"**{len(sells)} SELL signals**")
                st.dataframe(sells[["close", "rsi", "macd_hist", "sma_fast", "sma_slow"]].tail(10))


# ═══════════════════════════════════════════════════════════════════════
# BACKTEST PAGE
# ═══════════════════════════════════════════════════════════════════════
elif "Backtest" in page:
    st.title("Backtest")

    if is_tradingview():
        st.info("Backtesting requires a broker connection with historical data. Connect Zerodha, Upstox, Angel One, or Groww.")
        st.stop()

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
    st.title("Paper Trading")

    if is_tradingview():
        st.info("Paper trading requires a broker connection. Connect Zerodha, Upstox, Angel One, or Groww.")
        st.stop()

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
            st.success(f"{pt_action} {pt_qty} {pt_symbol} @ ₹{price:.2f}")
        else:
            st.error(f"{msg}")

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
    st.title("Live Orders")

    if is_tradingview():
        st.warning("Live orders require a real broker connection. TradingView is charting only.")
        st.stop()

    if not require_broker():
        st.stop()

    broker = get_broker()

    st.warning(
        "**This page places REAL orders with real money.** "
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
            st.error("You must type CONFIRM to place a live order.")
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
                    st.success(f"Order placed! ID: {result['order_id']}")
                    tg = dict(st.secrets.get("telegram", {})) if "telegram" in st.secrets else {}
                    if tg.get("bot_token") and tg.get("chat_id"):
                        msg = f"LIVE ORDER\n{lo_side} {lo_qty} {lo_symbol}\nType: {lo_type}\nID: {result['order_id']}"
                        send_telegram_message(tg["bot_token"], tg["chat_id"], msg)
                else:
                    st.error(f"Order failed: {result['message']}")

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
# SETTINGS PAGE
# ═══════════════════════════════════════════════════════════════════════
elif "Settings" in page:
    st.title("Settings")

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
    st.markdown("### TradingView Charts")
    st.session_state["tv_enabled"] = st.checkbox(
        "Enable TradingView widgets on Dashboard and Charts",
        value=st.session_state.get("tv_enabled", True)
    )
    if st.session_state["tv_enabled"]:
        st.success("TradingView charts are enabled. You'll see live TradingView widgets on the Dashboard and Charts pages.")
    else:
        st.info("TradingView charts are disabled. Enable to see live charts alongside broker data.")

    st.markdown("---")
    st.markdown("### Telegram Alerts")
    tg = dict(st.secrets.get("telegram", {})) if "telegram" in st.secrets else {}
    st.text_input("Bot Token", value=tg.get("bot_token", ""), key="tg_token", type="password")
    st.text_input("Chat ID", value=tg.get("chat_id", ""), key="tg_chat")
    if st.button("Send Test Alert"):
        token = st.session_state.get("tg_token", "")
        chat = st.session_state.get("tg_chat", "")
        ok = send_telegram_message(token, chat, "AlgoDesk test alert — your bot is configured!")
        if ok:
            st.success("Test alert sent!")
        else:
            st.error("Failed to send. Check your bot token and chat ID.")

    st.markdown("---")
    st.markdown("### About")
    st.info(
        f"**{APP_TITLE}**\n\n"
        "Supported brokers: Zerodha, Upstox, Angel One, Groww, TradingView (charts only).\n\n"
        "A technical/analytical tool — not financial advice. "
        "Test thoroughly in Paper Trading and Backtest before using Live Orders."
    )
