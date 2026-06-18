<div align="center">

# 📊 NSE Stock Sentiment Analyzer

**Multi-source sentiment + technical indicators for NSE equities & ETFs, in one dashboard.**

[![Streamlit](https://img.shields.io/badge/Built%20with-Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/AshayK003/nse-sentiment-analyzer?style=flat&logo=github)](https://github.com/AshayK003/nse-sentiment-analyzer)
[![Tests](https://img.shields.io/badge/tests-68%20passing-brightgreen)](#-testing)
[![UI: Dark Theme](https://img.shields.io/badge/UI-Dark%20Theme-13151a?logo=css3&logoColor=white)](https://nse-sentiment-analyzer.streamlit.app)

<p align="center">
  <b>🇮🇳 India-focused</b> &nbsp;·&nbsp; <b>🆓 Zero API costs</b> &nbsp;·&nbsp; <b>🔌 No API keys required</b> &nbsp;·&nbsp; <b>📡 Live data</b>
</p>

</div>

---

## Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
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
- **Source-weighted scoring** — each source has a confidence weight; the blended score is a weighted average
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
  │
  ├── data_fetcher.py ────── (stock info, RSS news, DuckDuckGo, Reddit)
  │     ├── yfinance        → stock price, info, 1yr history
  │     ├── feedparser      → RSS from 5 financial sources
  │     ├── duckduckgo_search → fallback when RSS < 3 articles
  │     └── requests/rdt-cli → Reddit (OAuth or local CLI)
  │
  ├── indicators.py ──────── (RSI, SMA crossover, MACD from OHLCV history)
  │
  ├── market_data.py ─────── (FII/DII flow data, optional)
  │
  └── persistence.py ─────── (JSON-based portfolio, track record, cache)
```

### Data Flow

```
Ticker Input
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  analyze_ticker(ticker, company)                    │
│                                                     │
│  ┌─────────────┐   ┌──────────┐   ┌─────────────┐  │
│  │ get_stock_   │   │ search_  │   │ get_techni- │  │
│  │ info()       │   │ news()   │   │ cal_indica- │  │
│  │ • yfinance   │   │ • 5 RSS  │   │ tors()      │  │
│  │ • 1yr hist   │   │ • DDG    │   │ • RSI(14)   │  │
│  │              │   │ • Reddit │   │ • SMA 50/200│  │
│  └──────┬──────┘   └────┬─────┘   │ • MACD      │  │
│         │               │         └──────┬───────┘  │
│         ▼               ▼                ▼          │
│  ┌─────────────────────────────────────────────┐    │
│  │ sentiment.py: source-weighted blending      │    │
│  │ VADER + financial lexicon (38 terms)        │    │
│  │ → BULLISH / NEUTRAL / BEARISH               │    │
│  └─────────────────────┬───────────────────────┘    │
│                        │                            │
└────────────────────────┼────────────────────────────┘
                         │
                         ▼
         ┌───────────────────────────────────┐
         │       render_dashboard()          │
         │   Dark-themed HTML via streamlit  │
         └───────────────────────────────────┘
```

### Source Weights

Each news source carries a confidence weight for the blended scoring:

| Source | Weight | Type | Available on Cloud |
|--------|--------|------|--------------------|
| Economic Times | 1.0 | RSS | ✅ |
| Moneycontrol | 0.9 | RSS | ✅ |
| LiveMint | 0.8 | RSS | ✅ |
| NDTV Profit | 0.7 | RSS | ✅ |
| Google News | 0.6 | RSS | ✅ |
| DuckDuckGo | 0.5 | Web search (fallback) | ✅ |
| Reddit * | 0.5 | OAuth / `rdt-cli` | ⚡ Local only |

*Reddit requires OAuth env vars (`REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`) or the `rdt-cli` tool. Falls back with weight 0.5 if not set up.

The **blended score** is:
```
blended = Σ(source_weight × source_avg_compound) / Σ(source_weight)
```

---

## ✨ Features

- **Live price data** — Current price, day change %, day range, volume, PE ratio for any NSE stock or ETF
- **Multi-source news** — Google News + Moneycontrol + Economic Times + LiveMint + NDTV Profit RSS feeds (DuckDuckGo fallback)
- **Reddit community chatter** — OAuth API or local `rdt-cli`. Brings retail conversation into the sentiment pipeline
- **Source-weighted scoring** — Each source has a confidence weight. Blended score = weighted average across active sources
- **VADER + Financial Lexicon** — 38 domain-specific financial terms tuned for Indian markets
- **BULLISH / NEUTRAL / BEARISH signal** — Weighted across sources, with per-source breakdown in the UI
- **Technical indicators** — RSI(14), SMA 50/200 crossover, MACD histogram. Works with 26+ days of data
- **News source health** — See which sources returned results at a glance
- **Clickable news links** — Every headline opens the original article
- **Headline breakdown** — See which headlines are driving sentiment positive / negative
- **Portfolio mode** — Add stocks to a watchlist and scan all at once
- **Track record** — Rate each signal as accurate or wrong; track your precision over time
- **Dark-themed UI** — Card-based layout, sentiment badges, responsive design
- **Zero API keys** — Works out of the box
- **Free & open-source** — MIT license

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

- **Reddit (local fallback)** — `uv tool install rdt-cli && rdt login`
- **FII/DII data** — `pip install nsepython` (lazy-loaded, app works without it)

Items with a ⚡ badge in the UI indicate active local-only sources.

---

## 🌐 Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `REDDIT_CLIENT_ID` | No | Reddit OAuth app client ID (requires `REDDIT_CLIENT_SECRET` too) |
| `REDDIT_CLIENT_SECRET` | No | Reddit OAuth app client secret |

When both Reddit env vars are set, the app uses Reddit's OAuth API (works on Streamlit Cloud). Without them, it falls back to local `rdt-cli` if available.

No other env vars are needed. All data sources are free and public.

---

## 💻 Local Development

### Project Structure

```
nse-sentiment-analyzer/
├── app.py                  # Streamlit entry point, UI logic
├── data_fetcher.py         # Stock info, RSS news, Reddit, DuckDuckGo
├── sentiment.py            # VADER + financial lexicon, source-weighted scoring
├── indicators.py           # RSI, SMA crossover, MACD
├── market_data.py          # FII/DII flow (optional, nsepython)
├── persistence.py          # JSON file I/O: portfolio, track record, cache
├── render.py               # Dark-themed HTML dashboard via st.components
├── requirements.txt
├── pyproject.toml          # Pytest config, coverage
├── .streamlit/
│   └── config.toml         # Theme + client settings
└── tests/
    ├── conftest.py         # Fixtures (tmp dir, mock stock data)
    ├── test_data_fetcher.py
    ├── test_indicators.py
    ├── test_persistence.py
    ├── test_render.py
    └── test_sentiment.py
```

### Adding a New News Source

1. **Fetch function** — Add a fetcher in `data_fetcher.py`. Return items as `{"title", "body", "url", "date", "source"}`.
2. **Register weight** — Add the source to `sentiment.py:SOURCE_WEIGHTS` dict.
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
# Run all tests (68 tests, mocked APIs, no network)
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
- **68 tests** across 5 modules (sentiment, indicators, data_fetcher, persistence, render)
- **No network calls** — `yfinance`, `feedparser`, `duckduckgo_search`, `requests`, and `rdt-cli` are all patched with `pytest-mock`

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
- The filesystem is ephemeral on Streamlit Cloud — portfolio and track records are session-only
- RSS + DuckDuckGo + Reddit OAuth work on the cloud
- `rdt-cli` and `nsepython` are local-only tools (not available on Streamlit Cloud)
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
| Reddit ⚡ badge missing / no Reddit results | `rdt-cli` not installed or not logged in | `uv tool install rdt-cli && rdt login` |
| `yfinance` returns no data for a ticker | Ticker may be delisted, suspended, or not on Yahoo Finance | Try the `.NS` suffix manually in custom input |
| RSS feeds return empty results | Rate-limiting or transient network issue | DuckDuckGo fallback kicks in automatically |
| Dashboard shows stale data | Cache TTL hasn't expired (default: 15 min) | Click cache button to clear, or wait |
| Streamlit Cloud "Module not found" | Missing dependency | Verify it's in `requirements.txt` |
| Duplicate track records | Fixed in commit `ecb5cc1` | Update to latest version |

### Getting Help

- Open a [GitHub Issue](https://github.com/AshayK003/nse-sentiment-analyzer/issues)
- Check existing closed issues for similar problems

---

## 🤝 Contributing

### What We Need

- **Better financial lexicon** — More Indian-market-specific terms for VADER
- **New news sources** — Wire up additional Indian financial RSS feeds
- **NSE ticker updates** — Mispelled tickers, delisted stocks, new listings
- **UI improvements** — Accessibility, mobile layout, i18n
- **Bug fixes** — Open an issue before submitting a PR
- **Tests** — Higher coverage on edge cases (empty results, partial data)

### PR Workflow

1. **Open an issue** describing the change (bug → reproduction steps; feature → use case)
2. **Fork and branch** from `master`
3. **Write tests first** for any new logic
4. **Run the full suite** — `python -m pytest tests/ -v -q` should pass
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
