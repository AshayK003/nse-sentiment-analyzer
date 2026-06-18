<div align="center">

# 📊 NSE Stock Sentiment Analyzer

Enter any NSE ticker & get live price + multi-source weighted sentiment + technical indicators in one dashboard.

[![Streamlit](https://img.shields.io/badge/Built%20with-Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/AshayK003/nse-sentiment-analyzer?style=flat&logo=github)](https://github.com/AshayK003/nse-sentiment-analyzer)
[![Open Source](https://img.shields.io/badge/Open%20Source-❤️-red)](https://github.com/AshayK003/nse-sentiment-analyzer)
[![UI: Dark Theme](https://img.shields.io/badge/UI-Dark%20Theme-13151a?logo=css3&logoColor=white)](https://github.com/AshayK003/nse-sentiment-analyzer)

<p align="center">
  <b>🇮🇳 India-focused</b> &nbsp;·&nbsp; <b>🆓 No API costs</b> &nbsp;·&nbsp; <b>🔌 No API keys</b> &nbsp;·&nbsp; <b>📡 Live data</b>
</p>

</div>

---

## ✨ Features

- **Live price data** — Current price, day change %, day range, volume, PE ratio for any NSE stock or ETF
- **Multi-source news** — Fetches from Google News + Moneycontrol + Economic Times + LiveMint + NDTV Profit RSS feeds (DuckDuckGo fallback)
- **Reddit community chatter** — Local-only source via `rdt-cli`, brings retail conversation into the signal
- **Source-weighted scoring** — Each source has a confidence weight (1.0 ET → 0.4 Reddit). Blended score = weighted average across sources
- **VADER + Financial Lexicon** — 38 domain-specific financial terms tuned for Indian markets
- **BUY / HOLD / CAUTION signal** — Weighted across sources, with per-source breakdown in the UI
|- **Technical indicators** — RSI(14), SMA 50/200 trend, MACD histogram. Works with 26+ days of data (newer stocks still get RSI + MACD).
- **News source health** — See which sources returned results at a glance
- **Clickable news links** — Every headline opens the original article
- **Headline breakdown** — See exactly which news is driving sentiment positive or negative
- **Portfolio mode** — Add stocks to a watchlist and scan all at once
- **Track record** — Rate signals as accurate/wrong and track your accuracy over time
- **Dark-themed UI** — Premium dark theme with card-based layout, sentiment badges, and responsive design
- **Loading states** — Visual feedback during data fetches so you're never staring at a blank screen
- **No API keys** — Works out of the box, zero configuration
- **Free & open-source** — MIT license, self-host or use the hosted version

---

## 🚀 Hosted Version

**Want to use it without touching a terminal?**

👉 **[Launch NSE Sentiment Analyzer](https://nse-sentiment-analyzer.streamlit.app)**

One click, zero setup. ₹199 one-time on [Gumroad](https://gumroad.com). No subscription, no API keys, no terminal.

> **Note:** The hosted version runs RSS-based sources only. Reddit is a local-only source (requires `rdt-cli` auth).

---

## 🛠️ How It Works

```
You type "RELIANCE"
        ↓
 yfinance → Live price, PE, volume, 52W range, 1yr history
        ↓
 RSS Feeds → Google News + Moneycontrol + ET + LiveMint + NDTV Profit
        ↓
 DuckDuckGo → Fallback when RSS returns < 3 articles
        ↓
 Reddit (local) → rdt-cli search for community chatter (⚡ badge in UI)
        ↓
 VADER + Financial Lexicon → Per-headline sentiment scores (38 finance terms)
        ↓
 Source-Weighted Blending → ET(1.0) + MC(0.9) + LM(0.8) + NDTV(0.7) + Google(0.6) + DDG(0.5) + Reddit(0.4)
        ↓
 yfinance 1yr history → RSI, SMA 50/200, MACD
        ↓
 Dashboard → Weighted signal + source breakdown + sentiment distribution + technicals
```

### Source Weighting Logic

Each news source has a **confidence weight** based on editorial reliability:

| Source | Weight | Type | Available on Cloud |
|--------|--------|------|--------------------|
| Economic Times | 1.0 | RSS | ✅ |
| Moneycontrol | 0.9 | RSS | ✅ |
| LiveMint | 0.8 | RSS | ✅ |
| NDTV Profit | 0.7 | RSS | ✅ |
| Google News | 0.6 | RSS | ✅ |
| DuckDuckGo | 0.5 | Web search (fallback) | ✅ |
| Reddit | 0.4 | CLI (`rdt-cli`) | ❌ Local only |

The **blended score** is a weighted average:
```
Blended = Σ(source_weight × source_avg_compound) / Σ(source_weight)
```

The final signal (BULLISH/NEUTRAL/BEARISH) is determined from the blended score, with per-source breakdown shown in the UI.

---

## 📦 Local Quick Start

```bash
# Clone the repo
git clone https://github.com/AshayK003/nse-sentiment-analyzer.git
cd nse-sentiment-analyzer

# Install dependencies (Python 3.11+)
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

Open **http://localhost:8501** in your browser and start analyzing.

### Local-Only Features

The following features require CLI tools on your machine and are **not available** on the hosted Streamlit Cloud version:

- **Reddit** — Requires `rdt-cli` with Reddit auth cookies. Install: `uv tool install rdt-cli && rdt login`
- **Twitter/X** — Architecture-ready. Install `twitter-cli` and set `TWITTER_AUTH_TOKEN` + `TWITTER_CT0` env vars.

These sources show a ⚡ badge in the UI when active on your local setup.

---

## 🧰 Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **UI** | [Streamlit](https://streamlit.io) + custom CSS dark theme | Card-based layout, skeleton loading, source badges, responsive breakpoints |
| **Market Data** | [yfinance](https://github.com/ranaroussi/yfinance) | Free Yahoo Finance API (`.NS` suffix for NSE) |
| **News (RSS)** | [feedparser](https://github.com/kurtmckee/feedparser) | Google News + Moneycontrol + ET + LiveMint + NDTV Profit |
| **News (fallback)** | [duckduckgo_search](https://github.com/deedy5/duckduckgo_search) | Used when RSS returns < 3 articles |
| **Reddit** | [rdt-cli](https://github.com/rdt-cli/rdt-cli) | Local-only, community sentiment via CLI |
| **Sentiment** | [VADER](https://github.com/cjhutto/vaderSentiment) + custom financial lexicon (38 terms) | Domain-tuned for Indian market terminology |
| **Scoring** | Source-weighted average | Per-source confidence blending |
| **Indicators** | [pandas](https://pandas.pydata.org) rolling/EWM | RSI(14), SMA 50/200, MACD(12,26,9) from 1yr history |
| **Hosting** | [Streamlit Community Cloud](https://streamlit.io/cloud) | Free deploy from GitHub |

**Zero API key costs.** Everything uses free/public data sources.

---

## 📋 Supported Tickers

100+ NSE-listed equities and ETFs built into the selector. Any other NSE ticker can be typed in the custom input.

**Nifty 50:** RELIANCE, HDFCBANK, TCS, INFY, ICICIBANK, SBIN, BHARTIARTL, ITC, LT, AXISBANK, BAJFINANCE, WIPRO, TITAN, MARUTI, HINDUNILVR, TATAMOTORS, TATASTEEL, ADANIENT, M&M, TATAPOWER, HINDALCO, BEL, and more.

**Banks & Finance:** KOTAKBANK, INDUSINDBK, BANKBARODA, PNB, YESBANK, IDFCFIRSTB, PFC, RECLTD, BAJAJFINSV, SBILIFE, HDFCLIFE

**Pharma:** SUNPHARMA, DIVISLAB, CIPLA, DRREDDY, TORNTPHARM, APOLLOHOSP, LUPIN, BIOCON

**Tech:** INFY, WIPRO, HCLTECH, TECHM, LTIM, DIXON

**Consumption:** ITC, NESTLEIND, DMART, BRITANNIA, DABUR, MARICO, GODREJCP, VBL, JUBLFOOD, TATACONSUM

**Auto:** MARUTI, TATAMOTORS, BAJAJ-AUTO, EICHERMOT, HEROMOTOCO, TVSMOTOR

**Infra & Industrials:** LT, ULTRACEMCO, GRASIM, ABB, SIEMENS, POLYCAB, PIDILITIND, HAVELLS, ASTRAL

**Energy:** ONGC, COALINDIA, IOC, BPCL, ADANIPOWER, ADANIGREEN, ADANITRANS, NHPC

**Special Situations:** IRFC, RVNL, IRCTC, IEX, DLF, INDIGO, HAL

**ETFs:** NIFTYBEES, GOLDBEES, NEXT50IETF, MIDCAPETF, MODEFENCE, MAKEINDIA, ENERGY, METALETF

**Custom:** Type any NSE ticker not in the list (e.g., NYKAA, ZOMATO, PWL, GROWW)

---

## ❤️ Support the Project

If you find this useful:

<div align="center">
  <a href="https://chai4.me/darkcharon3301">
    <img src="https://chai4.me/icons/wordmark.png" alt="Support on Chai4Me" height="36"/>
  </a>
  <br/>
  <a href="https://gumroad.com">Buy the hosted version →</a>
</div>

---

## 🤝 Contributing

- **Issues:** Found a bug? Open an issue.
- **PRs:** Feature ideas, better lexicon, UI improvements — all welcome.
- **Tickers:** Know a missing NSE stock? Send a PR to update `NSE_TICKERS` in `data_fetcher.py`.
- **New sources:** Add a fetcher function in `data_fetcher.py`, register its weight in `sentiment.py:SOURCE_WEIGHTS`, and it slots into the pipeline automatically.

---

## 📜 License

MIT © [Ashay Kushwaha](https://github.com/AshayK003)

---

<div align="center">
  <sub>Built by <a href="https://x.com/sentinelcipher">@sentinelcipher</a></sub>
  <br/>
  <sub>⚠️ Not financial advice. Always do your own research.</sub>
</div>
