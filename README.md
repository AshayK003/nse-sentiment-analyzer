<div align="center">

# NSE Stock Sentiment Analyzer

**Multi-source sentiment + technical indicators for NSE equities & ETFs, in one dashboard.**

[![Streamlit](https://img.shields.io/badge/Built%20with-Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/AshayK003/nse-sentiment-analyzer?style=flat&logo=github)](https://github.com/AshayK003/nse-sentiment-analyzer)
[![Tests](https://img.shields.io/badge/tests-171%20passing-brightgreen)](#-testing)
[![Security](https://img.shields.io/badge/security-XSS%20escaped-2ea44f)](#)
[![UI: Dark Theme](https://img.shields.io/badge/UI-Dark%20Theme-13151a?logo=css3&logoColor=white)](https://nse-sentiment-analyzer.streamlit.app)
[![Streamlit Limits](https://img.shields.io/badge/resource%20limits-500%20cache%2C%206%2Fmin%20throttle-blueviolet)](.streamlit/config.toml)

[Launch App](https://nse-sentiment-analyzer.streamlit.app) &nbsp;·&nbsp; [Report Bug](https://github.com/AshayK003/nse-sentiment-analyzer/issues) &nbsp;·&nbsp; [Request Feature](mailto:darkcharon3301@gmail.com)

</div>

---

## Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Environment Variables](#-environment-variables)
- [Project Structure](#-project-structure)
- [Local Development](#-local-development)
- [Testing](#-testing)
- [Deployment](#-deployment)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)

---

## Overview
Enter any NSE ticker **or company name** and get a **BULLISH / NEUTRAL / BEARISH** signal backed by:

- **Smart ticker search** — type a company name ("HDFC Bank", "Tata Motors", "Zomato"), alias ("SBI", "L&T"), or partial name and get the correct NSE ticker automatically. 504 aliases, Yahoo Finance REST API (~0.5s), yfinance SDK, and direct ticker probe — chained with caching. Handles rebrands (Zomato → Eternal) and splits (Tata Motors → TMPV/TMCV).
- **Live market data** — price, change %, volume, PE ratio, and D/E ratio via Yahoo Finance
- **Interactive price chart** — 2-year candlestick chart with volume bars, 50-day SMA, 200-day SMA, and Bollinger Bands (20,2) overlays. Powered by TradingView Lightweight Charts. Zoom, pan, crosshair on hover. Visual legend identifies all overlays. Zero Python dependencies.
- **Multi-source news sentiment** — RSS feeds from Moneycontrol, Economic Times, LiveMint (Markets + Companies + Industry), NDTV Profit, Google News, with DuckDuckGo fallback
- **Event-aware scoring** — headlines classified by 19 event types (earnings, order wins, litigation, regulatory approvals, buybacks, etc.) with signed sentiment bias. Correctly scores "SEBI penalty" as negative and "SEBI clears merger" as positive — something VADER alone misses.
- **SmartScore composite (0–100)** — combines recency-weighted EWMA (36h half-life), event-adjusted sentiment, headline breadth, and news volume into a single calibrated score
- **Self-calibrating source weights** — each source's confidence weight learns from your 👍/👎 votes via Bayesian Beta-Binomial inference. After ~10–50 votes, weights reflect your actual accuracy experience.
- **Enhanced VADER + 123-term Indian financial lexicon** — includes Indian banking metrics (NPA, GNPA, NIM, credit growth, slippage, provisioning), profitability shorthand (PAT, EBITDA, ROE, ROCE), IPO/capital market terms (oversubscribed, undersubscribed), fund flow terms (inflow, outflow), Hinglish (tezi, mandi, tej, mand), and general financial context not in vanilla VADER. Optionally swap to FinBERT via `USE_FINBERT=true`.
- **Technical indicators** — RSI(14), SMA crossover (50/200), MACD from 2-year OHLCV history
- **Portfolio mode** — track holdings with P&L, qty/shares field, auto-fetched LTPs, and one-click clear all
- **FII/DII institutional flow** — NSE India official FII/FPI and DII data with Net value. Glassmorphism card shows latest day's flow plus a 7-day history table. Auto-saves daily snapshots.
- **VWAP + Pivot levels** — intraday fair value and classic support/resistance from yesterday's HLC
- **Market Mood Index (MMI)** — 0–100 fear & greed gauge in the dashboard's Market Pulse card. 4 equally-weighted components: Trend Strength (Nifty vs 20-day SMA), VIX Fear Gauge (inverted India VIX), FII Money Flow (institutional confidence vs 21-day trailing average), Market Breadth (sector advance/decline across 10 sectoral indices). 5-zone system: Extreme Fear → Fear → Neutral → Greed → Extreme Greed. Sub-scores shown for each component. Zero extra API calls — assembled from yfinance + existing FII history.
- **Resource protections** — per-session rate limiter (6 searches/min), auto-pruning cache (500-entry cap), DDGS fallback cooldown, and thread-safe rate-limit tracking (including DDGS) prevent quota exhaustion and race conditions under multi-user load. Configured in `.streamlit/config.toml`.
- **XSS-safe rendering** — all user data (ticker names, company names) is HTML-escaped via `html.escape()` with single-quote support. Shareable `?ticker=` URLs are validated before API calls. RSS feed URLs are checked for `http://`/`https://` scheme.
- **CSP hardened** — Content Security Policy `connect-src` restricted to known API domains (Yahoo Finance, Google News, Moneycontrol, Economic Times, LiveMint, NDTV Profit). No wildcard.

**All data sources are free and public. Zero API keys required. No registration.**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  app.py                   Streamlit entry point, UI layout  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  data_fetcher.py    Yahoo Finance + RSS + DuckDuckGo  │  │
│  │                     NSE_TICKERS (271 stocks)          │  │
│  │                     Alias map (504 entries)           │  │
│  │                     Smart ticker resolution           │  │
│  │                       → local dict (instant)          │  │
│  │                       → aliases (instant)             │  │
│  │                       → Yahoo REST API (~0.5s)        │  │
│  │                       → yfinance SDK (~1s)            │  │
│  │                       → direct .NS probe (~1s)        │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                    │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │  sentiment.py         VADER + 125-term Indian financial│  │
│  │                       FinBERT integration (optional)  │  │
│  │                       Source-weighted blending        │  │
│  │  ┌─────────────────────────────────────────────────┐ │  │
│  │  │  event_classifier.py    19 event types           │ │  │
│  │  │                        Signed bias per event     │ │  │
│  │  └─────────────────────────────────────────────────┘ │  │
│  │  ┌─────────────────────────────────────────────────┐ │  │
│  │  │  aggregate_sentiment.py  SmartScore 0–100        │ │  │
│  │  │                        EWMA, breadth, volume    │ │  │
│  │  └─────────────────────────────────────────────────┘ │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                    │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │  indicators.py        RSI(14), SMA crossover, MACD    │  │
│  │  intraday.py          VWAP, pivot levels, India VIX   │  │
│  │  market_data.py       FII/DII flow, MMI               │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                    │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │  persistence.py       JSON file I/O                   │  │
│  │                       Portfolio, track record, cache  │  │
│  │                       Source accuracy (Bayesian)      │  │
│  │                       Sentiment history (CSV)         │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                    │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │  render.py            Dark HTML/CSS dashboard         │  │
│  │                       SmartScore sparkline            │  │
│  │                       Lucide SVG icons                │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Input** — User types a ticker or company name (e.g., "HDFC Bank", "Zomato", "RELIANCE")
2. **Resolve** — `resolve_ticker()` maps the input to an NSE ticker via 5-tier chain: local dict → aliases → Yahoo REST → yfinance SDK → direct probe. Returns `(ticker, company_name)`.
3. **Fetch** — `get_stock_info()`, `search_news()`, and `get_fii_dii_flow()` run in parallel via `ThreadPoolExecutor(3)`. Stock data comes from yfinance, news from RSS (9+ sources) with DuckDuckGo fallback, FII/DII from NSE India. Total fetch time: ~2s.
4. **Analyze** — `sentiment.py` scores each headline via VADER + financial lexicon, applies event-classifier corrections, then blends results using Bayesian source weights
5. **Aggregate** — `aggregate_sentiment.compute_smartscore()` produces the 0–100 SmartScore from EWMA, event-adjusted sentiment, breadth, and volume
6. **Indicators** — `indicators.py` computes RSI, SMA crossover, and MACD from 2-year OHLCV
7. **Render** — `render.render_dashboard()` assembles a dark-themed HTML dashboard rendered via `st.components.v1.html()`
8. **Vote** — Users rate signal accuracy (👍/👎). Votes update Beta posteriors for each source in `persistence.py`, which feeds back into step 4

### Source Weighting (Bayesian Calibration)

Each news source carries a confidence weight that self-calibrates via Beta-Binomial inference:

```
Weight = α / (α + β)
```

- **α** = correct votes for this source
- **β** = incorrect votes for this source
- Prior: hand-tuned (α₀, β₀) per source based on editorial quality
- Posterior updates on every 👍/👎 vote

The blended signal score is weighted by these posteriors:

```
signal = Σ(wᵢ · sᵢ) / Σ(wᵢ)
```

Where `wᵢ` is source weight and `sᵢ` is average compound score for that source.

After ~10–50 votes, weights converge from guesses to measurements.

---

## Quick Start

### Prerequisites

- Python 3.11+
- `pip` or `uv` (recommended for speed)

### Install & Run

```bash
git clone https://github.com/AshayK003/nse-sentiment-analyzer.git
cd nse-sentiment-analyzer

# Install (choose one)
pip install -r requirements.txt
# or
uv pip install -r requirements.txt

# Launch
streamlit run app.py
```

Open **http://localhost:8501** in your browser.

### Optional: Enable FinBERT

FinBERT offers ~15–20% better accuracy on financial text than VADER. Requires ~2GB of additional dependencies.

```bash
pip install torch transformers
USE_FINBERT=true streamlit run app.py
```

### Optional: FII/DII Institutional Data

```bash
pip install nsepython
```

The app works without it — this data appears as an informational section when available.

---

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `USE_FINBERT` | No | Set to `true` to enable FinBERT transformer. Requires `transformers` + `torch` (see `requirements.txt`). |

**That's it.** No API keys, no tokens, no secrets. All data comes from free public sources.

---

## Project Structure

```
nse-sentiment-analyzer/
├── app.py                  # Streamlit entry point, UI state machine
├── data_fetcher.py         # yfinance, RSS (feedparser), DuckDuckGo search
├── sentiment.py            # VADER + financial lexicon, FinBERT, source weights
├── event_classifier.py     # 19 event types with signed sentiment bias
├── aggregate_sentiment.py  # SmartScore 0–100 (EWMA, breadth, volume, events)
├── indicators.py           # RSI(14), SMA crossover, MACD
├── intraday.py             # VWAP, pivot levels, India VIX
├── market_data.py          # FII/DII flow, Market Mood Index (MMI)
├── persistence.py          # JSON file I/O, Bayesian source accuracy
├── render.py               # Dark-themed HTML/CSS dashboard + TradingView chart + overlays + a11y
├── requirements.txt
├── pyproject.toml          # Pytest config, coverage, markers
├── CHANGELOG.md            # Version history
├── LICENSE                 # AGPL v3
├── .streamlit/
│   └── config.toml         # Dark theme + minimal chrome
├── data/                   # Runtime data (gitignored)
│   ├── cache.json          # API response cache (15-min TTL)
│   ├── portfolio.json      # Saved tickers
│   ├── entry_prices.json   # P&L entry prices
│   ├── track_record.json   # Vote history
│   ├── source_accuracy.json # Bayesian posteriors per source
│   └── sentiment_history.csv # Daily SmartScore time series
└── tests/
    ├── conftest.py         # Fixtures: tmp data dir, mock stock data
    ├── test_analyze_ticker.py    # Full pipeline end-to-end
    ├── test_data_fetcher.py
    ├── test_indicators.py
    ├── test_persistence.py
    ├── test_render.py
    ├── test_sentiment.py
    ├── test_event_classifier.py
    ├── test_aggregate_sentiment.py
    ├── test_market_indicators.py  # Volume spike detection
    ├── test_entry_prices.py       # P&L tracking
    ├── test_intraday.py           # VWAP, pivots, VIX
    ├── test_changelog.py          # Infrastructure
    └── test_history_export.py     # CSV export
```

**10 source modules**, **14 test files**, **139 tests**.

---

## Local Development

### Adding a News Source

1. **Fetch function** — Add to `data_fetcher.py`. Return items as `{"title", "body", "url", "date", "source"}`
2. **Register prior** — Add source to `persistence.py:SOURCE_WEIGHTS_PRIOR` dict (used as Bayesian prior)
3. **Wire into pipeline** — Call your fetcher from `data_fetcher.py:search_news()`
4. **Test** — Add tests in `tests/test_data_fetcher.py`

### Adding a Technical Indicator

1. Add function to `indicators.py:get_technical_indicators()`
2. Add HTML display in `render.py:render_dashboard()`
3. Add tests in `tests/test_indicators.py`

### Code Conventions

- **Sync-first** — no async. Parallelism via `concurrent.futures.ThreadPoolExecutor`
- **Mock all external APIs** in tests — never hit production services
- **Use `cache_get`/`cache_set`** from `persistence.py` for API response caching
- **Prefer deletion over abstraction** — YAGNI as a principle. When in doubt, leave it out.
- **Lucide SVGs** for all UI icons — no emojis where an SVG serves the same purpose

---

## Testing

```bash
# Full suite (139 tests, mocked APIs, no network)
python -m pytest tests/ -v -q

# With coverage
python -m pytest tests/ --cov

# Specific file
python -m pytest tests/test_sentiment.py -v

# Specific test
python -m pytest tests/test_indicators.py::TestIndicators::test_rsi -v

# Slow tests (hit real APIs — not run by default)
python -m pytest tests/ -m slow

# Regression tests (previously fixed bugs)
python -m pytest tests/ -m regression
```

### Test Design

- **All external APIs mocked** — `yfinance`, `feedparser`, `duckduckgo_search`, `requests` patched with `pytest-mock`
- **Fixtures** in `conftest.py` provide isolated `tmp_data_dir` for file I/O + `sample_hist` DataFrame for indicators
- **Integration tests** verify the full pipeline at module boundaries (stock data → sentiment → event classification → SmartScore)
- **Markers** defined in `pyproject.toml`:
  - `slow` — tests hitting real APIs (opt-in)
  - `regression` — tests for previously-fixed bugs

---

## Deployment

### Streamlit Community Cloud (Free)

1. Fork/push to GitHub
2. Visit [streamlit.io/cloud](https://streamlit.io/cloud)
3. **New app** → select repo → branch → `app.py`
4. Deploy

The app runs at `https://<your-app>.streamlit.app`.

### Notes

- **Ephemeral filesystem** — portfolio, track records, and sentiment history are session-only on Streamlit Cloud. Data resets on each deploy.
- **RSS + DuckDuckGo** work on the cloud.
- **`nsepython`** is local-only (not available on Streamlit Cloud).
- **`yfinance`** can throttle if you queue many tickers rapidly. Use portfolio briefing mode for batch scans (skips news, ~1.5s/ticker).
- **No environment secrets needed** — all datasources are public APIs.

### Resetting Cached Data

```bash
# Clear local JSON cache
rm -f data/cache.json
```

Or click the cache stats button in the app sidebar.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: nsepython` | Optional dep missing | `pip install nsepython` (app works without it) |
| yfinance returns nothing for a ticker | Delisted, suspended, or not on Yahoo Finance | Try `.NS` suffix manually via custom input |
| RSS feeds return empty | Rate-limiting or network issue | DuckDuckGo fallback kicks in automatically |
| Dashboard shows stale data | Cache TTL (15 min) hasn't expired | Clear cache via sidebar button, or wait |
| Streamlit Cloud "Module not found" | Missing dependency in `requirements.txt` | Add it and redeploy |
| Duplicate track record entries | Repeated searches created extra rows | Update to latest version (dedup is automatic) |

### Legal Disclaimer

This tool is for **educational and informational purposes only**. Nothing on this platform constitutes investment advice. The creator is not a SEBI-registered advisor. Data comes from third-party public APIs and may be delayed or inaccurate. Always consult a SEBI-registered financial advisor before making investment decisions.

---

## Contributing

### What We Need

- **Financial lexicon expansion** — more Indian-market-specific terms for VADER
- **News source integration** — additional Indian financial RSS feeds
- **NSE ticker updates** — new listings, delistings, symbol changes
- **UI improvements** — accessibility, mobile responsiveness, i18n
- **Bug fixes** — open an issue first with reproduction steps
- **Test coverage** — edge cases for empty results, partial data, rate limits

### PR Workflow

1. **Open an issue** describing the change (bug → reproduction; feature → use case)
2. **Fork and branch** from `master`
3. **Write tests first** for any new logic
4. **Run the full suite** — `python -m pytest tests/ -q` must pass
5. **Keep diffs small** — one logical change per PR
6. **Commit messages** — prefixed by type: `fix:`, `feat:`, `test:`, `docs:`, `refactor:`

### Avoid

- Adding new dependencies without a strong reason
- Introducing async patterns (this project is sync-first)
- Patching symptoms instead of root causes
- Proposing features requiring paid APIs or API keys

---

## Support

If this tool saves you a bad trade or helps you learn, [buy the developer a chai](https://chai4.me/ashaykushwaha003).

---

## License

**GNU AGPL v3** — see [LICENSE](LICENSE).

This license ensures the code stays open and prevents closed-source monetization. Anyone who uses or modifies this code and runs it as a network service must release their changes under the same terms.

---

<div align="center">
  <sub>Built by <a href="https://x.com/sentinelcipher">@sentinelcipher</a></sub>
  <br/>
  <sub>Not financial advice. Always do your own research.</sub>
</div>
