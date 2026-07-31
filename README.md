# AlgoDesk — Multi-Broker Stock Trading Dashboard (Streamlit)

Switch between brokers from a dropdown; signals, charts, backtesting,
paper trading, and live orders (behind a confirmation step) all work the
same way regardless of which broker is active.

## Broker status

| Broker | Status | Login type | Notes |
|---|---|---|---|
| Zerodha (Kite Connect) | Fully implemented | Browser redirect | Rs 2,000/month API subscription, daily token expiry |
| Upstox | Fully implemented | Browser redirect | Free API. Verify endpoints against current Upstox docs before going live |
| Angel One (SmartAPI) | Fully implemented | Direct login (client code + password + live TOTP) | Free API. Enable TOTP-based API login in the Angel One app first |
| 5paisa | Not implemented | — | Adapter pattern is ready — see "Adding a new broker" below |
| AliceBlue | Not implemented | — | Same as above |
| Fyers | Not implemented | — | Same as above |

## What this is / isn't

- A real working dashboard: live signals (RSI+MACD+SMA), candlestick
  charts, no-lookahead backtesting, paper trading, and live order
  placement that always requires typing `CONFIRM`.
- Not a 24/7 unattended bot. Streamlit only runs while the app/browser
  session is active, and Zerodha/Upstox tokens expire daily requiring a
  fresh human login. For true unattended automation, run a separate
  always-on worker (VPS + scheduler) that writes to a shared database
  this dashboard reads from.

## Setup

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# fill in only the broker(s) you plan to use
streamlit run app.py
```

### Getting API keys (you must do this yourself — no one else can)

- **Zerodha**: developers.kite.trade → create app → Rs 2,000/month
  subscription → note API key/secret → set redirect URL to your deployed
  app's URL.
- **Upstox**: upstox.com/developer → create app (free) → note API
  key/secret → set redirect URI to match `UPSTOX_REDIRECT_URI`.
- **Angel One**: smartapi.angelbroking.com → create app (free) → note API
  key. Also enable TOTP-based login for API access in the Angel One
  mobile app under API settings.

## Deploy to Streamlit Community Cloud

1. Push to a GitHub repo (`.streamlit/secrets.toml` must be gitignored).
2. share.streamlit.io → connect repo → entry point `app.py`.
3. App Settings → Secrets → paste your real values from
  `secrets.toml.example`.
4. Update each broker's redirect URL/URI to your deployed app's address.

## Adding a new broker (5paisa, AliceBlue, Fyers, etc.)

1. Read that broker's official API docs.
2. Create `brokers/<name>.py` with a class implementing every method in
  `brokers/base.py` (`get_login_url`, `complete_login`, `get_historical`,
  `get_quote`, `place_order`, `get_positions`, `get_order_history`).
  `get_historical` must return a DataFrame indexed by datetime with
  columns `open, high, low, close, volume` — that's the only contract
  the rest of the app depends on.
3. Register it in `broker_factory.py` (`SUPPORTED_BROKERS` list + a new
  `elif` branch in `create_broker`).
4. Add its login UI block in `app.py`'s Connect page, following the
  Zerodha/Upstox/Angel One examples.

Everything else — Dashboard, Chart, Backtest, Paper Trading, Live Orders,
Settings — needs zero changes, since they all talk to whatever broker is
active through the same interface.

## Risk management

Configurable in Settings: max capital per trade, stop-loss %,
take-profit %, max open positions, daily loss limit. Enforced in the
backtester; for live trading these are guardrails you should also watch
manually, since this app doesn't run unattended background monitoring.

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI — broker selector + all pages |
| `broker_factory.py` | Constructs the right broker adapter from secrets |
| `brokers/base.py` | Abstract interface every broker adapter implements |
| `brokers/zerodha.py`, `upstox.py`, `angelone.py` | Concrete adapters |
| `config.py` | Watchlist/risk defaults, constants |
| `indicators.py` | RSI, MACD, SMA/EMA, Bollinger, ATR |
| `strategy.py` | Rule-based BUY/SELL/HOLD signal engine |
| `backtester.py` | No-lookahead backtest with metrics |
| `paper_trader.py` | Simulated portfolio |
| `telegram_alert.py` | Optional trade notifications |

## Disclaimer

Technical/analytical tool, not financial advice. Test in Paper Trading
and Backtest thoroughly before ever using Live Orders with real capital.
