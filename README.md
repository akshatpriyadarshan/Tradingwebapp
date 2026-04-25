# BharatTrade AI — Streamlit Trading Assistant

> Live NSE/BSE market data · AI Screener · Charts with Buy/Sell Signals · Financial News

---

## 🚀 Run Locally (3 commands)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
streamlit run app.py

# App opens at http://localhost:8501
```

---

## ☁️ Deploy to Streamlit Cloud (Free)

### Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/bharattrade-ai.git
git push -u origin main
```

### Step 2 — Deploy on Streamlit Cloud
1. Go to **https://share.streamlit.io**
2. Sign in with GitHub
3. Click **"New app"**
4. Select your repository → `app.py` as main file
5. Click **Deploy**

Done — your app is live at `https://YOUR_APP.streamlit.app`

---

## 📁 File Structure

```
trading_genie_streamlit/
├── app.py                   ← Complete self-contained app (single file)
├── requirements.txt         ← All Python dependencies
├── .streamlit/
│   └── config.toml          ← Dark theme + server config
└── README.md
```

---

## 📊 Features

### 🏠 Home Tab
- **Live market indices**: Nifty 50, Sensex, Bank Nifty, Nifty IT, Nifty Midcap
- **Market Open/Closed** banner (IST timezone aware, Mon–Fri 9:15–15:30)
- **Technicals panel**: Price, Change, Day High/Low, 52W High/Low, Prev Close, MA status
- **FII/DII activity** cards
- **50 curated news articles** from 5 RSS feeds, sorted by market impact, paginated into 5 pages of 10

### 🔍 Screener Tab
- **Swing mode** (weekly cache): 20 stocks under ₹1,000 with entry/SL/target
  - Scores: 50-DMA trend, 200-DMA trend, RSI oversold bounce, volume surge, 52W low proximity
- **Intraday mode** (daily cache): 20 stocks under ₹1,000 for same-day trading
  - Scores: VWAP position, volume ratio, gap plays, RSI extremes
- BUY/SELL/All filter buttons
- Each card shows: Symbol, Action, Confidence, Entry, Stop Loss, Target, Reason

### 📈 Charts Tab
- **40 stocks** available via dropdown selector
- **Intraday mode** (5-min candles):
  - Candlestick + VWAP + EMA9/21 + Bollinger Bands
  - **RSI** subplot
  - **MACD** subplot
  - Auto-detected **BUY/SELL signals** plotted on chart:
    - Bullish/Bearish Engulfing
    - RSI Oversold Bounce / Overbought
    - VWAP Bounce
    - EMA 9/21 Crossover / Death Cross
    - Volume Breakout (2× average)
    - Bollinger Band Upper/Lower Break
  - Signal log table with time, pattern, price
  - Live indicators: RSI, VWAP, EMA9, EMA21, ATR
- **Swing mode** (daily candles):
  - Candlestick + 50-DMA + 200-DMA + EMA9 + Bollinger Bands
  - RSI subplot
  - Key levels table

---

## 📡 Data Sources (All Free)

| Data | Source | Delay |
|------|--------|-------|
| Stock prices, indices, OHLCV | `yfinance` (Yahoo Finance) | ~15 min |
| Intraday 5-min candles | `yfinance` period=1d, interval=5m | ~15 min |
| Daily candles (swing) | `yfinance` period=3mo, interval=1d | ~15 min |
| Financial news (50 articles) | `feedparser` from 5 RSS feeds | Real-time |
| Technical indicators | `ta` library (pure Python) | Computed live |

### News RSS Feeds
- Economic Times Markets
- MoneyControl
- Business Standard
- NDTV Profit
- LiveMint

---

## ♻️ Cache Strategy

| Data | Cache TTL | Reason |
|------|-----------|--------|
| Indices & quotes | 60 seconds | Near-real-time |
| Intraday candles | 60 seconds | Refreshes each minute |
| Swing history (3mo daily) | 5 minutes | Rarely changes |
| News | 1 hour | RSS feeds update hourly |
| Swing screener results | 7 days | Weekly re-evaluation |
| Intraday screener results | 24 hours | Daily re-evaluation |

---

## 🔧 Technical Indicators Used

| Indicator | Library | Usage |
|-----------|---------|-------|
| RSI (14) | `ta.momentum` | Overbought/oversold signals |
| EMA 9, 21 | `ta.trend` | Trend + crossover signals |
| SMA 50, 200 | `ta.trend` | Swing trend filter |
| MACD | `ta.trend` | Momentum confirmation |
| Bollinger Bands | `ta.volatility` | Squeeze/breakout signals |
| ATR | `ta.volatility` | Volatility measure |
| VWAP | `ta.volume` | Intraday mean price reference |

---

## ⚙️ Signal Detection Patterns

| Pattern | Type | Condition |
|---------|------|-----------|
| Bullish Engulfing | BUY | Current green candle fully engulfs prior red |
| Bearish Engulfing | SELL | Current red candle fully engulfs prior green |
| RSI Oversold Bounce | BUY | RSI was <30, now rising |
| RSI Overbought | SELL | RSI was >70, now falling |
| VWAP Bounce | BUY | Price crossed above VWAP with green candle |
| EMA 9/21 Crossover | BUY | EMA9 crosses above EMA21 |
| EMA Death Cross | SELL | EMA9 crosses below EMA21 |
| Volume Breakout | BUY | Volume > 2× 20-period average + green candle |
| BB Lower Bounce | BUY | Close below lower Bollinger Band |
| BB Upper Break | SELL | Close above upper Bollinger Band |

---

## ⚠️ Disclaimer

For educational purposes only. Not investment advice. All signals are algorithmically generated from technical analysis and carry risk. Consult a SEBI-registered investment advisor before making any trading decisions. Past performance does not guarantee future results.
