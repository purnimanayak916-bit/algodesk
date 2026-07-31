"""
app.py
AlgoDesk — Multi-Broker Stock Trading Dashboard
Enter API keys directly in the UI — no need to edit secrets.toml.
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

# ── Custom CSS ───────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Dark theme background */
    .stApp {
        background: linear-gradient(135deg, #0a0e1a 0%, #06080f 100%);
    }
    .stSidebar {
        background: linear-gradient(180deg, #06080f 0%, #0a0e1a 100%);
        border-right: 1px solid rgba(0, 212, 255, 0.1);
    }
    /* Metric cards */
    div[data-testid="stMetric"] {
        background: rgba(15, 20, 35, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 16px;
        backdrop-filter: blur(10px);
    }
    /* Buttons */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
    }
    /* Headers */
    h1, h2, h3 {
        letter-spacing: -0.5px;
    }
    /* Connection status badge */
    .status-connected {
        background: rgba(0, 200, 83, 0.15);
        border: 1px solid rgba(0, 200, 83, 0.3);
        color: #00c853;
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 600;
        display: inline-block;
    }
    .status-disconnected {
        background: rgba(255, 59, 92, 0.1);
        border: 1px solid rgba(255, 59, 92, 0.2);
        color: #ff3b5c;
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 600;
        display: inline-block;
    }
    /* Broker cards */
    .broker-card {
        background: rgba(15, 20, 35, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 14px;
        padding: 24px;
        margin-bottom: 16px;
    }
    /* Info banner */
    .info-banner {
        background: linear-gradient(135deg, rgba(0, 212, 255, 0.08), rgba(176, 38, 255, 0.05));
        border: 1px solid rgba(0, 212, 255, 0.15);
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)


# ── Session state init ───────────────────────────────────────────────
def init_state():
    defaults = {
        "broker": None,
        "broker_name": None,
        "watchlist": DEFAULT_WATCHLIST.copy(),
        "risk": DEFAULT_RISK.copy(),
        "strategy_params": STRATEGY_PARAMS.copy(),
        "paper_trader": PaperTrader(),
        "tv_enabled": True,
        "auto_loaded": False,
        # UI-entered API keys (persist for browser session)
        "ui_keys": {},
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
)

st.sidebar.markdown("---")
st.session_state["tv_enabled"] = st.sidebar.checkbox(
    "TradingView Charts",
    value=st.session_state.get("tv_enabled", True),
)
st.sidebar.markdown("---")

pages = ["Dashboard", "Charts", "Backtest",
         "Paper Trading", "Live Orders", "Settings", "Connect"]
page = st.sidebar.radio("Navigate", pages)

# Connection status indicator
b = st.session_state.get("broker")
if b is not None and b.is_connected:
    st.sidebar.markdown(
        f'<span class="status-connected">Connected: {b.name}</span>',
        unsafe_allow_html=True
    )
else:
    st.sidebar.markdown(
        '<span class="status-disconnected">Not Connected</span>',
        unsafe_allow_html=True
    )


# ── Helpers ──────────────────────────────────────────────────────────
def get_broker():
    return st.session_state.get("broker")


def require_broker():
    b = get_broker()
    if b is None or not b.is_connected:
        st.warning("Not connected. Go to the Connect page to enter your API keys.")
        return False
    return True


def is_tradingview():
    b = get_broker()
    return b is not None and b.name == "TradingView"


def build_secrets_dict(broker_name: str) -> dict:
    """Build a secrets-like dict from UI-entered keys, falling back to st.secrets."""
    ui_keys = st.session_state.get("ui_keys", {})
    result = {}

    # Try to get from st.secrets first as fallback
    try:
        raw_secrets = dict(st.secrets)
    except Exception:
        raw_secrets = {}

    name_key = broker_name.lower().replace(" ", "")

    # Merge: st.secrets as base, UI keys override
    if name_key in raw_secrets:
        result[name_key] = dict(raw_secrets[name_key])
    elif name_key == "angelone" and "angelone" in raw_secrets:
        result[name_key] = dict(raw_secrets["angelone"])
    else:
        result[name_key] = {}

    # Override with UI-entered keys
    if name_key in ui_keys:
        for k, v in ui_keys[name_key].items():
            if v:  # Only override if non-empty
                result[name_key][k] = v

    return result


def try_create_broker():
    """Create broker from UI keys or secrets."""
    if st.session_state.get("broker_name") != broker_choice:
        try:
            secrets = build_secrets_dict(broker_choice)
            if not secrets.get(broker_choice.lower().replace(" ", "")):
                # No keys at all
                st.session_state["broker"] = None
                return None
            b = create_broker(broker_choice, secrets)
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
    return {
        "5 minute": "5", "15 minute": "15",
        "1 hour": "60", "1 day": "D",
    }.get(interval_label, "D")


# ── Broker field definitions ────────────────────────────────────────
BROKER_FIELDS = {
    "Zerodha": [
        ("api_key", "API Key", "text"),
        ("api_secret", "API Secret", "password"),
        ("redirect_uri", "Redirect URI", "text"),
    ],
    "Upstox": [
        ("api_key", "API Key", "text"),
        ("api_secret", "API Secret", "password"),
        ("redirect_uri", "Redirect URI", "text"),
    ],
    "Angel One": [
        ("api_key", "API Key", "text"),
        ("client_code", "Client Code", "text"),
        ("password", "Password", "password"),
        ("totp_secret", "TOTP Secret", "password"),
    ],
    "Groww": [
        ("api_key", "API Key", "text"),
    ],
}


# ═══════════════════════════════════════════════════════════════════════
# CONNECT PAGE
# ═══════════════════════════════════════════════════════════════════════
if "Connect" in page:
    st.title("Connect")

    # ── TradingView (no keys needed) ──
    if broker_choice == "TradingView":
        st.markdown('<div class="info-banner">', unsafe_allow_html=True)
        st.markdown("### TradingView — Free Charts")
        st.markdown(
            "No API key needed. TradingView provides free live charts, "
            "technical analysis, and market data widgets.\n\n"
            "Go to the **Dashboard** to see live charts immediately.\n\n"
            "For trading, connect a broker: **Zerodha**, **Upstox**, **Angel One**, or **Groww**."
        )
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### Other Brokers — Enter API Keys Below")
        st.markdown("Select a broker from the sidebar dropdown to enter your API keys.")

        # Show all broker key info in cards
        cols = st.columns(2)
        for i, (bname, fields) in enumerate(BROKER_FIELDS.items()):
            with cols[i % 2]:
                with st.expander(f"{bname} — Required Keys"):
                    for field_key, field_label, _ in fields:
                        st.markdown(f"**{field_label}** — `{field_key}`")
                    if bname == "Zerodha":
                        st.markdown("Get keys: developers.kite.trade")
                    elif bname == "Upstox":
                        st.markdown("Get keys: upstox.com/developer")
                    elif bname == "Angel One":
                        st.markdown("Get keys: smartapi.angelbroking.com")
                    elif bname == "Groww":
                        st.markdown("Get keys: groww.in/trade-api/api-keys")
        st.stop()

    # ── Real broker connect ──
    name_key = broker_choice.lower().replace(" ", "")
    st.markdown(f"### {broker_choice} — Enter Your API Keys")
    st.markdown(
        "Enter your API keys below. Keys are stored in your browser session only — "
        "they are not saved anywhere permanent. You can also set them in "
        "`secrets.toml` as a fallback."
    )

    # ── API key input form ──
    fields = BROKER_FIELDS.get(broker_choice, [])
    ui_keys = st.session_state.get("ui_keys", {})
    if name_key not in ui_keys:
        ui_keys[name_key] = {}

    # Pre-fill from secrets if available
    try:
        secret_vals = dict(st.secrets).get(name_key, {})
    except Exception:
        secret_vals = {}

    with st.form("api_key_form"):
        entered = {}
        for field_key, field_label, field_type in fields:
            # Default value: UI-entered first, then secrets
            default_val = ui_keys[name_key].get(field_key, "") or str(secret_vals.get(field_key, ""))
            if field_type == "password":
                entered[field_key] = st.text_input(
                    field_label, value=default_val, type="password",
                    key=f"key_{field_key}"
                )
            else:
                entered[field_key] = st.text_input(
                    field_label, value=default_val,
                    key=f"key_{field_key}"
                )

        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            submitted = st.form_submit_button("Save & Connect", type="primary")
        with col_btn2:
            cleared = st.form_submit_button("Clear Keys")

    if cleared:
        ui_keys[name_key] = {}
        st.session_state["ui_keys"] = ui_keys
        st.session_state["broker"] = None
        st.session_state["broker_name"] = None
        st.rerun()

    if submitted:
        # Save entered keys to session state
        saved = {}
        for field_key, _, _ in fields:
            val = entered.get(field_key, "")
            if val:
                saved[field_key] = val
        ui_keys[name_key] = saved
        st.session_state["ui_keys"] = ui_keys

        # Try to create broker
        try:
            secrets = build_secrets_dict(broker_choice)
            if not secrets.get(name_key):
                st.error(f"Please enter your {broker_choice} API keys above.")
            else:
                b = create_broker(broker_choice, secrets)
                st.session_state["broker"] = b
                st.session_state["broker_name"] = broker_choice
                st.session_state["auto_loaded"] = False
                st.success(f"API keys saved. {broker_choice} broker initialized.")
                st.rerun()
        except Exception as e:
            st.error(f"Failed to initialize: {e}")

    st.markdown("---")

    # ── Broker login flow (after keys are saved) ──
    if broker is not None and not broker.is_connected:
        st.markdown(f"### {broker_choice} Login")

        if broker_choice == "Zerodha":
            st.markdown("1. Click the login URL below.\n2. Authorize on Kite.\n3. Copy the `request_token` from the redirect URL.")
            if st.button("Get Login URL"):
                url = broker.get_login_url()
                st.code(url)
                st.markdown(f"[Open Login URL]({url})")
            request_token = st.text_input("Paste request_token here:", key="zd_token")
            if st.button("Complete Login", key="zd_login") and request_token:
                with st.spinner("Logging in..."):
                    if broker.complete_login(request_token=request_token):
                        st.success("Logged in to Zerodha!")
                        st.rerun()
                    else:
                        st.error("Login failed. Check your request_token and API keys.")

        elif broker_choice == "Upstox":
            st.markdown("1. Click the login URL below.\n2. Authorize on Upstox.\n3. Copy the `auth_code` from the redirect URL.")
            if st.button("Get Login URL"):
                url = broker.get_login_url()
                st.code(url)
                st.markdown(f"[Open Login URL]({url})")
            auth_code = st.text_input("Paste auth code here:", key="up_token")
            if st.button("Complete Login", key="up_login") and auth_code:
                with st.spinner("Logging in..."):
                    if broker.complete_login(auth_code=auth_code):
                        st.success("Logged in to Upstox!")
                        st.rerun()
                    else:
                        st.error("Login failed. Check your auth code and API keys.")

        elif broker_choice == "Angel One":
            st.markdown("Enter your TOTP below. Make sure TOTP-based API login is enabled in the Angel One app.")
            totp_input = st.text_input("Enter 6-digit TOTP:", max_chars=6, key="ao_totp")
            if st.button("Complete Login", key="ao_login") and totp_input:
                with st.spinner("Logging in..."):
                    if broker.complete_login(totp=totp_input):
                        st.success("Logged in to Angel One!")
                        st.rerun()
                    else:
                        st.error("Login failed. Check your TOTP and credentials.")

        elif broker_choice == "Groww":
            st.markdown("Enter your TOTP below. Generate your API key from groww.in/trade-api/api-keys")
            totp_input = st.text_input("Enter 6-digit TOTP:", max_chars=6, key="gw_totp")
            if st.button("Complete Login", key="gw_login") and totp_input:
                with st.spinner("Logging in..."):
                    if broker.complete_login(totp=totp_input):
                        st.success("Logged in to Groww!")
                        st.rerun()
                    else:
                        st.error("Login failed. Check your TOTP and API key.")

    elif broker is not None and broker.is_connected:
        st.markdown("---")
        st.success(f"Connected to {broker.name}! Go to Dashboard to see live data.")

        # Show which keys are active (masked)
        with st.expander("Active API Keys (masked)"):
            active_keys = ui_keys.get(name_key, {})
            for k, v in active_keys.items():
                masked = v[:4] + "****" + v[-4:] if len(v) > 8 else "****"
                st.text(f"{k}: {masked}")

        if st.button("Disconnect"):
            st.session_state["broker"] = None
            st.session_state["broker_name"] = None
            st.session_state["auto_loaded"] = False
            st.rerun()

    # ── How to get API keys ──
    st.markdown("---")
    st.markdown("### How to Get API Keys")

    help_data = [
        ("Zerodha", "developers.kite.trade", "Create app (Rs 2,000/month). Note API Key + Secret. Set redirect URL."),
        ("Upstox", "upstox.com/developer", "Create app (free). Note API Key + Secret. Set redirect URI."),
        ("Angel One", "smartapi.angelbroking.com", "Create app (free). Note API Key, Client Code, Password. Enable TOTP."),
        ("Groww", "groww.in/trade-api/api-keys", "Generate API Key (free). Set up TOTP in Google Authenticator."),
    ]

    cols = st.columns(2)
    for i, (bname, url, desc) in enumerate(help_data):
        with cols[i % 2]:
            with st.expander(bname):
                st.markdown(f"**URL:** {url}\n\n**Steps:** {desc}")


# ═══════════════════════════════════════════════════════════════════════
# DASHBOARD PAGE
# ═══════════════════════════════════════════════════════════════════════
elif "Dashboard" in page:
    st.title("Dashboard")

    watchlist = st.session_state["watchlist"]

    # TradingView ticker tape
    if st.session_state.get("tv_enabled"):
        tv_symbols = [(s, "NSE") for s in watchlist]
        render_tv(ticker_tape(tv_symbols), height=50)

    st.markdown("---")

    # ── TradingView mode ──
    if is_tradingview():
        col1, col2 = st.columns([3, 2])
        with col1:
            st.markdown("### Market Chart")
            render_tv(advanced_chart(watchlist[0], "NSE", "D", height=450), height=470)
        with col2:
            st.markdown("### Technical Analysis")
            render_tv(technical_analysis(watchlist[0], "NSE", height=450), height=470)

        st.markdown("---")
        st.markdown("### Market Overview")
        render_tv(market_overview([(s, "NSE") for s in watchlist], height=400), height=420)

        st.markdown("---")
        st.markdown("### Watchlist Charts")
        cols = st.columns(3)
        for i, sym in enumerate(watchlist[:6]):
            with cols[i % 3]:
                st.markdown(f"**{sym}**")
                render_tv(mini_chart(sym, "NSE", height=180), height=200)

        st.markdown("---")
        st.info("TradingView mode — live charts and market data. Connect a broker for trading.")
        st.stop()

    # ── Broker mode ──
    if not require_broker():
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

    interval_label = st.selectbox("Interval", list(INTERVAL_CHOICES.keys()), index=1)
    interval = INTERVAL_CHOICES[interval_label]

    st.markdown("---")

    # ── Auto-load quotes ──
    if not st.session_state.get("auto_loaded", False):
        with st.spinner("Loading market data..."):
            quote_data = []
            for symbol in watchlist:
                try:
                    q = broker.get_quote(symbol)
                    quote_data.append({
                        "Symbol": symbol, "LTP": q["ltp"],
                        "Open": q["open"], "High": q["high"],
                        "Low": q["low"], "Close": q["close"],
                    })
                except Exception:
                    quote_data.append({
                        "Symbol": symbol, "LTP": "—", "Open": "—",
                        "High": "—", "Low": "—", "Close": "—",
                    })
            if quote_data:
                st.session_state["auto_quotes"] = pd.DataFrame(quote_data)
            st.session_state["auto_loaded"] = True

    # Show auto-loaded quotes
    auto_quotes = st.session_state.get("auto_quotes")
    if auto_quotes is not None and not auto_quotes.empty:
        st.markdown("### Live Quotes")
        st.dataframe(auto_quotes, use_container_width=True, hide_index=True)

    # TradingView chart alongside broker data
    if st.session_state.get("tv_enabled"):
        st.markdown("---")
        st.markdown("### TradingView Live Chart")
        tv_sym = st.selectbox("Select Symbol", watchlist, key="tv_dash_chart")
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
                    signal_data.append({"Symbol": symbol, "Signal": "N/A", "RSI": None, "Price": None})
                    continue
                df = generate_signals(df, st.session_state["strategy_params"])
                last_row = df.iloc[-1]
                signal_data.append({
                    "Symbol": symbol, "Signal": last_row["signal_label"],
                    "RSI": round(last_row["rsi"], 2), "Price": round(last_row["close"], 2),
                    "MACD Hist": round(last_row["macd_hist"], 4),
                    "SMA Fast": round(last_row["sma_fast"], 2),
                    "SMA Slow": round(last_row["sma_slow"], 2),
                })
            except Exception as e:
                signal_data.append({"Symbol": symbol, "Signal": "ERROR", "RSI": None, "Price": None})
            progress.progress((i + 1) / len(watchlist))

        if signal_data:
            st.dataframe(pd.DataFrame(signal_data), use_container_width=True)

            tg = dict(st.secrets.get("telegram", {})) if "telegram" in st.secrets else {}
            buys = [d for d in signal_data if d.get("Signal") == "BUY"]
            sells = [d for d in signal_data if d.get("Signal") == "SELL"]
            if (buys or sells) and tg.get("bot_token") and tg.get("chat_id"):
                alerts = []
                if buys: alerts.append("BUY: " + ", ".join(d["Symbol"] for d in buys))
                if sells: alerts.append("SELL: " + ", ".join(d["Symbol"] for d in sells))
                send_telegram_message(tg["bot_token"], tg["chat_id"], "\n".join(alerts))
                st.toast("Telegram alerts sent!")

    # Quick quote
    st.markdown("---")
    st.subheader("Quick Quote")
    sym = st.selectbox("Symbol", watchlist, key="dq_sym")
    if st.button("Get Quote"):
        try:
            q = broker.get_quote(sym)
            cols = st.columns(5)
            cols[0].metric("LTP", f"₹{q['ltp']}")
            cols[1].metric("Open", f"₹{q['open']}")
            cols[2].metric("High", f"₹{q['high']}")
            cols[3].metric("Low", f"₹{q['low']}")
            cols[4].metric("Close", f"₹{q['close']}")
        except Exception as e:
            st.error(f"Error: {e}")

    if st.session_state.get("tv_enabled"):
        st.markdown("---")
        st.markdown("### Technical Analysis (TradingView)")
        render_tv(technical_analysis(sym, "NSE", height=400), height=420)


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

    if st.session_state.get("tv_enabled"):
        st.markdown("### TradingView Live Chart")
        render_tv(advanced_chart(chart_symbol.upper(), "NSE", interval_to_tv(chart_interval), height=500), height=520)

        st.markdown("---")
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown("### Technical Analysis")
            render_tv(technical_analysis(chart_symbol.upper(), "NSE", height=400), height=420)
        with c2:
            st.markdown("### Symbol Info")
            render_tv(symbol_info(chart_symbol.upper(), "NSE"), height=420)
        st.markdown("---")

    if is_tradingview():
        st.info("Broker charts require a broker connection. TradingView charts shown above.")
        st.stop()

    if not require_broker():
        st.stop()

    broker = get_broker()
    st.markdown("### Broker Chart (Plotly)")
    if st.button("Load Plotly Chart"):
        with st.spinner("Fetching data..."):
            try:
                df = broker.get_historical(chart_symbol.upper(),
                                            interval=INTERVAL_CHOICES[chart_interval], days=days)
                if df.empty:
                    st.warning("No data returned.")
                    st.stop()
            except Exception as e:
                st.error(f"Error: {e}")
                st.stop()

            df = generate_signals(df, st.session_state["strategy_params"])
            df = add_all_indicators(df, st.session_state["strategy_params"])

            fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                                row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.03,
                                subplot_titles=("Price & SMA", "Volume", "RSI"))
            fig.add_trace(go.Candlestick(x=df.index, open=df["open"], high=df["high"],
                                          low=df["low"], close=df["close"], name="OHLC"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["sma_fast"], name="SMA Fast",
                                      line=dict(color="blue", width=1.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["sma_slow"], name="SMA Slow",
                                      line=dict(color="orange", width=1.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["bb_upper"], name="BB Upper",
                                      line=dict(color="gray", dash="dash", width=1), opacity=0.5), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["bb_lower"], name="BB Lower",
                                      line=dict(color="gray", dash="dash", width=1), opacity=0.5), row=1, col=1)
            colors = ["green" if c >= o else "red" for c, o in zip(df["close"], df["open"])]
            fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="Volume",
                                  marker_color=colors, opacity=0.7), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["rsi"], name="RSI",
                                      line=dict(color="purple", width=1.5)), row=3, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
            fig.update_layout(height=800, xaxis_rangeslider_visible=False,
                              title_text=f"{chart_symbol.upper()} — {chart_interval}")
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
        st.info("Backtesting requires a broker with historical data. Connect Zerodha, Upstox, Angel One, or Groww.")
        st.stop()
    if not require_broker():
        st.stop()

    broker = get_broker()
    col1, col2 = st.columns(2)
    with col1:
        bt_symbol = st.text_input("Symbol", value=st.session_state["watchlist"][0], key="bt_symbol")
        bt_interval = st.selectbox("Interval", list(INTERVAL_CHOICES.keys()), index=3, key="bt_interval")
        bt_days = st.number_input("Lookback (days)", value=365, min_value=60, max_value=730, key="bt_days")
    with col2:
        bt_capital = st.number_input("Starting Capital (Rs)", value=100000, min_value=10000, key="bt_capital")

    if st.button("Run Backtest"):
        with st.spinner("Running backtest..."):
            try:
                interval = INTERVAL_CHOICES[bt_interval]
                df = broker.get_historical(bt_symbol.upper(), interval=interval, days=int(bt_days))
                if df.empty or len(df) < 60:
                    st.warning("Not enough data for backtesting.")
                    st.stop()
            except Exception as e:
                st.error(f"Error: {e}")
                st.stop()

            bt = Backtester(st.session_state["risk"])
            results = bt.run(df, starting_cash=bt_capital, strategy_params=st.session_state["strategy_params"])

            m = results["metrics"]
            cols = st.columns(4)
            cols[0].metric("Total Return", f"{m['total_return_pct']}%")
            cols[1].metric("Win Rate", f"{m['win_rate_pct']}%")
            cols[2].metric("Total Trades", m["total_trades"])
            cols[3].metric("Max Drawdown", f"{m['max_drawdown_pct']}%")

            cols2 = st.columns(3)
            cols2[0].metric("Final Equity", f"Rs {m['final_equity']:,.2f}")
            cols2[1].metric("Avg P&L/Trade", f"Rs {m['avg_pnl']:,.2f}")
            cols2[2].metric("Sharpe Ratio", m["sharpe_ratio"])

            if not results["equity_curve"].empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=results["equity_curve"]["time"],
                                          y=results["equity_curve"]["equity"],
                                          name="Equity", fill="tozeroy",
                                          line=dict(color="royalblue", width=2)))
                fig.update_layout(title="Equity Curve", height=400)
                st.plotly_chart(fig, use_container_width=True)

            if not results["trades"].empty:
                st.markdown("### Trade Log")
                st.dataframe(results["trades"], use_container_width=True)
            else:
                st.info("No trades generated. Adjust strategy parameters in Settings.")


# ═══════════════════════════════════════════════════════════════════════
# PAPER TRADING PAGE
# ═══════════════════════════════════════════════════════════════════════
elif "Paper Trading" in page:
    st.title("Paper Trading")

    if is_tradingview():
        st.info("Paper trading requires a broker connection. Connect Zerodha, Upstox, Upstox, Angel One, or Groww.")
        st.stop()
    if not require_broker():
        st.stop()

    broker = get_broker()
    pt = st.session_state["paper_trader"]

    st.markdown("### Portfolio")
    prices = {}
    for sym in st.session_state["watchlist"][:10]:
        try:
            q = broker.get_quote(sym)
            prices[sym] = q["ltp"]
        except Exception:
            pass

    portfolio_val = pt.portfolio_value(prices)
    cols = st.columns(3)
    cols[0].metric("Cash", f"Rs {pt.cash:,.2f}")
    cols[1].metric("Portfolio Value", f"Rs {portfolio_val:,.2f}")
    cols[2].metric("Return", f"{(portfolio_val / pt.starting_cash - 1) * 100:.2f}%")

    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    with col1: pt_sym = st.selectbox("Symbol", st.session_state["watchlist"], key="pt_symbol")
    with col2: pt_qty = st.number_input("Qty", min_value=1, value=10, key="pt_qty")
    with col3: pt_price = st.number_input("Price (0 = live LTP)", min_value=0.0, value=0.0, key="pt_price")
    with col4: pt_action = st.selectbox("Action", ["BUY", "SELL"], key="pt_action")

    if st.button("Execute Paper Trade"):
        price = pt_price
        if price == 0:
            try:
                price = broker.get_quote(pt_sym)["ltp"]
            except Exception as e:
                st.error(f"Couldn't get live price: {e}")
                st.stop()
        if pt_action == "BUY":
            ok, msg = pt.buy(pt_sym, pt_qty, price, "Manual")
        else:
            ok, msg = pt.sell(pt_sym, pt_qty, price, "Manual")
        if ok:
            st.success(f"{pt_action} {pt_qty} {pt_sym} @ Rs {price:.2f}")
        else:
            st.error(msg)

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
        st.warning("Live orders require a real broker. TradingView is charting only.")
        st.stop()
    if not require_broker():
        st.stop()

    broker = get_broker()
    st.warning("**This page places REAL orders with real money.** Test in Paper Trading first.")

    col1, col2, col3, col4 = st.columns(4)
    with col1: lo_sym = st.selectbox("Symbol", st.session_state["watchlist"], key="lo_symbol")
    with col2: lo_qty = st.number_input("Qty", min_value=1, value=1, key="lo_qty")
    with col3: lo_type = st.selectbox("Order Type", ["MARKET", "LIMIT"], key="lo_type")
    with col4: lo_side = st.selectbox("Side", ["BUY", "SELL"], key="lo_side")

    lo_price = 0.0
    if lo_type == "LIMIT":
        lo_price = st.number_input("Limit Price (Rs)", min_value=0.0, value=0.0, key="lo_price")

    st.markdown("---")
    st.markdown("**Type `CONFIRM` to place this order.**")
    confirm = st.text_input("Confirmation", key="lo_confirm", placeholder="CONFIRM")

    if st.button("Place Live Order", type="primary"):
        if confirm != "CONFIRM":
            st.error("You must type CONFIRM to place a live order.")
        else:
            with st.spinner("Placing order..."):
                result = broker.place_order(symbol=lo_sym.upper(), qty=lo_qty,
                                            side=lo_side, order_type=lo_type, price=lo_price)
                if result["success"]:
                    st.success(f"Order placed! ID: {result['order_id']}")
                    tg = dict(st.secrets.get("telegram", {})) if "telegram" in st.secrets else {}
                    if tg.get("bot_token") and tg.get("chat_id"):
                        send_telegram_message(tg["bot_token"], tg["chat_id"],
                                              f"LIVE ORDER\n{lo_side} {lo_qty} {lo_sym}\nID: {result['order_id']}")
                else:
                    st.error(f"Order failed: {result['message']}")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Current Positions")
        try:
            positions = broker.get_positions()
            if positions:
                st.dataframe(pd.DataFrame(positions), use_container_width=True)
            else:
                st.info("No open positions.")
        except Exception as e:
            st.error(f"Error: {e}")
    with c2:
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
    c1, c2 = st.columns(2)
    with c1:
        risk["max_capital_per_trade_pct"] = st.slider("Max Capital per Trade (%)", 1.0, 100.0, risk["max_capital_per_trade_pct"])
        risk["stop_loss_pct"] = st.slider("Stop Loss (%)", 0.5, 20.0, risk["stop_loss_pct"])
        risk["max_open_positions"] = st.slider("Max Open Positions", 1, 20, risk["max_open_positions"])
    with c2:
        risk["take_profit_pct"] = st.slider("Take Profit (%)", 0.5, 50.0, risk["take_profit_pct"])
        risk["daily_loss_limit_pct"] = st.slider("Daily Loss Limit (%)", 1.0, 30.0, risk["daily_loss_limit_pct"])
    st.session_state["risk"] = risk

    st.markdown("---")
    st.markdown("### Strategy Parameters")
    params = st.session_state["strategy_params"]
    c3, c4 = st.columns(2)
    with c3:
        params["rsi_oversold"] = st.slider("RSI Oversold", 10, 40, params["rsi_oversold"])
        params["rsi_overbought"] = st.slider("RSI Overbought", 60, 90, params["rsi_overbought"])
    with c4:
        params["sma_fast"] = st.slider("SMA Fast Period", 5, 50, params["sma_fast"])
        params["sma_slow"] = st.slider("SMA Slow Period", 20, 200, params["sma_slow"])
    st.session_state["strategy_params"] = params

    st.markdown("---")
    st.markdown("### TradingView Charts")
    st.session_state["tv_enabled"] = st.checkbox(
        "Enable TradingView widgets", value=st.session_state.get("tv_enabled", True)
    )
    if st.session_state["tv_enabled"]:
        st.success("TradingView charts enabled — live charts on Dashboard and Charts pages.")
    else:
        st.info("TradingView charts disabled.")

    st.markdown("---")
    st.markdown("### Telegram Alerts")
    tg = dict(st.secrets.get("telegram", {})) if "telegram" in st.secrets else {}
    st.text_input("Bot Token", value=tg.get("bot_token", ""), key="tg_token", type="password")
    st.text_input("Chat ID", value=tg.get("chat_id", ""), key="tg_chat")
    if st.button("Send Test Alert"):
        ok = send_telegram_message(
            st.session_state.get("tg_token", ""),
            st.session_state.get("tg_chat", ""),
            "AlgoDesk test alert"
        )
        if ok:
            st.success("Test alert sent!")
        else:
            st.error("Failed. Check your bot token and chat ID.")

    st.markdown("---")
    st.markdown("### About")
    st.info(
        f"**{APP_TITLE}**\n\n"
        "Brokers: Zerodha, Upstox, Angel One, Groww, TradingView (charts only).\n\n"
        "Enter API keys on the Connect page — keys stay in your browser session.\n"
        "You can also use secrets.toml as a fallback.\n\n"
        "Not financial advice. Test in Paper Trading before Live Orders."
    )
