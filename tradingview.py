"""
tradingview.py
TradingView widget generators for embedding free charts and market data.
No API key required — uses TradingView's free embeddable widgets.
Docs: https://www.tradingview.com/widget/

All functions return HTML strings — use with st.components.v1.html(html, height=...)
"""

import streamlit.components.v1 as components


def advanced_chart(symbol: str = "RELIANCE", exchange: str = "NSE",
                   interval: str = "D", height: int = 500) -> str:
    """TradingView Advanced Real-Time Chart widget."""
    tv_symbol = f"{exchange}:{symbol}"
    return f"""
    <div class="tradingview-widget-container" style="height:{height}px;">
      <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
      {{
        "autosize": true,
        "symbol": "{tv_symbol}",
        "interval": "{interval}",
        "timezone": "Asia/Kolkata",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "enable_publishing": false,
        "hide_side_toolbar": false,
        "allow_symbol_change": true,
        "studies": [
          "STD;RSI",
          "STD;MACD",
          "STD;SMA"
        ],
        "support_host": "s3.tradingview.com"
      }}
      </script>
    </div>
    """


def symbol_info(symbol: str = "RELIANCE", exchange: str = "NSE") -> str:
    """TradingView Symbol Info widget."""
    tv_symbol = f"{exchange}:{symbol}"
    return f"""
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-symbol-info.js" async>
      {{
        "symbol": "{tv_symbol}",
        "width": "100%",
        "locale": "en",
        "colorTheme": "dark",
        "isTransparent": false
      }}
      </script>
    </div>
    """


def technical_analysis(symbol: str = "RELIANCE", exchange: str = "NSE",
                        height: int = 400) -> str:
    """TradingView Technical Analysis widget."""
    tv_symbol = f"{exchange}:{symbol}"
    return f"""
    <div class="tradingview-widget-container" style="height:{height}px;">
      <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js" async>
      {{
        "interval": "1h",
        "width": "100%",
        "height": "{height}",
        "isTransparent": false,
        "symbol": "{tv_symbol}",
        "showIntervalTabs": true,
        "locale": "en",
        "colorTheme": "dark"
      }}
      </script>
    </div>
    """


def market_overview(symbols: list = None, height: int = 500) -> str:
    """TradingView Market Overview / Watchlist widget."""
    if symbols is None:
        symbols = [
            ("RELIANCE", "NSE"),
            ("TCS", "NSE"),
            ("HDFCBANK", "NSE"),
            ("INFY", "NSE"),
            ("ICICIBANK", "NSE"),
        ]

    quotes = [{"symbol": f"{ex}:{sym}", "proName": f"{ex}:{sym}"}
              for sym, ex in symbols]

    import json
    return f"""
    <div class="tradingview-widget-container" style="height:{height}px;">
      <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-market-quotes.js" async>
      {{
        "width": "100%",
        "height": "{height}",
        "symbols": {json.dumps(quotes)},
        "locale": "en",
        "colorTheme": "dark",
        "isTransparent": false
      }}
      </script>
    </div>
    """


def ticker_tape(symbols: list = None) -> str:
    """TradingView Ticker Tape widget — scrolling price ticker."""
    if symbols is None:
        symbols = [
            ("RELIANCE", "NSE"),
            ("TCS", "NSE"),
            ("HDFCBANK", "NSE"),
            ("INFY", "NSE"),
            ("ICICIBANK", "NSE"),
            ("SBIN", "NSE"),
            ("TATAMOTORS", "NSE"),
            ("ITC", "NSE"),
        ]

    quotes = [{"proName": f"{ex}:{sym}", "title": sym}
              for sym, ex in symbols]

    import json
    return f"""
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
      {{
        "symbols": {json.dumps(quotes)},
        "showSymbolLogo": true,
        "isTransparent": false,
        "displayMode": "adaptive",
        "colorTheme": "dark",
        "locale": "en"
      }}
      </script>
    </div>
    """


def mini_chart(symbol: str = "RELIANCE", exchange: str = "NSE",
               height: int = 200) -> str:
    """TradingView Mini Chart widget — compact symbol chart."""
    tv_symbol = f"{exchange}:{symbol}"
    return f"""
    <div class="tradingview-widget-container" style="height:{height}px;">
      <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-chart.js" async>
      {{
        "symbol": "{tv_symbol}",
        "width": "100%",
        "height": "{height}",
        "locale": "en",
        "dateRange": "3M",
        "colorTheme": "dark",
        "isTransparent": false,
        "autosize": true,
        "largeChartUrl": ""
      }}
      </script>
    </div>
    """


def render(html: str, height: int = 500):
    """Render TradingView widget HTML in Streamlit."""
    components.html(html, height=height)
