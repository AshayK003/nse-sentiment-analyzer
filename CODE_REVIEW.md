# NSE Sentiment Analyzer — Comprehensive Code Review

## File-by-File Analysis

---

## 1. app.py (746 lines) — Main Streamlit App

### CRITICAL: Ticker validation rejects hyphenated NSE tickers
**File: app.py, Line 201**
```python
if not t.isalnum():
    st.warning("Invalid ticker format")
```
`str.isalnum()` returns `False` for hyphens (`-`), ampersands (`&`), and slashes (`/`). Valid NSE tickers like `BAJAJ-AUTO`, `MCDOWELL-N`, `M&M`, `J&KBANK` will **always** be rejected by portfolio add. The user gets a "Invalid ticker format" warning and cannot add these stocks.

### CRITICAL: Bottom "Briefing" button does nothing
**File: app.py, Line 580**
```python
st.button(f"{_ZAP} Briefing", type="primary", use_container_width=True,
          key="btm_brief", help="Run portfolio briefing")
```
This button has no `on_click` callback, does not set any session state flag, and its `if` condition is never bound to any action. Clicking it is a **complete no-op** — the sidebar's Briefing button (`app.py:280`) sets `st.session_state.run_briefing = True`, but the bottom card version is dead UI.

### HIGH: Stale vote indicator on ticker mismatch
**File: app.py, Lines 505-506**
```python
elif last_rec and last_rec.get("vote") is not None:
    st.caption(f"You marked this signal as {'✅ accurate' if last_rec['vote'] else '❌ inaccurate'}")
```
`last_rec = records[-1]` fetches the most recent track record entry regardless of which ticker it belongs to. If you search RELIANCE after voting on HDFCBANK, the caption still shows HDFCBANK's vote status. Missing ticker comparison (`last_rec["ticker"] == final_ticker`).

### MEDIUM: Silent entry price parse failure
**File: app.py, Lines 207-211**
```python
try:
    save_entry_price(t, float(ep_input.strip().replace(",", "")))
except ValueError:
    pass
```
If the user enters a non-numeric ATP (e.g. "abc"), the `ValueError` is swallowed silently. The stock is added to the portfolio **without** the entry price, but the user gets no feedback. The same pattern exists on line 554.

### MEDIUM: Ticker text input has no `key` attribute
**File: app.py, Lines 373-378**
```python
ticker_input = st.text_input(
    "NSE Ticker Symbol",
    placeholder="e.g., RELIANCE, HDFCBANK, TCS, NYKAA, ZOMATO",
    max_chars=15,
    label_visibility="collapsed",
)
```
No explicit `key=`. Streamlit auto-generates one, which is fine here since it's the only instance, but it's inconsistent with all other inputs and fragile if refactored.

### MEDIUM: `change_pct or 0` pattern masks zero values
**File: app.py, Line 229** (and line 561)
```python
chg = sd_cache.get("change_pct") or 0
```
When `change_pct` is literally `0.0` (no price change today), `0.0 or 0` evaluates to `0` due to Python's falsy-zero. Functionally identical, but the `or` pattern wrongly suggests `change_pct` could be `None`. Safer: `sd_cache.get("change_pct", 0) or 0`.

### MEDIUM: Redundant yfinance call duplicates existing data
**File: app.py, Lines 452-453**
```python
import yfinance as yf
_hist = yf.download(f"{final_ticker}.NS", period="5d", progress=False, auto_adjust=True)
```
`get_stock_info` already fetched 1-year history and stored it in `_hist_cache` (data_fetcher.py:692). This second call for 5-day data is wasteful and increases rate-limit risk. Could reuse `_hist_cache[final_ticker]`.

### MEDIUM: Implicit import inside function body
**File: app.py, Line 451-452**
```python
import yfinance as yf
_hist = yf.download(...)
```
`yfinance` is already a dependency of `data_fetcher.py`, but importing it again inside the function is unconventional and could be confusing. Should be a top-level import or use `data_fetcher._hist_cache`.

### LOW: Portfolio badge uses substring match — false positives
**File: app.py, Lines 466-469**
```python
item["in_portfolio"] = any(
    t in (item.get("title") or "").upper()
    for t in portfolio
)
```
`"SBIN" in "SBINVIT SURGES..."` is `True`. Should use word-boundary regex (`\bSBIN\b`).

### LOW: No loading state for sidebar brief/refresh
**File: app.py, Lines 280-282**
The "Run Portfolio Briefing" button triggers `st.session_state.run_briefing = True` which leads to the briefing mode block (line 619+). But there's no spinner/deactivation — the button stays clickable during the brief, and multiple clicks spawn multiple briefings.

---

## 2. render.py (943 lines) — HTML Dashboard Renderer

### MEDIUM: Direct dict access without `.get()` in multiple places
**File: render.py, Lines 264, 265, 302**
```python
price = stock["current_price"]
change_val = stock["change"]
change_pct = stock["change_pct"]
vol_now = stock["volume"]
```
While `get_stock_info` always sets these keys, if a future code path or test passes a partial dict, these crash with `KeyError`. The downstream functions (`_is_valid_num`, `fmt_price`) handle None values, but the raw access doesn't.

### MEDIUM: RSI label from potentially non-finite value
**File: render.py, Lines 420-421**
```python
rsi = ti["rsi"]
rsi_label = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
```
If `rsi` is `inf` or `nan` (see indicators.py issue), comparison with `> 70` returns `False` for nan, and `< 30` also returns `False`, so it shows "Neutral". But the rendered value `rsi:.1f` would display "inf" or "nan" in the UI.

### LOW: Inconsistent naming — label vs CSS class
**File: render.py, Lines 538-546**
The sentiment label uses "Positive" / "Negative" / "Neutral" but the CSS class uses "bullish" / "bearish" / "neutral". Not a bug, but confusing for maintainers.

### LOW: Body text direct key access
**File: render.py, Line 562-563**
```python
body = h(item["body"][:200])
```
Uses direct `item["body"]` instead of `item.get("body", "")`. If a news source doesn't include a "body" key, this crashes. All current sources include it, but the contract is fragile.

### LOW: Accessibility — image icons lack alt text
**File: render.py, random locations**
The `_ICON` SVGs have `aria-hidden="true"` which is correct for decorative icons. But the SmartScore signal icon (`ss_icon`) and sentiment icons (`primary_emoji_svg`) convey meaning only through color — no textual fallback for screen readers.

---

## 3. intraday.py (136 lines) — VWAP, Pivot Levels, VIX

### Edge case: VWAP deviation with small denominators
**File: intraday.py, Line 51**
```python
deviation = ((current_price - vwap_val) / vwap_val) * 100 if vwap_val else 0.0
```
When `vwap_val` is very near zero (e.g. penny stocks), the percentage can be enormous (±100,000%). While `_is_valid_num` guards downstream, the deviation_pct could be an extreme value. No clamping.

### Defensive coding is good here
The try/except blocks at lines 32-49 gracefully handle missing columns, empty DataFrames, and zero-volume edge cases. `float(vol_sum) == 0` check prevents division by zero. `get_vix` is fully wrapped in try/except. These functions handle failure well.

---

## 4. aggregate_sentiment.py (194 lines) — SmartScore

### LOW: `history` date parsing assumes `%Y-%m-%d` format
**File: aggregate_sentiment.py, Line 124**
```python
d = datetime.strptime(h["date"], "%Y-%m-%d")
```
If the CSV date column has a different format (e.g. ISO with time component), `strptime` raises `ValueError`, which is caught by the `except (ValueError, TypeError)` on line 129-130. Gracefully handled but silently drops the row.

### Well-structured
The EWMA decay weights, component scoring, and signal thresholds are clean. The `_empty_result` path handles zero-headline edge case properly.

---

## 5. sentiment.py (191 lines) — VADER + FinBERT

### Confusing: Signal and blended_compound can disagree
**File: sentiment.py, Lines 181-189**
```python
if blended >= 0.2 and pos_count > neg_count:
    signal = "BULLISH 🟢"
elif blended <= -0.2 and neg_count > pos_count:
    signal = "BEARISH 🔴"
```
The signal requires BOTH a blended threshold AND a majority-count check. If `blended = 0.5` (from high-weight sources) but `pos_count == neg_count` (equal number of pos/neg headlines), the return is `("NEUTRAL ⚪", 0.5, "⚪", ...)`. The returned `signal` says neutral but the `blended_compound` says positive. Downstream code uses both values inconsistently.

### Good handling of optional FinBERT
The `get_finbert()` / `analyze_headline_finbert()` path is properly isolated behind env var `USE_FINBERT`, with graceful fallback to VADER. Exception handling in `analyze_headline_finbert` (line 132-133) ensures FinBERT failures don't crash the pipeline.

---

## 6. data_fetcher.py (1029 lines) — yfinance + News

### CRITICAL: Regulatory aliases cause pervasive false-positive news matches
**File: data_fetcher.py, Lines 562-581**
```python
"RBI": "SBIN",          # Reserve Bank of India → State Bank of India ❌
"SEBI": "SBIN",         # Market regulator → SBI ❌
"IRDAI": "SBILIFE",     # Insurance regulator → SBI Life ❌
"DGCA": "INDIGO",       # Aviation regulator → Indigo ❌
"TRAI": "BHARTIARTL",   # Telecom regulator → Airtel ❌
"CERC": "NTPC",         # Power regulator → NTPC ❌
"DGGI": "ITC",          # Tax enforcement → ITC ❌
"FDA": "SUNPHARMA",     # US drug regulator → Sun Pharma ❌
"ED": "SBIN",           # Enforcement Directorate → SBI ❌
"CBI": "SBIN",          # Central Bureau of Investigation → SBI ❌
"NCLT": "SBIN",         # Company law tribunal → ALL stocks to SBI ❌
```
These are **semantically incorrect**. A news headline about "RBI hikes repo rate" will match SBIN's analysis because `_alias_terms("SBIN")` returns `{'rbi', 'sebi', 'ed', 'cbi', ...}` from these aliases, and `_relevant()` matches any word in the text. This means:
- Every RBI/SEBI/CBI news article falsely appears in SBIN's analysis
- Every DGCA article falsely appears in INDIGO's analysis
- Every TRAI article falsely appears in BHARTIARTL's analysis
- The alias terms also expand the matching words for `_relevant()`, so even headlines mentioning "regulatory" loosely can match

### HIGH: Empty news results cached, blocking updates for 15 minutes
**File: data_fetcher.py, Line 1026**
```python
cache_set(f"news_{ticker}", (all_results, source_stats))
```
This caches the result unconditionally — even when `all_results` is empty (all RSS feeds down). The default cache TTL is 15 minutes (`CACHE_TTL = 15 * 60` in persistence.py). If the first search in 15 minutes hits all-down RSS, the user gets empty news for the next quarter hour.

### MEDIUM: Reddit OAuth token stored in module globals (non-thread-safe)
**File: data_fetcher.py, Lines 815-816**
```python
_REDDIT_TOKEN = None
_REDDIT_TOKEN_EXPIRY = 0
```
During portfolio briefing (ThreadPoolExecutor), multiple threads call `_fetch_reddit_oauth` simultaneously. The global `_REDDIT_TOKEN` and `_REDDIT_TOKEN_EXPIRY` have a **race condition**: two threads can check expiry simultaneously, both see expired token, and both fetch a new token. While not harmful (just redundant HTTP calls), the global mutation is technically unsafe.

### MEDIUM: `float(vol_raw)` without try/except in info fallback
**File: data_fetcher.py, Lines 711-712**
```python
vol_raw = info.get("volume")
volume = int(vol_raw) if vol_raw is not None and not math.isnan(float(vol_raw)) else 0
```
If yfinance returns `vol_raw` as a string or non-convertible type, `float(vol_raw)` raises `TypeError`/`ValueError`. Since this is inside the main try/except (line 742), it would be caught and return `None` — but the error message (`st.error(...)`) would mislead users into thinking the ticker is invalid rather than just a volume parse issue.

### MEDIUM: Heavy import inside hot path
**File: data_fetcher.py, Line 835**
```python
from duckduckgo_search import DDGS
```
Imported at module level (line 18), so not a per-call issue. But the `feedparser` and `requests` imports... let me verify. Line 6: `import requests`, Line 7: `import feedparser`, Line 18: `from duckduckgo_search import DDGS` — all at module level. Fine.

### LOW: Hardcoded 0.5s sleep between Reddit queries
**File: data_fetcher.py, Line 899**
```python
time.sleep(0.5)
```
Hardcoded delay. If rate limits change, this needs code change. Minor.

---

## 7. market_data.py (53 lines) — FII/DII

### Good: Clean, well-defended
The `@st.cache_data(ttl=3600)` caches for 1 hour. The `except Exception` catch-all on line 52 returns `None` gracefully. The `action()` helper function with hardcoded ₹200 Cr threshold is reasonable for market-wide data.

### LOW: Hardcoded threshold ₹200 Cr for "Buying"/"Selling" classification
**File: market_data.py, Lines 36-42**
```python
def action(net):
    if net > 200:
        return "Buying"
    elif net < -200:
        return "Selling"
    else:
        return "Flat"
```
₹200 Cr is a reasonable default, but on low-volume days, even ₹150 Cr could be significant. The threshold is not configurable.

---

## 8. event_classifier.py (253 lines) — Event Classification

### MEDIUM: Non-thread-safe lazy compilation in `_get_compiled`
**File: event_classifier.py, Lines 192-200**
```python
def _get_compiled():
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = [...]  # compile patterns
    return _COMPILED
```
During portfolio briefing, multiple threads call `classify_headline` → `_get_compiled`. The `if _COMPILED is None:` check is a **race condition** — two threads could both see `None` and compile duplicate pattern lists. The compiled regex objects are identical, so no data corruption, but work is duplicated. Low severity.

### MEDIUM: First-match-wins can miss stronger negative signals in mixed headlines
**File: event_classifier.py, Lines 29-186**
The `EVENT_MAP` is ordered with positive events before negative events. A headline like "XYZ wins $1B contract despite SEBI probe" matches ORDER_WIN (positive, first match) before LITIGATION (negative, later). The positive event masks the negative one. No mechanism to detect or weigh conflicting signals.

### Good: Comprehensive pattern coverage
The event patterns are thorough, use `\b` word boundaries, and use `.*?` between keywords for flexible matching. The `adjust_with_event` blending formula (lines 229-253) is mathematically sound, using VADER confidence to determine blend ratio.

---

## 9. indicators.py (102 lines) — RSI, MACD, Bollinger Bands

### HIGH: Division by zero in RSI computation
**File: indicators.py, Line 50**
```python
rs = gain / loss
```
When `loss` is 0 (no downward price movement in the last 14 days), `gain / loss` produces `inf`. Then:
```python
rsi = 100 - (100 / (1 + rs))  # = 100 - 100/(1+inf) = 100 - 0 = 100
```
This produces `rsi = 100.0` which is valid. HOWEVER, `float(rsi.iloc[-1])` returns `100.0` in this case, which is fine.

The real issue: if `loss` has ANY zero values in the rolling window before the final row, `rs` has `inf` entries. The `.iloc[-1]` might be `inf` if the trailing window has zero losses. But RSI(14) over 1Y of data is unlikely to have 14 consecutive zero-loss days. In practice, stock prices fluctuate enough. **Low probability but potential for `inf` to propagate.**

### MEDIUM: `avg_vol_50` can be NaN when `len(hist) >= 50`
**File: indicators.py, Line 86**
```python
avg_vol_50 = float(hist["Volume"].rolling(50).mean().iloc[-1]) if len(hist) >= 50 else None
```
`float(pd.NA)` is `nan`. If the 50-day volume rolling mean returns NaN (e.g., all volumes are 0 or missing), `avg_vol_50` becomes `nan`. This NaN propagates to `detect_volume_spike` via `render.py:306`. The check `avg_vol > 0` in `detect_volume_spike` is `False` for NaN, so spikes aren't detected. Safe but `nan` is a landmine for future code.

### MEDIUM: MultiIndex column ambiguity in yfinance DataFrames
**File: indicators.py, Line 44**
```python
close = hist["Close"]
```
Recent yfinance versions can return MultiIndex columns (especially with `auto_adjust=True` or `actions=True`). In that case, `hist["Close"]` returns a **DataFrame** (with columns like "Close" for each ticker), not a **Series**. Operations like `.diff()` work on DataFrames too, but `.iloc[-1]` returns a Series, and `float(...)` conversions might fail. This is a known yfinance quirk.

### LOW: SMA crossover not detected when price equals SMA
**File: indicators.py, Lines 74-83**
Crossovers are detected only when price **crosses** the SMA (one side yesterday, other side today). If price equals the SMA, no crossover is detected. This is standard practice for crossover detection — touch without cross doesn't count. Not a bug, but worth noting the `>` vs `>=` distinction.

---

## 10. persistence.py (284 lines) — JSON/CSV I/O

### CRITICAL: Missing `encoding="utf-8"` on all file opens
**File: persistence.py, Lines 28, 37, 162, 187, 209**
```python
with open(path) as f:           # Line 28
with open(path, "w") as f:      # Line 37
with open(HISTORY_FILE, newline="") as f:  # Line 162, 187
with open(HISTORY_FILE, "w", newline="") as f:  # Line 209
```
No explicit `encoding` parameter. On Windows (cp1252 default), reading/writing UTF-8 files containing the ₹ symbol, Indian language characters, or emoji causes `UnicodeDecodeError` or `UnicodeEncodeError`. Every `open()` call should use `encoding="utf-8"`.

### CRITICAL: Duplicate column headers in sentiment history CSV
**File: persistence.py, Line 205-206**
```python
fieldnames = ["date", "ticker"] + HISTORY_FIELDS
```
Where `HISTORY_FIELDS` (line 146-148) already includes `"date"` and `"ticker"`:
```python
HISTORY_FIELDS = [
    "date", "ticker", "headline_count", "pos_count", "neg_count",
    "avg_compound", "event_avg", "smartscore",
]
```
Result: `fieldnames = ["date", "ticker", "date", "ticker", "headline_count", ...]` — **duplicate columns** in CSV output. The `csv.DictWriter` writes duplicate column headers, which corrupts the CSV file. Any CSV reader will see two "date" and two "ticker" columns.

### CRITICAL: Race condition in `save_sentiment_history` during portfolio briefing
**File: persistence.py, Lines 186-211**
```python
existing = []
try:
    with open(HISTORY_FILE, newline="") as f:
        reader = csv.DictReader(f)
        existing = list(reader)
except (FileNotFoundError, IOError):
    pass

existing = [r for r in existing if not (r.get("ticker") == ticker and r.get("date") == today)]
new_row = {"date": today, "ticker": ticker}
new_row.update(row_data)
existing.append(new_row)

with open(HISTORY_FILE, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(existing)
```
This is a classic **read-modify-write race condition**. During portfolio briefing (`app.py:631`, ThreadPoolExecutor with 3 workers), multiple tickers are analyzed concurrently. Each thread calls `save_sentiment_history` which:
1. Reads the entire CSV
2. Modifies it in memory
3. Writes the entire CSV back

If Thread A reads the file, then Thread B reads it (before Thread A writes), Thread A's write will overwrite Thread B's read, **losing Thread B's update**. With 3 parallel workers, about 1 in 3 calls will lose data. This also affects `save_source_accuracy` (line 284) during concurrent voting.

### HIGH: Division by zero in `calc_portfolio_pnl`
**File: persistence.py, Lines 80-83**
```python
if not current_price or not entry_price:
    return {"pnl_abs": 0.0, "pnl_pct": 0.0}
pnl_pct = ((current_price - entry_price) / entry_price) * 100
```
If `entry_price` is `0` (user enters "0" as ATP), the guard `if not entry_price:` passes because `0` is falsy — so it returns `{"pnl_abs": 0.0, "pnl_pct": 0.0}`. This is safe. BUT if `entry_price` is `0.01` (one paisa), `not 0.01` is False, so division occurs: `(current_price - 0.01) / 0.01 * 100`, producing plausible P&L. The guard works only for exact 0, not near-zero values. OK in practice.

### MEDIUM: `cache_get` crashes on invalid `cached_at` format
**File: persistence.py, Lines 123-130**
```python
def cache_get(key):
    cache = load_cache()
    entry = cache.get(key)
    if entry:
        age = (datetime.now() - datetime.fromisoformat(entry["cached_at"])).total_seconds()
```
If the cache file is corrupted or manually edited with an invalid ISO date string, `datetime.fromisoformat()` raises `ValueError`. No try/except. Crash propagates up to `get_stock_info` (data_fetcher.py:607) which doesn't catch it either, causing a `st.error()` with a confusing traceback.

### MEDIUM: Cache TTL not respected for news caching
**File: persistence.py, Lines 123-130**
The `cache_get` function checks TTL correctly. But as noted in data_fetcher.py:1026, empty results are cached without special TTL. The news cache respects `CACHE_TTL` (15 min) regardless of result quality.

### LOW: `_save_json` silently discards write failures
**File: persistence.py, Lines 36-40**
```python
def _save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except (OSError, PermissionError):
        pass
```
Silent failure is intentional for Streamlit Cloud's read-only filesystem, but on a local install, users have no idea writes are failing. No logging, no toast notification.

---

## Cross-Cutting Issues

### 1. Thread Safety (Portfolio Briefing)
**Files: app.py:631, persistence.py:174-211, event_classifier.py:192-200, data_fetcher.py:815-816**
Portfolio briefing uses `ThreadPoolExecutor(max_workers=3)`. Multiple threads:
- Write to sentiment_history.csv (race condition, data loss)
- Write to source_accuracy.json (race condition, vote loss)
- Access `_COMPILED` global (double compilation)
- Access `_REDDIT_TOKEN` global (double token fetch)

### 2. Widget Key Collisions
**app.py:193** (`portfolio_add`), **app.py:545** (`btm_add`), **app.py:274** (`del_{t}`), **app.py:578** (`btm_del_{t}`) — Keys use different prefixes so there's no collision. OK.

### 3. Color-Only Indicators (Accessibility)
The heatmap (green/red/grey), sentiment indicators, and portfolio change indicators rely entirely on color. Screen readers and colorblind users cannot distinguish bullish/bearish signals. The SVG icons (`_ICON["dot_green"]`, etc.) use `aria-hidden="true"` which excludes them from assistive technology.

### 4. Empty Portfolio / No News / All-Neutral Edge Cases
- **Empty portfolio**: `portfolio = []` — all loops over `portfolio` are empty, sidebar shows nothing, briefing button shows warning. Handled.
- **No news articles**: `news_items = []` — `event_adjusted_scores` is empty, `save_sentiment_history` is not called (line 140). `get_weighted_signal` returns NEUTRAL. `compute_smartscore` returns `_empty_result`. Dashboard shows "No articles found". Handled.
- **All-neutral sentiment**: All compounds between -0.3 and 0.3. Signal = NEUTRAL. These values are valid and handled.
- **Very large portfolio**: No pagination or scrolling optimization. 50+ tickers in the sidebar could make the sidebar very long. No limit on portfolio size.

### 5. Unicode/Encoding on Windows
Multiple `open()` calls without `encoding="utf-8"` will fail on Windows for files containing emoji, ₹, or other non-Latin-1 characters.

---

## Summary Table

| File | Lines | Critical | High | Medium | Low |
|------|-------|----------|------|--------|-----|
| app.py | 746 | 2 | 2 | 4 | 3 |
| render.py | 943 | 0 | 0 | 2 | 3 |
| intraday.py | 136 | 0 | 0 | 0 | 1 |
| aggregate_sentiment.py | 194 | 0 | 0 | 0 | 1 |
| sentiment.py | 191 | 0 | 0 | 1 | 1 |
| data_fetcher.py | 1029 | 1 | 2 | 3 | 1 |
| market_data.py | 53 | 0 | 0 | 0 | 1 |
| event_classifier.py | 253 | 0 | 0 | 2 | 0 |
| indicators.py | 102 | 0 | 1 | 2 | 1 |
| persistence.py | 284 | 3 | 1 | 2 | 1 |
| **Total** | **~3733** | **6** | **6** | **16** | **12** |

### Top 5 Most Impactful Bugs

1. **persistence.py:205-206** — Duplicate CSV columns (corrupts sentiment_history.csv)
2. **data_fetcher.py:562-581** — Regulatory aliases cause false news matches for many tickers
3. **app.py:201** — `isalnum()` rejects hyphenated tickers (BAJAJ-AUTO, etc.)
4. **persistence.py:186-211** — Race condition loses sentiment history during portfolio briefing
5. **persistence.py:28,37,162,187,209** — Missing `encoding="utf-8"` on Windows
