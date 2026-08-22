"""
Data fetching for NSE Sentiment Analyzer.
Stock data via yfinance + news via RSS + DuckDuckGo fallback.
"""
import yfinance as yf
import requests
import feedparser
import html
import json
import os
import pandas as pd
import time
import logging
import streamlit as st
import re
import random
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from duckduckgo_search import DDGS
from persistence import cache_get, cache_set
from adaptive_sentiment import get_dissemination_clusterer, compute_dissemination_score, get_dissemination_clusters
logger = logging.getLogger(__name__)
# ─── Global rate-limit cooldown ───
# When yfinance returns 429, all yfinance calls skip for this duration
# to let the rate-limit window clear.
# Thread-safe via _rate_limit_lock (briefing mode runs parallel workers).
_RATE_LIMITED_UNTIL = 0.0
_RATE_LIMIT_COOLDOWN = 45  # seconds
_rate_limit_lock = threading.Lock()
# Separate cooldown for DuckDuckGo (known to return 202/captcha under load)
_DDGS_RATE_LIMITED_UNTIL = 0.0
_DDGS_COOLDOWN = 60  # seconds
_ddgs_rate_limit_lock = threading.Lock()
def _check_rate_limited():
    """Return True if we're in a global rate-limit cooldown.
    Resets automatically after COOLDOWN seconds. Thread-safe."""
    with _rate_limit_lock:
        return time.time() < _RATE_LIMITED_UNTIL
def _mark_rate_limited():
    """Set global cooldown. All yfinance calls skip for COOLDOWN seconds.
    Thread-safe — overlapping calls just extend the window slightly."""
    global _RATE_LIMITED_UNTIL
    with _rate_limit_lock:
        _RATE_LIMITED_UNTIL = time.time() + _RATE_LIMIT_COOLDOWN
def _mark_ddgs_rate_limited():
    """Set DDGS cooldown. Skips DuckDuckGo fallback for _DDGS_COOLDOWN seconds.
    Thread-safe — uses its own lock, separate from yfinance rate limiter."""
    global _DDGS_RATE_LIMITED_UNTIL
    with _ddgs_rate_limit_lock:
        _DDGS_RATE_LIMITED_UNTIL = time.time() + _DDGS_COOLDOWN
# ─── yfinance: set browser User-Agent to avoid 429 rate limiting ───
# yf.utils._session is semi-public (used by yfinance's own tests).
# yf._session was a private fallback for older versions — removed to avoid
# breakage on yfinance upgrades. If Ticker() calls fail with 429, check
# whether yfinance moved session handling.
_session = requests.Session()
_session.headers["User-Agent"] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
yf.utils._session = _session
# ─── NSE Tickers ───
# Ticker universe loaded from data/tickers.json — add/update tickers there,
# no code changes needed. (Issue: data belongs in data files, not source.)
_TICKER_DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tickers.json")
try:
    with open(_TICKER_DATA_PATH, encoding="utf-8") as _tf:
        NSE_TICKERS = json.load(_tf)
except (OSError, json.JSONDecodeError):  # missing/corrupt file: keep app alive with empty universe
    NSE_TICKERS = {}
# ─── Company name aliases for RSS headline matching ───
# Maps common names/abbreviations → ticker symbols.
# RSS headlines rarely use official company names ("SBI" not "State Bank of India").
# Aliases loaded from data/aliases.json — maps common names to ticker symbols.
_ALIAS_DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "aliases.json")
try:
    with open(_ALIAS_DATA_PATH, encoding="utf-8") as _af:
        ALIASES = json.load(_af)
except (OSError, json.JSONDecodeError):
    ALIASES = {}
# Precompute reverse ALIASES (lowercased name → ticker) for fast input resolution
_ALIAS_LOOKUP = {}
for _ak, _at in ALIASES.items():
    _alias_upper = _ak.strip().upper()
    if _alias_upper not in _ALIAS_LOOKUP:
        _ALIAS_LOOKUP[_alias_upper] = _at
def resolve_ticker(raw_input):
    """Resolve user input to a valid NSE ticker symbol.
    Handles tickers, company names, aliases, and partial matches.
    Returns (ticker, company_name) or (None, None) if unresolved.
    Resolution order (fast → slow):
      1. Exact NSE_TICKERS match
      2. Exact ALIASES match (e.g. "HDFC BANK" → "HDFCBANK")
      3. Company name reverse lookup
      4. Ticker prefix match
      5. yfinance search API fallback (network, ~1-2s)
    """
    if not raw_input or not raw_input.strip():
        return None, None
    q = raw_input.strip().upper().replace(".NS", "").replace(".BO", "")
    # 1. Exact ticker symbol match
    if q in NSE_TICKERS:
        return q, NSE_TICKERS[q]
    # 2. Exact alias match (e.g. "HDFC BANK" → "HDFCBANK")
    if q in _ALIAS_LOOKUP:
        ticker = _ALIAS_LOOKUP[q]
        return ticker, NSE_TICKERS.get(ticker, ticker)
    # 3. Company name reverse lookup — case-insensitive contains match
    for sym, name in NSE_TICKERS.items():
        if name.upper() == q:
            return sym, name
    # Partial company name match (e.g. "HDFC" matches "HDFC Bank")
    for sym, name in NSE_TICKERS.items():
        if q in name.upper():
            return sym, name
    # 4. Ticker prefix match (e.g. "HDFC" matches "HDFCBANK")
    for sym, name in NSE_TICKERS.items():
        if sym.startswith(q):
            return sym, name
    # 5. Online fallback — search yfinance for NSE ticker
    if not _check_rate_limited():
        online_result = _search_ticker_online(raw_input.strip())
        if online_result and online_result[0]:
            # Validate the found ticker exists in our system
            ticker, name = online_result
            if ticker in NSE_TICKERS:
                return ticker, NSE_TICKERS[ticker]
            # New ticker not in NSE_TICKERS — still valid, use it
            return ticker, name
    return None, None
# Cache for online ticker lookups (avoids repeated API calls)
_online_ticker_cache = {}
_online_cache_lock = threading.Lock()
_MAX_ONLINE_CACHE = 500
def _search_yahoo_finance(query):
    """Search Yahoo Finance REST API for NSE ticker. Fast (~200ms).
    Returns (ticker, name) or (None, None).
    """
    try:
        url = f'https://query2.finance.yahoo.com/v1/finance/search?q={requests.utils.quote(query)}&quotesCount=10&newsCount=0'
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        if r.status_code != 200:
            return None, None
        data = r.json()
        quotes = data.get('quotes', [])
        # Prefer NSE exchange (NSI), then any .NS symbol
        for q_item in quotes:
            sym = q_item.get('symbol', '')
            exch = q_item.get('exchange', '')
            if exch == 'NSI' and sym.endswith('.NS'):
                return sym.replace('.NS', ''), q_item.get('shortname', query)
        for q_item in quotes:
            sym = q_item.get('symbol', '')
            if sym.endswith('.NS'):
                return sym.replace('.NS', ''), q_item.get('shortname', query)
    except Exception as e:
        logger.debug("_search_yahoo_finance(%s) failed: %s", query, e)
    return None, None
def _search_yfinance_sdk(query):
    """Search yfinance SDK for NSE ticker. Slower (~1-2s) but more comprehensive.
    Returns (ticker, name) or (None, None).
    """
    try:
        search = yf.Search(query)
        quotes = search.quotes or []
        # Prefer NSE-listed stocks
        for q_item in quotes:
            sym = q_item.get('symbol', '')
            exch = q_item.get('exchDisp', '')
            if exch == 'NSE' and sym.endswith('.NS'):
                return sym.replace('.NS', ''), q_item.get('shortname', q_item.get('longname', query))
        for q_item in quotes:
            sym = q_item.get('symbol', '')
            if sym.endswith('.NS'):
                return sym.replace('.NS', ''), q_item.get('shortname', q_item.get('longname', query))
    except Exception as e:
        logger.debug("_search_yfinance_sdk(%s) failed: %s", query, e)
    return None, None
def _search_ticker_online(query):
    """Search for NSE ticker by company name using chained APIs.
    Resolution order:
      1. In-memory cache (instant)
      2. Yahoo Finance REST API (~200ms, fast)
      3. yfinance SDK Search (~1-2s, more comprehensive)
      4. Direct ticker probe — try query as .NS ticker (~1s)
    Returns (ticker, name) or (None, None).
    """
    q = query.strip()
    if not q or len(q) < 2:
        return None, None
    q_upper = q.upper()
    with _online_cache_lock:
        cached = _online_ticker_cache.get(q_upper)
        if cached is not None:
            return cached
    # Tier 1: Yahoo Finance REST API (fast)
    result = _search_yahoo_finance(q)
    if result and result[0]:
        with _online_cache_lock:
            if len(_online_ticker_cache) < _MAX_ONLINE_CACHE:
                _online_ticker_cache[q_upper] = result
        return result
    # Tier 2: yfinance SDK Search (slower, more comprehensive)
    if not _check_rate_limited():
        result = _search_yfinance_sdk(q)
        if result and result[0]:
            with _online_cache_lock:
                if len(_online_ticker_cache) < _MAX_ONLINE_CACHE:
                    _online_ticker_cache[q_upper] = result
            return result
        # Tier 3: Direct ticker probe — try query as .NS ticker
        # Handles rebranded stocks (Zomato→Eternal), splits, and
        # stocks Yahoo search doesn't index.
        result = _probe_ticker_direct(q)
        if result and result[0]:
            with _online_cache_lock:
                if len(_online_ticker_cache) < _MAX_ONLINE_CACHE:
                    _online_ticker_cache[q_upper] = result
            return result
    with _online_cache_lock:
        if len(_online_ticker_cache) < _MAX_ONLINE_CACHE:
            _online_ticker_cache[q_upper] = (None, None)
    return None, None
def _probe_ticker_direct(query):
    """Try the query (and common variations) as direct .NS ticker.
    When search APIs fail (rebranded stocks, delisted names, missing index
    entries), this probes yfinance directly. Handles:
      - "Zomato" → tries ZOMATO.NS (fails) → no match
      - "Eternal" → tries ETERNAL.NS (works) → ETERNAL
      - "Tata Steel" → tries TATA.NS, STEEL.NS (fail) → no match
      - "TATASTEEL" → tries TATASTEEL.NS (works) → TATASTEEL
    """
    q = query.strip().upper().replace(".NS", "").replace(".BO", "")
    if not q or len(q) < 2:
        return None, None
    # Build candidate tickers: the query itself, plus word-based variations
    candidates = [q]
    # "Tata Steel" → ["TATA STEEL", "TATASTEEL", "TATA", "STEEL"]
    words = q.split()
    if len(words) > 1:
        candidates.append("".join(words))  # TATASTEEL
        candidates.extend(words)            # TATA, STEEL
    for candidate in candidates:
        if len(candidate) < 2 or len(candidate) > 20:
            continue
        try:
            tk = yf.Ticker(f"{candidate}.NS")
            info = tk.info
            # Valid ticker: has a name and isn't an error placeholder
            name = info.get("shortName") or info.get("longName") or ""
            if name and name != "N/A" and len(info) > 5:
                return candidate, name
        except Exception:
            continue
    return None, None
# In-memory 1y price history cache, populated by get_stock_info,
# consumed by get_technical_indicators to avoid duplicate yfinance calls
_PRICE_CACHE_DIR = ".price_cache"
_CACHE_TTL_DAYS = 7
os.makedirs(_PRICE_CACHE_DIR, exist_ok=True)

_hist_cache = {}
_hist_cache_lock = threading.RLock()
_MAX_CACHED_TICKERS = 50
def _evict_hist_cache():
    """Evict oldest entries when cache exceeds _MAX_CACHED_TICKERS and clear stale L2 disk cache."""
    with _hist_cache_lock:
        while len(_hist_cache) > _MAX_CACHED_TICKERS:
            # dict preserves insertion order (Python 3.7+) — pop first key
            _hist_cache.pop(next(iter(_hist_cache)), None)
    
    # Evict stale L2 disk cache
    if os.path.exists(_PRICE_CACHE_DIR):
        now = time.time()
        for filename in os.listdir(_PRICE_CACHE_DIR):
            filepath = os.path.join(_PRICE_CACHE_DIR, filename)
            if os.path.isfile(filepath):
                try:
                    if (now - os.path.getmtime(filepath)) > _CACHE_TTL_DAYS * 86400:
                        os.remove(filepath)
                except Exception:
                    pass

def get_cached_history(ticker):
    """Return 1y price history for a ticker, from memory cache, disk cache, or yfinance.
    Populated by get_stock_info() to share the yfinance 1y OHLCV fetch.
    """
    with _hist_cache_lock:
        cached = _hist_cache.get(ticker)
    if cached is not None:
        return cached

    # Sanitize ticker to prevent path traversal
    safe_ticker = re.sub(r"[^A-Za-z0-9._-]", "_", ticker)
    
    # L2 Fallback: check disk cache
    cache_path = os.path.join(_PRICE_CACHE_DIR, f"{safe_ticker}.json")
    if os.path.exists(cache_path):
        try:
            if (time.time() - os.path.getmtime(cache_path)) <= _CACHE_TTL_DAYS * 86400:
                hist = pd.read_json(cache_path, orient="index")
                with _hist_cache_lock:
                    _hist_cache[ticker] = hist
                    needs_evict = len(_hist_cache) > _MAX_CACHED_TICKERS
                if needs_evict:
                    _evict_hist_cache()
                return hist
        except Exception as e:
            logger.debug(f"Cache read error for {ticker}: {e}")  # Corrupted or unreadable, fall through to L3

    # L3 Fallback: fetch directly from yfinance (cheap — yfinance caches internally)
    for suffix in [".NS", ".BO", ""]:
        try:
            stock = yf.Ticker(f"{ticker}{suffix}")
            hist = stock.history(period="2y")
            if hist is not None and not hist.empty:
                try:
                    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                    hist.to_json(cache_path, orient="index", date_format="iso")
                except Exception as e:
                    logger.debug(f"Cache write error for {ticker}: {e}")
                
                with _hist_cache_lock:
                    _hist_cache[ticker] = hist
                    needs_evict = len(_hist_cache) > _MAX_CACHED_TICKERS
                if needs_evict:
                    _evict_hist_cache()
                return hist
        except Exception:
            continue
    return None
def _strip_html(text):
    """Strip HTML tags + unescape entities for clean text analysis & display."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.split())
def _retry_fetch(max_attempts=3, base_wait=1, backoff=2):
    """Generator that yields attempt numbers for retry loops.
    Uses exponential backoff with full jitter (AWS retry style).
    If _check_rate_limited() is True, skips sleep and yields immediately.
    """
    for attempt in range(max_attempts):
        yield attempt
        if attempt < max_attempts - 1:
            if _check_rate_limited():
                continue
            sleep = base_wait * (backoff ** attempt)
            jitter = sleep * 0.5 * random.random()
            time.sleep(sleep + jitter)
def _nf(v):
    """NaN-safe float extractor — returns None for NaN/None."""
    if v is None:
        return None
    f = float(v)
    return None if math.isnan(f) else f
def get_stock_info(ticker):
    """Fetch stock data from yfinance with retry and backoff.
    Two-phase approach:
      1. info (metadata: name, sector, PE, 52w) — best-effort, not blocking.
         If it fails, defaults are used.
      2. history (price data: close, change, volume) — required.
         Falls back to .BO suffix if .NS fails, then bare ticker.
    """
    cached = cache_get(f"stock_{ticker}")
    if cached:
        # Populate in-memory history cache so downstream (get_cached_history,
        # get_technical_indicators) don't re-fetch from yfinance.
        if ticker not in _hist_cache:
            get_cached_history(ticker)
        return cached
    # Global rate-limit cooldown — if yfinance recently 429'd us, wait and retry
    if _check_rate_limited():
        import time as _time
        remaining = int(_RATE_LIMITED_UNTIL - _time.time())
        if remaining > 0 and remaining <= _RATE_LIMIT_COOLDOWN:
            st.info(f"⏳ Yahoo Finance rate-limited. Waiting {remaining}s before retrying...")
            _time.sleep(remaining + 1)
            # Re-check — if still limited after wait, give up
            if _check_rate_limited():
                st.warning("Still rate-limited. Please try again in a moment.")
                return None
    suffixes = [".NS", ".BO", ""]
    info = None
    hist = None
    name_fallback = ticker
    try:
        # ── Phase 1: info (best-effort metadata) ──
        for suffix in suffixes:
            stock = yf.Ticker(f"{ticker}{suffix}")
            for attempt in _retry_fetch(max_attempts=3, base_wait=0.5):
                try:
                    raw = stock.info
                    if raw and isinstance(raw, dict) and len(raw) > 10:
                        info = raw
                        name_fallback = info.get("longName", info.get("shortName", ticker))
                        break
                except Exception as e:
                    # Any yfinance error could be rate-limiting
                    if "429" in str(e) or "Too Many" in str(e) or "Rate Limit" in str(e):
                        _mark_rate_limited()
                    continue  # retry same suffix with backoff before trying next
            if info:
                break  # found valid info, stop trying suffixes
        # ── Phase 2: history (required price data) ──
        for suffix in suffixes if not hist else []:
            stock = yf.Ticker(f"{ticker}{suffix}")
            for attempt in _retry_fetch(max_attempts=3, base_wait=1):
                try:
                    raw = stock.history(period="2y")
                    if raw is not None and not raw.empty:
                        hist = raw
                        break
                except Exception:
                    continue  # retry with backoff
            if hist is not None:
                break  # found valid history
        # ── Phase 2b: retry info if it failed (rate-limit may have cleared
        #    during the history phase which took ~3-6s) ──
        if info is None and hist is not None:
            for suffix in suffixes:
                stock = yf.Ticker(f"{ticker}{suffix}")
                try:
                    raw = stock.info
                    if raw and isinstance(raw, dict) and len(raw) > 10:
                        info = raw
                        name_fallback = info.get("longName", info.get("shortName", ticker))
                        break
                except Exception:
                    continue
        # ── Phase 2c: targeted sector/industry fetch ──
        #    yfinance .info is flaky for Indian stocks — sometimes returns
        #    partial dicts or None. Retry specifically for sector/industry.
        #    Skip if info was a full response (30+ keys) — fields are legitimately
        #    absent for ETFs/index funds, retrying won't help.
        _sec = info.get("sector") if info else None
        _ind = info.get("industry") if info else None
        _info_sparse = info is None or len(info) < 30
        _has_na = _sec == "N/A" or _ind == "N/A"
        if (_info_sparse or _has_na) and ((_sec is None or _sec == "N/A") or (_ind is None or _ind == "N/A")):
            for suffix in suffixes:
                try:
                    stock = yf.Ticker(f"{ticker}{suffix}")
                    raw = stock.info
                    if raw and isinstance(raw, dict):
                        if not _sec or _sec == "N/A":
                            _sec = raw.get("sector")
                        if not _ind or _ind == "N/A":
                            _ind = raw.get("industry")
                        if _sec and _sec != "N/A" and _ind and _ind != "N/A":
                            break
                except Exception:
                    continue
            # Patch into info dict (create one if it was None)
            if info is None:
                info = {}
            if _sec and _sec != "N/A":
                info["sector"] = _sec
            if _ind and _ind != "N/A":
                info["industry"] = _ind
        # ── Build result dict ──
        if hist is not None and not hist.empty:
            with _hist_cache_lock:
                _hist_cache[ticker] = hist
                while len(_hist_cache) > _MAX_CACHED_TICKERS:
                    _hist_cache.pop(next(iter(_hist_cache)), None)
            current_price = _nf(hist["Close"].iloc[-1])
            prev_close = _nf(hist["Close"].iloc[-2]) if len(hist) > 1 else current_price
            if current_price is not None and prev_close is not None:
                change = float(current_price - prev_close)
                change_pct = float((change / prev_close) * 100) if prev_close != 0 else 0.0
            else:
                change = None
                change_pct = None
            day_high = _nf(hist["High"].iloc[-1])
            day_low = _nf(hist["Low"].iloc[-1])
            vol_raw = hist["Volume"].iloc[-1]
            volume = int(vol_raw) if not math.isnan(vol_raw) else 0
        elif info:
            # No history but info is available — use info fields for price
            current_price = _nf(info.get("currentPrice")) or _nf(info.get("regularMarketPrice"))
            change = _nf(info.get("regularMarketChange"))
            change_pct = _nf(info.get("regularMarketChangePercent"))
            day_high = _nf(info.get("dayHigh"))
            day_low = _nf(info.get("dayLow"))
            vol_raw = info.get("volume")
            volume = int(vol_raw) if vol_raw is not None and not math.isnan(float(vol_raw)) else 0
        else:
            # Neither info nor history — give up
            st.error(
                f"Could not fetch data for {ticker}. "
                "Yahoo Finance may be rate-limited — wait a moment and try again."
            )
            return None
        result = {
            "name": info.get("longName", info.get("shortName", name_fallback)) if info else name_fallback,
            "sector": info.get("sector", "N/A") if info else "N/A",
            "industry": info.get("industry", "N/A") if info else "N/A",
            "market_cap": info.get("marketCap") if info else None,
            "pe_ratio": info.get("trailingPE") if info else None,
            "debt_to_equity": _nf(info.get("debtToEquity")) if info else None,
            "current_price": current_price,
            "change": change,
            "change_pct": change_pct,
            "day_high": day_high,
            "day_low": day_low,
            "volume": volume,
            "52w_high": info.get("fiftyTwoWeekHigh") if info and info.get("fiftyTwoWeekHigh") is not None else (_nf(hist["High"].max()) if hist is not None and not hist.empty else None),
            "52w_low": info.get("fiftyTwoWeekLow") if info and info.get("fiftyTwoWeekLow") is not None else (_nf(hist["Low"].min()) if hist is not None and not hist.empty else None),
        }
        if info:
            cache_set(f"stock_{ticker}", result)
        else:
            cache_set(f"stock_{ticker}", result, ttl=120)  # 2 min
        return result
    except Exception as e:
        logger.warning("get_stock_info(%s) failed: %s", ticker, e)
        st.error(f"Could not fetch data for {ticker}: {e}")
        return None
def _parse_date(d):
    """Parse RSS date tuple to ISO date string."""
    try:
        return datetime(*d[:6]).isoformat()[:10]
    except Exception:
        return ""
def _relevant(ticker, company_name, title, body):
    """Check if a headline is relevant to the given ticker/company.
    Uses phrase-level matching to avoid false positives:
    1. Ticker symbol (e.g. 'RELIANCE', 'HDFCBANK') — most reliable
    2. Full company name as phrase (e.g. 'Reliance Industries')
    3. Alias keys as phrases (e.g. 'SBI' for SBIN, 'L&T' for LT)
    Individual word matching is avoided — words like 'bank', 'power',
    'tata', 'steel' are too common and cause irrelevant headlines to pass.
    """
    text = (title + " " + (body or "")).lower()
    # Tier 1: Ticker symbol
    if re.search(r'\b' + re.escape(ticker.lower()) + r'\b', text):
        return True
    # Tier 2: Full company name as phrase
    if re.search(r'\b' + re.escape(company_name.lower()) + r'\b', text):
        return True
    # Tier 3: Alias keys as phrases (e.g. 'L&T', 'SBI', 'HDFC')
    for alias_key, alias_ticker in ALIASES.items():
        if alias_ticker == ticker:
            alias_lower = alias_key.lower()
            if len(alias_lower) > 2 and re.search(r'\b' + re.escape(alias_lower) + r'\b', text):
                return True
    return False
# ─── RSS Feeds ───
# Yahoo Finance RSS removed (returns 429 / rate-limited on cloud IPs)
# LiveMint and Business Standard tested; BS returns 403
TICKER_RSS_FEEDS = [
    # Google News RSS for ticker-specific results
    lambda t, c: f"https://news.google.com/rss/search?q={t}+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en",
    lambda t, c: f"https://news.google.com/rss/search?q={c}+NSE&hl=en-IN&gl=IN&ceid=IN:en" if c != t else None,
]
INDIA_RSS_FEEDS = [
    ("Moneycontrol Buzzing", "https://www.moneycontrol.com/rss/buzzingstocks.xml"),
    ("Moneycontrol News", "https://www.moneycontrol.com/rss/latestnews.xml"),
    ("Moneycontrol Reports", "https://www.moneycontrol.com/rss/marketreports.xml"),
    ("Economic Times Markets", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("Economic Times Company", "https://economictimes.indiatimes.com/news/company/rssfeeds/2143429.cms"),
    ("LiveMint Markets", "https://www.livemint.com/rss/markets"),
    ("LiveMint Companies", "https://www.livemint.com/rss/companies"),
    ("LiveMint Industry", "https://www.livemint.com/rss/industry"),
    ("NDTV Profit", "https://feeds.feedburner.com/ndtvprofit-latest"),
]
COMMODITY_RSS_FEEDS = [
    ("Moneycontrol Commodities", "https://www.moneycontrol.com/rss/commodities.xml"),
    ("ET Commodities", "https://economictimes.indiatimes.com/commodity/rssfeeds/1138948049.cms"),
    ("Google News Commodities", "https://news.google.com/rss/search?q=crude+oil+OR+gold+OR+sugar+OR+aluminum+price+India&hl=en-IN&gl=IN&ceid=IN:en"),
]
SOURCE_LABELS = {
    "google news": "Google News",
    "moneycontrol buzzing": "Moneycontrol",
    "moneycontrol news": "Moneycontrol",
    "moneycontrol reports": "Moneycontrol",
    "moneycontrol commodities": "Moneycontrol",
    "economic times markets": "Economic Times",
    "economic times company": "Economic Times",
    "economic times commodities": "Economic Times",
    "livemint markets": "LiveMint",
    "livemint companies": "LiveMint",
    "livemint industry": "LiveMint",
    "ndtv profit": "NDTV Profit",
    "google news commodities": "Google News",
    "duckduckgo": "DuckDuckGo",
}
def _parse_rss_feed(source_name, url, ticker, company_name):
    """Parse one RSS feed in a worker thread — no shared state mutation.

    Returns (relevant_items, all_items, label):
      - relevant_items: pass the ticker-relevance filter (shown in UI)
      - all_items: all deduplicated items (used for cascade detection)
    """
    label = SOURCE_LABELS.get(source_name.lower().replace("_", " "), source_name)
    relevant = []
    all_items = []
    try:
        try:
            feed = feedparser.parse(url, timeout=10)
        except TypeError:
            feed = feedparser.parse(url)
        for entry in feed.entries[:7]:
            link = entry.get("link", "")
            title = entry.get("title", "")
            body = _strip_html(entry.get("summary", ""))
            if link and link.startswith(("http://", "https://")):
                item = {
                    "title": title,
                    "body": body,
                    "date": _parse_date(entry.get("published_parsed")),
                    "url": link,
                    "source": label,
                }
                all_items.append(item)
                if _relevant(ticker, company_name, title, body):
                    relevant.append(item)
    except Exception:
        pass
    return relevant, all_items, label
def _ddgs_search(ticker, company_name, seen_urls, all_results, source_stats, max_results):
    """Search DuckDuckGo as fallback when RSS returns little."""
    with DDGS() as ddgs:
        for query in [f"{ticker} NSE", f"{company_name} stock"]:
            try:
                results = list(ddgs.news(query, max_results=3, timelimit="w"))
            except Exception:
                results = []
            if not results:
                try:
                    results = list(ddgs.text(query, max_results=3))
                except Exception:
                    results = []
            for r in results:
                url = r.get("url", "") or r.get("link", "")
                if url and url.startswith(("http://", "https://")) and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append({
                        "title": r.get("title", ""),
                        "body": r.get("body", ""),
                        "date": r.get("date", ""),
                        "url": url,
                        "source": "DuckDuckGo",
                    })
                    source_stats["DuckDuckGo"] = source_stats.get("DuckDuckGo", 0) + 1
            time.sleep(0.3)
            if len(all_results) >= max_results:
                break
def search_news(ticker, company_name, max_results=10):
    """Fetch news from RSS feeds (primary), fallback to DuckDuckGo.

    Returns (articles, cascade_pool, source_health):
      - articles: ticker-relevant articles for display
      - cascade_pool: all articles (including non-relevant) for cascade/ripple detection
      - source_health: source hit counts
    """
    cached = cache_get(f"news_{ticker}")
    if cached:
        news, health = cached
        # Return full cached list for cascade_pool so commodity detection
        # has more articles to scan, even on cache hit.
        dissemination_clusters = get_dissemination_clusters(news)
        dissemination_score = compute_dissemination_score(news)
        return news[:max_results], news, health, dissemination_clusters, dissemination_score
    seen_urls = set()
    all_results = []
    cascade_pool = []
    cascade_urls = set()
    source_stats = {}  # source_name -> hit_count
    # Ticker-specific RSS feeds
    for rss_fn in TICKER_RSS_FEEDS:
        url = rss_fn(ticker, company_name)
        if url is None:
            continue
        try:
            try:
                feed = feedparser.parse(url, timeout=10)
            except TypeError:
                feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                link = entry.get("link", "")
                if link and link.startswith(("http://", "https://")) and link not in seen_urls:
                    seen_urls.add(link)
                    cascade_urls.add(link)
                    item = {
                        "title": entry.get("title", ""),
                        "body": _strip_html(entry.get("summary", "")),
                        "date": _parse_date(entry.get("published_parsed")),
                        "url": link,
                        "source": "Google News",
                    }
                    all_results.append(item)
                    cascade_pool.append(item)
                    source_stats["Google News"] = source_stats.get("Google News", 0) + 1
        except Exception as e:
            logger.debug("Ticker RSS feed failed for %s: %s", ticker, e)
            continue
    # Indian market RSS feeds — returns (relevant, all, label)
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_parse_rss_feed, name, url, ticker, company_name): name for name, url in INDIA_RSS_FEEDS}
        for future in as_completed(futures):
            items, all_items, label = future.result()
            for item in items:
                link = item["url"]
                if link not in seen_urls:
                    seen_urls.add(link)
                    all_results.append(item)
                    source_stats[label] = source_stats.get(label, 0) + 1
            for item in all_items:
                link = item["url"]
                if link not in cascade_urls:
                    cascade_urls.add(link)
                    cascade_pool.append(item)
    # Fallback: DuckDuckGo when RSS returns little — skip if DDGS rate-limited
    # DDGS has no built-in timeout; wrap in ThreadPoolExecutor to prevent hangs
    if len(all_results) < 3 and time.time() >= _DDGS_RATE_LIMITED_UNTIL:
        try:
            with ThreadPoolExecutor(max_workers=1) as ddgs_pool:
                ddgs_pool.submit(
                    _ddgs_search, ticker, company_name,
                    seen_urls, all_results, source_stats, max_results,
                ).result(timeout=15)
        except Exception as e:
            logger.debug("DuckDuckGo fallback failed for %s: %s", ticker, e)
            _mark_ddgs_rate_limited()
    # Reconcile DuckDuckGo additions into cascade_pool
    for item in all_results:
        if item["url"] not in cascade_urls:
            cascade_urls.add(item["url"])
            cascade_pool.append(item)
    all_results.sort(key=lambda x: x["date"], reverse=True)
    cascade_pool.sort(key=lambda x: x["date"], reverse=True)

    # Compute dissemination clusters for the cascade_pool (broader market awareness)
    dissemination_clusters = get_dissemination_clusters(cascade_pool)
    dissemination_score = compute_dissemination_score(cascade_pool)

    if all_results:
        cache_set(f"news_{ticker}", (all_results, source_stats))
    else:
        # Cache empty results briefly to avoid hammering feeds on every search
        cache_set(f"news_{ticker}", ([], source_stats), ttl=60)
        st.info("ℹ️ News feed unavailable. Showing price data only.")
    return all_results[:max_results], cascade_pool, source_stats, dissemination_clusters, dissemination_score


def _ddgs_commodity_search(all_items, seen_urls):
    """DuckDuckGo fallback for commodity news when RSS returns little."""
    _COMMODITY_QUERIES = [
        "crude oil price India today",
        "gold price today India",
        "sugar price India mill",
        "aluminum price LME India",
        "commodity market India news",
    ]
    with DDGS() as ddgs:
        for query in _COMMODITY_QUERIES:
            if time.time() < _DDGS_RATE_LIMITED_UNTIL:
                break
            try:
                results = list(ddgs.news(query, max_results=3, timelimit="w"))
            except Exception:
                results = []
            if not results:
                try:
                    results = list(ddgs.text(query, max_results=3))
                except Exception:
                    results = []
            for r in results:
                url = r.get("url", "") or r.get("link", "")
                if url and url.startswith(("http://", "https://")) and url not in seen_urls:
                    seen_urls.add(url)
                    all_items.append({
                        "title": r.get("title", ""),
                        "body": r.get("body", ""),
                        "date": r.get("date", ""),
                        "url": url,
                        "source": "DuckDuckGo",
                    })
            time.sleep(0.3)


def fetch_market_headlines():
    """Fetch broad market + commodity headlines for cascade detection.

    Fetches both INDIA_RSS_FEEDS and COMMODITY_RSS_FEEDS without ticker filtering.
    Falls back to DuckDuckGo commodity search when RSS returns fewer than 3 articles.
    Cached for 5 minutes to avoid hammering feeds on every rerun.

    Returns list of dicts with title, body, date, url, source.
    """
    cached = cache_get("market_headlines")
    if cached:
        return cached
    all_items = []
    seen_urls = set()
    all_feeds = list(INDIA_RSS_FEEDS) + list(COMMODITY_RSS_FEEDS)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_parse_rss_feed, name, url, "", ""): name for name, url in all_feeds}
        for future in as_completed(futures):
            _, items, _ = future.result()
            for item in items:
                link = item["url"]
                if link not in seen_urls:
                    seen_urls.add(link)
                    all_items.append(item)
    # DDG fallback when RSS returns little
    if len(all_items) < 3 and time.time() >= _DDGS_RATE_LIMITED_UNTIL:
        try:
            _ddgs_commodity_search(all_items, seen_urls)
        except Exception:
            pass
    all_items.sort(key=lambda x: x["date"], reverse=True)
    cache_set("market_headlines", all_items, ttl=300)
    return all_items