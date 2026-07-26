# Changelog

## [2.11.0] — 2026-07-16

### Fixed

- **Missing `yfinance` import in app.py** — `_fetch_portfolio_price()` called `yf.Ticker()` but `import yfinance as yf` was nowhere in the module. Crashed with `NameError` on any portfolio price refresh. Fixed with a one-line import.

- **Broken pyproject.toml build backend** — `build-backend` was set to the nonexistent `setuptools.backends._legacy:_Backend`. Changed to `setuptools.build_meta`. `pip install -e .` and `python -m build` now work.

- **`analyze_ticker()` quick mode leaked futures** — The `quick=True` path submitted all 3 parallel tasks (stock + news + FII) but then returned before consuming the news future. The `ThreadPoolExecutor.__exit__` blocked waiting for the news search to finish, negating the purpose of quick mode. Restructured so quick mode only submits stock + FII (2 workers), skipping news entirely.

- **Persistence read/write race conditions** — `load_source_accuracy()` and `load_sentiment_history()` had no thread locks while their write counterparts (`update_source_accuracy()`, `save_sentiment_history()`) did. Added `with _accuracy_lock` / `with _history_lock` to both readers. Changed all three locks to `RLock` for safe reentrancy since `update_source_accuracy()` calls `load_source_accuracy()` internally.

### Tests

- **218 passed, 0 failed** — zero regressions.

### Added
- **L2 disk cache for price history** — `get_cached_history()` now has a 3-tier cache: L1 (in-memory dict, same session), L2 (`.price_cache/` JSON files on disk, survives Streamlit Cloud restarts), and L3 (yfinance network call). 7-day TTL for disk cache entries. Cache directory auto-cleaned via LRU eviction when the in-memory limit is exceeded. Significantly faster cold starts after Streamlit Cloud deployments.
- **`get_stock_info()` deduplication** — The persistence cache hit path now populates `_hist_cache` via `get_cached_history()`, removing 14 lines of duplicated yfinance fetch logic. Eliminates redundant network calls on subsequent technical indicator computation.
- **205 tests** (was 197) — 8 new tests covering L1/L2/L3 hit paths, LRU eviction, disk cache corruption fallback, mtime-based eviction, nonexistent tickers, and disk write-through verification.

### Fixed
- **Static dates in aggregate sentiment test** — `test_history_affects_recency` used hardcoded 2026-06 dates that would fail in 2027. Now generates dates dynamically relative to current time.

## [2.9.0] — 2026-06-27

### Added
- **CASCADE_MAP expanded** — 8 drivers, 27 tickers. Added ONGC to Crude Oil (upstream, direction -1), pharma exporters (SUNPHARMA, DRREDDY, CIPLA, DIVISLAB) to Rupee/USD, new **Sugar** driver (BAJAJHIND, BALRAMPUR, DHAMPUR, TRIVENI, DCMSHRIRAM), and new **Aluminum** driver (HINDALCO, NATIONALUM). 5 new tickers + aliases in NSE_TICKERS.
- **Commodity-specific RSS feeds** — `COMMODITY_RSS_FEEDS` with Moneycontrol Commodities, ET Commodities, and Google News Commodities search. `fetch_market_headlines()` fetches from both INDIA_RSS_FEEDS and COMMODITY_RSS_FEEDS in parallel (ThreadPoolExecutor max_workers=8), with DuckDuckGo fallback when RSS returns fewer than 3 articles.
- **Home page cascade card** — `fetch_market_headlines()` deduplicates and returns all market + commodity headlines (5-min cache). `app.py` empty-state renders inline cascade card via `st.markdown()` with self-contained CSS.
- **Expanded direction keywords** — `_DIR_UP` now includes `bullish`, `tightens?`, `uptick`, `upswing`, `upward`, `inflow`. `_DIR_DOWN` now includes `bearish`, `glut`, `selloff`, `dip`, `eases?`, `eased`, `outflow`.

### Changed
- **Per-ticker direction refactor** — `affects` tuples changed from 3-field `(ticker, bad_reason, good_reason)` to 4-field `(ticker, direction, bad_reason, good_reason)` where `direction` is per-ticker sensitivity to commodity rise (+1 = bad, -1 = good). `detect_cascade()` computes `ticker_impact = article_direction × ticker_dir`. Render shows per-ticker Bullish/Bearish labels instead of driver-level label.
- **`fetch_market_headlines()` dual feed sources** — Now fetches from both INDIA_RSS_FEEDS and COMMODITY_RSS_FEEDS, with DDG fallback for light RSS days.

### Fixed
- **Cascade card not showing on home page** — Was only available on the ticker analysis page. Now the home page empty-state renders an inline cascade card with market + commodity headlines.

## [2.8.1] — 2026-06-27

### Fixed
- **Cascade card invisible for most tickers** — `_parse_rss_feed()` was filtering out broader market headlines ("Crude oil surges", "Rupee weakens") via `_relevant()` before cascade could scan them. Now returns a separate `cascade_pool` containing all unfiltered market feed items; `detect_cascade()` scans this broader pool instead of ticker-filtered display items. On cache hit, falls back to display items (same as before) — benefit is on fresh fetches.
- **Cascade direction label inverted** — Arrow was pointing down and label showed "Bullish" (green) for commodity price increases. Fixed: arrow now points up when commodity price rises, and the label is always "Bearish" (red), reflecting the negative impact on affected tickers.
- **Cascade direction hardcoded — never matched article content** — `CASCADE_MAP.direction` was always used verbatim, regardless of whether the article said "crude surges" (price up) or "crude crashes" (price down). Now `detect_cascade()` scans matched article text for direction keywords (`surge`/`jump`/`rally` → up, `fall`/`crash`/`slump` → down) and infers whether the commodity is actually rising or falling. When detected, the `impact` field flags whether the movement is Bearish (bad for tickers) or Bullish (good). On ambiguous/no-direction articles, defaults to cautious (Bearish + CASCADE_MAP default arrow).
- **UTF-8 `open()` crash on Windows** — `app.py` and `tests/test_changelog.py` called `open()` on CHANGELOG.md without `encoding="utf-8"`, causing `UnicodeDecodeError` on Windows with UTF-8 content. Added `encoding="utf-8"` at both call sites.

### Changed
- **`_parse_rss_feed()` return signature** — Now returns `(relevant_items, all_items, label)` instead of `(items, label)`. `all_items` skips the `_relevant()` filter and includes every parsed market feed article.
- **`search_news()` return signature** — Now returns `(display_items, cascade_pool, source_stats)` instead of `(items, source_stats)`. `cascade_pool` is a deduplicated superset of all fetched articles.
- **`analyze_ticker()` cascade wiring** — Passes `cascade_pool` (broader set) instead of `news_items` to `detect_cascade()`.
- **`detect_cascade()` result now includes `impact` field** — `+1` = Bearish (bad for tickers), `-1` = Bullish (good for tickers). Derived from: `inferred_article_direction × CASCADE_MAP.direction`. Used by `render.py` to show the correct green/red label instead of hardcoded "Bearish".
- **`_render_cascade_html()` label now dynamic** — Reads `effect["impact"]` to show green "Bullish" (+22b573) or red "Bearish" (#f85149) instead of always red.
- **Direction keyword regexes** — `_DIR_UP` and `_DIR_DOWN` compiled at module scope. 35+ total terms covering surge, jump, rally, climb, soar, rebound, spike, hike, gain, rise, skyrocket, appreciate (up) and fall, drop, decline, slump, plunge, tumble, sink, crash, collapse, weaken, slide, plummet, tank, nosedive, depreciate (down).
- **`\bcrude\b` tightened** — Now uses negative lookahead `(?!\s+steel\b)` to avoid false matching "crude steel output".
- **Removed redundant `\bRupee\b` pattern** — All CASCADE_MAP patterns are compiled with `re.IGNORECASE`, so lowercase `\brupee\b` already covered "Rupee".
- **CHANGELOG.md sidebar read cached** — File is now read once per session via `st.session_state._changelog_cache` instead of on every page rerun.
- **Ticker mention scanning** — `detect_cascade()` now scans matching articles for each ticker symbol and company name. Only tickers mentioned in the article text are included in the results. Falls back to all tickers if none are mentioned (no false empty cards).
- **Direction-aware impact reasons** — Each ticker in CASCADE_MAP now has two reasons: one for when the commodity move is bad (Bearish) and one for when it's good (Bullish). `detect_cascade()` picks the matching reason based on the inferred impact direction.
- **Searched-ticker highlighting** — `detect_cascade()` accepts `focus_ticker` parameter. Only commodities that affect the searched ticker are shown. The searched ticker sorts first in the affects list. `render.py` adds `cascade-searched` CSS class for visual promotion.
- **`focus_ticker` wired in `app.py`** — `detect_cascade(cascade_pool, ticker_lookup=NSE_TICKERS, focus_ticker=ticker)` makes the cascade card ticker-specific.
- **197 tests** (was 191) — 6 new tests covering ticker mention scanning, fallback behavior, focus_ticker filtering, focus_ticker sorting, and direction-aware reason selection.

## [2.8.0] — 2026-06-28

### Added
- **Cascade / Ripple Tracking** — When news mentions a macro driver (crude oil, rupee, gold, steel, natural gas, coal), the dashboard now shows which other tickers are indirectly affected and why. Hand-curated relationship map covers 6 commodity groups and 20+ tickers across OMCs, aviation, paints, IT, gold, steel, city gas, coal/power, and logistics. No extra network calls — reuses already-fetched news text. See [`cascade.py`](cascade.py).
- **184 tests** (was 171) — 13 new tests covering commodity keyword detection, multiple-commodity hits, false-positive rejection, company name resolution, and matched-article counting.

## [2.7.1] — 2026-06-27

### Fixed
- **17 duplicate keys in ALIASES dictionary** — Removed redundant first occurrences of 16 entries that mapped to the same ticker, plus one stale `"TATA MOTORS" → "TATAMOTORS"` that was silently overwritten by the correct post-split mapping `"TATA MOTORS" → "TMPV"`. Alias dictionary now has 461 clean unique entries.
- **Unused import `get_market_verdict`** — Removed from app.py. Leftover from the MMI system replacing the old Market Climate verdict in v2.7.0.
- **Race condition in `save_fiidii_snapshot`** — Added `_fiidii_lock` thread lock to prevent duplicate FII/DII entries under concurrent requests.

### Changed
- **Extracted inline closures to module-level functions** — `_ddgs_search` in data_fetcher.py and `_fetch_portfolio_price` in app.py are now testable module-level functions instead of closures defined inside other functions.
- **Added `__version__ = "2.7.1"`** to app.py for runtime version checking.

## [2.7.0] — 2026-06-26

### Added
- **Market Mood Index (MMI)** — 0–100 fear & greed gauge in the Market Pulse card. 4 equally-weighted components: Trend Strength (Nifty vs 20-day SMA), VIX Fear Gauge (inverted India VIX), FII Money Flow (institutional confidence vs 21-day trailing average), Market Breadth (sector advance/decline ratio across 10 sectoral indices). Replaces the previous binary Climate verdict with a 5-zone system (Extreme Fear → Extreme Greed). Sub-scores shown for each component. All data from yfinance + existing FII history — zero new API dependencies.

## [2.6.0] — 2026-06-23

### Added
- **Smart ticker resolution** — Type any company name, alias, or partial name and get the correct NSE ticker automatically. Resolution chain: local dictionary (instant) → ALIASES (instant) → Yahoo Finance REST API (~0.5s) → yfinance SDK Search (~1s) → direct ticker probe (~1s). Results cached in memory (500 entries).
- **504 aliases for company name → ticker** — "HDFC Bank" → HDFCBANK, "SBI" → SBIN, "L&T" → LT, etc. Case-insensitive. Works with or without spaces.
- **Rebranding and split handling** — Zomato → ETERNAL (rebranded to Eternal Ltd), Tata Motors → TMPV/TMCV (passenger/commercial split). Stale tickers updated, aliases added.
- **Direct ticker probe** — When search APIs fail, tries the query as a `.NS` ticker directly via yfinance. Handles stocks Yahoo's search index doesn't cover.
- **Yahoo Finance REST API search** — Fast (~200ms) ticker lookup by company name. Filters for NSE-listed stocks. Primary online fallback.
- **Rate limit auto-retry** — When yfinance is rate-limited (429), waits for the cooldown period and retries automatically instead of failing immediately. Shows "⏳ Waiting Xs..." info banner.

### Fixed
- **"Could not find data for HDFC BANK"** — User-typed company names with spaces now resolve to correct tickers via ALIASES before hitting yfinance. No more manual ticker lookup required.
- **Rebranded stocks failing** — Zomato (now Eternal), Tata Motors (now split) resolve correctly. ALIASES and NSE_TICKERS updated for current market.
- **Rate limit showed scary error** — Now waits and retries instead of immediately showing "Could not find data" on transient rate limits.

## [2.5.9] — 2026-06-23

### Added
- **Autocomplete ticker search** — Type-ahead dropdown appears as you type in the search box, showing matching NSE tickers and company names. Filters all 271 tickers client-side (instant, no network calls). Shows up to 8 results with highlighted matches. Click a result to fill the ticker and trigger analysis. Minimum 2 characters to activate.

## [2.5.8] — 2026-06-23

### Fixed
- **Ticker search extremely slow (~13s+)** — Root cause: `get_fii_dii_flow()` (8.5s) ran sequentially after the spinner closed, freezing the page with no loading indicator. Now runs in parallel with stock info + news fetch via ThreadPoolExecutor (3 workers). Total search flow dropped from ~13s to ~2s.
- **Deadlock in `_hist_cache_lock`** — `_evict_hist_cache()` was called while already holding the non-reentrant `threading.Lock`, causing indefinite hangs in tests and occasional production deadlocks. Inlined the eviction logic at all 3 call sites.
- **ETF searches wasted ~2s on useless retries** — Phase 2c (sector/industry retry) fired for every ETF because their `sector`/`industry` fields are legitimately `None`. Now only retries when the info response was sparse (<30 keys, meaning rate-limited) or fields are explicitly `"N/A"`.
- **Cache hits caused redundant yfinance calls** — When `get_stock_info` returned from the persistence cache, it skipped populating `_hist_cache`. Downstream `get_cached_history()` and `get_technical_indicators()` then made separate yfinance calls. Now populates `_hist_cache` on every cache hit.
- **Retry backoff too aggressive** — Phase 1 used 1s/2s waits, Phase 2 used 2s/4s waits between retries. Reduced to 0.5s/1s and 1s/2s respectively.

### Changed
- **Parallelized `get_stock_info` + `search_news` + `get_fii_dii_flow`** — All three independent network calls now run concurrently via `ThreadPoolExecutor(max_workers=3)`. Bottleneck is the slowest single call (~2s) instead of the sum (~13s).

## [2.5.7] — 2026-06-23

### Fixed
- **Portfolio entry prices loaded once per page** — Removed redundant `load_entry_prices()` call inside the bottom card renderer. Prices are now loaded once in the sidebar and passed to both views, saving a file read on every page load.
- **Price refresh failures now visible** — If Yahoo Finance can't fetch a portfolio holding's price, the app now shows a warning listing which tickers failed (instead of silently logging to the console).
- **Removed redundant import in chart renderer** — `math` was imported twice in `render.py` (module level + function body). Kept the module-level import, removed the local duplicate.

### Changed
- **`_render_bottom_cards()` signature** — Now accepts `entry_prices` as a parameter instead of calling `load_entry_prices()` internally. Cleaner function boundary, less I/O.

## [2.5.6] — 2026-06-22

### Added
- **Institutional flow card** — Glassmorphism card showing latest FII/FPI and DII net flow (₹ Cr) with Net value. Compact table below shows last 7 days of history (Date, FII/FPI, DII, Net). Daily snapshots auto-saved to `fiidii_history.json` (90-day rolling) whenever FII/DII data is fetched.
- **Shares quantity field** — New Qty input alongside ATP in the add-ticker form. Quantity defaults to 1 if left blank. P&L calculations are now qty-weighted: `(price − entry) * qty`.
- **Auto-fetch LTPs for all portfolio holdings** — `_refresh_price_cache()` batch-fetches yfinance prices for any portfolio ticker missing from the session cache on every page load. Previously prices only showed for tickers you'd searched.
- **Clear portfolio buttons** — "Clear all holdings" in both the sidebar (below portfolio list) and the main portfolio card area. Wipes portfolio list + entry prices in one click.

### Changed
- **Portfolio entry price format** — Changed from flat `{ticker: price}` to nested `{ticker: {price, qty}}`. Old format auto-migrated on load via `get_entry_info()` helper.
- **Sentiment History collapsed by default** — Converted from raw `<details>` HTML to `st.expander(expanded=False)`. No longer takes up vertical space until clicked.
- **FII/DII card simplified** — Removed line chart, unified to show latest day's FII/FPI, DII, and Net values with green/red coloring.
- **Add button icon** — Replaced Lucide SVG attempt (unreliable with Streamlit's DOM) with clean `"+"` button label.
- **Sidebar portfolio list** — Now displays holdings with delete buttons and a Clear All button. Previously the sidebar loaded the portfolio but never rendered it.
- **Summary stats qty-weighted** — Invested and Current values now use `price × qty` instead of summing prices directly.

### Fixed
- **Rate limiter blocking add/delete** — Moved rate-limiter check inside `_skip_reanalysis` guard so cache-hit reruns (portfolio add/delete) skip the 20 s cooldown.
- **Empty state on rerun after add** — Persisted active ticker in `st.session_state._active_ticker` so portfolio add/delete buttons preserve the current stock view across reruns.
- **Clear button inline import** — Moved `ENTRY_PRICES_FILE` import to top-level to prevent silent failure in Streamlit's execution context.

## [2.5.5] — 2026-06-22

### Fixed
- **Dashboard content cut off on mobile** -- iframe had `scrolling=False`, so if the auto-height script failed to fire (CSP, Streamlit version), content below Source Calibration was inaccessible. Changed to `scrolling=True` as fallback. Also relaxed `.cal-src` min-width on mobile to prevent horizontal overflow.
- **Portfolio card HTML structure broken** -- `<div class="btm-card">` was split across separate `st.markdown` calls, causing heatmap and portfolio rows to render OUTSIDE the card wrapper (no background, no border, no padding). Refactored: card title + heatmap + rows + summary now render in ONE `st.markdown` call via `_build_heatmap_html`, `_build_portfolio_rows_html`, `_build_portfolio_summary_html` helpers. Track record card fixed the same way.
- **Heatmap 0% change showed as green** -- `if chg >= 0` caught zero as positive. Fixed to three-way: `> 0` green, `< 0` red, `== 0` neutral gray.
- **DuckDuckGo fallback could hang indefinitely** -- When RSS feeds returned few results and DuckDuckGo was slow or unresponsive, the news fetcher would block forever. Now wrapped in a 15-second timeout via `ThreadPoolExecutor`; triggers rate limiter on timeout instead of hanging.
- **Search button breaking on Streamlit updates** — The custom search button used a single DOM selector (`input[placeholder*="RELIANCE"]`) that broke when Streamlit changed its internal DOM structure. Now tries three fallback selectors for resilience.
- **Thread lock contention between unrelated operations** — Sentiment history saves (CSV) and source accuracy updates (JSON) shared a single lock, blocking each other unnecessarily. Split into two independent locks.
- **Stale aliases pointing to non-existent tickers** — Removed `KTKBANK`, `DCBBANK`, `DHANBANK`, `SBICARD`, `IOB`, `PSB` aliases that mapped to tickers not in the NSE ticker database, causing silent match failures.

### Changed
- **Portfolio section visual overhaul** — Heatmap tiles now have color-coded backgrounds (green tint for gainers, red for losers) with bigger text and proper grid layout. Portfolio rows use compact single-line layout with CSS classes (`.pf-row`, `.pf-ticker`, `.pf-price`, `.pf-pnl-*`) instead of markdown separators. New summary row shows total invested, current value, P&L %, and day change. Track Record card redesigned with large color-coded accuracy percentage, visual progress bar, and Scans/Right/Wrong stat row. Mobile: heatmap collapses to 2 columns.
- **yfinance session handling documented** — Removed private `yf._session` attribute patch (breaks on yfinance upgrades). Added comments explaining the semi-public `yf.utils._session` approach for future maintainers.
- **Iframe height estimation documented** — Added comments clarifying that the hardcoded height is a safe default, with the auto-height script in render.py handling real adjustment via `postMessage`.

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
