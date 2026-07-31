"""
ai_analysis.py
AI Pattern Detection & Analysis Engine for AlgoDesk.
Detects: Golden/Death Cross, Support/Resistance Breakout, RSI Overbought/Oversold,
Volume Spikes, Trend Identification. Includes simulated data fallback.
"""
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def generate_simulated_data(days=120, base_price=None):
    """Generate simulated OHLCV data for demo when no broker connected."""
    if base_price is None:
        base_price = 100 + np.random.random() * 50
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='D')
    prices = []
    last = base_price
    trend_dir = 1
    trend_counter = 0
    for i in range(days):
        if trend_counter <= 0:
            trend_dir = np.random.choice([1, -1])
            trend_counter = 8 + int(np.random.random() * 15)
        trend_counter -= 1
        drift = trend_dir * np.random.random() * 0.6
        noise = (np.random.random() - 0.5) * 1.8
        o = last
        c = max(1, o + drift + noise)
        h = max(o, c) + np.random.random() * 0.8
        l = min(o, c) - np.random.random() * 0.8
        v = np.random.random() * 1000000 + 500000
        prices.append({'open': o, 'high': h, 'low': l, 'close': c, 'volume': v})
        last = c
    return pd.DataFrame(prices, index=dates)


def compute_sma(series, period):
    return series.rolling(window=period).mean()

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def compute_volatility(series, period=14):
    return series.rolling(window=period).std()


def detect_all_patterns(df):
    """Detect all patterns and return (signals_list, analyzed_df)."""
    signals = []
    df = df.copy()
    df['sma9'] = compute_sma(df['close'], 9)
    df['sma21'] = compute_sma(df['close'], 21)
    df['rsi'] = compute_rsi(df['close'], 14)
    if len(df) < 25:
        return signals, df

    for i in range(1, len(df)):
        s9, s21 = df['sma9'].iloc[i], df['sma21'].iloc[i]
        s9p, s21p = df['sma9'].iloc[i-1], df['sma21'].iloc[i-1]
        if pd.isna(s9) or pd.isna(s21) or pd.isna(s9p) or pd.isna(s21p):
            continue
        dt = df.index[i]
        dt_str = dt.strftime('%Y-%m-%d') if hasattr(dt, 'strftime') else str(dt)

        if s9p <= s21p and s9 > s21:
            signals.append({'date': dt_str, 'type': 'BUY', 'price': df['close'].iloc[i],
                            'reason': 'AI ne SMA9 ko SMA21 ke upar cross karte dekha — bullish golden cross, momentum badh raha hai.'})
        if s9p >= s21p and s9 < s21:
            signals.append({'date': dt_str, 'type': 'SELL', 'price': df['close'].iloc[i],
                            'reason': 'AI ne SMA9 ko SMA21 ke neeche cross karte dekha — bearish death cross, weakness dikh rahi hai.'})

    for i in range(20, len(df)):
        recent = df.iloc[i-20:i]
        res = recent['high'].max()
        sup = recent['low'].min()
        dt = df.index[i]
        dt_str = dt.strftime('%Y-%m-%d') if hasattr(dt, 'strftime') else str(dt)
        if df['close'].iloc[i] > res and df['close'].iloc[i-1] <= res:
            signals.append({'date': dt_str, 'type': 'BUY', 'price': df['close'].iloc[i],
                            'reason': f'Price ne resistance ({res:.2f}) break kiya — breakout, buyers active.'})
        if df['close'].iloc[i] < sup and df['close'].iloc[i-1] >= sup:
            signals.append({'date': dt_str, 'type': 'SELL', 'price': df['close'].iloc[i],
                            'reason': f'Price support ({sup:.2f}) ke neeche — breakdown, sellers hawi.'})

    for i in range(14, len(df)):
        r = df['rsi'].iloc[i]
        if pd.isna(r):
            continue
        rp = df['rsi'].iloc[i-1]
        dt = df.index[i]
        dt_str = dt.strftime('%Y-%m-%d') if hasattr(dt, 'strftime') else str(dt)
        if r > 70 and not pd.isna(rp) and rp <= 70:
            signals.append({'date': dt_str, 'type': 'SELL', 'price': df['close'].iloc[i],
                            'reason': f'RSI {r:.1f} > 70 — overbought zone, correction possible.'})
        if r < 30 and not pd.isna(rp) and rp >= 30:
            signals.append({'date': dt_str, 'type': 'BUY', 'price': df['close'].iloc[i],
                            'reason': f'RSI {r:.1f} < 30 — oversold zone, bounce possible.'})

    return signals, df


def render_ai_chart(df, signals):
    """Render candlestick chart with AI overlays."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.75, 0.25], vertical_spacing=0.05,
                        subplot_titles=("Price + AI Pattern Detection", "Volume"))
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name="OHLC", increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ), row=1, col=1)
    if 'sma9' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['sma9'], name="SMA 9",
                                 line=dict(color='#3b82f6', width=1.5)), row=1, col=1)
    if 'sma21' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['sma21'], name="SMA 21",
                                 line=dict(color='#f0b429', width=1.5)), row=1, col=1)

    recent = df.tail(20)
    if len(recent) >= 5:
        res = recent['high'].max()
        sup = recent['low'].min()
        fig.add_hline(y=res, line_dash="dash", line_color="#f0b429", opacity=0.5,
                      annotation_text=f"R: {res:.2f}", row=1, col=1)
        fig.add_hline(y=sup, line_dash="dash", line_color="#3b82f6", opacity=0.5,
                      annotation_text=f"S: {sup:.2f}", row=1, col=1)

    buys = [s for s in signals if s['type'] == 'BUY']
    sells = [s for s in signals if s['type'] == 'SELL']
    if buys:
        fig.add_trace(go.Scatter(
            x=[s['date'] for s in buys], y=[s['price'] for s in buys],
            mode='markers', marker=dict(symbol='triangle-up', size=14, color='#26a69a'),
            name='BUY'), row=1, col=1)
    if sells:
        fig.add_trace(go.Scatter(
            x=[s['date'] for s in sells], y=[s['price'] for s in sells],
            mode='markers', marker=dict(symbol='triangle-down', size=14, color='#ef5350'),
            name='SELL'), row=1, col=1)

    if 'volume' in df.columns:
        colors = ['#26a69a' if c >= o else '#ef5350' for c, o in zip(df['close'], df['open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume',
                             marker_color=colors, opacity=0.5), row=2, col=1)

    fig.update_layout(height=600, xaxis_rangeslider_visible=False,
                      template='plotly_dark', showlegend=True,
                      margin=dict(l=50, r=20, t=40, b=20),
                      font=dict(family="Segoe UI, sans-serif"))
    return fig


def run_sma_backtest(df):
    """Run SMA9/SMA21 crossover backtest."""
    df = df.copy()
    df['sma9'] = compute_sma(df['close'], 9)
    df['sma21'] = compute_sma(df['close'], 21)
    position = None
    trades = []
    equity = 100
    peak = 100
    max_dd = 0
    for i in range(21, len(df)):
        s9, s21 = df['sma9'].iloc[i], df['sma21'].iloc[i]
        s9p, s21p = df['sma9'].iloc[i-1], df['sma21'].iloc[i-1]
        if pd.isna(s9) or pd.isna(s21) or pd.isna(s9p) or pd.isna(s21p):
            continue
        price = df['close'].iloc[i]
        if position is None and s9p <= s21p and s9 > s21:
            position = {'entry': price, 'date': df.index[i]}
        elif position is not None and s9p >= s21p and s9 < s21:
            ret = (price - position['entry']) / position['entry'] * 100
            trades.append({'entry_date': position['date'], 'exit_date': df.index[i],
                           'entry': position['entry'], 'exit': price,
                           'return_pct': ret, 'win': ret > 0})
            equity *= (1 + ret / 100)
            peak = max(peak, equity)
            max_dd = min(max_dd, (equity - peak) / peak * 100)
            position = None
    if position is not None:
        price = df['close'].iloc[-1]
        ret = (price - position['entry']) / position['entry'] * 100
        trades.append({'entry_date': position['date'], 'exit_date': df.index[-1],
                       'entry': position['entry'], 'exit': price,
                       'return_pct': ret, 'win': ret > 0})
        equity *= (1 + ret / 100)
        peak = max(peak, equity)
        max_dd = min(max_dd, (equity - peak) / peak * 100)
    wins = sum(1 for t in trades if t['win'])
    return {
        'trades': trades, 'win_rate': (wins / len(trades) * 100) if trades else 0,
        'total_trades': len(trades), 'net_pnl': equity - 100,
        'max_drawdown': max_dd, 'equity': equity
    }


def get_live_metrics(df):
    """Get live quantitative metrics from dataframe."""
    closes = df['close']
    rsi = compute_rsi(closes, 14)
    sma9 = compute_sma(closes, 9)
    sma21 = compute_sma(closes, 21)
    vol = compute_volatility(closes, 14)
    last_rsi = rsi.iloc[-1] if len(rsi) > 0 and not pd.isna(rsi.iloc[-1]) else None
    last_s9 = sma9.iloc[-1] if len(sma9) > 0 and not pd.isna(sma9.iloc[-1]) else None
    last_s21 = sma21.iloc[-1] if len(sma21) > 0 and not pd.isna(sma21.iloc[-1]) else None
    last_vol = vol.iloc[-1] if len(vol) > 0 and not pd.isna(vol.iloc[-1]) else None
    if last_s9 and last_s21:
        trend = "Bullish" if last_s9 > last_s21 else "Bearish"
    else:
        trend = "Neutral"
    last_price = closes.iloc[-1]
    prev_price = closes.iloc[-2] if len(closes) > 1 else last_price
    change = last_price - prev_price
    change_pct = (change / prev_price * 100) if prev_price else 0
    return {
        'price': last_price, 'change': change, 'change_pct': change_pct,
        'rsi': last_rsi, 'sma9': last_s9, 'sma21': last_s21,
        'volatility': last_vol, 'trend': trend
    }
