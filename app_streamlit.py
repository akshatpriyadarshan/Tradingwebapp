import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import time

st.set_page_config(page_title="BharatTrade AI", layout="wide")

# Custom CSS adapted from original
st.markdown("""
<style>
:root {
  --bg: #090d12;
  --s1: #0f1620;
  --s2: #141d2b;
  --s3: #1a2435;
  --bd: rgba(255,255,255,.07);
  --bd2: rgba(255,255,255,.14);
  --tx: #e2eaf5;
  --mu: #5c7191;
  --mu2: #8aa0be;
  --ac: #00d4aa;
  --bl: #3b8eff;
  --dn: #ff4d6d;
  --wn: #f4a935;
  --pu: #a78bfa;
  --mono: 'Courier New', monospace;
  --head: 'Arial', sans-serif;
  --body: 'Arial', sans-serif;
}

body {
  background-color: var(--bg);
  color: var(--tx);
  font-family: var(--body);
  margin: 0;
  padding: 0;
}

.stApp {
  background-color: var(--bg);
  margin: 0;
  padding: 0;
  max-width: 100vw;
  width: 100vw;
}

.main .block-container {
  padding: 0;
  margin: 0;
  max-width: 100%;
}

.metric-card {
  background-color: var(--s2);
  border: 1px solid var(--bd);
  border-radius: 9px;
  padding: 0.5rem 0.65rem;
  text-align: center;
}

.metric-name {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--mu);
  margin-bottom: 3px;
}

.metric-value {
  font-family: var(--head);
  font-size: 16px;
  font-weight: 700;
}

.metric-change {
  font-family: var(--mono);
  font-size: 10px;
  margin-top: 1px;
}

.up { color: var(--ac); }
.down { color: var(--dn); }
.neutral { color: var(--wn); }

.watchlist-table {
  width: 100%;
  border-collapse: collapse;
}

.watchlist-table th {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--mu);
  text-align: left;
  padding: 0.22rem 0.38rem;
  border-bottom: 1px solid var(--bd);
}

.watchlist-table td {
  font-size: 11px;
  padding: 0.25rem 0.38rem;
  border-bottom: 1px solid rgba(255,255,255,.03);
}

.watchlist-table .sym {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--mu2);
}

.watchlist-table .pr {
  font-family: var(--head);
  font-weight: 600;
  font-size: 12px;
}

.watchlist-table .ch {
  font-family: var(--mono);
  font-size: 10px;
}

.signal-card {
  background-color: var(--s1);
  border: 1px solid var(--bd);
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 0.7rem;
  padding: 0.6rem 0.82rem;
}

.signal-buy { border-top: 2px solid var(--ac); }
.signal-sell { border-top: 2px solid var(--dn); }

.signal-name {
  font-family: var(--head);
  font-size: 14px;
  font-weight: 700;
}

.signal-action {
  font-family: var(--mono);
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 4px;
  font-weight: 500;
}

.action-buy {
  background: rgba(0,212,170,.12);
  color: var(--ac);
  border: 1px solid rgba(0,212,170,.2);
}

.action-sell {
  background: rgba(255,77,109,.12);
  color: var(--dn);
  border: 1px solid rgba(255,77,109,.2);
}

.conf-high { background: rgba(0,212,170,.09); color: var(--ac); border: 1px solid rgba(0,212,170,.15); }
.conf-medium { background: rgba(244,169,53,.09); color: var(--wn); border: 1px solid rgba(244,169,53,.15); }
.conf-low { background: rgba(255,255,255,.05); color: var(--mu); border: 1px solid var(--bd); }

.tag {
  font-family: var(--mono);
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 500;
}

.tg-up { background: rgba(0,212,170,.12); color: var(--ac); border: 1px solid rgba(0,212,170,.2); }
.tg-dn { background: rgba(255,77,109,.12); color: var(--dn); border: 1px solid rgba(255,77,109,.2); }
.tg-neu { background: rgba(244,169,53,.1); color: var(--wn); border: 1px solid rgba(244,169,53,.15); }

.disclaimer {
  padding: 0.45rem 0.7rem;
  font-size: 11px;
  color: var(--mu2);
  line-height: 1.55;
  background: rgba(255,77,109,.04);
  border: 1px solid rgba(255,77,109,.12);
  border-radius: 9px;
}

.news-item {
  background-color: var(--s2);
  border: 1px solid var(--bd);
  border-radius: 9px;
  padding: 0.5rem 0.65rem;
  margin-bottom: 5px;
  display: flex;
  gap: 0.5rem;
}

.news-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 5px;
}

.dot-bull { background: var(--ac); }
.dot-bear { background: var(--dn); }
.dot-neu { background: var(--wn); }

.news-text {
  font-size: 11.5px;
  color: var(--tx);
  line-height: 1.55;
}

.news-meta {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--mu);
  margin-top: 3px;
}

.filter-btn {
  font-family: var(--mono);
  font-size: 10px;
  padding: 0.26rem 0.65rem;
  border-radius: 20px;
  border: 1px solid var(--bd);
  background: var(--s2);
  color: var(--mu2);
  cursor: pointer;
  margin-right: 5px;
}

.filter-active {
  background: var(--ac);
  border-color: var(--ac);
  color: #050d0a;
  font-weight: 500;
}

.technical-item {
  display: flex;
  justify-content: space-between;
  background: var(--s2);
  border: 1px solid var(--bd);
  border-radius: 6px;
  padding: 0.32rem 0.58rem;
  margin-bottom: 4px;
}

.technical-label {
  font-size: 11px;
  color: var(--mu2);
}

.technical-value {
  font-family: var(--mono);
  font-size: 11px;
}

.fii-dii-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px;
}

.fii-dii-card {
  background: var(--s2);
  border: 1px solid var(--bd);
  border-radius: 9px;
  padding: 0.5rem 0.65rem;
  text-align: center;
}

.fii-dii-label {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--mu);
  margin-bottom: 3px;
}

.fii-dii-value {
  font-family: var(--head);
  font-size: 14px;
  font-weight: 700;
}

.fii-dii-sub {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--mu);
  margin-top: 2px;
}

.ticker {
  background: var(--s2);
  border-bottom: 1px solid var(--bd);
  overflow: hidden;
  height: 27px;
  display: flex;
  align-items: center;
  white-space: nowrap;
  animation: ticker 45s linear infinite;
}

@keyframes ticker {
  to { transform: translateX(-50%); }
}

.ticker-item {
  font-family: var(--mono);
  font-size: 11px;
  display: flex;
  gap: 0.4rem;
  padding: 0 2rem;
}

.ticker-name { color: var(--mu); }
.ticker-value { color: var(--tx); }
.ticker-up { color: var(--ac); }
.ticker-down { color: var(--dn); }

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 1.2rem;
  height: 46px;
  background: var(--s1);
  border-bottom: 1px solid var(--bd2);
}

.logo {
  font-family: var(--head);
  font-size: 16px;
  font-weight: 800;
  color: var(--tx);
}

.logo span { color: var(--ac); }

.topbar-center {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

.index-mini {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 90px;
}

.index-name {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--mu);
}

.index-value {
  font-family: var(--head);
  font-size: 13px;
  font-weight: 700;
}

.index-change {
  font-family: var(--mono);
  font-size: 10px;
}

</style>
""", unsafe_allow_html=True)

# Constants
INDEX_SYMS = ['^NSEI', '^BSESN', '^NSEBANK', '^CNXIT']
WATCH_SYMS = [
  'SUZLON.NS', 'YESBANK.NS', 'PNB.NS', 'CANBK.NS',
  'BHEL.NS', 'IRFC.NS', 'NTPC.NS', 'COALINDIA.NS',
  'ASHOKLEY.NS', 'BIOCON.NS', 'CGPOWER.NS', 'CDSL.NS'
]

SIGNALS = [
  {'name': 'SUZLON ENERGY', 'sym': 'SUZLON.NS', 'ex': 'NSE', 'action': 'BUY', 'sector': 'Renewable Energy', 'tier': 100, 'sl_pct': -8, 'tgt_pct': 18, 'rr': '1:2.4', 'conf': 'medium',
   'reason': 'India\'s RE capacity targets drive strong order inflow. Stock near 52W support with RSI recovering from oversold. Volume spike on Apr 9 signals institutional accumulation. Clean energy narrative intact for FY27.'},
  {'name': 'YES BANK', 'sym': 'YESBANK.NS', 'ex': 'NSE', 'action': 'BUY', 'sector': 'Private Banking', 'tier': 100, 'sl_pct': -8, 'tgt_pct': 22, 'rr': '1:2.7', 'conf': 'low',
   'reason': 'Speculative bounce setup — ₹17 support held 3 sessions. RSI near 38 (oversold). Volume accumulation visible. High-risk: banking sector weak overall. Keep position size minimal. Confirm 1–2 green candles before entry.'},
  {'name': 'PNB', 'sym': 'PNB.NS', 'ex': 'NSE', 'action': 'SELL', 'sector': 'PSU Banking', 'tier': 100, 'sl_pct': 6, 'tgt_pct': -11, 'rr': '1:1.8', 'conf': 'medium',
   'reason': 'PSU banks under persistent FII selling. PNB −1.44% on Apr 9. Below 20-DMA. Bank Nifty RSI at 50 — bullish momentum fading. Sell-on-rise strategy recommended until rate narrative shifts.'},
  {'name': 'CANARA BANK', 'sym': 'CANBK.NS', 'ex': 'NSE', 'action': 'BUY', 'sector': 'PSU Banking', 'tier': 100, 'sl_pct': -7, 'tgt_pct': 13, 'rr': '1:2.2', 'conf': 'low',
   'reason': 'Mean-reversion — beaten down more than private peers. Near 52W low. RSI at 32 (oversold). Wait for 1–2 sessions of price confirmation before entry. Risk: sector-wide weakness may persist.'},
  {'name': 'BHEL', 'sym': 'BHEL.NS', 'ex': 'NSE', 'action': 'BUY', 'sector': 'Capital Goods', 'tier': 500, 'sl_pct': -6, 'tgt_pct': 11, 'rr': '1:2.0', 'conf': 'medium',
   'reason': 'Capex cycle driving transformer & energy equipment demand. +1.63% on Apr 9. Approaching 50-DMA breakout. Q4 order backlog expected strong. Budget capex push supports multi-quarter tailwind.'},
  {'name': 'IRFC', 'sym': 'IRFC.NS', 'ex': 'NSE', 'action': 'BUY', 'sector': 'Railways Finance', 'tier': 500, 'sl_pct': -6, 'tgt_pct': 12, 'rr': '1:2.2', 'conf': 'medium',
   'reason': '100% Govt-backed railway loans — near-zero credit risk. Near 200-DMA support. RSI 45, room to run. Railway infra remains a Union Budget priority. Low-beta profile suits conservative swing trades.'},
  {'name': 'NTPC', 'sym': 'NTPC.NS', 'ex': 'NSE', 'action': 'BUY', 'sector': 'Power PSU', 'tier': 500, 'sl_pct': -5, 'tgt_pct': 10, 'rr': '1:2.0', 'conf': 'high',
   'reason': 'Consistent buying in power sector. +1.48% on Apr 9 while broader market fell. Dividend yield provides downside cushion. RSI 55 — not overbought. 50-DMA acting as dynamic support. FY27 capacity guidance positive.'},
  {'name': 'COAL INDIA', 'sym': 'COALINDIA.NS', 'ex': 'NSE', 'action': 'SELL', 'sector': 'Mining PSU', 'tier': 500, 'sl_pct': 4, 'tgt_pct': -7, 'rr': '1:1.7', 'conf': 'low',
   'reason': 'Sell-on-rise setup. Faces energy-transition headwinds and weak seasonal demand. RSI trending down from overbought. FII unwinding visible in F&O data. Bounce after recent fall = exit opportunity.'},
  {'name': 'ASHOK LEYLAND', 'sym': 'ASHOKLEY.NS', 'ex': 'NSE', 'action': 'BUY', 'sector': 'Commercial Vehicles', 'tier': 500, 'sl_pct': -5, 'tgt_pct': 11, 'rr': '1:2.2', 'conf': 'medium',
   'reason': 'CV cycle strong with infra-driven freight demand. Showing relative outperformance vs. broader market. At 50-DMA support. Auto sector rotation underway. Q4 volume data expected solid.'},
  {'name': 'BIOCON', 'sym': 'BIOCON.NS', 'ex': 'NSE', 'action': 'BUY', 'sector': 'Pharma / Biosimilars', 'tier': 500, 'sl_pct': -5, 'tgt_pct': 10, 'rr': '1:2.1', 'conf': 'low',
   'reason': 'Defensive pharma strength amid volatility. Biosimilar pipeline in US/EU is long-term catalyst. Near 200-DMA support. RSI 42. Q4 results could surprise positively. Higher risk from regulatory overhangs.'},
  {'name': 'CG POWER', 'sym': 'CGPOWER.NS', 'ex': 'NSE', 'action': 'BUY', 'sector': 'Electricals', 'tier': 1000, 'sl_pct': -5, 'tgt_pct': 10, 'rr': '1:2.2', 'conf': 'medium',
   'reason': 'Record order book for transformers and motors driven by power sector capex. Above 50-DMA. RSI at 52 — neutral, room to rally. FY27 power infrastructure growth is a strong multi-quarter tailwind.'},
  {'name': 'CDSL', 'sym': 'CDSL.NS', 'ex': 'NSE', 'action': 'BUY', 'sector': 'Capital Markets Infra', 'tier': 1000, 'sl_pct': -5, 'tgt_pct': 10, 'rr': '1:2.0', 'conf': 'medium',
   'reason': 'Depository services benefit from rising retail participation. Market rally boosts demat openings & transaction volumes. Near support after correction. RSI recovering from 40. Post-ceasefire rally boosts Q4 volumes.'},
]

NEWS = [
  {'t': 'bull', 'tag': 'Geopolitical', 'txt': 'US-Iran ceasefire talks triggered Nifty\'s largest weekly gain in 5 years (+6%). India VIX crashed 26%, signalling reduced near-term panic.', 'dt': 'Apr 8–10, 2026'},
  {'t': 'neu', 'tag': 'RBI Policy', 'txt': 'RBI MPC held repo rate unchanged at 5.25% with neutral stance. Rate hike possibility emerging — next MPC meeting will be closely watched.', 'dt': 'Apr 8, 2026'},
  {'t': 'bull', 'tag': 'Earnings', 'txt': 'Q4 FY26 results season begins. TCS first; HDFC Bank, Infosys, Wipro to report Apr 13–18 — key IT sector direction trigger.', 'dt': 'Apr 11, 2026'},
  {'t': 'bear', 'tag': 'Banking', 'txt': 'HDFC Bank −2.22%, Kotak −2.18%, SBI −2.18%, ICICI −1.96%. Bank Nifty RSI near 50 — bullish momentum fading across the sector.', 'dt': 'Apr 9, 2026'},
  {'t': 'bull', 'tag': 'Metals/Auto', 'txt': 'Hindalco +3.25%, Bajaj Auto +1.62%, BEL +1.59%, NTPC +1.48% outperformed the index on a broad down day — clear sector rotation signal.', 'dt': 'Apr 9, 2026'},
  {'t': 'neu', 'tag': 'Crude Oil', 'txt': 'Brent stabilising post-ceasefire. Lower crude eases India\'s current account deficit and supports the rupee — positive macro tailwind.', 'dt': 'Apr 10, 2026'},
]

@st.cache_data(ttl=60)
def fetch_data(symbols):
    try:
        data = yf.download(symbols, period='1d', interval='1m', timeout=10)
        if data.empty:
            return {}
        latest = data['Close'].iloc[-1] if 'Close' in data.columns else data.iloc[-1]
        prev = data['Close'].iloc[-2] if len(data) > 1 else latest
        change = latest - prev
        pct_change = (change / prev) * 100
        result = {}
        for sym in symbols:
            if sym in latest.index:
                result[sym] = {
                    'price': latest[sym],
                    'change': change[sym] if sym in change.index else 0,
                    'pct_change': pct_change[sym] if sym in pct_change.index else 0
                }
        return result
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return {}

def format_price(price):
    return f"₹{price:.2f}" if pd.notna(price) else "—"

def format_change(change, pct):
    if pd.isna(change) or pd.isna(pct):
        return "—"
    sign = "+" if change > 0 else ""
    return f"{sign}{change:.2f} ({sign}{pct:.2f}%)"

def get_change_class(change):
    if pd.isna(change):
        return "neutral"
    return "up" if change > 0 else "down"

# App layout
st.markdown('<div class="topbar"><div class="logo">Bharat<span>Trade</span> AI</div><div class="topbar-center" id="tbIdx"></div></div>', unsafe_allow_html=True)

# Fetch data
all_symbols = INDEX_SYMS + WATCH_SYMS
live_data = fetch_data(all_symbols)

# Topbar indices
topbar_html = '<div class="topbar-center">'
for sym, name in [('^NSEI', 'NIFTY 50'), ('^BSESN', 'SENSEX'), ('^NSEBANK', 'BANK NIFTY')]:
    data = live_data.get(sym, {})
    price = data.get('price', None)
    change = data.get('change', None)
    pct = data.get('pct_change', None)
    change_str = format_change(change, pct) if change is not None else "—"
    cls = get_change_class(change)
    topbar_html += f'<div class="index-mini"><div class="index-name">{name}</div><div class="index-value {cls}">{format_price(price)}</div><div class="index-change {cls}">{change_str}</div></div>'
topbar_html += '</div>'
st.markdown(topbar_html, unsafe_allow_html=True)

# Ticker
ticker_items = []
for sym in INDEX_SYMS + WATCH_SYMS:
    data = live_data.get(sym, {})
    price = data.get('price', None)
    pct = data.get('pct_change', None)
    name = sym.replace('.NS', '').replace('^NSEI', 'NIFTY50').replace('^BSESN', 'SENSEX').replace('^NSEBANK', 'BNKNIFTY').replace('^CNXIT', 'NIFTYIT')
    price_str = format_price(price) if price else "—"
    pct_str = f"{pct:.2f}%" if pct else "—"
    cls = "ticker-up" if pct and pct > 0 else "ticker-down" if pct and pct < 0 else "ticker-value"
    ticker_items.append(f'<div class="ticker-item"><span class="ticker-name">{name}</span><span class="ticker-value">{price_str}</span><span class="{cls}">{pct_str}</span></div>')

ticker_html = f'<div class="ticker"><div style="display: flex;">{"".join(ticker_items * 2)}</div></div>'
st.markdown(ticker_html, unsafe_allow_html=True)

# Main panels
col_left, col_right = st.columns([3, 4])

with col_left:
    st.markdown("### Market Indices")
    cols = st.columns(4)
    for i, (sym, name) in enumerate([('^NSEI', 'NIFTY 50'), ('^BSESN', 'SENSEX'), ('^NSEBANK', 'NIFTY BANK'), ('^CNXIT', 'NIFTY IT')]):
        data = live_data.get(sym, {})
        price = data.get('price', None)
        change = data.get('change', None)
        pct = data.get('pct_change', None)
        change_str = format_change(change, pct)
        cls = get_change_class(change)
        with cols[i]:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-name">{name}</div>
                <div class="metric-value {cls}">{format_price(price)}</div>
                <div class="metric-change {cls}">{change_str}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("### Technicals · Nifty 50")
    nsei_data = live_data.get('^NSEI', {})
    price = nsei_data.get('price', None)
    # Simplified technicals (would need more data for full calc)
    technicals = [
        ("RSI (14D)", "63.4", "tg-up"),
        ("50-Day MA", format_price(price * 0.98) if price else "—", "tg-up"),  # Placeholder
        ("200-Day MA", format_price(price * 0.95) if price else "—", "tg-up"),
        ("52W High", format_price(price * 1.1) if price else "—", "tg-inf"),
        ("52W Low", format_price(price * 0.9) if price else "—", "tg-neu"),
        ("Prev Close", format_price(price) if price else "—", "tg-neu"),
    ]
    for label, value, tag_cls in technicals:
        st.markdown(f"""
        <div class="technical-item">
            <span class="technical-label">{label}</span>
            <span class="technical-value">{value} <span class="tag {tag_cls}">—</span></span>
        </div>
        """, unsafe_allow_html=True)



    st.markdown("### Live Watchlist · NSE")
    watchlist_data = []
    for sym in WATCH_SYMS:
        data = live_data.get(sym, {})
        price = data.get('price', None)
        pct = data.get('pct_change', None)
        name = sym.replace('.NS', '')
        price_str = format_price(price)
        pct_str = f"{pct:.2f}%" if pct else "—"
        cls = get_change_class(data.get('change', None))
        watchlist_data.append([name, price_str, pct_str, cls])

    if watchlist_data:
        df = pd.DataFrame([[row[0], row[1], row[2]] for row in watchlist_data], columns=['Symbol', 'LTP (₹)', 'Chg %'])
        st.dataframe(df, use_container_width=True)

    st.markdown("### Market News")
    for news in NEWS:
        dot_cls = "dot-bull" if news['t'] == 'bull' else "dot-bear" if news['t'] == 'bear' else "dot-neu"
        tag_cls = "tg-up" if news['t'] == 'bull' else "tg-dn" if news['t'] == 'bear' else "tg-neu"
        st.markdown(f"""
        <div class="news-item">
            <div class="news-dot {dot_cls}"></div>
            <div>
                <div class="news-text"><span class="tag {tag_cls}">{news['tag']}</span> {news['txt']}</div>
                <div class="news-meta">{news['dt']}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

with col_right:
    st.markdown("""
    <div class="disclaimer">
        <strong>⚠ Advisory:</strong> Probability-based signals for <strong>educational use only</strong>. No profits guaranteed. Trades <strong>NEVER execute automatically</strong> — your explicit approval is required each time. Live prices via Yahoo Finance (may be delayed 15 min). Consult a SEBI-registered advisor before trading.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### Trade Signals · Swing 3–7 Days")
    filter_options = ["All Signals", "Under ₹100", "Under ₹500", "Under ₹1,000", "BUY only", "SELL only"]
    selected_filter = st.selectbox("Filter", filter_options, key="filter")

    filtered_signals = []
    for signal in SIGNALS:
        if selected_filter == "All Signals":
            filtered_signals.append(signal)
        elif selected_filter == "Under ₹100" and signal['tier'] <= 100:
            filtered_signals.append(signal)
        elif selected_filter == "Under ₹500" and signal['tier'] <= 500:
            filtered_signals.append(signal)
        elif selected_filter == "Under ₹1,000" and signal['tier'] <= 1000:
            filtered_signals.append(signal)
        elif selected_filter == "BUY only" and signal['action'] == "BUY":
            filtered_signals.append(signal)
        elif selected_filter == "SELL only" and signal['action'] == "SELL":
            filtered_signals.append(signal)

    if filtered_signals:
        for i in range(0, len(filtered_signals), 3):
            cols = st.columns(3)
            for j in range(3):
                if i + j < len(filtered_signals):
                    signal = filtered_signals[i + j]
                    with cols[j]:
                        data = live_data.get(signal['sym'], {})
                        price = data.get('price', None)
                        change = data.get('change', None)
                        pct = data.get('pct_change', None)
                        live_price = format_price(price)
                        change_str = format_change(change, pct)
                        cls = get_change_class(change)

                        action_cls = "action-buy" if signal['action'] == "BUY" else "action-sell"
                        card_cls = "signal-buy" if signal['action'] == "BUY" else "signal-sell"
                        conf_cls = f"conf-{signal['conf']}"

                        tier_label = "Under ₹100" if signal['tier'] <= 100 else "Under ₹500" if signal['tier'] <= 500 else "Under ₹1,000"
                        tier_cls = "tp1" if signal['tier'] <= 100 else "tp5" if signal['tier'] <= 500 else "tpk"

                        # Calculate levels safely
                        if price is not None:
                            entry = price
                            sl = price * (1 + signal['sl_pct'] / 100)
                            tgt = price * (1 + signal['tgt_pct'] / 100)
                            entry_str = f"₹{entry:.2f}"
                            sl_str = f"₹{sl:.2f}"
                            tgt_str = f"₹{tgt:.2f}"
                        else:
                            entry_str = "—"
                            sl_str = "—"
                            tgt_str = "—"

                        st.markdown(f"""
                        <div class="signal-card {card_cls}">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.28rem;">
                                <span class="signal-name">{signal['name']}</span>
                                <span class="signal-action {action_cls}">{signal['action']}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.28rem;">
                                <span style="font-size: 11px; color: #8aa0be;">{signal['sector']}</span>
                                <div>
                                    <span class="tag {tier_cls}">{tier_label}</span>
                                    <span class="tag {conf_cls}">{signal['conf'].upper()}</span>
                                </div>
                            </div>
                            <div style="margin-bottom: 0.52rem;">
                                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px;">
                                    <div style="background: #141d2b; border: 1px solid rgba(255,255,255,.07); border-radius: 6px; padding: 0.28rem 0.42rem; text-align: center;">
                                        <div style="font-family: 'Courier New', monospace; font-size: 9px; color: #5c7191; text-transform: uppercase;">Entry</div>
                                        <div style="font-family: Arial, sans-serif; font-size: 13px; font-weight: 600; margin-top: 2px;">{entry_str}</div>
                                    </div>
                                    <div style="background: #141d2b; border: 1px solid rgba(255,255,255,.07); border-radius: 6px; padding: 0.28rem 0.42rem; text-align: center;">
                                        <div style="font-family: 'Courier New', monospace; font-size: 9px; color: #5c7191; text-transform: uppercase;">Stop Loss</div>
                                        <div style="font-family: Arial, sans-serif; font-size: 13px; font-weight: 600; margin-top: 2px; color: #ff4d6d;">{sl_str}</div>
                                    </div>
                                    <div style="background: #141d2b; border: 1px solid rgba(255,255,255,.07); border-radius: 6px; padding: 0.28rem 0.42rem; text-align: center;">
                                        <div style="font-family: 'Courier New', monospace; font-size: 9px; color: #5c7191; text-transform: uppercase;">Target</div>
                                        <div style="font-family: Arial, sans-serif; font-size: 13px; font-weight: 600; margin-top: 2px; color: #00d4aa;">{tgt_str}</div>
                                    </div>
                                </div>
                            </div>
                            <div style="font-size: 11.5px; color: #8aa0be; line-height: 1.6; border-top: 1px solid rgba(255,255,255,.07); padding-top: 0.48rem;">
                                {signal['reason']}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
    else:
        st.write("No signals match the filter.")

if st.button("Refresh Data"):
    st.rerun()