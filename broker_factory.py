"""
broker_factory.py
Constructs the right broker adapter from Streamlit secrets.
Add new brokers here by extending SUPPORTED_BROKERS and the create_broker() function.
"""

from config import DEFAULT_WATCHLIST


SUPPORTED_BROKERS = ["Zerodha", "Upstox", "Angel One", "Groww", "TradingView"]


def create_broker(broker_name: str, secrets: dict):
    """
    Instantiate and return the broker adapter for the given name.
    `secrets` is typically st.secrets (dict-like with section keys).
    Returns a BaseBroker subclass instance or raises ValueError.
    """
    broker_name = broker_name.lower().replace(" ", "").replace("one", "one")

    if broker_name in ("zerodha", "kite"):
        from brokers.zerodha import ZerodhaBroker
        return ZerodhaBroker(
            api_key=secrets["zerodha"]["api_key"],
            api_secret=secrets["zerodha"]["api_secret"],
            redirect_uri=secrets["zerodha"].get("redirect_uri", "http://localhost:8501"),
        )

    elif broker_name in ("upstox",):
        from brokers.upstox import UpstoxBroker
        return UpstoxBroker(
            api_key=secrets["upstox"]["api_key"],
            api_secret=secrets["upstox"]["api_secret"],
            redirect_uri=secrets["upstox"].get("redirect_uri", "http://localhost:8501"),
        )

    elif broker_name in ("angelone", "angel", "angel1"):
        from brokers.angelone import AngelOneBroker
        return AngelOneBroker(
            api_key=secrets["angelone"]["api_key"],
            client_code=secrets["angelone"]["client_code"],
            password=secrets["angelone"]["password"],
            totp_secret=secrets["angelone"]["totp_secret"],
        )

    elif broker_name in ("groww",):
        from brokers.groww import GrowwBroker
        return GrowwBroker(
            api_key=secrets["groww"]["api_key"],
            totp_secret=secrets["groww"].get("totp_secret", ""),
        )

    elif broker_name in ("tradingview", "tv"):
        from brokers.tradingview import TradingViewBroker
        return TradingViewBroker()

    else:
        raise ValueError(
            f"Unsupported broker: {broker_name}. "
            f"Supported brokers: {SUPPORTED_BROKERS}"
        )
