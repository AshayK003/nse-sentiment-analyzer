# Architecture Overview

## System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        app.py (Streamlit)                       │
│  UI state machine, user input, dashboard rendering              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ data_fetcher  │   │  persistence  │   │  market_data  │
│   .py         │   │    .py        │   │    .py        │
│               │   │               │   │               │
│ • yfinance    │   │ • JSON I/O    │   │ • FII/DII     │
│ • RSS feeds   │   │ • Portfolio   │   │ • MMI         │
│ • DDG search  │   │ • Track record│   │               │
│ • Smart ticker│   │ • Source acc  │   │               │
│   resolution  │   │ • Sentiment   │   │               │
│               │   │   history     │   │               │
└───────┬───────┘   └───────────────┘   └───────┬───────┘
        │                                       │
        ▼                                       │
┌───────────────────────────────────────────────┘
│           sentiment.py                         │
│  • VADER + 125-term Indian financial lexicon  │
│  • FinBERT integration (optional)             │
│  • Bayesian source weighting                  │
└───────┬───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────┐
│         event_classifier.py                   │
│  • 19 event types with signed sentiment bias  │
│  • Pattern-based classification               │
└───────┬───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────┐
│       aggregate_sentiment.py                  │
│  • SmartScore 0–100                           │
│  • EWMA (36h half-life)                       │
│  • Event-adjusted sentiment                   │
│  • Headline breadth & volume                  │
└───────┬───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────┐
│           cascade.py                          │
│  • 8 macro drivers → 27 tickers               │
│  • Per-ticker direction sensitivity           │
│  • Direction inferred from article text       │
│  • Ticker mention scanning                    │
└───────┬───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────┐
│      adaptive_sentiment.py (P0)               │
│  • Adaptive TF-IDF Cluster Learner            │
│    - Groups headlines into semantic clusters  │
│    - Tracks realized price reactions          │
│    - Auto-adapts as regimes shift             │
│    - 72h calibration window                   │
│  • News Dissemination Breadth Clustering      │
│    - TF-IDF + DBSCAN for article similarity   │
│    - Cluster size = dissemination breadth     │
│    - Large multi-source = high impact         │
└───────┬───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────┐
│        indicators.py / intraday.py            │
│  • RSI(14), SMA crossover, MACD              │
│  • VWAP, pivot levels, India VIX             │
└───────┬───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────┐
│            render.py                          │
│  • Dark-themed HTML/CSS dashboard             │
│  • TradingView Lightweight Charts             │
│  • Candlestick + volume + SMA50/200 + BB(20,2)│
│  • Lucide SVG icons, WCAG 2.1 AA              │
└───────────────────────────────────────────────┘
```

## Module Responsibilities

| Module | Purpose | Key Exports |
|--------|---------|-------------|
| `app.py` | Streamlit entry point, UI state machine, request routing | `main()` |
| `data_fetcher.py` | All external data: yfinance, RSS, DDG, ticker resolution | `get_stock_info()`, `search_news()`, `resolve_ticker()`, `get_cached_history()` |
| `sentiment.py` | VADER + financial lexicon, FinBERT, Bayesian source weights | `score_headlines()`, `update_source_accuracy()` |
| `event_classifier.py` | 19 event types with signed bias | `classify_event()` |
| `aggregate_sentiment.py` | SmartScore computation | `compute_smartscore()` |
| `cascade.py` | Macro driver → ticker ripple effects | `detect_cascade()` |
| `adaptive_sentiment.py` | Adaptive learner + dissemination clustering | `AdaptiveClusterLearner`, `DisseminationClusterer` |
| `indicators.py` | Technical indicators from OHLCV | `get_technical_indicators()` |
| `intraday.py` | VWAP, pivots, VIX | `compute_vwap()`, `compute_pivots()`, `get_vix()` |
| `market_data.py` | FII/DII flow, MMI | `get_fii_dii_flow()`, `compute_mmi()` |
| `persistence.py` | File I/O, Bayesian posteriors | `save_*()`, `load_*()`, `cache_*()` |
| `render.py` | HTML/CSS/JS dashboard rendering | `render_dashboard()` |

## Data Flow

```
User Input (ticker/name)
        │
        ▼
resolve_ticker() ──5-tier chain──▶ NSE ticker + company name
        │
        ├──────────────────┬──────────────────┬──────────────────┐
        ▼                  ▼                  ▼                  ▼
get_stock_info()    search_news()        get_fii_dii_flow()  (parallel)
        │                  │                  │
        │            RSS feeds             NSE India
        │            + DDG fallback
        │                  │
        ▼                  ▼
   OHLCV + info      Articles[] ──▶ score_headlines() ──▶ classify_event()
        │                  │                  │                  │
        │                  ▼                  ▼                  ▼
        │            VADER/FinBERT      19 event types    Signed bias
        │                  │                  │                  │
        │                  └──────────────────┼──────────────────┘
        │                                     ▼
        │                          compute_smartscore()
        │                          (EWMA + events + breadth)
        │                                     │
        ▼                                     ▼
   Technical indicators                detect_cascade()
   (RSI, SMA, MACD)                       │
        │                                 ▼
        │                          Macro drivers
        │                          (8 groups, 27 tickers)
        │                                     │
        └─────────────────────────────────────┘
                                      │
                                      ▼
                            render_dashboard()
                            (HTML + TradingView chart)
```

## Key Design Decisions

### Sync-First Architecture
- **No `async`/`await`** — all I/O is synchronous
- **Parallelism** via `ThreadPoolExecutor` (3 workers for stock/news/FII, 5 for portfolio briefing)
- Simpler debugging, no event loop complications on Streamlit Cloud

### 3-Tier Price Cache
1. **L1** — In-memory dict (`_hist_cache`), same session
2. **L2** — `.price_cache/` JSON files on disk, survives restarts, 7-day TTL
3. **L3** — yfinance network call (only on L1/L2 miss)

### Smart Ticker Resolution (5-tier)
1. Local dict (instant)
2. ALIASES dict (461 entries, instant)
3. Yahoo Finance REST API (~200ms, no auth)
4. yfinance SDK Search (~1s)
5. Direct `.NS` probe (~1s)

### Bayesian Source Calibration
Each source has `(α, β)` posterior:
- **Weight** = α / (α + β)
- **Prior** from editorial quality (hand-tuned)
- **Updates** on every 👍/👎 vote
- Converges from guess → measurement after ~10-50 votes

### Adaptive Sentiment Engine (P0)
- **Learns from price reactions, not labels**
- TF-IDF clusters → track average price move per cluster
- 72h calibration recalibrates weights against ground truth
- Zero GPU, pure CPU, sub-second latency

### Dissemination Breadth Clustering
- Article similarity → TF-IDF + DBSCAN
- Cluster size = market impact proxy
- Large multi-source clusters = high-impact events

## Configuration

| File | Purpose |
|------|---------|
| `.streamlit/config.toml` | Dark theme, cache limits, CORS/XSRF |
| `pyproject.toml` | Pytest config, coverage, markers |
| `requirements.txt` | Runtime dependencies |
| `data/` (gitignored) | Runtime JSON/CSV data |

## Deployment

**Streamlit Community Cloud** (free):
- Push to GitHub → New App → select repo/branch → `app.py`
- Ephemeral filesystem (data resets on deploy)
- `nsepython` not available (local only)

**Local / Docker**:
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Testing

```bash
# Full suite (180 tests, mocked APIs)
python -m pytest tests/ -q

# With coverage
python -m pytest tests/ --cov

# Specific module
python -m pytest tests/test_sentiment.py -v

# Slow tests (real APIs)
python -m pytest tests/ -m slow

# Regression tests
python -m pytest tests/ -m regression
```

## External Dependencies

| Package | Purpose | Required |
|---------|---------|----------|
| `streamlit` | Web framework | Yes |
| `yfinance` | Yahoo Finance data | Yes |
| `feedparser` | RSS parsing | Yes |
| `duckduckgo-search` | News fallback | Yes |
| `pandas` / `numpy` | Data manipulation | Yes |
| `scikit-learn` | TF-IDF, DBSCAN | Yes (P0 features) |
| `nltk` | VADER sentiment | Yes |
| `torch` + `transformers` | FinBERT (optional) | No (`USE_FINBERT=true`) |
| `nsepython` | FII/DII (optional) | No (local only) |