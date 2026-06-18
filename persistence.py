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
        if age < CACHE_TTL:
            return entry["data"]
    return None


def cache_set(key, data):
    cache = load_cache()
    cache[key] = {"data": data, "cached_at": datetime.now().isoformat()}
    save_cache(cache)
