"""
Data persistence for NSE Sentiment Analyzer.
Portfolio, track record, and cache — with Streamlit Cloud-safe fallback.
"""

import json
import streamlit as st
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
TRACK_FILE = DATA_DIR / "track_record.json"
CACHE_FILE = DATA_DIR / "cache.json"
HISTORY_FILE = DATA_DIR / "sentiment_history.csv"

CACHE_TTL = 15 * 60  # 15 minutes


# ─── Helpers ───

def _load_json(path, default=None):
    """Try loading from file; return default on any failure."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []


def _save_json(path, data):
    """Save to file; silently ignore if filesystem is read-only (Streamlit Cloud)."""
    try:
        with open(path, "w") as f:
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
    """Write cache to disk + sync in-memory copy."""
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
        age = (datetime.now() - datetime.fromisoformat(entry["cached_at"])).total_seconds()
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
    import csv

    records = []
    try:
        with open(HISTORY_FILE, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("ticker") == ticker:
                    records.append(row)
    except (FileNotFoundError, IOError):
        return []

    records.sort(key=lambda r: r.get("date", ""))
    return records[-days:]


def save_sentiment_history(ticker, row_data):
    """Append or update today's sentiment history entry for a ticker.

    row_data: dict with keys matching HISTORY_FIELDS (excluding date/ticker).
    If an entry already exists for this ticker today, it's updated in-place.
    Silently handles read-only filesystem (Streamlit Cloud).
    """
    import csv

    today = datetime.now().strftime("%Y-%m-%d")

    existing = []
    try:
        with open(HISTORY_FILE, newline="") as f:
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

    # Ensure all fields exist (fill missing with defaults)
    for f in HISTORY_FIELDS:
        new_row.setdefault(f, "")

    existing.append(new_row)

    try:
        with open(HISTORY_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
            writer.writeheader()
            writer.writerows(existing)
    except (OSError, PermissionError):
        pass  # Read-only filesystem on Streamlit Cloud
