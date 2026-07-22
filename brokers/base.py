"""
brokers/base.py
Abstract base class defining the interface every broker adapter must implement.
The rest of the app only depends on this contract — never on a specific broker.
"""

from abc import ABC, abstractmethod
import pandas as pd


class BaseBroker(ABC):
    """Abstract interface for all broker adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable broker name."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True if the broker session is authenticated and ready."""
        ...

    @abstractmethod
    def get_login_url(self) -> str:
        """Return the URL the user should visit to authenticate."""
        ...

    @abstractmethod
    def complete_login(self, **kwargs) -> bool:
        """
        Complete the OAuth/login flow using broker-specific params.
        Returns True on success.
        """
        ...

    @abstractmethod
    def get_historical(self, symbol: str, interval: str, days: int = 365) -> pd.DataFrame:
        """
        Fetch historical OHLCV data.
        Must return a DataFrame indexed by datetime with columns:
        open, high, low, close, volume
        """
        ...

    @abstractmethod
    def get_quote(self, symbol: str) -> dict:
        """
        Return a live quote dict: {symbol, ltp, open, high, low, close, volume}
        """
        ...

    @abstractmethod
    def place_order(self, symbol: str, qty: int, side: str,
                    order_type: str = "MARKET", price: float = 0.0) -> dict:
        """
        Place an order.
        side: 'BUY' or 'SELL'
        order_type: 'MARKET' or 'LIMIT'
        price: limit price (0 for market orders)
        Returns {success: bool, order_id: str, message: str}
        """
        ...

    @abstractmethod
    def get_positions(self) -> list:
        """Return current open positions as a list of dicts."""
        ...

    @abstractmethod
    def get_order_history(self) -> list:
        """Return recent order history as a list of dicts."""
        ...
