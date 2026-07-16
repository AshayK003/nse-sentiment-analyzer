"""
Data persistence for NSE Sentiment Analyzer.
Portfolio, track record, and cache — with Streamlit Cloud-safe fallback.
"""

import csv
import io
import json
import logging
import threading
import streamlit as st
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
TRACK_FILE = DATA_DIR / "track_record.json"
CACHE_FILE = DATA_DIR / "cache.json"
HISTORY_FILE = DATA_DIR / "sentiment_history.csv"
ENTRY_PRICES_FILE = DATA_DIR / "entry_prices.json"
FIIDII_HISTORY_FILE = DATA_DIR / "fiidii_history.json"

CACHE_TTL = 15 * 60  # 15 minutes
MAX_CACHE_ENTRIES = 500  # drop oldest entries when exceeding this (prevents unbounded growth under multi-user load)

# Thread locks — separate for CSV history, source accuracy, and FII/DII (different files)
_history_lock = threading.RLock()
_accuracy_lock = threading.RLock()
_fiidii_lock = threading.RLock()


# ─── Helpers ───

def _load_json(path, default=None):
    """Try loading from file; return default on any failure."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []


def _save_json(path, data):
    """Save to file; silently ignore if filesystem is read-only (Streamlit Cloud)."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except (OSError, PermissionError):
        pass  # Ephemeral filesystem on Streamlit Cloud


# ─── Portfolio ───

def load_portfolio():
    portfolios = _load_json(PORTFOLIO_FILE, [])
    # Try session_state as fallback (Streamlit Cloud persistence)
    if st.session_state.get("_portfolio"):
        # Merge: file is primary, session supplements
        sp = st.session_state._portfolio
        for t in sp:
            if t not in portfolios:
                portfolios.append(t)
    return portfolios


def save_portfolio(tickers):
    _save_json(PORTFOLIO_FILE, tickers)
    st.session_state._portfolio = list(tickers)


# ─── Entry Prices ───

def load_entry_prices():
    """Return {ticker: {"price": float, "qty": int}} dict. Empty dict if none saved.
    Auto-migrates old flat format {ticker: price} to new nested format.
    """
    raw = _load_json(ENTRY_PRICES_FILE, {})
    prices = {}
    for ticker, val in raw.items():
        if isinstance(val, (int, float)):
            prices[ticker] = {"price": float(val), "qty": 1}
        elif isinstance(val, dict):
            prices[ticker] = {"price": float(val.get("price", 0)), "qty": int(val.get("qty", 1))}
    return prices


def save_entry_price(ticker, price, qty=1):
    """Save or update entry price and quantity for a ticker."""
    prices = load_entry_prices()
    prices[ticker.upper()] = {"price": float(price), "qty": int(qty)}
    _save_json(ENTRY_PRICES_FILE, prices)


def get_entry_info(entry):
    """Extract (price, qty) from an entry_prices value (handles old + new format)."""
    if isinstance(entry, dict):
        return float(entry.get("price", 0)), int(entry.get("qty", 1))
    if isinstance(entry, (int, float)):
        return float(entry), 1
    return 0, 1


def calc_portfolio_pnl(entry_price, current_price, qty=1):
    """Calculate P&L from entry price, current price, and quantity.
    Returns {pnl_abs: float, pnl_pct: float}.
    """
    if not current_price or not entry_price:
        return {"pnl_abs": 0.0, "pnl_pct": 0.0}
    pnl_abs = (current_price - entry_price) * qty
    pnl_pct = ((current_price - entry_price) / entry_price) * 100
    return {"pnl_abs": round(pnl_abs, 2), "pnl_pct": round(pnl_pct, 2)}


# ─── Track Record ───

def load_track_record():
    return _load_json(TRACK_FILE, [])


def save_track_record(records):
    _save_json(TRACK_FILE, records)


# ─── Cache ───

def load_cache():
    """Return cache dict, lazy-loading from file and detecting external changes via mtime."""
    cache_mtime = st.session_state.get("_cache_mtime", -1)
    try:
        current_mtime = CACHE_FILE.stat().st_mtime
    except OSError:
        current_mtime = -1

    if current_mtime > cache_mtime or "_cache_data" not in st.session_state:
        st.session_state._cache_data = _load_json(CACHE_FILE, {})
        st.session_state._cache_mtime = current_mtime
    return st.session_state._cache_data


def save_cache(cache):
    """Write cache to disk + sync in-memory copy.
    Prunes oldest entries if cache exceeds MAX_CACHE_ENTRIES."""
    # Prune: keep only the newest N entries by cached_at timestamp
    if len(cache) > MAX_CACHE_ENTRIES:
        sorted_keys = sorted(cache, key=lambda k: cache[k].get("cached_at", ""))
        for key in sorted_keys[:len(cache) - MAX_CACHE_ENTRIES]:
            del cache[key]
    st.session_state._cache_data = cache
    try:
        st.session_state._cache_mtime = CACHE_FILE.stat().st_mtime
    except OSError:
        pass
    _save_json(CACHE_FILE, cache)


def cache_get(key):
    cache = load_cache()
    entry = cache.get(key)
    if entry:
        try:
            age = (datetime.now() - datetime.fromisoformat(entry["cached_at"])).total_seconds()
        except (ValueError, KeyError, TypeError):
            return None
        ttl = entry.get("ttl", CACHE_TTL)
        if age < ttl:
            return entry["data"]
    return None


def cache_set(key, data, ttl=None):
    cache = load_cache()
    entry = {"data": data, "cached_at": datetime.now().isoformat()}
    if ttl is not None:
        entry["ttl"] = ttl
    cache[key] = entry
    save_cache(cache)


# ─── Sentiment History (CSV) ───


HISTORY_FIELDS = [
    "date", "ticker", "headline_count", "pos_count", "neg_count",
    "avg_compound", "event_avg", "smartscore",
]


def load_sentiment_history(ticker, days=10):
    """Load last N days of aggregated sentiment history for a ticker.

    Returns list of dicts sorted by date ascending (oldest first).
    Returns [] if file missing or ticker not found.
    """
    with _history_lock:
        records = []
        try:
            with open(HISTORY_FILE, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("ticker") == ticker:
                        records.append(row)
        except (FileNotFoundError, IOError):
            return []

        records.sort(key=lambda r: r.get("date", ""))
        return records[-days:]


def save_sentiment_history(ticker, row_data):
    """Append or update today's aggregated sentiment history entry for a ticker.

    row_data: dict with keys matching HISTORY_FIELDS (excluding date/ticker).
    If an entry already exists for this ticker today, it's updated in-place.
    Silently handles read-only filesystem (Streamlit Cloud).
    Thread-safe via _history_lock.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    with _history_lock:
        existing = []
        try:
            with open(HISTORY_FILE, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                existing = list(reader)
        except (FileNotFoundError, IOError):
            pass

        # Remove any existing entry for this ticker today
        existing = [
            r for r in existing
            if not (r.get("ticker") == ticker and r.get("date") == today)
        ]

        # Build new row
        new_row = {"date": today, "ticker": ticker}
        new_row.update(row_data)

        existing.append(new_row)
        try:
            # HISTORY_FIELDS already includes "date" and "ticker"
            fieldnames = HISTORY_FIELDS
            with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(existing)
        except (IOError, OSError):
            pass  # Read-only filesystem


def history_to_csv(ticker, records):
    """Convert sentiment history records to CSV string, filtered by ticker.

    Returns a CSV string with header row. If records is empty, returns
    just the header row. Only includes rows matching the given ticker.
    """
    # Filter to matching ticker
    filtered = [r for r in records if r.get("ticker") == ticker]

    # Determine field names from data, or fall back to known fields
    if filtered:
        fieldnames = list(filtered[0].keys())
    else:
        fieldnames = ["date", "ticker", "smartscore", "avg_compound", "headline_count"]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(filtered)
    return buf.getvalue()


# ─── Bayesian Source Calibration ───
# Each source is tracked as a Beta(alpha, beta) distribution.
# Weight = alpha / (alpha + beta) = posterior mean accuracy.
# Priors start centered on the hand-tuned default weights.

SOURCE_WEIGHTS_PRIOR = {
    "Economic Times": 1.0, "Moneycontrol": 0.9, "LiveMint": 0.8,
    "NDTV Profit": 0.7, "Google News": 0.6, "DuckDuckGo": 0.5,
    "Unknown": 0.5,
}
ACCURACY_FILE = DATA_DIR / "source_accuracy.json"


def load_source_accuracy():
    """Return {source: {"alpha": float, "beta": float}}.
    Starts with an informative Beta(weight*10+1, (1-weight)*10+1) prior
    centered on the hand-tuned default weights.
    """
    with _accuracy_lock:
        try:
            data = _load_json(ACCURACY_FILE, None)
            if data:
                return data
        except Exception:
            pass
        return {
            src: {"alpha": w * 10 + 1, "beta": (1 - w) * 10 + 1}
            for src, w in SOURCE_WEIGHTS_PRIOR.items()
        }


def save_source_accuracy(data):
    _save_json(ACCURACY_FILE, data)


def update_source_accuracy(source, was_correct):
    """Increment alpha (correct) or beta (wrong) for a source.
    Called after each user vote. Creates entry with prior if new source.
    Thread-safe via _history_lock.
    """
    with _accuracy_lock:
        acc = load_source_accuracy()
        if source not in acc:
            prior_w = SOURCE_WEIGHTS_PRIOR.get(source, 0.5)
            acc[source] = {"alpha": prior_w * 10 + 1, "beta": (1 - prior_w) * 10 + 1}
        if was_correct:
            acc[source]["alpha"] += 1
        else:
            acc[source]["beta"] += 1
        save_source_accuracy(acc)


# ─── FII/DII Daily History ───

def load_fiidii_history():
    """Return list of {date, fii_net, dii_net} dicts, sorted by date ascending."""
    return _load_json(FIIDII_HISTORY_FILE, [])


def save_fiidii_snapshot(fii_data):
    """Append today's FII/DII data if not already recorded for this date.
    Thread-safe via _fiidii_lock.
    """
    if not fii_data:
        return
    with _fiidii_lock:
        history = load_fiidii_history()
        today = fii_data.get("date", "")
        # Don't duplicate same date
        if history and history[-1].get("date") == today:
            return
        history.append({
            "date": today,
            "fii_net": fii_data.get("fii_net", 0),
            "dii_net": fii_data.get("dii_net", 0),
        })
        # Keep last 90 days
        history = history[-90:]
        _save_json(FIIDII_HISTORY_FILE, history)
