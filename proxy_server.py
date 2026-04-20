"""
BharatTrade AI — Local NSE Proxy Server (v2)
=============================================
Fetches REAL-TIME prices from NSE India with automatic Yahoo fallback.
No API key needed. Uses 5-second cache + automatic retry.

SETUP (one-time):
  pip install flask flask-cors requests

RUN:
  python proxy_server.py

Then in the trading dashboard:
  - Click ⚙ Config
  - Select "NSE Proxy (local server, real-time)"
  - Proxy URL: http://localhost:8000
  - Save & Connect
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import threading
import json

app = Flask(__name__)
CORS(app)

# ── Session with retry strategy ──────────────────────────────────
def create_session():
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=['GET']
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount('http://', adapter)
    s.mount('https://', adapter)
    
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.nseindia.com/',
        'Connection': 'keep-alive',
    })
    return s

session = create_session()
quote_cache = {}
cache_time = {}
CACHE_TTL = 5  # 5 second cache

def refresh_nse_session():
    """Visit NSE to establish fresh session/cookies."""
    try:
        print('[NSE] Refreshing session…')
        session.get('https://www.nseindia.com', timeout=10)
        time.sleep(0.5)
    except Exception as e:
        print(f'[NSE] Session refresh failed: {e}')

refresh_nse_session()

def session_refresher():
    while True:
        time.sleep(1800)  # refresh every 30 min
        refresh_nse_session()

threading.Thread(target=session_refresher, daemon=True).start()

# ── Fallback: Yahoo Finance (faster, delayed but reliable) ──────
def fetch_from_yahoo(symbol: str) -> dict | None:
    """Fallback to Yahoo Finance if NSE fails."""
    try:
        url = f'https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}.NS&fields=regularMarketPrice,regularMarketChange,regularMarketChangePercent,regularMarketPreviousClose,fiftyTwoWeekHigh,fiftyTwoWeekLow'
        r = requests.get(url, timeout=6)
        if r.status_code == 200:
            data = r.json().get('quoteResponse', {}).get('result', [{}])[0]
            if data.get('regularMarketPrice'):
                result = {
                    'symbol': symbol + '.NS',
                    'shortName': symbol,
                    'regularMarketPrice': data.get('regularMarketPrice'),
                    'regularMarketChange': data.get('regularMarketChange', 0),
                    'regularMarketChangePercent': data.get('regularMarketChangePercent', 0),
                    'regularMarketPreviousClose': data.get('regularMarketPreviousClose', 0),
                    'fiftyTwoWeekHigh': data.get('fiftyTwoWeekHigh', 0),
                    'fiftyTwoWeekLow': data.get('fiftyTwoWeekLow', 0),
                    'regularMarketVolume': 0,
                    '_source': 'Yahoo (delayed ~15min)',
                }
                print(f'[Yahoo] {symbol} ✓')
                return result
    except Exception as e:
        print(f'[Yahoo] Error: {str(e)[:50]}')
    return None

# ── Primary: NSE India Quote API ─────────────────────────────────
def fetch_nse_quote(symbol: str) -> dict | None:
    """Fetch from NSE quote API with proper error handling."""
    sym_clean = symbol.replace('.NS', '').upper()
    
    # Check cache
    if sym_clean in quote_cache and time.time() - cache_time.get(sym_clean, 0) < CACHE_TTL:
        return quote_cache[sym_clean]
    
    url = f'https://www.nseindia.com/api/quote-equity?symbol={sym_clean}'
    
    for attempt in range(2):
        try:
            r = session.get(url, timeout=8)
            
            if r.status_code == 401 or r.status_code == 403:
                print(f'[NSE] {r.status_code} for {sym_clean}, refreshing session…')
                refresh_nse_session()
                time.sleep(0.3)
                continue
            
            if r.status_code != 200:
                print(f'[NSE] {r.status_code} for {sym_clean}')
                continue
            
            # Try parsing JSON
            data = r.json()
            if not data or 'priceInfo' not in data:
                print(f'[NSE] Empty response for {sym_clean}')
                continue
            
            pi = data.get('priceInfo', {})
            whl = pi.get('weekHighLow', {})
            info = data.get('info', {})
            mdo = data.get('marketDeptOrderBook', {})
            ti = mdo.get('tradeInfo', {}) if mdo else {}
            
            # Validate we have a price
            if not pi.get('lastPrice'):
                print(f'[NSE] No price in response for {sym_clean}')
                continue
            
            result = {
                'symbol': sym_clean + '.NS',
                'shortName': info.get('companyName', sym_clean),
                'regularMarketPrice': pi.get('lastPrice', 0),
                'regularMarketChange': pi.get('change', 0),
                'regularMarketChangePercent': pi.get('pChange', 0),
                'regularMarketPreviousClose': pi.get('previousClose', 0),
                'regularMarketOpen': pi.get('open', 0),
                'regularMarketDayHigh': pi.get('intraDayHighLow', {}).get('max', 0),
                'regularMarketDayLow': pi.get('intraDayHighLow', {}).get('min', 0),
                'fiftyTwoWeekHigh': whl.get('max', 0),
                'fiftyTwoWeekLow': whl.get('min', 0),
                'regularMarketVolume': ti.get('totalTradedVolume', 0),
                '_source': 'NSE (real-time)',
            }
            
            # Cache it
            quote_cache[sym_clean] = result
            cache_time[sym_clean] = time.time()
            print(f'[NSE] {sym_clean} ✓ ₹{result["regularMarketPrice"]}')
            return result
        
        except json.JSONDecodeError as e:
            print(f'[NSE] JSON error for {sym_clean}: {str(e)[:40]}')
            refresh_nse_session()
        except Exception as e:
            print(f'[NSE] Error for {sym_clean}: {str(e)[:50]}')
        
        time.sleep(0.2)
    
    # All NSE attempts failed — fallback to Yahoo
    print(f'[NSE] Fallback to Yahoo for {sym_clean}')
    return fetch_from_yahoo(sym_clean)

# ── Index quote ───────────────────────────────────────────────────
INDEX_SYMBOL_MAP = {
    '^NSEI':    'NIFTY 50',
    '^BSESN':   'SENSEX',
    '^NSEBANK': 'NIFTY BANK',
    '^CNXIT':   'NIFTY IT',
}

def fetch_index_quote(yf_symbol: str) -> dict | None:
    """Fetch index quote."""
    nse_name = INDEX_SYMBOL_MAP.get(yf_symbol)
    if not nse_name:
        return None
    
    try:
        url = 'https://www.nseindia.com/api/allIndices'
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            indices = r.json().get('data', [])
            for idx in indices:
                if idx.get('index') == nse_name:
                    prev = idx.get('previousClose', idx.get('last', 1))
                    last = idx.get('last', 0)
                    chg = idx.get('variation', 0)
                    pct = (chg / prev * 100) if prev else idx.get('percentChange', 0)
                    
                    print(f'[NSE] {yf_symbol} ✓')
                    return {
                        'symbol': yf_symbol,
                        'shortName': nse_name,
                        'regularMarketPrice': last,
                        'regularMarketChange': chg,
                        'regularMarketChangePercent': pct,
                        'regularMarketPreviousClose': prev,
                        'fiftyTwoWeekHigh': idx.get('yearHigh', 0),
                        'fiftyTwoWeekLow': idx.get('yearLow', 0),
                        'regularMarketVolume': 0,
                        '_source': 'NSE (real-time)',
                    }
    except Exception as e:
        print(f'[NSE] Index error {yf_symbol}: {e}')
    
    # Yahoo fallback for indices
    try:
        r = requests.get(
            f'https://query1.finance.yahoo.com/v7/finance/quote?symbols={yf_symbol}&fields=regularMarketPrice,regularMarketChange,regularMarketChangePercent,regularMarketPreviousClose',
            timeout=6
        )
        if r.status_code == 200:
            data = r.json().get('quoteResponse', {}).get('result', [{}])[0]
            if data.get('regularMarketPrice'):
                print(f'[Yahoo] {yf_symbol} ✓')
                return {
                    'symbol': yf_symbol,
                    'shortName': INDEX_SYMBOL_MAP.get(yf_symbol, yf_symbol),
                    'regularMarketPrice': data.get('regularMarketPrice'),
                    'regularMarketChange': data.get('regularMarketChange', 0),
                    'regularMarketChangePercent': data.get('regularMarketChangePercent', 0),
                    'regularMarketPreviousClose': data.get('regularMarketPreviousClose', 0),
                    'regularMarketVolume': 0,
                    '_source': 'Yahoo (delayed)',
                }
    except:
        pass
    
    return None


# ── Routes ────────────────────────────────────────────────────────
@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'source': 'NSE India + Yahoo fallback',
        'time': time.strftime('%H:%M:%S IST'),
        'cached_symbols': len(quote_cache)
    })


@app.route('/quotes')
def get_quotes():
    """GET /quotes?symbols=SUZLON,PNB,CANBK,^NSEI,^BSESN"""
    raw = request.args.get('symbols', '')
    symbols = [s.strip() for s in raw.split(',') if s.strip()]

    results = []
    for sym in symbols:
        if sym.startswith('^'):
            q = fetch_index_quote(sym)
        else:
            clean = sym.replace('.NS', '').replace('.BO', '')
            q = fetch_nse_quote(clean)
        
        if q:
            results.append(q)
        
        time.sleep(0.1)

    return jsonify(results)


@app.route('/screener/under100')
def screener_under100():
    """GET /screener/under100?limit=15"""
    limit = int(request.args.get('limit', 15))
    
    candidate_symbols = [
        'YESBANK', 'PNB', 'CANBK', 'IDFCFIRSTB', 'SUZLON', 'SAIL', 'IRFC', 'NHPC', 
        'RECLTD', 'BANKBARODA', 'ONGC', 'IOC', 'POWERGRID', 'NTPC', 'COALINDIA',
        'TRIDENT', 'HFCL', 'VEDL', 'BEL', 'BHEL', 'ASHOKLEY', 'BIOCON', 'CGPOWER'
    ]
    
    results = []
    for sym in candidate_symbols[:limit+5]:
        q = fetch_nse_quote(sym)
        if q and 0 < q.get('regularMarketPrice', 999) < 100:
            results.append({
                'symbol': sym,
                'name': q.get('shortName', sym),
                'price': q.get('regularMarketPrice', 0),
                'change': q.get('regularMarketChange', 0),
                'pchange': q.get('regularMarketChangePercent', 0),
                'volume': q.get('regularMarketVolume', 0),
            })
        time.sleep(0.05)
    
    results.sort(key=lambda x: x.get('volume', 0), reverse=True)
    return jsonify(results[:limit])


if __name__ == '__main__':
    print('=' * 70)
    print('  BharatTrade AI — NSE Proxy Server (v2)')
    print('  Real-time prices from NSE India + Yahoo fallback')
    print('  Running on http://localhost:8000')
    print('=' * 70)
    print()
    print('  Endpoints:')
    print('    /health                         — server status')
    print('    /quotes?symbols=SUZLON,PNB      — fetch stock quotes')
    print('    /screener/under100?limit=15     — stocks under ₹100')
    print()
    print('  Dashboard: ⚙ Config → NSE Proxy → http://localhost:8000 → Save')
    print()
    print('  If NSE API fails, Yahoo fallback activates automatically (~15 min delay)')
    print()
    
    try:
        app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)
    except OSError as e:
        if 'Address already in use' in str(e):
            print('❌ Port 8000 in use. Kill existing process or use port 8001')
        else:
            print(f'Error: {e}')
