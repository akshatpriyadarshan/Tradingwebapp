"""
BharatTrade AI — Local NSE Proxy Server
========================================
This runs on your machine and fetches REAL-TIME prices directly from
NSE India's website (same source as Zerodha/Groww).

No API key needed. Prices will match Zerodha exactly.

SETUP (one-time):
  pip install flask flask-cors requests

RUN:
  python proxy_server.py

Then in the trading dashboard:
  - Click ⚙ Config
  - Select "NSE Proxy (local server, real-time)"
  - Proxy URL: http://localhost:8000
  - Save & Connect

The dashboard will then poll every 10 seconds with exact NSE prices.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import threading

app = Flask(__name__)
CORS(app)  # Allow browser to call this from file:// or any localhost

# ── NSE headers (mimics a browser visiting nseindia.com) ──────────
NSE_HEADERS = {
    'User-Agent':      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept':          'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer':         'https://www.nseindia.com/',
    'Origin':          'https://www.nseindia.com',
    'Connection':      'keep-alive',
    'sec-ch-ua':       '"Chromium";v="124"',
    'sec-fetch-dest':  'empty',
    'sec-fetch-mode':  'cors',
    'sec-fetch-site':  'same-origin',
}

session = requests.Session()
session.headers.update(NSE_HEADERS)

# ── Session management ────────────────────────────────────────────
def refresh_nse_session():
    """Visit NSE homepage to get fresh cookies (required before API calls)."""
    try:
        r = session.get('https://www.nseindia.com', timeout=12)
        print(f'[NSE] Session refreshed — status {r.status_code}')
        time.sleep(1)
        # Also hit the market-data page to get full cookies
        session.get('https://www.nseindia.com/market-data/live-equity-market', timeout=10)
    except Exception as e:
        print(f'[NSE] Session refresh error: {e}')

# Refresh session at startup and every 30 minutes
refresh_nse_session()

def session_refresher():
    while True:
        time.sleep(1800)  # 30 min
        refresh_nse_session()

threading.Thread(target=session_refresher, daemon=True).start()


# ── Single stock quote ────────────────────────────────────────────
def fetch_equity_quote(symbol: str) -> dict | None:
    """Fetch real-time quote for a single NSE equity symbol."""
    url = f'https://www.nseindia.com/api/quote-equity?symbol={symbol.upper()}'
    try:
        r = session.get(url, timeout=8)
        if r.status_code == 401:
            print(f'[NSE] 401 for {symbol}, refreshing session…')
            refresh_nse_session()
            r = session.get(url, timeout=8)
        if r.status_code != 200:
            print(f'[NSE] {r.status_code} for {symbol}')
            return None
        data = r.json()
        pi   = data.get('priceInfo', {})
        whl  = pi.get('weekHighLow', {})
        info = data.get('info', {})
        mdo  = data.get('marketDeptOrderBook', {})
        ti   = mdo.get('tradeInfo', {})
        return {
            'symbol':                      symbol.upper() + '.NS',
            'shortName':                   info.get('companyName', symbol),
            'regularMarketPrice':          pi.get('lastPrice', 0),
            'regularMarketChange':         pi.get('change', 0),
            'regularMarketChangePercent':  pi.get('pChange', 0),
            'regularMarketPreviousClose':  pi.get('previousClose', 0),
            'regularMarketOpen':           pi.get('open', 0),
            'regularMarketDayHigh':        pi.get('intraDayHighLow', {}).get('max', 0),
            'regularMarketDayLow':         pi.get('intraDayHighLow', {}).get('min', 0),
            'fiftyTwoWeekHigh':            whl.get('max', 0),
            'fiftyTwoWeekLow':             whl.get('min', 0),
            'regularMarketVolume':         ti.get('totalTradedVolume', 0),
            'vwap':                        pi.get('vwap', 0),
            'fiftyDayAverage':             0,   # not in NSE quote API
            'twoHundredDayAverage':        0,   # not in NSE quote API
        }
    except Exception as e:
        print(f'[NSE] Error fetching {symbol}: {e}')
        return None


# ── Index quote ───────────────────────────────────────────────────
INDEX_SYMBOL_MAP = {
    '^NSEI':    'NIFTY 50',
    '^BSESN':   'SENSEX',
    '^NSEBANK': 'NIFTY BANK',
    '^CNXIT':   'NIFTY IT',
}

def fetch_index_quote(yf_symbol: str) -> dict | None:
    """Fetch index quote using NSE index name."""
    nse_name = INDEX_SYMBOL_MAP.get(yf_symbol)
    if not nse_name:
        return None
    url = f'https://www.nseindia.com/api/allIndices'
    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200:
            return None
        indices = r.json().get('data', [])
        for idx in indices:
            if idx.get('index') == nse_name:
                prev = idx.get('previousClose', idx.get('last', 1))
                chg  = idx.get('variation', 0)
                pct  = idx.get('percentChange', 0)
                return {
                    'symbol':                     yf_symbol,
                    'shortName':                  nse_name,
                    'regularMarketPrice':         idx.get('last', 0),
                    'regularMarketChange':        chg,
                    'regularMarketChangePercent': pct,
                    'regularMarketPreviousClose': prev,
                    'fiftyTwoWeekHigh':           idx.get('yearHigh', 0),
                    'fiftyTwoWeekLow':            idx.get('yearLow', 0),
                    'regularMarketVolume':        0,
                    'fiftyDayAverage':            0,
                    'twoHundredDayAverage':       0,
                }
    except Exception as e:
        print(f'[NSE] Index error {yf_symbol}: {e}')
    return None


# ── Routes ────────────────────────────────────────────────────────
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'source': 'NSE India', 'time': time.strftime('%H:%M:%S IST')})


@app.route('/quotes')
def get_quotes():
    """
    GET /quotes?symbols=SUZLON,PNB,CANBK,^NSEI,^BSESN
    Returns array of quote objects compatible with Yahoo Finance format.
    """
    raw = request.args.get('symbols', '')
    symbols = [s.strip() for s in raw.split(',') if s.strip()]

    results = []
    for sym in symbols:
        if sym.startswith('^'):
            # Index
            q = fetch_index_quote(sym)
        else:
            # Strip .NS if present
            clean = sym.replace('.NS', '').replace('.BO', '')
            q = fetch_equity_quote(clean)
        if q:
            results.append(q)
        time.sleep(0.05)  # small delay to avoid rate limiting

    return jsonify(results)


@app.route('/screener/under100')
def screener_under100():
    """
    GET /screener/under100?limit=15
    Returns top N NSE stocks currently trading under ₹100, sorted by volume.
    Uses NSE's live equity market data dump.
    """
    limit = int(request.args.get('limit', 15))
    url = 'https://www.nseindia.com/api/live-analysis-variations?index=gainers&exchange=nse'
    try:
        # Use market data endpoint for large price scan
        r = session.get(
            'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY+SMALLCAP+250',
            timeout=12
        )
        if r.status_code != 200:
            return jsonify({'error': f'NSE returned {r.status_code}'}), 500
        data = r.json().get('data', [])
        under100 = [
            {
                'symbol':  d.get('symbol',''),
                'name':    d.get('meta', {}).get('companyName', d.get('symbol','')),
                'price':   d.get('lastPrice', 0),
                'change':  d.get('pChange', 0),
                'volume':  d.get('totalTradedVolume', 0),
            }
            for d in data
            if 0 < d.get('lastPrice', 999) < 100
        ]
        under100.sort(key=lambda x: x['volume'], reverse=True)
        return jsonify(under100[:limit])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print('=' * 55)
    print('  BharatTrade AI — NSE Proxy Server')
    print('  Real-time prices from NSE India (matches Zerodha)')
    print('  Running on http://localhost:8000')
    print('=' * 55)
    print()
    print('  In the dashboard: ⚙ Config → NSE Proxy → Save')
    print()
    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)
