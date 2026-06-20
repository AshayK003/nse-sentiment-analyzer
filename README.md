<div align="center">

# 📊 NSE Stock Sentiment Analyzer

**Multi-source sentiment + technical indicators for NSE equities & ETFs, in one dashboard.**

[![Streamlit](https://img.shields.io/badge/Built%20with-Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
| [![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
| [![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
| [![GitHub Stars](https://img.shields.io/github/stars/AshayK003/nse-sentiment-analyzer?style=flat&logo=github)](https://github.com/AshayK003/nse-sentiment-analyzer)
[![Tests](https://img.shields.io/badge/tests-143%20passing-brightgreen)](#-testing)
| [![UI: Dark Theme](https://img.shields.io/badge/UI-Dark%20Theme-13151a?logo=css3&logoColor=white)](https://nse-sentiment-analyzer.streamlit.app)
|
|<p align="center">
|  <b>🇮🇳 India-focused</b> &nbsp;·&nbsp; <b>🆓 Zero API costs</b> &nbsp;·&nbsp; <b>🔌 No API keys required</b> &nbsp;·&nbsp; <b>📡 Live data</b>
|</p>

</div>

---

## Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [What's New](#-whats-new)
- [Features](#-features)
- [Quick Start](#-quick-start)
- [Environment Variables](#-environment-variables)
- [Local Development](#-local-development)
- [Testing](#-testing)
- [Deployment](#-deployment)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)

---

## 📋 Overview

Enter any NSE ticker and get:

- **Live market data** — price, change %, volume, PE ratio via Yahoo Finance
- **Multi-source news sentiment** — RSS feeds from Moneycontrol, Economic Times, LiveMint, NDTV Profit, Google News, with DuckDuckGo fallback
- **Event-aware scoring** — headlines classified by event type (earnings, order wins, litigation, regulatory, buybacks, etc.) with signed sentiment bias. Catches what VADER misses—"SEBI penalty" is correctly scored as negative
- **SmartScore composite (0–100)** — combines recency-weighted EWMA (36h half-life), event-adjusted sentiment, headline breadth, and news volume into a single score
- **Source-weighted scoring** — each source has a confidence weight that **self-calibrates via Bayesian learning** from your votes
- **Optional FinBERT engine** — toggle `USE_FINBERT=true` to replace VADER + event rules with a financial-domain transformer model for +15-20% accuracy on financial text
- **Technical indicators** — RSI(14), SMA crossover (50/200), MACD from 1-year history
- **Portfolio mode** — scan multiple tickers at once with a single run
- **Track record** — vote on signal accuracy and track precision over time

All data sources are **free and public**. No API keys required.

---

## 🏗️ Architecture

### Module Dependency Map

```
app.py ───────────────────── (entry point, Streamlit UI)
  │
  ├── render.py ──────────── (HTML/CSS dashboard template via st.components)
  │
  ├── sentiment.py ───────── (VADER + financial lexicon, source-weighted scoring)
  │     ├── event_classifier.py ── (30 event types — used in VADER mode only)
  │     ├── get_finbert()    ── (optional: FinBERT transformer, USE_FINBERT=true)
  │     └── get_source_weights() ── (Bayesian calibration from track record votes)
  │
  ├── aggregate_sentiment.py ── (SmartScore 0–100: EWMA recency, breadth,
  │                               volume, event-weighted components)
  │
  ├── data_fetcher.py ────── (stock info, RSS news, DuckDuckGo, Reddit)
  │     ├── yfinance        → stock price, info, 1yr history
  │     ├── feedparser      → RSS from 5 financial sources
  │     ├── duckduckgo_search → fallback when RSS < 3 articles
  │     └── requests        → Reddit OAuth API (cloud-compatible)
  │
  ├── indicators.py ──────── (RSI, SMA crossover, MACD from OHLCV history)
  │
  ├── market_data.py ─────── (FII/DII flow data, optional)
  │
  └── persistence.py ─────── (JSON-based portfolio, track record, cache +
                               CSV-based sentiment history for SmartScore)
                               └── Added: Bayesian source accuracy (source_accuracy.json)
```

### Data Flow

```
Ticker Input
    │
    ▼
┌───────────────────────────────────────────────────────────────────┐
│  analyze_ticker(ticker, company)                                  │
│                                                                   │
│  ┌─────────────┐   ┌──────────┐   ┌─────────────┐                │
│  │ get_stock_   │   │ search_  │   │ get_techni- │                │
│  │ info()       │   │ news()   │   │ cal_indica- │                │
│  │ • yfinance   │   │ • 5 RSS  │   │ tors()      │                │
│  │ • 1yr hist   │   │ • DDG    │   │ • RSI(14)   │                │
│  │              │   │ • Reddit │   │ • SMA 50/200│                │
│  └──────┬──────┘   └────┬─────┘   │ • MACD      │                │
│         │               │         └──────┬───────┘                │
│         ▼               ▼                ▼                        │
│  ┌─────────────────────────────────────────────────────┐          │
│  │ sentiment.py: source-weighted blending               │          │
│  │                                                      │          │
│  │ ┌─ VADER mode (default) ──────────────────────────┐ │          │
│  │ │ VADER + 38-term financial lexicon               │ │          │
│  │ │   └── event_classifier.py: classify headline    │ │          │
│  │ │        → adjust_with_event() blends VADER+event │ │          │
│  │ └─────────────────────────────────────────────────┘ │          │
│  │                                                      │          │
│  │ ┌─ FinBERT mode (USE_FINBERT=true) ──────────────┐ │          │
│  │ │ ProsusAI/finbert transformer                    │ │          │
│  │ │   → compound = pos_score − neg_score            │ │          │
│  │ │   → 15-20% accuracy gain on financial text      │ │          │
│  │ └─────────────────────────────────────────────────┘ │          │
│  │                                                      │          │
│  │ Source weights self-calibrate via Bayesian learning  │          │
│  │ from 👍/👎 votes (Beta(α,β) per source)              │          │
│  │                                                      │          │
│  │ aggregate_sentiment.py: SmartScore composite (0–100) │          │
│  │   ├── S_recency: EWMA, half-life 36h                │          │
│  │   ├── S_events:  event-adjusted sentiment            │          │
│  │   ├── S_breadth: (pos − neg) / total                 │          │
│  │   └── S_volume:  log(news count)                     │          │
│  │                                                      │          │
│  │ → BULLISH / NEUTRAL / BEARISH + SmartScore          │          │
│  └─────────────────────┬───────────────────────────────┘          │
│                        │                                          │
└────────────────────────┼──────────────────────────────────────────┘
                         │
                         ▼
         ┌───────────────────────────────────┐
         │       render_dashboard()          │
         │   Dark-themed HTML + SmartScore   │
         │   number + component bars +       │
         │   trend sparkline                 │
         └───────────────────────────────────┘
```

### Source Weights

Each news source carries a confidence weight for the blended scoring.
**Weights self-calibrate via Bayesian learning** — when you vote 👍/👎 on a signal, every source that contributed to that signal gets an alpha (correct) or beta (wrong) increment. Weight = `α/(α+β)` — the posterior mean of a Beta distribution.

| Source | Weight | Type | Available on Cloud |
|--------|--------|------|--------------------|
| Economic Times | Learned | RSS | ✅ |
| Moneycontrol | Learned | RSS | ✅ |
| LiveMint | Learned | RSS | ✅ |
| NDTV Profit | Learned | RSS | ✅ |
| Google News | Learned | RSS | ✅ |
| DuckDuckGo | Learned | Web search (fallback) | ✅ |
| Reddit * | Learned | OAuth API | ✅ |

*Starts at hand-tuned priors, converges to your actual source accuracy over ~10-50 votes. Source weights persist across sessions.*

*Reddit requires OAuth env vars (`REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`). Falls back with learned weight if not set up.*

The **blended score** is:
```
blended = Σ(source_weight × source_avg_compound) / Σ(source_weight)
```

---

## 🆕 What's New

### v2.3.0 — VWAP, pivot levels, India VIX (June 2026)

**VWAP + Deviation** — Every analysis now shows a VWAP badge beneath the price: green *"🔺 VWAP: ₹101.33 (+0.66% above)"* or red *"🔻 VWAP: ₹101.33 (−1.20% below)"*. Fetches 5-min intraday data for the day. Price above VWAP = bullish intraday bias, below = bearish. Deviation % tells you if momentum is exhausted.

**Pivot Levels** — R1, Pivot, and S1 levels computed from yesterday's high/low/close using the classic formula `P=(H+L+C)/3`, `R1=2P−L`, `S1=2P−H`. Displayed as a compact 3-column grid inside the Technical Indicators card. Know your intraday entry/exit levels without switching to a charting app.

**India VIX in Sidebar** — VIX level, daily change, and volatility bucket (Low/Medium/High) shown in the sidebar, fetched once per session. Caption tells you what the level means: *"⚠️ High VIX (>20) — sharp reversals likely"* or *"✅ Low VIX (<15) — trending markets favored"*.

**13 new tests** — Full TDD: RED → GREEN before implementation. 143 total.

### v2.2.2 — Smarter trend, clearer portfolio sidebar (June 2026)

**SmartScore trend accuracy improved** — The SmartScore now accounts for event-adjusted headline signals (earnings, deals, regulatory actions) when measuring market breadth. The composite trend number and component bars are more reliable when event-heavy news is in play.

**Sidebar portfolio UX redesigned** — Clearer section labels, current price shown inline with every holding, and a heatmap legend so you know what each colour means at a glance.

**Sidebar ticker names fixed** — Bold ticker names in the portfolio list were rendering as `**RELIANCE**` due to a markdown rendering bug. Now showing correctly as **RELIANCE**.

### v2.2.1 — Leaner code, cleaner Reddit setup (June 2026)

**App loads faster** — Removed unused code paths and consolidated duplicate configuration. Smaller codebase means less to maintain.

**Reddit: no more local CLI setup** — Removed the `rdt-cli` fallback. Reddit now works exclusively through OAuth (the cloud-friendly path). If you have OAuth env vars set, Reddit posts show up; if not, they're skipped — no extra tools needed.

**Volume spike detection now active** — The volume spike badges on portfolio holdings were always computed but never shown. Now they're live.

**Bug fix: Sentiment history CSV** — The `neg_count` column in exported CSVs was mislabelled (stored neutral count instead of negatives). Exports now correctly label negative headline counts.

### v2.2.0 — Investonks-inspired: P&amp;L tracking, heatmap, news badges, volume spike detection (June 2026)

**Four new features inspired by competitor analysis (investonks.com):**

**P&amp;L from Entry** — Add entry price when adding a stock to your portfolio. The sidebar shows live P&amp;L (₹ and %) for every holding, green for profit, red for loss.

**Market Heatmap** — Compact 3-column grid in the sidebar showing every portfolio ticker color-coded by daily % change. At-a-glance portfolio health.

**Portfolio News Badges** — News headlines that mention a stock you hold get a 📌 In portfolio badge. You never miss news that affects your money.

**Volume Spike Detection** — Flags holdings trading at abnormal volume (N× their 20-day average). Early warning for accumulation/distribution.

**18 new tests** — TDD workflow: RED → GREEN before any implementation.

**Bug fix** — Trend sparkline now shows a flat line + dot for single data points instead of rendering blank. Users see their SmartScore on first analysis.

### v2.1.3 — Phase 0 moats: Shareable links, changelog, history archive (June 2026)

**Shareable Sentiment Snapshot Links** — Every ticker now has a public URL (`?ticker=RELIANCE`). Send the link on Telegram/WhatsApp/X — recipients see a teaser card with SmartScore, signal, and price, with a "Buy ₹499" CTA to unlock the full analysis.

**Public changelog** — CHANGELOG.md + sidebar expander so users can see what's new.

**Historical Sentiment Archive** — Sentiment History expander in every dashboard: line chart + CSV export. After 6 months of daily usage, this becomes the largest free NSE sentiment time series.

**Legal disclaimer** — Expanded ⚠️ Disclaimer expander covering not financial advice, no SEBI registration, data accuracy, no liability, past performance, and use-at-your-own-risk. Footer strengthened with explicit SEBI-registered advisor consultation warning.

- 119 tests passing (+10 new: public teaser, changelog, history CSV export)

### v2.1.2 — Bug fix: ETF NaN prices + audit pass (June 2026)

**Critical bug fix:** ETFs (NIFTYBEES, GOLDBEES, MIDCAPETF, etc.) showed `₹nan` and `nan%` for price/change/day-range. Root cause: yfinance returns `NaN` for ETF price fields, and `float('nan')` is truthy in Python, so `or` fallbacks and `isinstance(val, float)` checks both passed NaN through to the renderer.

- Added `_nf()` NaN-safe extractor in `data_fetcher.py:get_stock_info()` — returns `None` for NaN on all price fields
- Added `_is_valid_num()` in `render.py` — rejects NaN/Inf in `fmt_price`, `fmt_delta`, `fmt_vol`, `fmt_large`, PE ratio, and HTML template ternary
- Added `test_stock_info_nan_prices_from_etf` regression test (simulates yfinance returning NaN for all ETF fields)
- Consolidated `from math import sqrt` → `import math` in render.py (eliminates redundant local import)
- 109 tests passing (108 → 109 with new regression test)

### v2.1.1 — Audit cleanup: -22 lines, responsive layout, dynamic iframe height (June 2026)

**Ponytail audit findings applied:**
- Removed duplicate emoji-to-SVG mapping (`_emoji_to_icon`), now using `get_signal_icon()` throughout — eliminates a maintenance drift point
- Collapsed 15-line if/elif sentiment class chain into a 7-line dict lookup
- Moved lazy `import os` / `import math` / `import random` to module-level — fewer per-call allocations
- Removed 6 redundant `str()` wrappers in `save_sentiment_history()` — CSV writer handles conversion natively
- All 108 tests still pass — zero regressions

**UX improvements:**
- Dashboard iframe height now uses a properly measured formula (`2200 + n_news*120`, capped at 6000) — each section measured in pixels from rendered CSS. The auto-height postMessage script refines after load as a secondary adjustment
- Added mobile-responsive CSS breakpoints — buttons and inputs scale on screens under 640px

### v2.1 — Moat Build: 504 Aliases, 18 Event Types, Bayesian Benchmark UI (June 2026)

**Alias Map: 72 → 504 entries.** Every major NSE stock now has 2-3 common name/abbreviation aliases. Headline matching recall is dramatically higher — \"HUL\", \"L&T\", \"SBI CARD\", \"JINDAL STAINLESS\", \"RBI\", \"SEBI\", \"CBI\" all map to the right ticker. Organised by sector with regulatory body coverage spanning 18 Indian agencies (ED, CBI, NCLT, SAT, RERA, NPCI, DGFT, FSSAI, CCI, SFIO, DRI, PERDA, etc.).

**Event Classifier: 13 → 18 event types.**
- New positive: `RATING_UPGRADE` (credit upgrades), `JV_MOU` (joint ventures, MoUs, strategic partnerships), `FUNDRAISE` (QIP, FPO, rights issue)
- New negative: `CONTRACT_LOSS` (lost/terminated orders), `DIVESTMENT` (promoter stake sale, exit)
- Enhanced LITIGATION: SFIO, DRI, NIA, asset freeze, director disqualification
- Enhanced REGULATORY: PERDA/PFRDA, RERA, NCLT/NCLAT, SAT, DGCA, TRAI, CERC, DGFT, FSSAI

**Bayesian Calibration now visible in the dashboard.** The Source Calibration card shows per-source Beta(α,β) distributions with accuracy %, total votes, and a 95% credibility interval. Users can see which sources earn their trust — Economic Times vs Moneycontrol vs LiveMint — all tuned by your 👍/👎 votes. This is the first published Beta-benchmark for Indian financial news source accuracy.

**NSE_TICKERS: 85 → 270 stocks.** Full Nifty 200+ coverage plus sector depth in banking, IT, pharma, auto, FMCG, energy, metals, cement, capital goods, chemicals, infra, media, logistics, and textiles.

**Other improvements:**
- Event classifier ~80 lines richer with LITIGATION + REGULATORY body coverage
- All 109 tests pass — zero regressions from expansion
- Ticker alias matching now covers 504 common name forms and 20+ regulatory agencies

### v2.0 — Bayesian Calibration + Optional FinBERT (June 2026)

**Source weights now learn from your votes.** The old hand-tuned weights (ET=1.0, MC=0.9, ...) were guesses. Every time you vote 👍/👎 on a signal, the app updates a Beta distribution for each source that contributed. Weight = `α/(α+β)` — the posterior mean. After ~10-50 votes, your source weights converge to your actual accuracy experience.

**FinBERT transformer support** — set `USE_FINBERT=true` to replace VADER + event rules with `ProsusAI/finbert`, a financial-domain transformer. Delivers 15-20% better accuracy on financial text. Falls back gracefully if dependencies aren't available. Feature-gated — VADER mode is unchanged by default.

**Other improvements:**
- Yahoo Finance retries now use 5-shot with AWS-style jitter + suffix fallback (`.NS` → `.BO` → bare)
- Stock info and history are decoupled — if metadata fetch fails, price data still loads
- Cache entries with partial metadata expire in 2 min instead of 15 (next retry comes sooner)
- Technical indicators fall back through `.BO` suffix
- All 108 tests pass
- **Lucide SVGs** — All UI indicators migrated from Unicode emojis to inline Lucide SVGs (source badges, SMA indicators, news icons) for sharper rendering and consistency
- **Housekeeping** — Removed dead `format_large_num` / `_is_numeric` functions (−21 lines)

---

## ✨ Features

- **Live price data** — Current price, day change %, day range, volume, PE ratio for any NSE stock or ETF
- **Multi-source news** — Google News + Moneycontrol + Economic Times + LiveMint + NDTV Profit RSS feeds (DuckDuckGo fallback)
- **Reddit community chatter** — OAuth API (requires `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`). Brings retail conversation into the sentiment pipeline
- **Event-aware classification** — Headlines automatically tagged by event type: earnings beats/misses, order wins, litigation, regulatory actions, buybacks/dividends, debt stress, management changes, product launches, guidance changes, expansion, rating upgrades, joint ventures, fundraises, contract losses, divestments. Each event type carries a signed sentiment bias that corrects VADER's blind spots
- **SmartScore composite (0–100)** — A weighted index of 4 components: recency-weighted EWMA (45%), event-adjusted sentiment (25%), headline breadth (20%), and news volume (10%). The SmartScore replaces guesswork with a single, calibrated number
- **Source-weighted scoring** — Each source has a confidence weight. Blended score = weighted average across active sources. This is the sole signal (supersedes simple unweighted averaging)
- **Bayesian source calibration** — Weights self-tune from 👍/👎 votes using Beta-Binomial inference. After ~10-50 votes, source weights reflect your actual accuracy experience instead of guesses
- **Optional FinBERT sentiment** — Set `USE_FINBERT=true` to replace VADER + event rules with `ProsusAI/finbert`. No code changes needed — same signal output, ~15-20% better accuracy on financial text. Falls back to VADER if torch/transformers unavailable
- **SmartScore trend sparkline** — Visual history of SmartScore over recent sessions, showing sentiment momentum at a glance
- **Track record dedup** — Repeated scans of the same ticker update the latest unvoted entry instead of creating duplicates
- **VADER + Financial Lexicon** — 38 domain-specific financial terms tuned for Indian markets
- **BULLISH / NEUTRAL / BEARISH signal** — Weighted across sources, with per-source breakdown in the UI
- **Technical indicators** — RSI(14), SMA 50/200 crossover, MACD histogram. Works with 26+ days of data
- **Ticker alias matching** — 500+ company name aliases (SBI→SBIN, HUL→HINDUNILVR, DIVIS→DIVISLAB, HDFC BANK→HDFCBANK, plus 18 Indian regulatory agencies: RBI, SEBI, CBI, ED, NCLT, RERA, DGFT, FSSAI, TRAI, IRDAI, PFRDA, CERC, DGCA, DGGI, CCI, SFIO, DRI, NPCI) ensure every headline finds the right ticker
- **News source health** — See which sources returned results at a glance
- **Clickable news links** — Every headline opens the original article
- **Headline breakdown** — See which headlines are driving sentiment positive / negative
- **Portfolio mode** — Add stocks to a watchlist and scan all at once
- **Track record** — Rate each signal as accurate or wrong; track your precision over time
- **Dark-themed UI** — Card-based layout, sentiment badges, responsive design
- **Single search input** — Text input + 🔍 search button replaces confusing dual-input. Type any ticker and press Enter or click Search
- **Quick-action chips** — RELIANCE, HDFCBANK, TCS, INFY, SBIN one-click buttons in the empty state for instant access
- **Guided empty state** — Centered launchpad with popular ticker chips replaces the old instruction wall
- **Larger, readable type** — Minimum font raised from 8.8px → 10.4px, with clearer visual hierarchy: Price (2rem) > SmartScore (1.5rem) > Signal
- **FII/DII institutional flow** — NSE India's official FII/FPI and DII data, shown in Cr with net buying/selling stance
- **Shareable snapshot links** — Every ticker has a public URL (`?ticker=RELIANCE`) with teaser card + paywall CTA
- **Portfolio P&amp;L tracking** — Entry price per holding, live P&amp;L (₹ and %) in sidebar
- **Market heatmap** — Portfolio stocks color-coded by daily % change
- **Volume spike detection** — Flags abnormal trading volume (N× average)
- **VWAP + Deviation** — Volume-weighted average price with % deviation badge beneath the price. Shows intraday fair value and whether momentum is bullish (above VWAP) or bearish (below).
- **Pivot Levels (R1 / Pivot / S1)** — Classic intraday support/resistance levels from yesterday's HLC. Compact 3-column grid inside Technical Indicators.
- **India VIX** — Sidebar shows live VIX level, daily change, and volatility bucket (Low/Medium/High) with actionable captions.
- **Portfolio news badges** — 📌 highlights headlines matching your holdings
- **Historical sentiment archive** — SmartScore time series + CSV export per ticker
- **Public changelog** — Sidebar shows what's new; feature requests via email
- **Zero API keys** — Works out of the box
- **Free & open-source** — MIT license
- **Legal disclaimer** — No SEBI registration, not financial advice, use at your own risk

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- `pip` or `uv` (recommended)

### Install & Run

```bash
# Clone
git clone https://github.com/AshayK003/nse-sentiment-analyzer.git
cd nse-sentiment-analyzer

# Install
pip install -r requirements.txt
# or
uv pip install -r requirements.txt

# Run
streamlit run app.py
```

Open **http://localhost:8501** in your browser.

### Local-Only Features

These features require additional CLI tools on your machine:

- **FII/DII data** — `pip install nsepython` (lazy-loaded, app works without it)

Items with a ⚡ badge in the UI indicate active local-only sources.

---

## 🌐 Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `REDDIT_CLIENT_ID` | No | Reddit OAuth app client ID (requires `REDDIT_CLIENT_SECRET` too) |
| `REDDIT_CLIENT_SECRET` | No | Reddit OAuth app client secret |
| `USE_FINBERT` | No | Set to `true` to enable FinBERT transformer model for financial sentiment (requires `transformers` + `torch` installed) |

When both Reddit env vars are set, the app uses Reddit's OAuth API (works on Streamlit Cloud). Without them, Reddit is skipped.

No other env vars are needed. All data sources are free and public.

---

## 💻 Local Development

### Project Structure

```
nse-sentiment-analyzer/
├── app.py                  # Streamlit entry point, UI logic
├── data_fetcher.py         # Stock info, RSS news, Reddit, DuckDuckGo
├── sentiment.py            # VADER + financial lexicon, FinBERT integration, source-weighted scoring
├── event_classifier.py     # 18 event types: earnings, litigation, order wins, etc.
├── aggregate_sentiment.py  # SmartScore 0–100: EWMA, breadth, volume, events
├── indicators.py           # RSI, SMA crossover, MACD
├── market_data.py          # FII/DII flow (optional, nsepython)
├── persistence.py          # JSON file I/O: portfolio, track record, cache, sentiment history, source accuracy
├── render.py               # Dark-themed HTML dashboard + SmartScore sparkline
├── requirements.txt
├── pyproject.toml          # Pytest config, coverage
├── .streamlit/
│   └── config.toml         # Theme + client settings
├── data/                   # Runtime data directory (gitignored)
│   ├── cache.json          # API response cache (15-min TTL)
│   ├── portfolio.json      # Saved portfolio tickers
│   ├── entry_prices.json   # Portfolio entry prices (for P&L tracking)
│   ├── track_record.json   # Signal accuracy history
│   ├── source_accuracy.json # Bayesian source weights (learned from votes)
│   └── sentiment_history.csv # Daily SmartScore history for sparkline
└── tests/
    ├── conftest.py         # Fixtures (tmp dir, mock stock data)
    ├── test_analyze_ticker.py   # Integration: full pipeline end-to-end
    ├── test_data_fetcher.py
    ├── test_indicators.py
    ├── test_persistence.py
    ├── test_render.py
    ├── test_sentiment.py
    ├── test_event_classifier.py   # 18 event types, VADER blending
    ├── test_aggregate_sentiment.py # EWMA, breadth, volume, sparkline
    ├── test_public_teaser.py      # Shareable snapshot public card
    ├── test_changelog.py          # CHANGELOG.md infrastructure
    ├── test_market_indicators.py  # Volume spike detection
    ├── test_entry_prices.py       # Portfolio P&L, entry prices
    ├── test_intraday.py           # VWAP, pivot levels, India VIX
    └── test_history_export.py     # Sentiment archive CSV export
```

### Adding a New News Source

1. **Fetch function** — Add a fetcher in `data_fetcher.py`. Return items as `{"title", "body", "url", "date", "source"}`.
2. **Register weight** — Add the source to `persistence.py:SOURCE_WEIGHTS_PRIOR` dict (used as Bayesian learning prior).
3. **Wire into pipeline** — Add the fetcher call in `data_fetcher.py:search_news()`.
4. **Test** — Add test cases in `tests/test_data_fetcher.py`.

### Adding a New Technical Indicator

1. Add the indicator function in `indicators.py:get_technical_indicators()`.
2. Add display in `render.py:render_dashboard()`.
3. Add tests in `tests/test_indicators.py`.

### Code Style

- Follow existing patterns (pandas for data, ThreadPoolExecutor for parallelism)
- No async (sync-first design using `concurrent.futures`)
- Use `cache_get`/`cache_set` from `persistence.py` for API caches
- All external APIs must be mockable in tests
- Profile: Ponytail (YAGNI) — prefer deletion over abstraction

---

## 🧪 Testing

```bash
# Run all tests (143 tests, mocked APIs, no network)
python -m pytest tests/ -v -q

# Run with coverage
python -m pytest tests/ --cov

# Run a specific test file
python -m pytest tests/test_sentiment.py -v

# Run a specific test
python -m pytest tests/test_sentiment.py::TestSentiment::test_bullish_headline -v
```

### Test Design

- **All external APIs are mocked** — tests run offline
- **Fixtures** in `conftest.py` provide a `tmp_data_dir` for isolated file I/O + a `sample_hist` DataFrame for indicators
- **143 tests across 12 modules**
- **Integration tests** verify the full pipeline end-to-end at module boundaries (stock data → sentiment → event classification → SmartScore)
- **No network calls** — `yfinance`, `feedparser`, `duckduckgo_search`, and `requests` are all patched with `pytest-mock`

### Test Markers

Defined in `pyproject.toml`:

| Marker | Purpose |
|--------|---------|
| `slow` | Tests that hit real APIs — not run by default |
| `regression` | Tests for previously-fixed bugs |

---

## 🚢 Deployment

### Streamlit Community Cloud (Free)

1. Push to a GitHub repository
2. Go to [streamlit.io/cloud](https://streamlit.io/cloud)
3. Click **"New app"** → select repo → branch → `app.py`
4. For Reddit OAuth: add `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` in **Advanced Settings → Secrets**
5. Deploy

The app runs at `https://<your-app>.streamlit.app`.

**Notes:**
- The filesystem is ephemeral on Streamlit Cloud — portfolio, track records, and sentiment history are session-only
- SmartScore history resets on each deploy — the sparkline shows your current score as a flat line + dot even on the first analysis
- RSS + DuckDuckGo + Reddit OAuth work on the cloud
- `nsepython` is a local-only tool (not available on Streamlit Cloud)
- `yfinance` can be throttled if you run too many tickers in rapid succession

### Resetting Cached Data

```bash
# Clear the JSON cache file
rm -f ~/.nse_sentiment_cache.json
```

Or click the "Cache: … entries" button in the app sidebar.

---

## 🔧 Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: No module named 'nsepython'` | Optional dep for FII/DII data | `pip install nsepython` (app works without it) |
| `yfinance` returns no data for a ticker | Ticker may be delisted, suspended, or not on Yahoo Finance | Try the `.NS` suffix manually in custom input |
| RSS feeds return empty results | Rate-limiting or transient network issue | DuckDuckGo fallback kicks in automatically |
| Dashboard shows stale data | Cache TTL hasn't expired (default: 15 min) | Click cache button to clear, or wait |
| Streamlit Cloud "Module not found" | Missing dependency | Verify it's in `requirements.txt` |
| Duplicate track records | Repeated searches of the same ticker created extra entries | Fixed: dedup updates the latest unvoted entry per ticker. Update to latest version |

### Legal Disclaimer

This tool provides data-driven sentiment analysis and technical indicators for **educational and informational purposes only**. Nothing on this platform constitutes investment advice, a recommendation, or a solicitation to buy or sell securities.

- **Not SEBI registered.** The creator is not a SEBI-registered investment advisor.
- **Data may be inaccurate.** Data comes from third-party public APIs and may be delayed or incomplete.
- **No liability.** The creator is not liable for any financial losses arising from use of this tool.
- **Past performance ≠ future results.** Historical sentiment scores do not guarantee future outcomes.
- **Consult a professional.** Always consult a SEBI-registered financial advisor before making investment decisions.

### Getting Help

- Open a [GitHub Issue](https://github.com/AshayK003/nse-sentiment-analyzer/issues)
- Check existing closed issues for similar problems

---

## 🤝 Contributing

### What We Need

- **Better financial lexicon** — More Indian-market-specific terms for VADER
- **FinBERT fine-tuning** — The optional FinBERT model could be fine-tuned on Indian financial news for even better accuracy
- **New news sources** — Wire up additional Indian financial RSS feeds
- **NSE ticker updates** — Misspelled tickers, delisted stocks, new listings
- **UI improvements** — Accessibility, mobile layout, i18n
- **Bug fixes** — Open an issue before submitting a PR
- **Tests** — Higher coverage on edge cases (empty results, partial data)

### PR Workflow

1. **Open an issue** describing the change (bug → reproduction steps; feature → use case)
2. **Fork and branch** from `master`
3. **Write tests first** for any new logic
4. **Run the full suite** — `python -m pytest tests/ -q` should pass
5. **Keep diffs small** — one logical change per PR
6. **Commit messages** — concise, prefixed by type: `fix:`, `feat:`, `test:`, `docs:`, `refactor:`

### Avoid

- Adding new dependencies without a strong reason
- Introducing async patterns (the project is sync-first)
- Patching symptoms instead of root causes (see [Karpathy Guidelines](https://e2eml.school/karpathy_guidelines))
- Proposing features that require paid APIs or API keys

---

## 📜 License

MIT &mdash; see [LICENSE](LICENSE).

---

<div align="center">
  <sub>Built by <a href="https://x.com/sentinelcipher">@sentinelcipher</a></sub>
  <br/>
  <sub>⚠️ Not financial advice. Always do your own research.</sub>
</div>
