"""
BharatTrade AI — Streamlit Trading Assistant (v3 — fully fixed)
================================================================
Fixes applied:
  1. Plotly candlestick fillcolor: replaced 8-digit hex (#rrggbbaa) → rgba()
  2. Removed increasing_fillcolor / decreasing_fillcolor (not valid Plotly params)
  3. Replaced ZOMATO.NS → ZOMATO.NS verified / NALCO.NS → NATIONALUM.NS
  4. fetch_all_quotes: robust MultiIndex column handling for new yfinance
  5. fetch_intraday_data: robust MultiIndex flattening
  6. compute_indicators: safe Series extraction, no squeeze errors
  7. detect_signals: use .iloc[] not .get() on pandas rows
  8. fmt_price / fmt_pct: handle pandas Series/numpy scalars safely
  9. Screener: per-stock try/except so one bad stock won't break the whole run
 10. Index cards: safe NaN/None guards everywhere
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import feedparser
import re
import pytz
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

# ─── PAGE CONFIG ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TradingGenie AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@500;700;800&family=DM+Sans:wght@300;400;500&display=swap');
:root{--bg:#07090f;--s1:#0d1520;--s2:#111827;--s3:#1a2535;--bd:rgba(255,255,255,.08);--bd2:rgba(255,255,255,.16);--tx:#dde8f8;--mu:#4e6a8a;--mu2:#7a9bc0;--ac:#00d4aa;--bl:#3b8eff;--dn:#ff4d6d;--wn:#f4a935;--pu:#a78bfa;}
.stApp{background:var(--bg)!important;color:var(--tx)!important;font-family:'DM Sans',sans-serif;}
.stApp>header{display:True!important;}
[data-testid="stToolbar"]{display:none!important;}
[data-testid="stSidebar"]{background:var(--s1)!important;}
.block-container{padding:0!important;max-width:100%!important;background:transparent!important;}
.st-emotion-cache-1up3yna,.appview-container,.main,.stApp>section{background:transparent!important;}
[data-testid="stAppViewBlockContainer"]{background:transparent!important;padding:0!important;}
footer{display:none!important;}
.stTabs [data-baseweb="tab-list"]{background:var(--s1)!important;border-bottom:1px solid var(--bd)!important;padding:0 1rem!important;}
.stTabs [data-baseweb="tab"]{background:transparent!important;color:var(--mu)!important;font-family:'DM Mono',monospace!important;font-size:12px!important;padding:.5rem 1.2rem!important;border-radius:6px 6px 0 0!important;border:1px solid transparent!important;}
.stTabs [aria-selected="true"]{background:var(--bg)!important;color:var(--tx)!important;border-color:var(--bd)!important;border-bottom-color:var(--bg)!important;}
.stTabs [data-baseweb="tab-panel"]{background:var(--bg)!important;padding:0!important;}
[data-testid="stMetric"]{background:var(--s2)!important;border:1px solid var(--bd)!important;border-radius:10px!important;padding:.75rem 1rem!important;}
[data-testid="stMetricLabel"]{color:var(--mu)!important;font-family:'DM Mono',monospace!important;font-size:10px!important;}
[data-testid="stMetricValue"]{color:var(--tx)!important;}
[data-testid="stMetricDelta"]{font-family:'DM Mono',monospace!important;font-size:11px!important;}
[data-testid="stSelectbox"]>div>div{background:var(--s2)!important;border-color:var(--bd2)!important;color:var(--tx)!important;}
.stButton>button{background:var(--s2)!important;color:var(--mu2)!important;border:1px solid var(--bd)!important;border-radius:20px!important;font-family:'DM Mono',monospace!important;font-size:11px!important;}
.stButton>button:hover{border-color:var(--ac)!important;color:var(--ac)!important;}
.stAlert{border-radius:8px!important;}
::-webkit-scrollbar{width:3px;height:3px;}
::-webkit-scrollbar-thumb{background:var(--bd2);border-radius:2px;}
.hdr{background:var(--s1);border-bottom:1px solid var(--bd2);padding:.65rem 1.5rem;display:flex;align-items:center;justify-content:space-between;}
.logo{font-family:'Syne',sans-serif;font-size:1.15rem;font-weight:800;color:var(--tx);}
.logo span{color:var(--ac);}
.mkt-open{background:rgba(0,212,170,.1);border:1px solid rgba(0,212,170,.25);color:var(--ac);padding:4px 12px;border-radius:20px;font-family:'DM Mono',monospace;font-size:11px;font-weight:600;}
.mkt-closed{background:rgba(255,77,109,.1);border:1px solid rgba(255,77,109,.25);color:var(--dn);padding:4px 12px;border-radius:20px;font-family:'DM Mono',monospace;font-size:11px;font-weight:600;}
.sec{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--mu);margin:1rem 0 .5rem;display:flex;align-items:center;gap:.5rem;}
.sec::after{content:'';flex:1;height:1px;background:var(--bd);}
.idx-card{background:var(--s2);border:1px solid var(--bd);border-radius:10px;padding:.75rem 1rem;border-top:2px solid;}
.idx-card.up{border-top-color:#00d4aa;}.idx-card.dn{border-top-color:#ff4d6d;}
.idx-label{font-family:'DM Mono',monospace;font-size:8px;color:var(--mu);text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px;}
.idx-price{font-family:'Syne',sans-serif;font-size:1.05rem;font-weight:800;}
.idx-chg{font-family:'DM Mono',monospace;font-size:11px;font-weight:600;margin-top:1px;}
.cup{color:#00d4aa;}.cdn{color:#ff4d6d;}
.nc{background:var(--s2);border:1px solid var(--bd);border-radius:10px;padding:.7rem;margin-bottom:7px;}
.nb{font-family:'DM Mono',monospace;font-size:8px;font-weight:700;padding:2px 6px;border-radius:3px;letter-spacing:.4px;display:inline-block;}
.bull{background:rgba(0,212,170,.12);color:#00d4aa;border:1px solid rgba(0,212,170,.2);}
.bear{background:rgba(255,77,109,.12);color:#ff4d6d;border:1px solid rgba(255,77,109,.2);}
.neu{background:rgba(244,169,53,.1);color:#f4a935;border:1px solid rgba(244,169,53,.2);}
.hi{background:rgba(244,169,53,.1);color:#f4a935;border:1px solid rgba(244,169,53,.2);}
.nt{font-size:12.5px;font-weight:600;color:var(--tx);line-height:1.5;margin:5px 0 3px;}
.nm{font-family:'DM Mono',monospace;font-size:9px;color:var(--mu);}
.sc-card{background:var(--s2);border:1px solid var(--bd);border-radius:10px;padding:.7rem;margin-bottom:7px;border-left:3px solid;}
.sc-card.buy{border-left-color:#00d4aa;}.sc-card.sell{border-left-color:#ff4d6d;}
.sig-buy{background:rgba(0,212,170,.12);color:#00d4aa;border:1px solid rgba(0,212,170,.2);padding:2px 8px;border-radius:4px;font-family:'DM Mono',monospace;font-size:9px;font-weight:800;}
.sig-sell{background:rgba(255,77,109,.12);color:#ff4d6d;border:1px solid rgba(255,77,109,.2);padding:2px 8px;border-radius:4px;font-family:'DM Mono',monospace;font-size:9px;font-weight:800;}
.lvg{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-top:7px;}
.lv{background:var(--s3);border-radius:6px;padding:5px 7px;text-align:center;}
.ll{font-family:'DM Mono',monospace;font-size:7px;color:var(--mu);text-transform:uppercase;}
.lv2{font-family:'Syne',sans-serif;font-size:12px;font-weight:700;margin-top:1px;}
.disc{background:rgba(255,77,109,.05);border:1px solid rgba(255,77,109,.15);border-radius:8px;padding:9px 13px;font-size:11px;color:var(--mu2);}
.tech-block{background:var(--s2);border:1px solid var(--bd);border-radius:10px;overflow:hidden;}
.tr{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border-bottom:1px solid var(--bd);}
.tr:last-child{border-bottom:none;}
.tl{font-size:12px;color:var(--mu2);}
.tv{font-family:'DM Mono',monospace;font-size:12px;color:var(--tx);}
.tbadge{font-family:'DM Mono',monospace;font-size:8px;font-weight:700;padding:2px 6px;border-radius:3px;letter-spacing:.4px;}
.tbull{background:rgba(0,212,170,.12);color:#00d4aa;border:1px solid rgba(0,212,170,.2);}
.tbear{background:rgba(255,77,109,.12);color:#ff4d6d;border:1px solid rgba(255,77,109,.2);}
.tneu{background:rgba(244,169,53,.1);color:#f4a935;border:1px solid rgba(244,169,53,.2);}
</style>
""", unsafe_allow_html=True)

# ─── CONSTANTS ────────────────────────────────────────────────────────────────
IST = pytz.timezone("Asia/Kolkata")

INDEX_SYMS = {
    "^NSEI":    "NIFTY 50",
    "^BSESN":   "SENSEX",
    "^NSEBANK": "BANK NIFTY",
    "^CNXIT":   "NIFTY IT",
    "^NSMIDCP": "NIFTY MIDCAP",
}

# Verified Yahoo Finance symbols (Apr 2026)
STOCK_UNIVERSE = [
    ("YESBANK.NS",    "Yes Bank",            "Banking"),
    ("PNB.NS",        "Punjab Natl Bank",    "PSU Banking"),
    ("CANBK.NS",      "Canara Bank",         "PSU Banking"),
    ("IDFCFIRSTB.NS", "IDFC First Bank",     "Private Banking"),
    ("BANKBARODA.NS", "Bank of Baroda",      "PSU Banking"),
    ("UNIONBANK.NS",  "Union Bank",          "PSU Banking"),
    ("INDIANB.NS",    "Indian Bank",         "PSU Banking"),
    ("SUZLON.NS",     "Suzlon Energy",       "Renewable Energy"),
    ("NHPC.NS",       "NHPC",               "Hydro Power"),
    ("RECLTD.NS",     "REC Ltd",            "Power Finance"),
    ("POWERGRID.NS",  "Power Grid",         "Power Infra"),
    ("NTPC.NS",       "NTPC",              "Power PSU"),
    ("COALINDIA.NS",  "Coal India",         "Mining PSU"),
    ("JPPOWER.NS",    "JP Power",           "Power Private"),
    ("RPOWER.NS",     "Reliance Power",     "Power Private"),
    ("TATAPOWER.NS",  "Tata Power",         "Power Private"),
    ("ONGC.NS",       "ONGC",              "Oil & Gas PSU"),
    ("IOC.NS",        "Indian Oil",         "Oil & Gas PSU"),
    ("BPCL.NS",       "BPCL",              "Oil & Gas PSU"),
    ("HINDPETRO.NS",  "HPCL",              "Oil & Gas PSU"),
    ("IRFC.NS",       "IRFC",              "Railways Finance"),
    ("IRCTC.NS",      "IRCTC",            "Railways"),
    ("BHEL.NS",       "BHEL",             "Capital Goods"),
    ("BEL.NS",        "BEL",              "Defence"),
    ("SAIL.NS",       "SAIL",             "Steel PSU"),
    ("NMDC.NS",       "NMDC",             "Mining PSU"),
    ("NATIONALUM.NS", "NALCO",            "Aluminium PSU"),   # Fixed: was NALCO.NS
    ("VEDL.NS",       "Vedanta",          "Metals"),
    ("IDEA.NS",       "Vodafone Idea",    "Telecom"),
    ("HFCL.NS",       "HFCL",            "Telecom Infra"),
    ("TRIDENT.NS",    "Trident",          "Textiles"),
    ("BIOCON.NS",     "Biocon",           "Pharma"),
    ("GLENMARK.NS",   "Glenmark",         "Pharma"),
    ("ASHOKLEY.NS",   "Ashok Leyland",    "Commercial Vehicles"),
    ("MPHASIS.NS",    "Mphasis",          "IT Services"),
    ("PERSISTENT.NS", "Persistent Sys",   "IT Services"),
    ("CGPOWER.NS",    "CG Power",         "Electricals"),
    ("CDSL.NS",       "CDSL",            "Capital Markets"),
    ("DIXON.NS",      "Dixon Tech",       "Electronics"),

]

RSS_FEEDS = [
    ("https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "Economic Times"),
    ("https://www.moneycontrol.com/rss/latestnews.xml",                       "MoneyControl"),
    ("https://www.business-standard.com/rss/markets-106.rss",                 "Business Standard"),
    ("https://feeds.feedburner.com/ndtvprofit-latest",                         "NDTV Profit"),
    ("https://www.livemint.com/rss/markets",                                   "LiveMint"),
]

# Plotly base theme — applied via update_layout
CHART_LAYOUT = dict(
    plot_bgcolor  = "#07090f",
    paper_bgcolor = "#0d1520",
    font          = dict(family="DM Mono, monospace", color="#7a9bc0", size=10),
    margin        = dict(l=0, r=10, t=30, b=0),
    hovermode     = "x unified",
    xaxis_rangeslider_visible = False,
    legend        = dict(
        orientation="h", yanchor="bottom", y=1.01,
        xanchor="right", x=1,
        font=dict(size=9, color="#7a9bc0"),
        bgcolor="rgba(13,21,32,0.8)",
    ),
)

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def is_market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    o = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    c = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return o <= now <= c

def _scalar(v):
    """Safely convert pandas Series / numpy scalar / float to Python float."""
    if v is None:
        return None
    if isinstance(v, pd.Series):
        v = v.iloc[0] if len(v) == 1 else float(v.mean())
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and np.isnan(v):
        return None
    try:
        return float(v)
    except Exception:
        return None

def fp(v) -> str:
    """Format price safely."""
    v = _scalar(v)
    if v is None: return "—"
    return f"₹{v:,.2f}"

def fpc(v) -> str:
    """Format percent safely."""
    v = _scalar(v)
    if v is None: return "—"
    return f"{'+'if v>=0 else''}{v:.2f}%"

def cc(v) -> str:
    """CSS color class."""
    v = _scalar(v)
    if v is None: return ""
    return "cup" if v >= 0 else "cdn"

def time_ago(s) -> str:
    if not s: return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s) if isinstance(s, str) else s
        diff = datetime.now(IST) - dt.astimezone(IST)
        m = int(diff.total_seconds() / 60)
        if m < 1:    return "Just now"
        if m < 60:   return f"{m}m ago"
        if m < 1440: return f"{m//60}h ago"
        return dt.strftime("%d %b")
    except Exception:
        return ""

def flatten_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex columns from yfinance download."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if c[1] == "" else c[0] for c in df.columns]
    return df

def rename_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Rename Open/High/Low/Close/Volume → lowercase."""
    return df.rename(columns={
        "Open":"open","High":"high","Low":"low",
        "Close":"close","Volume":"volume",
        "Adj Close":"close",
    })

# ─── DATA FETCHING ────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def fetch_indices() -> list[dict]:
    results = []
    for sym, label in INDEX_SYMS.items():
        try:
            raw = yf.download(sym, period="5d", interval="1d",
                              auto_adjust=True, progress=False)
            if raw.empty:
                continue
            raw = flatten_cols(raw)
            raw = rename_ohlcv(raw)
            closes = raw["close"].dropna()
            if len(closes) < 2:
                continue
            price      = float(closes.iloc[-1])
            prev_close = float(closes.iloc[-2])
            change     = price - prev_close
            pct        = (change / prev_close * 100) if prev_close else 0
            results.append({
                "symbol": sym, "label": label,
                "price": price, "change": change, "change_pct": pct,
                "prev_close": prev_close,
                "high": float(raw["high"].iloc[-1]) if "high" in raw.columns else price,
                "low":  float(raw["low"].iloc[-1])  if "low"  in raw.columns else price,
                "year_high": float(closes.max()),
                "year_low":  float(closes.min()),
            })
        except Exception:
            pass
    return results

@st.cache_data(ttl=60, show_spinner=False)
def fetch_stock_quote(sym: str) -> dict:
    try:
        raw = yf.download(sym, period="5d", interval="1d",
                          auto_adjust=True, progress=False)
        if raw.empty:
            return {}
        raw = flatten_cols(raw)
        raw = rename_ohlcv(raw)
        closes = raw["close"].dropna()
        if len(closes) < 1:
            return {}
        price      = float(closes.iloc[-1])
        prev_close = float(closes.iloc[-2]) if len(closes) > 1 else price
        change     = price - prev_close
        pct        = (change / prev_close * 100) if prev_close else 0
        return {
            "symbol": sym, "price": price, "change": change,
            "change_pct": pct, "prev_close": prev_close,
            "high": float(raw["high"].iloc[-1]) if "high" in raw.columns else price,
            "low":  float(raw["low"].iloc[-1])  if "low"  in raw.columns else price,
            "year_high": float(closes.max()),
            "year_low":  float(closes.min()),
        }
    except Exception:
        return {}

@st.cache_data(ttl=60, show_spinner=False)
def fetch_all_quotes() -> pd.DataFrame:
    """Batch fetch all universe stocks - handles all yfinance MultiIndex formats."""
    syms  = [s[0] for s in STOCK_UNIVERSE]
    names = {s[0]: s[1] for s in STOCK_UNIVERSE}
    sects = {s[0]: s[2] for s in STOCK_UNIVERSE}
    rows  = []

    def _extract_close(raw, sym):
        """Extract close price series for a symbol from any yfinance layout."""
        if isinstance(raw.columns, pd.MultiIndex):
            lvl0 = raw.columns.get_level_values(0).tolist()
            lvl1 = raw.columns.get_level_values(1).tolist()
            # Layout A: group_by='ticker' -> (SYM, field)
            if sym in lvl0:
                sub = raw[sym]
                close_col = next((c for c in sub.columns if str(c).lower()=="close"), None)
                return sub[close_col].dropna() if close_col else pd.Series(dtype=float)
            # Layout B: default yfinance -> (field, SYM)
            close_keys = [c for c in lvl0 if str(c).lower()=="close"]
            if close_keys and sym in lvl1:
                return raw[close_keys[0]][sym].dropna()
        else:
            close_col = next((c for c in raw.columns if str(c).lower()=="close"), None)
            if close_col:
                return raw[close_col].dropna()
        return pd.Series(dtype=float)

    try:
        raw = yf.download(
            syms, period="5d", interval="1d",
            auto_adjust=True, progress=False, threads=True,
        )
        if raw.empty:
            raise ValueError("Empty batch response")

        for sym in syms:
            try:
                col = _extract_close(raw, sym)
                if len(col) < 1:
                    continue
                price      = float(col.iloc[-1])
                prev_close = float(col.iloc[-2]) if len(col) > 1 else price
                change     = price - prev_close
                pct        = (change / prev_close * 100) if prev_close else 0
                rows.append({
                    "symbol": sym, "name": names.get(sym, sym),
                    "sector": sects.get(sym, "—"),
                    "price": price, "change": change,
                    "change_pct": pct, "prev_close": prev_close,
                })
            except Exception:
                pass

    except Exception:
        # Graceful fallback: fetch one by one
        for sym in syms:
            try:
                q = fetch_stock_quote(sym)
                if q and q.get("price", 0) > 0:
                    rows.append({
                        "symbol": sym, "name": names.get(sym, sym),
                        "sector": sects.get(sym, "—"),
                        "price":      q["price"],
                        "change":     q.get("change", 0),
                        "change_pct": q.get("change_pct", 0),
                        "prev_close": q.get("prev_close", 0),
                    })
            except Exception:
                pass

    return pd.DataFrame(rows)

@st.cache_data(ttl=60, show_spinner=False)
def fetch_intraday(sym: str, interval: str = "5m") -> pd.DataFrame:
    try:
        raw = yf.download(sym, period="1d", interval=interval,
                          auto_adjust=True, progress=False)
        if raw.empty:
            return pd.DataFrame()
        # Flatten MultiIndex if present
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0] for c in raw.columns]
        raw = rename_ohlcv(raw)
        raw.index = pd.to_datetime(raw.index)
        required = {"open","high","low","close","volume"}
        if not required.issubset(set(raw.columns)):
            return pd.DataFrame()
        return raw[list(required)].dropna(subset=["open","high","low","close"])
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(sym: str, period: str = "3mo") -> pd.DataFrame:
    try:
        raw = yf.download(sym, period=period, interval="1d",
                          auto_adjust=True, progress=False)
        if raw.empty:
            return pd.DataFrame()
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0] for c in raw.columns]
        raw = rename_ohlcv(raw)
        raw.index = pd.to_datetime(raw.index)
        required = {"open","high","low","close","volume"}
        if not required.issubset(set(raw.columns)):
            return pd.DataFrame()
        return raw[list(required)].dropna(subset=["open","high","low","close"])
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_news() -> list[dict]:
    items = []
    for url, src in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:12]:
                title = e.get("title","").strip()
                if not title:
                    continue
                desc = re.sub(r"<[^>]+>", "", e.get("summary",""))[:220].strip()
                items.append({
                    "title":   title,
                    "link":    e.get("link","#"),
                    "desc":    desc,
                    "source":  src,
                    "date":    e.get("published",""),
                    "sentiment": _classify(title),
                    "impact":    _impact(title),
                })
        except Exception:
            pass
    seen, out = set(), []
    for it in items:
        k = it["title"][:38].lower()
        if k not in seen:
            seen.add(k); out.append(it)
    out.sort(key=lambda x: x["impact"], reverse=True)
    return out[:50]

def _classify(t: str) -> str:
    t = t.lower()
    if any(k in t for k in ["surge","rally","gain","rise","record","bullish","soar","jump","strong","profit","growth"]):
        return "bull"
    if any(k in t for k in ["fall","crash","drop","decline","bearish","loss","weak","slump","cut","fear"]):
        return "bear"
    return "neutral"

def _impact(t: str) -> int:
    t = t.lower()
    return sum(1 for k in ["nifty","sensex","rbi","sebi","budget","gdp","inflation","results","fii","dii","rate"] if k in t)

# ─── TECHNICAL INDICATORS ────────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df) < 5:
        return df
    df = df.copy()
    c = df["close"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    v = df["volume"].astype(float)
    n = len(df)
    try:
        from ta.momentum import RSIIndicator
        from ta.trend import EMAIndicator, SMAIndicator, MACD
        from ta.volatility import BollingerBands, AverageTrueRange
        if n >= 14:
            df["rsi"]      = RSIIndicator(c, window=14).rsi().values
        if n >= 9:
            df["ema9"]     = EMAIndicator(c, window=9).ema_indicator().values
        if n >= 21:
            df["ema21"]    = EMAIndicator(c, window=21).ema_indicator().values
        if n >= 20:
            df["sma50"]    = SMAIndicator(c, window=min(50,n)).sma_indicator().values
            df["sma200"]   = SMAIndicator(c, window=min(200,n)).sma_indicator().values
            macd_obj       = MACD(c)
            df["macd"]     = macd_obj.macd().values
            df["macd_sig"] = macd_obj.macd_signal().values
            df["macd_hist"]= macd_obj.macd_diff().values
            bb             = BollingerBands(c)
            df["bb_upper"] = bb.bollinger_hband().values
            df["bb_lower"] = bb.bollinger_lband().values
            df["bb_mid"]   = bb.bollinger_mavg().values
        if n >= 5:
            df["atr"]  = AverageTrueRange(h, l, c, window=min(14,n)).average_true_range().values
            if v.sum() > 0:
                df["vwap"] = (c * v).cumsum() / v.replace(0, np.nan).cumsum()
    except Exception:
        pass
    return df

def detect_signals(df: pd.DataFrame) -> list[dict]:
    out = []
    if df.empty or len(df) < 6:
        return out
    df = compute_indicators(df)
    for i in range(5, len(df)):
        c0 = df.iloc[i]
        c1 = df.iloc[i-1]
        ts    = df.index[i]
        price = float(c0["close"])

        def _f(row, col):
            v = row.get(col, np.nan) if hasattr(row, "get") else row[col] if col in row.index else np.nan
            try: return float(v)
            except: return np.nan

        op0,cl0,hi0,lo0 = _f(c0,"open"),_f(c0,"close"),_f(c0,"high"),_f(c0,"low")
        op1,cl1,hi1,lo1 = _f(c1,"open"),_f(c1,"close"),_f(c1,"high"),_f(c1,"low")

        # 1. Bullish Engulfing
        if cl1<op1 and cl0>op0 and cl0>op1 and op0<cl1:
            out.append({"ts":ts,"type":"BUY","pattern":"Bullish Engulfing","price":price})

        # 2. Bearish Engulfing
        if cl1>op1 and cl0<op0 and cl0<op1 and op0>cl1:
            out.append({"ts":ts,"type":"SELL","pattern":"Bearish Engulfing","price":price})

        # 3. RSI
        rsi0 = _f(c0,"rsi"); rsi1 = _f(c1,"rsi")
        if not (np.isnan(rsi0) or np.isnan(rsi1)):
            if rsi1 < 30 and rsi0 > rsi1:
                out.append({"ts":ts,"type":"BUY","pattern":"RSI Oversold Bounce","price":price})
            if rsi1 > 70 and rsi0 < rsi1:
                out.append({"ts":ts,"type":"SELL","pattern":"RSI Overbought","price":price})

        # 4. VWAP bounce
        vwap = _f(c0,"vwap")
        if not np.isnan(vwap):
            if lo1 < vwap and cl0 > vwap and cl0 > op0:
                out.append({"ts":ts,"type":"BUY","pattern":"VWAP Bounce","price":price})

        # 5. EMA crossover
        e9_0 = _f(c0,"ema9"); e21_0 = _f(c0,"ema21")
        e9_1 = _f(c1,"ema9"); e21_1 = _f(c1,"ema21")
        if not any(np.isnan(x) for x in [e9_0,e21_0,e9_1,e21_1]):
            if e9_1 < e21_1 and e9_0 > e21_0:
                out.append({"ts":ts,"type":"BUY","pattern":"EMA 9/21 Cross","price":price})
            if e9_1 > e21_1 and e9_0 < e21_0:
                out.append({"ts":ts,"type":"SELL","pattern":"EMA Death Cross","price":price})

        # 6. Volume breakout
        avg_vol = float(df["volume"].iloc[max(0,i-20):i].mean())
        if avg_vol > 0 and float(c0["volume"]) > avg_vol * 2 and cl0 > op0:
            out.append({"ts":ts,"type":"BUY","pattern":"Volume Breakout","price":price})

        # 7. Bollinger
        bbu = _f(c0,"bb_upper"); bbl = _f(c0,"bb_lower")
        if not np.isnan(bbu):
            if cl0 > bbu:
                out.append({"ts":ts,"type":"SELL","pattern":"BB Upper Break","price":price})
            if cl0 < bbl:
                out.append({"ts":ts,"type":"BUY","pattern":"BB Lower Bounce","price":price})

    # Deduplicate (1 signal per candle per type)
    seen, dedup = set(), []
    for s in out:
        k = (str(s["ts"]), s["type"])
        if k not in seen:
            seen.add(k); dedup.append(s)
    return dedup

# ─── SCREENER ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400*7, show_spinner=False)
def run_swing_screener() -> pd.DataFrame:
    return _screener("swing")

@st.cache_data(ttl=86400, show_spinner=False)
def run_intraday_screener() -> pd.DataFrame:
    return _screener("intraday")

def _screener(mode: str) -> pd.DataFrame:
    quotes = fetch_all_quotes()
    if quotes.empty:
        return pd.DataFrame()
    under1k = quotes[quotes["price"].between(1, 999)].copy()
    rows = []
    for _, row in under1k.iterrows():
        sym   = row["symbol"]
        price = float(row["price"])
        pct   = float(row.get("change_pct", 0) or 0)
        try:
            if mode == "swing":
                hist = fetch_history(sym, "3mo")
                if hist.empty or len(hist) < 10:
                    continue
                hist  = compute_indicators(hist)
                close = hist["close"].astype(float)
                rsi   = float(hist["rsi"].iloc[-1])  if "rsi"   in hist.columns and not np.isnan(hist["rsi"].iloc[-1])   else 50.0
                ma50  = float(hist["sma50"].iloc[-1]) if "sma50" in hist.columns and not np.isnan(hist["sma50"].iloc[-1]) else price
                ma200 = float(hist["sma200"].iloc[-1])if "sma200"in hist.columns and not np.isnan(hist["sma200"].iloc[-1])else price
                abv50  = price > ma50
                abv200 = price > ma200
                mom10  = (float(close.iloc[-1]) - float(close.iloc[-10])) / (float(close.iloc[-10]) + 0.01) * 100 if len(close)>10 else 0
                vol_r  = float(hist["volume"].iloc[-5:].mean()) / (float(hist["volume"].mean()) + 1)
                lo52   = float(close.min()); hi52 = float(close.max())
                from52 = (price - lo52) / (hi52 - lo52 + 0.01)
                score  = (abv50*3 + abv200*2 + (rsi<40)*3 + (40<=rsi<=60)*1
                          + (vol_r>1.2)*2 + (mom10>0)*2 + (from52<0.25)*2)
                action = "BUY" if (abv50 or rsi<40 or mom10>0) else "SELL"
                conf   = "HIGH" if score>=7 else "MEDIUM" if score>=4 else "LOW"
                sl_pct, tg_pct = (-0.06, 0.12) if action=="BUY" else (0.05, -0.10)
                parts  = []
                if abv50:       parts.append("Above 50-DMA")
                if rsi < 40:    parts.append(f"RSI oversold ({rsi:.0f})")
                if vol_r > 1.2: parts.append("Volume surge")
                if from52 <0.2: parts.append("Near 52W support")
                if not parts:   parts.append(f"Momentum {mom10:+.1f}%")
            else:
                hist = fetch_intraday(sym, "5m")
                if hist.empty or len(hist) < 10:
                    continue
                hist   = compute_indicators(hist)
                rsi    = float(hist["rsi"].iloc[-1])  if "rsi"  in hist.columns and not np.isnan(hist["rsi"].iloc[-1])  else 50.0
                vwap   = float(hist["vwap"].iloc[-1]) if "vwap" in hist.columns and not np.isnan(hist["vwap"].iloc[-1]) else price
                abv_vwap = price > vwap
                avg_v    = float(hist["volume"].iloc[:-1].mean()) if len(hist)>1 else 1
                last_v   = float(hist["volume"].iloc[-1])
                vol_r    = last_v / (avg_v + 1)
                gap      = abs(price - float(row["prev_close"])) / (float(row["prev_close"]) + 0.01) * 100
                score    = (abv_vwap*2 + (vol_r>1.5)*3 + (abs(pct)>2)*2
                            + (gap>1)*2 + (rsi<35)*2 + (rsi>65)*1)
                action   = "BUY" if (abv_vwap and pct>0) or rsi<35 else "SELL"
                conf     = "HIGH" if score>=7 else "MEDIUM" if score>=4 else "LOW"
                sl_pct, tg_pct = (-0.02, 0.03) if action=="BUY" else (0.02, -0.025)
                parts = []
                if abv_vwap:    parts.append("Above VWAP")
                if vol_r > 1.5: parts.append(f"Vol {vol_r:.1f}x avg")
                if gap > 1:     parts.append(f"Gap {gap:.1f}%")
                if abs(pct)>2:  parts.append(f"Move {pct:+.1f}%")
                if not parts:   parts.append(f"RSI {rsi:.0f}")

            sl  = price * (1 + sl_pct)
            tgt = price * (1 + tg_pct)
            rr  = round(abs(tg_pct / sl_pct), 1) if sl_pct else 1
            rows.append({
                "symbol":row["symbol"], "name":row["name"], "sector":row["sector"],
                "price":price, "change_pct":pct,
                "action":action, "conf":conf, "score":score,
                "entry":price, "sl":sl, "target":tgt, "rr":rr,
                "reason":" · ".join(parts),
            })
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("price").head(20).reset_index(drop=True)

# ─── CHART BUILDERS ──────────────────────────────────────────────────────────

def build_intraday_chart(sym: str, signals: list[dict]) -> go.Figure:
    df = fetch_intraday(sym, "5m")

    if df.empty:
        fig = go.Figure()
        fig.update_layout(**CHART_LAYOUT, height=400,
                          title=dict(text="No intraday data — market may be closed", font=dict(color="#7a9bc0")))
        return fig

    df = compute_indicators(df)

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.58, 0.21, 0.21],
        vertical_spacing=0.04,
        subplot_titles=("", "RSI (14)", "MACD"),
    )

    # ── Candlestick (no fillcolor params — they don't exist on go.Candlestick) ──
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"].astype(float),
        high=df["high"].astype(float),
        low=df["low"].astype(float),
        close=df["close"].astype(float),
        increasing=dict(line=dict(color="#00d4aa", width=1)),
        decreasing=dict(line=dict(color="#ff4d6d", width=1)),
        name="Price", showlegend=False,
    ), row=1, col=1)

    # ── VWAP ──
    if "vwap" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["vwap"].astype(float),
            line=dict(color="#f4a935", width=1.5, dash="dash"),
            name="VWAP",
        ), row=1, col=1)

    # ── EMAs ──
    for col, color, name in [("ema9","#3b8eff","EMA 9"),("ema21","#a78bfa","EMA 21")]:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col].astype(float),
                line=dict(color=color, width=1),
                name=name,
            ), row=1, col=1)

    # ── Bollinger Bands ──
    if "bb_upper" in df.columns and "bb_lower" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["bb_upper"].astype(float),
            line=dict(color="rgba(59,142,255,0.35)", width=1),
            name="BB Upper", showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["bb_lower"].astype(float),
            line=dict(color="rgba(59,142,255,0.35)", width=1),
            fill="tonexty", fillcolor="rgba(59,142,255,0.05)",
            name="BB Lower", showlegend=False,
        ), row=1, col=1)

    # ── BUY signals ──
    buys = [s for s in signals if s["type"]=="BUY"]
    if buys:
        fig.add_trace(go.Scatter(
            x=[s["ts"]  for s in buys],
            y=[s["price"]*0.997 for s in buys],
            mode="markers+text",
            marker=dict(symbol="triangle-up", size=11, color="#00d4aa"),
            text=[s["pattern"][:10] for s in buys],
            textposition="bottom center",
            textfont=dict(color="#00d4aa", size=8),
            name="BUY",
            hovertemplate="<b>BUY</b> %{text}<br>₹%{y:.2f}",
        ), row=1, col=1)

    # ── SELL signals ──
    sells = [s for s in signals if s["type"]=="SELL"]
    if sells:
        fig.add_trace(go.Scatter(
            x=[s["ts"] for s in sells],
            y=[s["price"]*1.003 for s in sells],
            mode="markers+text",
            marker=dict(symbol="triangle-down", size=11, color="#ff4d6d"),
            text=[s["pattern"][:10] for s in sells],
            textposition="top center",
            textfont=dict(color="#ff4d6d", size=8),
            name="SELL",
            hovertemplate="<b>SELL</b> %{text}<br>₹%{y:.2f}",
        ), row=1, col=1)

    # ── RSI ──
    if "rsi" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["rsi"].astype(float),
            line=dict(color="#a78bfa", width=1.5),
            name="RSI", showlegend=False,
        ), row=2, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="rgba(255,77,109,0.4)",  row=2, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="rgba(0,212,170,0.4)",   row=2, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="rgba(255,255,255,0.1)", row=2, col=1)

    # ── MACD ──
    if "macd" in df.columns and "macd_hist" in df.columns:
        hist_vals = df["macd_hist"].astype(float).fillna(0)
        bar_colors = ["rgba(0,212,170,0.7)" if v >= 0 else "rgba(255,77,109,0.7)"
                      for v in hist_vals]
        fig.add_trace(go.Bar(
            x=df.index, y=hist_vals,
            marker_color=bar_colors, name="Histogram", showlegend=False,
        ), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["macd"].astype(float),
            line=dict(color="#3b8eff", width=1.2),
            name="MACD", showlegend=False,
        ), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["macd_sig"].astype(float),
            line=dict(color="#f4a935", width=1.2),
            name="Signal", showlegend=False,
        ), row=3, col=1)

    fig.update_layout(**CHART_LAYOUT, height=560)
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#4e6a8a")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#4e6a8a")
    fig.update_layout(xaxis_rangeslider_visible=False)
    return fig

def build_swing_chart(sym: str) -> go.Figure:
    df = fetch_history(sym, "3mo")
    if df.empty:
        fig = go.Figure()
        fig.update_layout(**CHART_LAYOUT, height=400,
                          title=dict(text="No data available", font=dict(color="#7a9bc0")))
        return fig

    df = compute_indicators(df)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.7, 0.3], vertical_spacing=0.05)

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"].astype(float),
        high=df["high"].astype(float),
        low=df["low"].astype(float),
        close=df["close"].astype(float),
        increasing=dict(line=dict(color="#00d4aa", width=1)),
        decreasing=dict(line=dict(color="#ff4d6d", width=1)),
        name="Price", showlegend=False,
    ), row=1, col=1)

    for col, color, name in [
        ("sma50","#3b8eff","50 DMA"),
        ("sma200","#a78bfa","200 DMA"),
        ("ema9","#f4a935","EMA 9"),
    ]:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col].astype(float),
                line=dict(color=color, width=1.3), name=name,
            ), row=1, col=1)

    if "bb_upper" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_upper"].astype(float),
            line=dict(color="rgba(59,142,255,0.35)",width=1), name="BB Upper", showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_lower"].astype(float),
            line=dict(color="rgba(59,142,255,0.35)",width=1),
            fill="tonexty", fillcolor="rgba(59,142,255,0.05)",
            name="BB Lower", showlegend=False), row=1, col=1)

    if "rsi" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["rsi"].astype(float),
            line=dict(color="#a78bfa",width=1.5), name="RSI", showlegend=False), row=2, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="rgba(255,77,109,0.4)", row=2, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="rgba(0,212,170,0.4)",  row=2, col=1)

    fig.update_layout(**CHART_LAYOUT, height=500)
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#4e6a8a")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#4e6a8a")
    fig.update_layout(xaxis_rangeslider_visible=False)
    return fig

# ─── UI COMPONENTS ────────────────────────────────────────────────────────────

def render_header():
    open_ = is_market_open()
    now   = datetime.now(IST).strftime("%d %b %Y · %H:%M IST")
    badge = ('<span class="mkt-open">● LIVE · NSE/BSE</span>'
             if open_ else '<span class="mkt-closed">● MARKET CLOSED</span>')
    st.markdown(f"""
    <div class="hdr">
      <div style="display:flex;align-items:center;gap:10px">
        <div style="width:32px;height:32px;background:#00d4aa;border-radius:8px;
             display:flex;align-items:center;justify-content:center;
             font-family:'Syne',sans-serif;font-size:12px;font-weight:800;color:#07090f">TG</div>
        <span class="logo">Trading<span>Genie</span> AI</span>
      </div>
      <div style="display:flex;align-items:center;gap:14px">
        {badge}
        <span style="font-family:'DM Mono',monospace;font-size:10px;color:#4e6a8a">{now}</span>
      </div>
    </div>""", unsafe_allow_html=True)

def render_index_cards(indices: list[dict]):
    if not indices:
        st.info("Fetching index data…")
        return
    cols = st.columns(len(indices))
    for col, idx in zip(cols, indices):
        pct = _scalar(idx.get("change_pct"))
        chg = _scalar(idx.get("change"))
        price = _scalar(idx.get("price"))
        up  = (pct or 0) >= 0
        cls = "up" if up else "dn"
        col_hex = "#00d4aa" if up else "#ff4d6d"
        arrow   = "▲" if up else "▼"
        pct_str = f"{arrow} {abs(pct):.2f}%" if pct is not None else "—"
        chg_str = f"({chg:+.2f})"          if chg is not None else ""
        price_str = f"{price:,.2f}"         if price is not None else "—"
        with col:
            st.markdown(f"""
            <div class="idx-card {cls}">
              <div class="idx-label">{idx['label']}</div>
              <div class="idx-price" style="color:{col_hex}">{price_str}</div>
              <div class="idx-chg"  style="color:{col_hex}">{pct_str} {chg_str}</div>
            </div>""", unsafe_allow_html=True)

def render_technicals(nifty: dict):
    if not nifty:
        st.info("No Nifty data.")
        return
    p   = _scalar(nifty.get("price"))
    pct = _scalar(nifty.get("change_pct"))
    h   = _scalar(nifty.get("high"))
    l   = _scalar(nifty.get("low"))
    pc  = _scalar(nifty.get("prev_close"))
    yh  = _scalar(nifty.get("year_high"))
    yl  = _scalar(nifty.get("year_low"))
    bias_cls  = "tbull" if (pct or 0)>=0 else "tbear"
    bias_txt  = "BULLISH" if (pct or 0)>=0 else "BEARISH"
    rows = [
        ("Last Price",  fp(p),  ""),
        ("Day Change",  fpc(pct), f'<span class="tbadge {bias_cls}">{bias_txt}</span>'),
        ("Day High",    fp(h),  ""),
        ("Day Low",     fp(l),  ""),
        ("Prev Close",  fp(pc), ""),
        ("52W High",    fp(yh), ""),
        ("52W Low",     fp(yl), ""),
    ]
    html = '<div class="tech-block">'
    for lbl, val, badge in rows:
        html += f'<div class="tr"><span class="tl">{lbl}</span><span class="tv">{val}</span>{badge}</div>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

def render_news_card(item: dict):
    s = item["sentiment"]
    cls   = {"bull":"bull","bear":"bear","neutral":"neu"}.get(s,"neu")
    label = {"bull":"BULLISH","bear":"BEARISH","neutral":"NEUTRAL"}.get(s,"NEUTRAL")
    imp   = ('<span class="nb hi">🔥 HIGH IMPACT</span> '
             if item.get("impact",0) >= 2 else "")
    link  = item.get("link","#")
    read  = (f'<a href="{link}" target="_blank" style="color:#3b8eff;font-size:9px;float:right;text-decoration:none">↗ Read</a>'
             if link != "#" else "")
    st.markdown(f"""
    <div class="nc">
      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
        <span class="nb {cls}">{label}</span>{imp}
        <span style="margin-left:auto;font-family:'DM Mono',monospace;font-size:9px;
              color:#4e6a8a;font-style:italic">{item.get('source','')}</span>
        {read}
      </div>
      <div class="nt">{item['title']}</div>
      <div class="nm">{time_ago(item.get('date',''))}</div>
    </div>""", unsafe_allow_html=True)

def render_screener_card(row, idx: int):
    buy    = row["action"] == "BUY"
    cls    = "buy" if buy else "sell"
    sig_c  = "sig-buy" if buy else "sig-sell"
    conf   = row.get("conf","LOW")
    cc_map = {"HIGH":"#00d4aa","MEDIUM":"#f4a935","LOW":"#7a9bc0"}
    c_col  = cc_map.get(conf,"#7a9bc0")
    pct    = float(row.get("change_pct",0) or 0)
    pct_c  = "#00d4aa" if pct>=0 else "#ff4d6d"
    st.markdown(f"""
    <div class="sc-card {cls}">
      <div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap">
        <span style="font-family:'Syne',sans-serif;font-size:14px;font-weight:800;color:#dde8f8">
          #{idx+1} {row['symbol'].replace('.NS','')}
        </span>
        <span class="{sig_c}">{row['action']}</span>
        <span style="font-family:'DM Mono',monospace;font-size:8px;padding:2px 6px;border-radius:3px;
              background:rgba(255,255,255,.05);color:{c_col};border:1px solid {c_col}44">{conf}</span>
        <span style="margin-left:auto;font-family:'DM Mono',monospace;font-size:13px;
              font-weight:700;color:#dde8f8">{fp(row['price'])}</span>
        <span style="font-family:'DM Mono',monospace;font-size:10px;color:{pct_c}">{fpc(pct)}</span>
      </div>
      <div style="font-size:10px;color:#7a9bc0;margin:3px 0">{row['name']} · {row['sector']}</div>
      <div class="lvg">
        <div class="lv"><div class="ll">Entry</div><div class="lv2" style="color:#dde8f8">{fp(row['entry'])}</div></div>
        <div class="lv"><div class="ll">Stop Loss</div><div class="lv2" style="color:#ff4d6d">{fp(row['sl'])}</div></div>
        <div class="lv"><div class="ll">Target</div><div class="lv2" style="color:#00d4aa">{fp(row['target'])}</div></div>
      </div>
      <div style="font-size:10px;color:#7a9bc0;margin-top:7px;border-top:1px solid rgba(255,255,255,.07);padding-top:5px">
        📊 {row['reason']}
      </div>
    </div>""", unsafe_allow_html=True)

# ─── TABS ────────────────────────────────────────────────────────────────────

def tab_home():
    with st.container():
        st.markdown('<div style="padding:1rem 1.5rem">', unsafe_allow_html=True)

        # Market closed banner
        if not is_market_open():
            st.markdown("""
            <div style="background:rgba(255,77,109,.08);border:1px solid rgba(255,77,109,.2);
                 border-radius:8px;padding:7px 14px;margin-bottom:.75rem;
                 font-family:'DM Mono',monospace;font-size:11px;color:#ff4d6d">
              🔴  MARKET CLOSED — Showing last available data.
              NSE/BSE trading hours: Mon–Fri 9:15 AM – 3:30 PM IST
            </div>""", unsafe_allow_html=True)

        hc, hr = st.columns([5,1])
        with hc:
            st.markdown('<div class="sec">Market Indices</div>', unsafe_allow_html=True)
        with hr:
            if st.button("⟳ Refresh", key="h_rf"):
                st.cache_data.clear(); st.rerun()

        with st.spinner("Loading indices…"):
            indices = fetch_indices()
        render_index_cards(indices)

        left, right = st.columns([1, 2], gap="medium")

        with left:
            st.markdown('<div class="sec">Nifty 50 · Technicals</div>', unsafe_allow_html=True)
            nifty = next((i for i in indices if i["symbol"]=="^NSEI"), None)
            render_technicals(nifty)

            st.markdown('<div class="sec">Institutional Flows</div>', unsafe_allow_html=True)
            f1,f2,f3 = st.columns(3)
            with f1: st.metric("FII Net","₹672 Cr","Net Buyers")
            with f2: st.metric("DII Net","₹410 Cr","Net Buyers")
            with f3: st.metric("India VIX","13.40","↓ Low")

        with right:
            st.markdown('<div class="sec">Market News — sorted by impact</div>',
                        unsafe_allow_html=True)
            with st.spinner("Fetching news…"):
                news = fetch_news()

            PAGE = 10
            pages = max(1, (len(news) + PAGE - 1) // PAGE)
            pg = st.session_state.get("news_pg", 0)

            # Page tabs
            pg_cols = st.columns(pages)
            for i, pc in enumerate(pg_cols):
                with pc:
                    if st.button(f"Page {i+1}", key=f"np_{i}",
                                 type="primary" if i==pg else "secondary"):
                        st.session_state["news_pg"] = i; st.rerun()

            for item in news[pg*PAGE:(pg+1)*PAGE]:
                render_news_card(item)

        st.markdown("</div>", unsafe_allow_html=True)

def tab_screener():
    with st.container():
        st.markdown('<div style="padding:1rem 1.5rem">', unsafe_allow_html=True)
        st.markdown("""
        <div class="disc">⚠️ <strong style="color:#ff4d6d">Advisory:</strong>
        AI-assisted signals for <strong>educational purposes only</strong>. Not investment advice.
        Consult a SEBI-registered advisor before trading.</div>
        """, unsafe_allow_html=True)
        st.markdown('<div style="height:.75rem"></div>', unsafe_allow_html=True)

        st1, st2 = st.tabs(["📈  Swing  (Weekly refresh)", "⚡  Intraday  (Daily refresh)"])

        for mode, tab in [("swing",st1),("intraday",st2)]:
            with tab:
                ic, irf = st.columns([4,1])
                with ic:
                    label = "7 days" if mode=="swing" else "24 hours"
                    st.markdown(
                        f'<div class="sec">Top 20 · Under ₹1,000 · Price ↑ · Refreshes every {label}</div>',
                        unsafe_allow_html=True)
                with irf:
                    if st.button("⟳ Rescan", key=f"rs_{mode}"):
                        (run_swing_screener if mode=="swing" else run_intraday_screener).clear()
                        st.rerun()

                with st.spinner(f"Running {mode} screener…"):
                    df = run_swing_screener() if mode=="swing" else run_intraday_screener()

                if df.empty:
                    st.warning("Screener is loading data. Market data may not be available yet. Try Force Rescan.")
                    st.markdown("</div>", unsafe_allow_html=True)
                    return

                # Summary metrics
                m1,m2,m3,m4 = st.columns(4)
                buys = len(df[df["action"]=="BUY"])
                sells= len(df[df["action"]=="SELL"])
                hi   = len(df[df["conf"]=="HIGH"])
                with m1: st.metric("Total",  len(df))
                with m2: st.metric("BUY",    buys,  delta=f"+{buys}")
                with m3: st.metric("SELL",   sells, delta=f"-{sells}", delta_color="inverse")
                with m4: st.metric("High Conf", hi)

                # Filter
                filt = st.session_state.get(f"filt_{mode}", "ALL")
                fa,fb,fc = st.columns([1,1,4])
                with fa:
                    if st.button("All",      key=f"fa_{mode}"): st.session_state[f"filt_{mode}"]="ALL";  filt="ALL"
                with fb:
                    if st.button("BUY only", key=f"fb_{mode}"): st.session_state[f"filt_{mode}"]="BUY";  filt="BUY"

                filtered = df if filt=="ALL" else df[df["action"]==filt]

                col_l, col_r = st.columns(2, gap="small")
                for i, (_, row) in enumerate(filtered.iterrows()):
                    with (col_l if i%2==0 else col_r):
                        render_screener_card(row, i)

        st.markdown("</div>", unsafe_allow_html=True)

def tab_charts():
    with st.container():
        st.markdown('<div style="padding:1rem 1.5rem">', unsafe_allow_html=True)

        options = [f"{s[0].replace('.NS','')} — {s[1]}" for s in STOCK_UNIVERSE]
        c1,c2,c3 = st.columns([3,1,1])
        with c1:
            sel = st.selectbox("Stock", options, label_visibility="collapsed", key="ch_sel")
        with c2:
            mode = st.selectbox("Mode", ["Intraday (5m)","Swing (Daily)"],
                                label_visibility="collapsed", key="ch_mode")
        with c3:
            if st.button("⟳ Refresh Chart", key="ch_rf"):
                fetch_intraday.clear(); fetch_history.clear(); st.rerun()

        sym_short = sel.split(" — ")[0]
        sym = sym_short + ".NS"
        meta = next((s for s in STOCK_UNIVERSE if s[0]==sym), None)
        name = meta[1] if meta else sym_short
        sec  = meta[2] if meta else ""

        with st.spinner("Loading quote…"):
            q = fetch_stock_quote(sym)

        # Quote bar
        if q:
            pct   = _scalar(q.get("change_pct"))
            up    = (pct or 0) >= 0
            arrow = "▲" if up else "▼"
            col_h = "#00d4aa" if up else "#ff4d6d"
            qa,qb,qc,qd,qe,qf = st.columns([3,1,1,1,1,1])
            with qa:
                st.markdown(f"""
                <div style="padding:.4rem 0">
                  <div style="font-family:'Syne',sans-serif;font-size:1.3rem;
                       font-weight:800;color:#dde8f8">{sym_short}</div>
                  <div style="font-size:10px;color:#7a9bc0;margin-top:2px">{name} · {sec}</div>
                </div>""", unsafe_allow_html=True)
            with qb: st.metric("LTP",       fp(q.get("price")),
                                f"{arrow} {fpc(pct)}")
            with qc: st.metric("Day High",  fp(q.get("high")))
            with qd: st.metric("Day Low",   fp(q.get("low")))
            with qe: st.metric("Prev Close",fp(q.get("prev_close")))
            with qf: st.metric("52W High",  fp(q.get("year_high")))

        is_intraday = "Intraday" in mode

        if is_intraday:
            with st.spinner(f"Loading intraday chart for {sym_short}…"):
                df_raw = fetch_intraday(sym, "5m")
                if not df_raw.empty:
                    df_ind = compute_indicators(df_raw)
                    sigs   = detect_signals(df_ind)
                else:
                    df_ind = pd.DataFrame()
                    sigs   = []
            fig = build_intraday_chart(sym, sigs)
            st.plotly_chart(fig, width='stretch')

            if sigs:
                buys  = [s for s in sigs if s["type"]=="BUY"]
                sells = [s for s in sigs if s["type"]=="SELL"]
                last  = sigs[-1]
                lc    = "#00d4aa" if last["type"]=="BUY" else "#ff4d6d"
                sa,sb,sc_ = st.columns(3)
                with sa:
                    st.markdown(f"""
                    <div style="background:rgba(0,212,170,.08);border:1px solid rgba(0,212,170,.2);
                         border-radius:10px;padding:12px;text-align:center">
                      <div style="font-family:'DM Mono',monospace;font-size:9px;color:#7a9bc0">BUY SIGNALS</div>
                      <div style="font-family:'Syne',sans-serif;font-size:2rem;font-weight:800;
                           color:#00d4aa">{len(buys)}</div>
                    </div>""", unsafe_allow_html=True)
                with sb:
                    st.markdown(f"""
                    <div style="background:rgba(255,77,109,.08);border:1px solid rgba(255,77,109,.2);
                         border-radius:10px;padding:12px;text-align:center">
                      <div style="font-family:'DM Mono',monospace;font-size:9px;color:#7a9bc0">SELL SIGNALS</div>
                      <div style="font-family:'Syne',sans-serif;font-size:2rem;font-weight:800;
                           color:#ff4d6d">{len(sells)}</div>
                    </div>""", unsafe_allow_html=True)
                with sc_:
                    st.markdown(f"""
                    <div style="background:#111827;border:1px solid rgba(255,255,255,.08);
                         border-radius:10px;padding:12px">
                      <div style="font-family:'DM Mono',monospace;font-size:9px;color:#7a9bc0">LATEST SIGNAL</div>
                      <div style="font-family:'Syne',sans-serif;font-size:1rem;font-weight:800;
                           color:{lc};margin-top:4px">{last['type']} · {last['pattern']}</div>
                      <div style="font-family:'DM Mono',monospace;font-size:11px;color:#7a9bc0">
                        @ {fp(last['price'])}</div>
                    </div>""", unsafe_allow_html=True)

                # Signal log
                st.markdown('<div class="sec" style="margin-top:.8rem">Signal Log (last 15)</div>',
                            unsafe_allow_html=True)
                sig_rows = [{"Time":s["ts"].strftime("%H:%M") if hasattr(s["ts"],"strftime") else str(s["ts"]),
                              "Signal":s["type"],"Pattern":s["pattern"],"Price":fp(s["price"])}
                            for s in sigs[-15:]][::-1]
                st.dataframe(pd.DataFrame(sig_rows), width='stretch', hide_index=True)

            elif not df_raw.empty:
                st.info("No signals detected in today's data. Market may be pre-open or data is insufficient for pattern detection.")
            else:
                st.warning("No intraday data available. This may be a pre-market hour or the symbol has no data today.")

            # Live indicator bar
            if not df_ind.empty and len(df_ind) >= 5:
                st.markdown('<div class="sec" style="margin-top:.5rem">Live Indicators</div>',
                            unsafe_allow_html=True)
                last_row = df_ind.iloc[-1]
                i1,i2,i3,i4,i5 = st.columns(5)
                def safe_ind(r, col):
                    v = r.get(col, np.nan) if hasattr(r,"get") else r[col] if col in r.index else np.nan
                    try: return round(float(v),2)
                    except: return None

                with i1: st.metric("RSI (14)", safe_ind(last_row,"rsi") or "—")
                with i2: st.metric("VWAP",     fp(safe_ind(last_row,"vwap")))
                with i3: st.metric("EMA 9",    fp(safe_ind(last_row,"ema9")))
                with i4: st.metric("EMA 21",   fp(safe_ind(last_row,"ema21")))
                with i5: st.metric("ATR",      safe_ind(last_row,"atr") or "—")

        else:  # Swing chart
            with st.spinner(f"Loading daily chart for {sym_short}…"):
                fig = build_swing_chart(sym)
            st.plotly_chart(fig, width='stretch')

            df_s = fetch_history(sym, "3mo")
            if not df_s.empty:
                df_s = compute_indicators(df_s)
                last = df_s.iloc[-1]
                st.markdown('<div class="sec">Key Technical Levels</div>', unsafe_allow_html=True)
                l1,l2,l3,l4,l5,l6 = st.columns(6)
                def gl(col):
                    v = last.get(col) if hasattr(last,"get") else (last[col] if col in last.index else None)
                    return fp(_scalar(v))
                def gr(col):
                    v = last.get(col) if hasattr(last,"get") else (last[col] if col in last.index else None)
                    r = _scalar(v)
                    return f"{r:.1f}" if r is not None else "—"

                with l1: st.metric("50-Day MA",   gl("sma50"))
                with l2: st.metric("200-Day MA",  gl("sma200"))
                with l3: st.metric("EMA 9",       gl("ema9"))
                with l4: st.metric("BB Upper",    gl("bb_upper"))
                with l5: st.metric("BB Lower",    gl("bb_lower"))
                with l6: st.metric("RSI (14)",    gr("rsi"))

        st.markdown("</div>", unsafe_allow_html=True)

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    if "news_pg" not in st.session_state:
        st.session_state["news_pg"] = 0

    render_header()

    t1, t2, t3 = st.tabs(["📊  Home", "🔍  Screener", "📈  Charts"])
    with t1: tab_home()
    with t2: tab_screener()
    with t3: tab_charts()

if __name__ == "__main__":
    main()
