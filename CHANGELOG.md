# Changelog

## [2.5.4] — 2026-06-22

### Added
- **Interactive price chart (2Y candlestick + volume)** — TradingView Lightweight Charts integration. 2-year candlestick chart with green/red volume bars, crosshair, zoom/pan. Zero Python dependencies — loads ~40KB JS from CDN.
- **Chart overlays** — Bollinger Bands (20-period, 2 std dev, purple dashed) and 200-day SMA (gold dashed) computed from cached OHLCV data. 50-day SMA (blue solid) computed in JS. Visual legend below chart title.
- **Accessibility: focus-visible rings** — Visible focus outlines on all interactive elements for keyboard navigation. WCAG 2.4.7 compliance.

### Changed
- **Dashboard layout restructured** — Price Chart moved after Technical Indicators (was between Price and Sentiment). Stats (sector, industry, market cap, 52W range) merged into Price Card. Sentiment Distribution bar inlined into Sentiment Card.
- **Technical Indicators grid** — 5 columns (MACD no longer wraps to a lonely second row).
- **Tablet responsive breakpoint** — 768px breakpoint for better tablet layouts.
- **Confidence percentage color** — Matches signal direction (green/red/grey) instead of always green.
- **Extended price history** — yfinance period changed from 1Y to 2Y for fuller SMA200 coverage and Bollinger Bands.

### Fixed
- **Chart not rendering** — CSP `script-src` now includes `https://unpkg.com` alongside nonce. Lightweight Charts CDN was being blocked.
- **Sector/Industry showing N/A** — Added Phase 2c targeted retry for sector/industry across all suffixes (.NS, .BO, bare). yfinance `.info` is flaky for Indian stocks.
- **Chart data missing on cache hit** — `get_cached_history()` now falls back to direct yfinance fetch when `_hist_cache` is empty (persistence cache early return skipped `_hist_cache` population).

## [2.5.3] — 2026-06-22

### Added
- **Interactive price chart (1Y candlestick + volume)** — TradingView Lightweight Charts integration. Candlestick chart with green/red volume bars, 50-day SMA overlay, crosshair, zoom/pan. Zero Python dependencies — loads ~40KB JS from CDN. Chart sits between the price card and sentiment card in the dashboard.
- **Chart overlays** — Bollinger Bands (20-period, 2 std dev, purple dashed) and 200-day SMA (gold dashed) computed from cached OHLCV data. Visual legend below chart title identifies all three overlays (SMA50, SMA200, Bollinger).

## [2.5.2] — 2026-06-22

### Fixed
- **Pivot levels rendering** — Added missing `_render_pivot_html()` function. Pivot/support/resistance values now display correctly in the technical indicators card. Previously crashed with `NameError` on every analysis.
- **Duplicate VADER lexicon keys** — Removed duplicate `"growth"` (second definition was `0.5`, overriding intended `1.0`) and duplicate `"sell"` entries. First definition now wins as intended.
- **Dead VADER bigram entries removed** — `"profit booking"` and `"GDP growth"` were multi-word keys that VADER never scored (single-token scorer only). Decomposed single-word equivalents already exist.
- **News relevance filtering tightened** — `_relevant()` now uses phrase-level matching (ticker symbol, full company name, alias keys) instead of individual word matching. Previously, words like "bank", "power", "tata", "steel" caused headlines about unrelated companies to pass the filter. E.g., searching HDFCBANK would match any headline mentioning "bank".
- **Event classifier false positives reduced** — Six broad patterns tightened: `stellar`, `unveils`, `introduces`, `quit`, `penalty`, and `promoted` now require financial context (e.g., "stellar Q4 results" not "stellar cast", "penalty of Rs 5Cr" not "sports penalty"). Reduces misclassification of non-financial headlines.

### Changed
- **`_parse_rss_feed()` promoted to module level** — Moved from inside `search_news()` to module scope. Eliminates per-call function object creation during concurrent RSS fetches.
- **`_pct()` promoted to module level** — Moved from inside `render_dashboard()` to module scope near other helpers.
- **Thread-safe history cache** — `_hist_cache` dict now protected by `_hist_cache_lock`. Prevents potential data races when briefing mode runs parallel workers writing to the shared cache.
- **Removed duplicate import** — `get_cached_history` was imported twice in `app.py` (top-level and inside function body). Top-level import kept.

## [2.5.1] — 2026-06-22

### Security
- **URL scheme validation** — All RSS feed hrefs and DuckDuckGo results now verify `http://` or `https://` before use. Prevents `javascript:` protocol injection via crafted RSS entries.
- **CSP connect-src tightened** — Replaced wildcard `connect-src *` with an explicit allowlist of known API domains (Yahoo Finance, Google News, Moneycontrol, Economic Times, LiveMint, NDTV Profit).

### Changed
- **Logging in all modules** — Every source file now has `logging.getLogger(__name__)` with `logger.warning()`/`logger.debug()` on error paths. Streamlit Cloud captures these via stdout/stderr for production diagnostics.
- **DDGS rate limiter is now thread-safe** — `_mark_ddgs_rate_limited()` uses the same `_rate_limit_lock` as yfinance. Prevents data races when briefing mode runs 5 parallel workers.
- **Inline functions promoted to module level** — `_wilders_smooth()`, `_retry_fetch()`, `_nf()`, `_fii_dii_action()` moved from function bodies to module scope. Eliminates per-call function object creation.
- **VADER bigram entries decomposed** — 15+ bigram keys (`"all-time high"`, `"margin call"`, `"insider trading"`, etc.) replaced with meaningful single-word entries. VADER scores single tokens only — bigrams never fired.
- **`import csv` / `import io` moved to module level** — Removed from 3 function bodies in `persistence.py`.

### Cleaned
- **app.py refactored** — Extracted `_render_briefing()`, `_render_empty_state()`, `_render_bottom_cards()` from inline code. Main flow reduced from ~930 to ~840 lines with clearer function boundaries.
- **market_data.py rewritten** — `action()` moved to module-level `_fii_dii_action()`. Added logging to error path.
- **Dead VADER bigrams removed** — ~15 entries that could never fire (bigram keys in a single-token scorer) replaced with decomposed single-word equivalents.

## [2.5.0] — 2026-06-21

### Added
- **Indian financial lexicon expanded to 123 terms** — Added 53 new entries across 10 categories:
  - IPO/capital markets: oversubscribed, undersubscribed, listing
  - Banking/NPA: slippage, provisioning, moratorium, recapitalization, infusion, pledged, unpledged
  - Fund flows: inflow, outflow, buying, selling
  - Results: doubled, tripled, multibagger, topline, bottomline
  - Corporate governance: mismanagement, compliance, scrutiny
  - Corporate action: buyout, merger, acquisition, delisting
  - Macro: depreciation, appreciation, deficit
  - Hinglish: tej, mand, gire, giri, chade, chadi
  - Fixed wrong-direction VADER scores: "profit warning" now correctly negative (+0.128 → -0.103), "overweight" now correctly positive (-0.361 → +0.361)
- **REGULATORY_APPROVAL event type** — "SEBI clears merger", "RBI approves", "CCI okays" are now classified as positive events (base +0.15) instead of falling through to LITIGATION. Catches 5 regulatory bodies across 5 patterns.
- **LiveMint Companies and Industry RSS feeds** — Two additional source feeds from livemint.com to improve news coverage depth.

### Changed
- **Disclaimer updated** — Sentiment model and event classifier limitations now reflect the expanded lexicon and REGULATORY_APPROVAL fix. "SEBI clears merger" example updated from "flagged as penalty" to "correctly classified as regulatory approval".
- **License changed from MIT to AGPL v3** — Prevents closed-source monetization while allowing open sharing.
- **Landing page** — Metrics updated: 9+ data sources, 19 event types, 135 tests, AGPL v3 license. Lexicon count updated throughout docs.
- **README** — Lexicon count synced to 125-term across overview and architecture diagram.

## [2.4.2] — 2026-06-21

### Fixed
- **Shareable snapshot links now work** — `?ticker=NIFTYBEES` URLs crashed with a `TypeError` because the rendering pipeline wasn't setting up technical indicators and other supporting data for snapshot-only visits. Now they load the same full dashboard as a normal search.
- **`get_cached_history` import was inline-only** — Couldn't be reached from the snapshot code path without a separate inline import. Promoted to module-level import so all paths can use it.

### Cleaned
- **Function-level imports moved to module level** — `sentiment.py` was importing from `persistence` inside a function body (leftover from an old circular-dependency scare). `intraday.py` had `import yfinance` inside two separate functions. Both now import at the top of the file — cleaner, faster, and more predictable.
- **PEP 8 spacing** — Trimmed extra blank lines between functions in `render.py`.

## [2.4.1] — 2026-06-21

### Security
- **HTML escaping extended** — `h()` now escapes single quotes (`'` → `&#39;`) in all rendered output. Prevents XSS via ticker names in shareable `?ticker=` links.
- **Ticker query param validation** — `?ticker=` URL parameter is now validated against `^[A-Z0-9&-]+$` before any API call. Invalid tickers show a warning instead of triggering yfinance lookups.

### Fixed
- **RSS feed timeout** — `feedparser.parse()` now uses `timeout=10` to prevent a single slow RSS source from hanging the entire analysis pipeline indefinitely.
- **DuckDuckGo rate-limit cooldown** — Separate 60s cooldown added for DDGS fallback. If DDGS returns a captcha/error page, all subsequent DDGS calls skip for 60s.
- **Thread-safe rate-limit cooldown** — `_RATE_LIMITED_UNTIL` is now protected by `threading.Lock`, preventing races when briefing mode runs 5 parallel workers.
- **Retry skips sleep during cooldown** — If yfinance calls enter a global rate-limit cooldown during retry backoff, the sleep is skipped so retries happen faster instead of burning time.

### Changed
- **Contact info consolidated** — Email, X handle, and Chai4Me URL are now in a single `CONTACT` dict at the top of `app.py`. All 5 references (sidebar, footer, privacy policy, disclaimer, Chai4Me button) draw from it.

## [2.4.0] — 2026-06-21

### Added
- **Rate limiter** — Per-session throttle (6 searches/minute) prevents rapid-fire clicking from burning through shared yfinance quota under multi-user load. Warning message shows cooldown remaining.
- **Cache pruning** — `cache.json` capped at 500 entries. Oldest entries evict automatically when limit exceeded, preventing unbounded file growth on multi-tenant Streamlit Cloud.
- **Streamlit config** — `.streamlit/config.toml` with `maxCacheSize=250`, CORS, XSRF, and dark theme baked into the Streamlit Cloud build settings.

### Changed
- **VWAP skipped during rate-limit cooldown** — `compute_vwap()` fires a separate `yf.download()` call. Now it's gated behind the same rate-limit cooldown as stock data fetches. Reduces yfinance pressure when already rate-limited.

### Cleaned
- Removed 7 dead variables in `app.py` — `stock_data`, `headline_scores`, `signal`, `avg_compound`, `signal_emoji`, `source_stats`, `confidence`. These were orphaned when the old inline rendering was extracted to `render_dashboard()`.
- Removed unused `import os` from `data_fetcher.py`.

## [2.3.1] — 2026-06-20

### Added
- **Lucide SVGs in card titles and footer** — Replaced emojis with Lucide folder, bar-chart, check, x, and mail icons in the bottom dashboard cards
- **ATP parse failure feedback** — Non-numeric entry prices now show a warning instead of silently adding the stock without a price
- **Briefing button loading state** — Both sidebar and bottom briefing buttons disable while running to prevent double-trigger
- **Thread-safe file locking** — `threading.Lock` added to `save_sentiment_history` and `update_source_accuracy` to prevent data loss during concurrent portfolio briefing

### Changed
- **Briefing is 5× faster** — `analyze_ticker()` now accepts `quick=True` for briefing mode, skipping all news fetching (9 RSS feeds + DuckDuckGo + Reddit). Per-ticker: ~9s → ~1.5s. Workers increased from 3 to 5.
- **Portfolio/Track Record cards moved to bottom** — Dashboard cards now appear after analysis results (below institutional flow) instead of above the ticker input
- **Ticker validation now accepts hyphens and ampersands** — `str.isalnum()` replaced with `re.match(r'^[A-Z0-9&-]+$')`. BAJAJ-AUTO, M&M, J&KBANK etc. can now be added.

### Fixed
- **Briefing not running** — Stale ticker text in the search input hijacked the if/elif chain, causing the analysis block to run instead of briefing. Briefing now clears stale ticker state.
- **Bottom "Briefing" button was dead** — ⚡ Briefing button had no `if` condition. Clicking it did nothing. Now wired to `st.session_state.run_briefing`.
- **Stale vote indicator** — `elif` for vote status didn't check `last_rec["ticker"] == final_ticker`, showing the wrong ticker's vote. Fixed.
- **30+ regulator aliases removed from news matching** — RBI→SBIN, SEBI→SBIN, DGCA→INDIGO, TRAI→BHARTIARTL, FDA→SUNPHARMA etc. caused false-positive news matches. Removed.
- **RSI division by zero** — `gain / loss` when `loss = 0` produced `inf`. Now clamped to 100.
- **Empty news caching** — Empty results (all feeds down) were cached for 15 minutes, blocking recovery. Now only non-empty results are cached.
- **Missing `encoding="utf-8"` on all file I/O** — Every `open()` call in `persistence.py` now uses `encoding="utf-8"`. Was crashing on Windows with ₹/Unicode characters.
- **Duplicate CSV column headers** — `fieldnames = ["date", "ticker"] + HISTORY_FIELDS` doubled date/ticker columns since `HISTORY_FIELDS` already included them. Fixed.
- **Portfolio badge substring match** — `"SBIN" in "SBINVIT SURGES"` returned True. Now uses word-boundary regex.
- **Missing `import re`** — `re.match()` and `re.search()` were used without importing `re`. Added.
- **NaN avg_vol** — `float(pd.NA)` propagated NaN to volume spike detection. Now guarded with `pd.isna()`.
- **Empty portfolio Back button** — Briefing with no portfolio showed a warning with no way to navigate back. Added "← Back" button.

## [2.2.1] — 2026-06-20

### Changed
- **App loads faster** — Removed unused code paths and consolidated duplicate configuration. Smaller codebase = less to maintain.
- **Reddit: no more local CLI setup** — Removed the `rdt-cli` fallback. Reddit now works exclusively through OAuth (the cloud-friendly path). If you have OAuth env vars set, Reddit posts show up; if not, they're skipped — no extra tools needed.
- **Volume spike detection wired to dashboard** — `detect_volume_spike()` was already tested and ready, now it powers the volume spike badges you see on each holding. No change in behaviour, just cleaner under the hood.

### Fixed
- **Sentiment history CSV had a mislabeled column** — The `neg_count` field in exported CSVs was actually storing neutral headline count instead of negatives. Exports now correctly label negative headline counts.

## [2.2.0] — 2026-06-20

### Added
- **Portfolio P&L Tracking** — Set entry price when adding a stock. Sidebar shows live P&L (₹ and %) per holding, green for profit, red for loss.
- **Market Heatmap** — Compact 3-column grid in sidebar, every holding color-coded by daily % change.
- **Portfolio News Badges** — 📌 In portfolio badge on headlines that mention your holdings.
- **Volume Spike Detection** — `detect_volume_spike()` flags abnormal trading volume (N× 20-day average).
- **Stagnation Warnings** — `detect_stagnation()` flags stocks stuck in a tight range for 10+ days.

### Changed
- New entry price column in add-ticker row (sidebar)
- Metrics grid on landing page expanded from 4 to 6 columns

### Fixed
- **Trend sparkline blank on first analysis** — `render_sparkline()` now draws a dashed flat line + dot for single data points instead of returning empty SVG. Users see their SmartScore level immediately on first use.

## [2.1.3] — 2026-06-20

### Added
- **Shareable Snapshot Links** — Every ticker now has a public URL (`?ticker=RELIANCE`) showing SmartScore, signal, and price. Share on Telegram/WhatsApp/X. Full analysis unlocks behind the paywall.
- **Public changelog** — This file. Users can see what's new.
- **Feature request channel** — Feedback form linked in sidebar.

### Fixed
- **ETF 52W proximity crash** — `None` price (ETFs) caused `TypeError` in the proximity badge calculation. Guarded with `_is_valid_num()`.

## [2.1.2] — 2026-06-20

### Fixed
- **ETF NaN prices** — ETFs (NIFTYBEES, GOLDBEES, MIDCAPETF) showed `₹nan` and `nan%` because `float('nan')` is truthy in Python. Added `_nf()` NaN-safe extractor and `_is_valid_num()` guards throughout.

## [2.1.1] — 2026-06-20

### Changed
- Removed duplicate emoji-to-SVG mapping, consolidated to `get_signal_icon()`
- Collapsed 15-line if/elif sentiment chain to 7-line dict lookup
- Moved lazy imports to module level
- Removed 6 redundant `str()` wrappers

### Fixed
- Dashboard iframe height: formula-based (`2200 + n_news*120`)
- Mobile-responsive CSS breakpoints

## [2.1.0] — 2026-06-20

### Added
- 504 ticker aliases (was 72)
- 18 event types (was 13): `RATING_UPGRADE`, `JV_MOU`, `FUNDRAISE`, `CONTRACT_LOSS`, `DIVESTMENT`
- Bayesian calibration visible in dashboard
- 270 NSE tickers (was 85)

## [2.0.0] — 2026-06

### Added
- Bayesian source calibration (learns from 👍/👎 votes)
- Optional FinBERT transformer (`USE_FINBERT=true`)
- Lucide SVG icons throughout (replaced Unicode emojis)
- Yahoo Finance retries with jitter + suffix fallback

## [1.0.0] — 2026-05

### Added
- Initial release
- Live NSE stock data via yfinance
- Multi-source RSS news sentiment
- SmartScore composite (0-100)
- Technical indicators (RSI, SMA, MACD)
- Portfolio tracking
- Dark-themed HTML dashboard
