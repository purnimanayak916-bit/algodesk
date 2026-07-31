"""
ai_analysis.py — AI Pattern Detection, Quant Analysis & Scoring Engine for AlgoDesk.
All features: Pattern detection, Deep Quant (Sharpe/Z-score/Bollinger/Skew),
Technical+Quant+Fundamental scoring with gauge, Up/Down analysis,
Returns histogram, SMA crossover backtest.
"""
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def generate_simulated_data(days=120, base_price=None):
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


# ── INDICATORS ──
def compute_sma(s, p): return s.rolling(window=p).mean()
def compute_ema(s, p):
    return s.ewm(span=p, adjust=False).mean()
def compute_rsi(s, p=14):
    delta = s.diff()
    gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    ag = gain.rolling(p).mean(); al = loss.rolling(p).mean()
    rs = ag / al.replace(0, np.nan)
    return 100 - (100 / (1 + rs))
def compute_volatility(s, p=14): return s.rolling(p).std()
def compute_macd(s):
    e12 = compute_ema(s, 12); e26 = compute_ema(s, 26)
    macd_line = e12 - e26
    signal = compute_ema(macd_line, 9)
    hist = macd_line - signal
    return macd_line, signal, hist


# ── DEEP QUANT FUNCTIONS ──
def get_returns(df, n=60):
    closes = df['close'].iloc[-n-1:] if len(df) > n else df['close']
    return closes.pct_change().dropna() * 100

def compute_sharpe_ratio(df, n=30):
    rets = get_returns(df, n)
    if len(rets) < 5: return None
    m = rets.mean(); sd = rets.std()
    if sd == 0: return 0
    return (m / sd) * np.sqrt(252)

def compute_zscore(df, p=20):
    if len(df) < p: return None
    slice_c = df['close'].iloc[-p:]
    m = slice_c.mean(); sd = slice_c.std()
    if sd == 0: return 0
    return (df['close'].iloc[-1] - m) / sd

def compute_momentum(df, p=10):
    if len(df) < p + 1: return None
    return (df['close'].iloc[-1] - df['close'].iloc[-1-p]) / df['close'].iloc[-1-p] * 100

def compute_annualized_vol(df, n=20):
    rets = get_returns(df, n)
    if len(rets) < 5: return None
    return rets.std() * np.sqrt(252)

def compute_bollinger_position(df, p=20, mult=2):
    if len(df) < p: return None
    slice_c = df['close'].iloc[-p:]
    m = slice_c.mean(); sd = slice_c.std()
    upper = m + mult * sd; lower = m - mult * sd
    price = df['close'].iloc[-1]
    if upper == lower: return 50
    return ((price - lower) / (upper - lower)) * 100

def compute_return_skew(df, n=60):
    rets = get_returns(df, n)
    if len(rets) < 10: return None
    m = rets.mean(); sd = rets.std()
    if sd == 0: return 0
    return rets.skew()

def get_returns_distribution(df, n=60, bins=12):
    rets = get_returns(df, n)
    if len(rets) < 5: return None
    counts, edges = np.histogram(rets, bins=bins)
    return {'counts': counts.tolist(), 'edges': edges.tolist(),
            'min': rets.min(), 'max': rets.max(), 'rets': rets.tolist()}


# ── SCORING ENGINE ──
def compute_technical_score(df):
    closes = df['close']
    if len(closes) < 30: return {'score': 50, 'notes': ['Not enough history']}
    notes = []; score = 50
    r = compute_rsi(closes, 14).iloc[-1]
    if not pd.isna(r):
        if r < 30: score += 15; notes.append(f'RSI {r:.1f} — oversold, bullish tilt')
        elif r > 70: score -= 15; notes.append(f'RSI {r:.1f} — overbought, bearish tilt')
        else: notes.append(f'RSI {r:.1f} — neutral')
    s20 = compute_sma(closes, 20); s50 = compute_sma(closes, min(50, len(closes)-1))
    lc = closes.iloc[-1]; ls20 = s20.iloc[-1]; ls50 = s50.iloc[-1]
    if not pd.isna(ls20):
        if lc > ls20: score += 8; notes.append('Price above 20-SMA — uptrend')
        else: score -= 8; notes.append('Price below 20-SMA — downtrend')
    if not pd.isna(ls20) and not pd.isna(ls50):
        if ls20 > ls50: score += 7; notes.append('20-SMA > 50-SMA — golden trend')
        else: score -= 7; notes.append('20-SMA < 50-SMA — death cross')
    _, _, hist = compute_macd(closes)
    lh = hist.iloc[-1]; ph = hist.iloc[-2] if len(hist) > 1 else None
    if not pd.isna(lh) and ph is not None and not pd.isna(ph):
        if lh > 0 and lh > ph: score += 10; notes.append('MACD rising — momentum building')
        elif lh > 0: score += 4; notes.append('MACD positive but flattening')
        elif lh < 0 and lh < ph: score -= 10; notes.append('MACD falling — momentum weakening')
        else: score -= 4; notes.append('MACD negative but improving')
    recent = closes.iloc[-20:]
    vol = recent.std() / recent.mean() if recent.mean() else 0
    if vol > 0.06: notes.append(f'High volatility ({vol*100:.1f}%) — wider stops advised')
    return {'score': max(0, min(100, score)), 'notes': notes, 'rsi': r, 'vol': vol}

def compute_quant_score(df):
    closes = df['close']
    if len(closes) < 20: return {'score': 50, 'notes': ['Insufficient data'], 'sharpe': None}
    rets = closes.pct_change().dropna()
    mr = rets.mean(); vr = rets.std() or 1e-9
    sharpe = (mr / vr) * np.sqrt(len(rets))
    score = 50 + sharpe * 8
    notes = [f'Mean return {mr*100:.2f}%, vol {vr*100:.2f}%', f'Sharpe-like {sharpe:.2f}']
    mom = (closes.iloc[-1] - closes.iloc[-14]) / closes.iloc[-14] * 100 if len(closes) > 14 else 0
    score += mom
    notes.append(f'14-period momentum {mom:.2f}%')
    return {'score': max(0, min(100, score)), 'notes': notes, 'sharpe': sharpe}

def compute_fundamental_score(df):
    closes = df['close']
    notes = []; score = 50
    if len(closes) >= 60:
        ls = compute_sma(closes, 60).iloc[-1]
        lc = closes.iloc[-1]
        if not pd.isna(ls):
            gap = (lc - ls) / ls
            if gap > 0.05: score += 10; notes.append('Above 60-period trend — confidence')
            elif gap < -0.05: score -= 10; notes.append('Below trend — eroding confidence')
            else: notes.append('Tracking long-run trend')
    rv = closes.iloc[-30:].std()
    mp = closes.iloc[-30:].mean()
    rel_vol = rv / mp if mp else 0
    if rel_vol < 0.02: score += 6; notes.append('Low volatility — stable')
    elif rel_vol > 0.05: score -= 4; notes.append('High volatility — uncertain')
    notes.append('Equity fundamentals are market-derived proxies, not balance-sheet data')
    return {'score': max(0, min(100, score)), 'notes': notes}

def verdict_from_score(s):
    if s >= 75: return 'STRONG BUY', '#34D399'
    if s >= 58: return 'BUY', '#1C7C54'
    if s >= 42: return 'NEUTRAL / HOLD', '#D4A62A'
    if s >= 25: return 'SELL', '#B23A2E'
    return 'STRONG SELL', '#F0665A'


# ── UP/DOWN ANALYSIS ──
def get_up_down_analysis(df):
    recent = df.tail(20)
    session_high = recent['high'].max()
    session_low = recent['low'].min()
    last = df['close'].iloc[-1]
    up_candles = (df['close'] >= df['open']).sum()
    down_candles = (df['close'] < df['open']).sum()
    total = up_candles + down_candles
    return {
        'from_high': ((last - session_high) / session_high * 100) if session_high else 0,
        'from_low': ((last - session_low) / session_low * 100) if session_low else 0,
        'up_pct': (up_candles / total * 100) if total else 0,
        'down_pct': (down_candles / total * 100) if total else 0,
        'up_count': up_candles, 'down_count': down_candles,
        'session_high': session_high, 'session_low': session_low
    }


# ── PATTERN DETECTION ──
def detect_all_patterns(df):
    signals = []
    df = df.copy()
    df['sma9'] = compute_sma(df['close'], 9)
    df['sma21'] = compute_sma(df['close'], 21)
    df['rsi'] = compute_rsi(df['close'], 14)
    if len(df) < 25: return signals, df
    for i in range(1, len(df)):
        s9, s21 = df['sma9'].iloc[i], df['sma21'].iloc[i]
        s9p, s21p = df['sma9'].iloc[i-1], df['sma21'].iloc[i-1]
        if pd.isna(s9) or pd.isna(s21) or pd.isna(s9p) or pd.isna(s21p): continue
        dt = df.index[i]; ds = dt.strftime('%Y-%m-%d') if hasattr(dt, 'strftime') else str(dt)
        if s9p <= s21p and s9 > s21:
            signals.append({'date': ds, 'type': 'BUY', 'price': df['close'].iloc[i],
                'reason': 'AI ne SMA9 ko SMA21 ke upar cross karte dekha — bullish golden cross, momentum badh raha hai.'})
        if s9p >= s21p and s9 < s21:
            signals.append({'date': ds, 'type': 'SELL', 'price': df['close'].iloc[i],
                'reason': 'AI ne SMA9 ko SMA21 ke neeche cross karte dekha — bearish death cross, weak ho raha hai.'})
    for i in range(20, len(df)):
        r = df.iloc[i-20:i]; res = r['high'].max(); sup = r['low'].min()
        dt = df.index[i]; ds = dt.strftime('%Y-%m-%d') if hasattr(dt, 'strftime') else str(dt)
        if df['close'].iloc[i] > res and df['close'].iloc[i-1] <= res:
            signals.append({'date': ds, 'type': 'BUY', 'price': df['close'].iloc[i],
                'reason': f'Price ne resistance ({res:.2f}) break kiya — breakout, buyers active.'})
        if df['close'].iloc[i] < sup and df['close'].iloc[i-1] >= sup:
            signals.append({'date': ds, 'type': 'SELL', 'price': df['close'].iloc[i],
                'reason': f'Price support ({sup:.2f}) ke neeche — breakdown, sellers hawi.'})
    for i in range(14, len(df)):
        rv = df['rsi'].iloc[i]
        if pd.isna(rv): continue
        rp = df['rsi'].iloc[i-1] if i > 0 else None
        dt = df.index[i]; ds = dt.strftime('%Y-%m-%d') if hasattr(dt, 'strftime') else str(dt)
        if rv > 70 and rp is not None and not pd.isna(rp) and rp <= 70:
            signals.append({'date': ds, 'type': 'SELL', 'price': df['close'].iloc[i],
                'reason': f'RSI {rv:.1f} > 70 — overbought, correction possible.'})
        if rv < 30 and rp is not None and not pd.isna(rp) and rp >= 30:
            signals.append({'date': ds, 'type': 'BUY', 'price': df['close'].iloc[i],
                'reason': f'RSI {rv:.1f} < 30 — oversold, bounce possible.'})
    return signals, df


# ── CHART RENDERING ──
def render_ai_chart(df, signals):
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.55, 0.20, 0.25], vertical_spacing=0.04,
        subplot_titles=("Price + AI Patterns", "Volume", "RSI"))
    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'],
        low=df['low'], close=df['close'], name="OHLC",
        increasing_line_color='#20c997', decreasing_line_color='#ff5d6c'), row=1, col=1)
    if 'sma9' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['sma9'], name="SMA 9",
            line=dict(color='#5b7fff', width=1.5)), row=1, col=1)
    if 'sma21' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['sma21'], name="SMA 21",
            line=dict(color='#ffb648', width=1.5)), row=1, col=1)
    recent = df.tail(20)
    if len(recent) >= 5:
        res = recent['high'].max(); sup = recent['low'].min()
        fig.add_hline(y=res, line_dash="dash", line_color="#ffb648", opacity=0.5,
            annotation_text=f"R: {res:.2f}", row=1, col=1)
        fig.add_hline(y=sup, line_dash="dash", line_color="#5b7fff", opacity=0.5,
            annotation_text=f"S: {sup:.2f}", row=1, col=1)
    buys = [s for s in signals if s['type'] == 'BUY']
    sells = [s for s in signals if s['type'] == 'SELL']
    if buys:
        fig.add_trace(go.Scatter(x=[s['date'] for s in buys], y=[s['price'] for s in buys],
            mode='markers', marker=dict(symbol='triangle-up', size=14, color='#20c997'),
            name='BUY'), row=1, col=1)
    if sells:
        fig.add_trace(go.Scatter(x=[s['date'] for s in sells], y=[s['price'] for s in sells],
            mode='markers', marker=dict(symbol='triangle-down', size=14, color='#ff5d6c'),
            name='SELL'), row=1, col=1)
    if 'volume' in df.columns:
        colors = ['#20c997' if c >= o else '#ff5d6c' for c, o in zip(df['close'], df['open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume',
            marker_color=colors, opacity=0.5), row=2, col=1)
    if 'rsi' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], name='RSI',
            line=dict(color='#8b6bff', width=1.5)), row=3, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="#ff5d6c", opacity=0.3, row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="#20c997", opacity=0.3, row=3, col=1)
    fig.update_layout(height=700, xaxis_rangeslider_visible=False, template='plotly_dark',
        showlegend=True, margin=dict(l=50, r=20, t=40, b=20),
        font=dict(family="Inter, sans-serif"))
    return fig


def render_gauge(score):
    verdict, color = verdict_from_score(score)
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=score,
        gauge={'axis': {'range': [0, 100]},
            'bar': {'color': color},
            'steps': [
                {'range': [0, 25], 'color': 'rgba(240,102,90,0.15)'},
                {'range': [25, 42], 'color': 'rgba(178,58,46,0.15)'},
                {'range': [42, 58], 'color': 'rgba(212,166,42,0.15)'},
                {'range': [58, 75], 'color': 'rgba(28,124,84,0.15)'},
                {'range': [75, 100], 'color': 'rgba(52,211,153,0.15)'}],
            'threshold': {'line': {'color': color, 'width': 4}, 'value': score}},
        title={'text': verdict, 'font': {'color': color, 'size': 16}}))
    fig.update_layout(height=250, template='plotly_dark', margin=dict(l=20,r=20,t=40,b=10))
    return fig


def render_returns_histogram(df, n=60, bins=12):
    dist = get_returns_distribution(df, n, bins)
    if dist is None: return None
    fig = go.Figure()
    for i in range(bins):
        left = dist['edges'][i]; right = dist['edges'][i+1]
        mid = (left + right) / 2
        color = '#20c997' if mid >= 0 else '#ff5d6c'
        fig.add_trace(go.Bar(x=[f"{left:.1f}% to {right:.1f}%"], y=[dist['counts'][i]],
            marker_color=color, opacity=0.75, showlegend=False,
            text=[dist['counts'][i]], textposition='auto'))
    fig.update_layout(title="Returns Distribution (last 60 candles)", height=280,
        template='plotly_dark', margin=dict(l=30,r=10,t=40,b=10),
        xaxis_title="Return range", yaxis_title="Frequency")
    return fig


# ── BACKTEST ──
def run_sma_backtest(df):
    df = df.copy()
    df['sma9'] = compute_sma(df['close'], 9)
    df['sma21'] = compute_sma(df['close'], 21)
    position = None; trades = []; equity = 100; peak = 100; max_dd = 0
    for i in range(21, len(df)):
        s9, s21 = df['sma9'].iloc[i], df['sma21'].iloc[i]
        s9p, s21p = df['sma9'].iloc[i-1], df['sma21'].iloc[i-1]
        if pd.isna(s9) or pd.isna(s21) or pd.isna(s9p) or pd.isna(s21p): continue
        price = df['close'].iloc[i]
        if position is None and s9p <= s21p and s9 > s21:
            position = {'entry': price, 'date': df.index[i]}
        elif position is not None and s9p >= s21p and s9 < s21:
            ret = (price - position['entry']) / position['entry'] * 100
            trades.append({'entry_date': position['date'], 'exit_date': df.index[i],
                'entry': position['entry'], 'exit': price, 'return_pct': ret, 'win': ret > 0})
            equity *= 1 + ret / 100; peak = max(peak, equity)
            max_dd = min(max_dd, (equity - peak) / peak * 100); position = None
    if position is not None:
        price = df['close'].iloc[-1]; ret = (price - position['entry']) / position['entry'] * 100
        trades.append({'entry_date': position['date'], 'exit_date': df.index[-1],
            'entry': position['entry'], 'exit': price, 'return_pct': ret, 'win': ret > 0})
        equity *= 1 + ret / 100; peak = max(peak, equity)
        max_dd = min(max_dd, (equity - peak) / peak * 100)
    wins = sum(1 for t in trades if t['win'])
    return {'trades': trades, 'win_rate': (wins/len(trades)*100) if trades else 0,
        'total_trades': len(trades), 'net_pnl': equity - 100,
        'max_drawdown': max_dd, 'equity': equity}


# ── LIVE METRICS ──
def get_live_metrics(df):
    closes = df['close']
    rsi = compute_rsi(closes, 14); sma9 = compute_sma(closes, 9)
    sma21 = compute_sma(closes, 21); vol = compute_volatility(closes, 14)
    lr = rsi.iloc[-1] if len(rsi) > 0 and not pd.isna(rsi.iloc[-1]) else None
    ls9 = sma9.iloc[-1] if len(sma9) > 0 and not pd.isna(sma9.iloc[-1]) else None
    ls21 = sma21.iloc[-1] if len(sma21) > 0 and not pd.isna(sma21.iloc[-1]) else None
    lv = vol.iloc[-1] if len(vol) > 0 and not pd.isna(vol.iloc[-1]) else None
    trend = "Bullish" if (ls9 and ls21 and ls9 > ls21) else ("Bearish" if (ls9 and ls21) else "Neutral")
    lp = closes.iloc[-1]; pp = closes.iloc[-2] if len(closes) > 1 else lp
    ch = lp - pp; chp = (ch / pp * 100) if pp else 0
    return {'price': lp, 'change': ch, 'change_pct': chp, 'rsi': lr,
        'sma9': ls9, 'sma21': ls21, 'volatility': lv, 'trend': trend}


def get_all_quant_metrics(df):
    return {
        'sharpe': compute_sharpe_ratio(df),
        'zscore': compute_zscore(df),
        'momentum': compute_momentum(df),
        'ann_vol': compute_annualized_vol(df),
        'bollinger': compute_bollinger_position(df),
        'skew': compute_return_skew(df),
    }


def get_quant_narrative(df):
    q = get_all_quant_metrics(df)
    notes = []
    if q['sharpe'] is not None:
        if q['sharpe'] > 1: notes.append('Risk-adjusted return (Sharpe) achha hai — returns volatility ke muqable strong.')
        elif q['sharpe'] < 0: notes.append('Sharpe negative — recent returns risk ke muqable weak.')
        else: notes.append('Sharpe moderate range mein hai.')
    if q['zscore'] is not None and abs(q['zscore']) > 1.5:
        notes.append(f"Price apne 20-candle average se {q['zscore']:.1f}σ door hai — statistically stretched zone.")
    if q['bollinger'] is not None:
        if q['bollinger'] > 80: notes.append('Price upper Bollinger Band ke paas — mean-reversion ka chance zyada.')
        elif q['bollinger'] < 20: notes.append('Price lower Bollinger Band ke paas — oversold-type zone.')
    if q['momentum'] is not None:
        notes.append(f"10-candle momentum {'positive' if q['momentum']>=0 else 'negative'} hai ({q['momentum']:.2f}%).")
    if q['skew'] is not None and abs(q['skew']) > 0.5:
        direction = 'upside' if q['skew'] > 0 else 'downside'
        notes.append(f"Return distribution mein {'positive' if q['skew']>0 else 'negative'} skew — {direction} outlier moves zyada frequent.")
    return notes, q
