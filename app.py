"""
NSE Stock Sentiment Analyzer
Enter any NSE ticker → get live price + news sentiment score + signal.
Built with Streamlit + yfinance + VADER + custom financial lexicon.
"""

__version__ = "2.9.0"

import json
import logging
import streamlit as st
import os
import re
import time
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)


def _ohlcv_to_json(hist):
    """Convert yfinance OHLCV DataFrame to JSON for TradingView Lightweight Charts."""
    if hist is None or hist.empty:
        return "[]"
    records = []
    for idx, row in hist.iterrows():
        ts = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        o = float(row.get("Open", 0) or 0)
        h = float(row.get("High", 0) or 0)
        l = float(row.get("Low", 0) or 0)
        c = float(row.get("Close", 0) or 0)
        v = int(row.get("Volume", 0) or 0)
        records.append({"time": ts, "open": o, "high": h, "low": l, "close": c, "volume": v})
    return json.dumps(records)


# ─── Contact / feature request info
CONTACT = {
    "email": "darkcharon3301@gmail.com",
    "x_url": "https://x.com/sentinelcipher",
    "x_handle": "@sentinelcipher",
    "chai_url": "https://chai4.me/ashaykushwaha003",
}

from data_fetcher import (
    NSE_TICKERS, get_stock_info, search_news, get_cached_history,
    resolve_ticker, fetch_market_headlines,
)
from sentiment import get_sia, analyze_headline_sentiment, get_weighted_signal
from event_classifier import classify_headline, adjust_with_event
from cascade import detect_cascade
from indicators import get_technical_indicators
from persistence import load_portfolio, save_portfolio, load_track_record, save_track_record, load_sentiment_history, save_sentiment_history, history_to_csv, update_source_accuracy, load_entry_prices, save_entry_price, get_entry_info, calc_portfolio_pnl, load_fiidii_history, save_fiidii_snapshot, ENTRY_PRICES_FILE
from render import render_dashboard, _is_valid_num
from market_data import get_fii_dii_flow, get_market_pulse, get_mmi
from aggregate_sentiment import compute_smartscore
from intraday import compute_vwap, compute_pivot_levels, get_vix


# ─── Page config ───
st.set_page_config(
    page_title="NSE Bull/Bear Edge — AI-Powered Sentiment Analyzer",
    page_icon="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 24 24' fill='none' stroke='%2322b573' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><line x1='12' y1='20' x2='12' y2='10'/><line x1='18' y1='20' x2='18' y2='4'/><line x1='6' y1='20' x2='6' y2='16'/></svg>",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ─── Global UI constants & styles ───
_CARET = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#8891a0" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="caret"><path d="m9 18 6-6-6-6"/></svg>'
st.markdown("""<style>
details.hermes-expander {
    background:rgba(255,255,255,0.03);
    border:1px solid rgba(255,255,255,0.06);
    border-radius:8px;
    padding:0.5rem 0.75rem;
    margin-bottom:0.5rem;
}
details.hermes-expander summary {
    cursor:pointer;
    display:flex;
    align-items:center;
    gap:6px;
    font-weight:600;
    font-size:0.95rem;
    color:#e4e6eb;
    list-style:none;
}
details.hermes-expander summary::-webkit-details-marker { display:none; }
details.hermes-expander summary .caret {
    transition:transform 0.2s;
}
details.hermes-expander[open] summary .caret {
    transform:rotate(90deg);
}
</style>""", unsafe_allow_html=True)

# ─── Streamlit chrome CSS (Geist, hide chrome, widget overrides) ───
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
    * { font-family: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif; }
    /* Hide Streamlit chrome */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stAppToolbar {display: none;}
    /* Custom scrollbar */
    ::-webkit-scrollbar {width: 6px;}
    ::-webkit-scrollbar-track {background: #0a0b0f;}
    ::-webkit-scrollbar-thumb {background: #1e2028; border-radius: 3px;}
    ::-webkit-scrollbar-thumb:hover {background: #2a2d35;}
    /* Widget overrides */
    .stTextInput input {border-radius: 8px;border-color: #1e2028 !important;font-size:1rem;padding:0.6rem 0.75rem;}

    /* Ticker search row: tighter spacing between input and search button */
    div[data-testid="column"]:has(button#svgsrch) {padding-left:0 !important;}
    div[data-testid="column"]:has(input[placeholder*="RELIANCE"]) {padding-right:0 !important;}
    div[data-testid="column"]:has(input[placeholder*="HDFCBANK"]) {padding-right:0 !important;}
    .stTextInput {margin-bottom:0 !important;}
    div[data-testid="stHorizontalBlock"]:has(div button#svgsrch) {gap:0 !important;}
    .stTextInput input:focus {border-color: #22b573 !important;box-shadow: 0 0 0 2px rgba(34,181,115,0.1) !important;}
    .stButton button {border-radius: 8px;border: 1px solid #1e2028;background: rgba(19,21,26,0.6);color: #e4e6eb;font-weight: 500;transition: all 0.2s ease;}
    .stButton button:hover {border-color: rgba(34,181,115,0.3);background: rgba(34,181,115,0.08);}
    /* Compact delete button for portfolio rows */
    .pf-del button {min-height:0 !important;padding:0.15rem 0.5rem !important;font-size:0.75rem !important;line-height:1 !important;border:none !important;background:transparent !important;color:#6b7280 !important;}
    .pf-del button:hover {color:#ef4444 !important;background:rgba(239,68,68,0.08) !important;}
    /* Tighten column gaps in portfolio section */
    .pf-row-cols [data-testid="stHorizontalBlock"] {gap: 0.25rem !important;}
    /* Custom header */
    .custom-header {display:flex;align-items:center;justify-content:space-between;padding:0.5rem 0 1.5rem 0;border-bottom:1px solid #1e2028;margin-bottom:1.5rem;}
    .custom-header .left {display:flex;align-items:center;gap:0.75rem;}
    .custom-header .logo {font-size:1.75rem;font-weight:800;letter-spacing:-0.03em;background:linear-gradient(135deg,#22b573,#0d9488);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
    .custom-header .tagline {font-size:0.8rem;color:#6b7280;margin-top:0.1rem;}
    .custom-header .gh-btn {display:inline-flex;align-items:center;gap:0.4rem;padding:0.4rem 0.75rem;border:1px solid #1e2028;border-radius:8px;color:#e4e6eb;font-size:0.8rem;font-weight:500;text-decoration:none;transition:all 0.2s ease;}
    .custom-header .gh-btn:hover {border-color:#22b573;color:#22b573;background:rgba(34,181,115,0.05);}
    /* Recalculate height now that header/footer are hidden */
    .block-container {padding-top:1rem !important;padding-bottom:0 !important;}

    /* Responsive: mobile-friendly adjustments */
    @media (max-width: 640px) {
        /* General sizing and tap targets */
        .stButton button {font-size: 0.8rem; padding: 0.3rem 0.5rem; min-height: 40px;}
        .stTextInput input {font-size: 0.95rem; padding: 0.5rem 0.65rem;}
        .st-emotion-cache-16idsys {gap: 0.25rem;}
        .block-container {padding-left: 0.75rem !important; padding-right: 0.75rem !important;}

        /* Search button — bigger tap target */
        .stTextInput + div .stButton button {font-size: 1.15rem; padding: 0.45rem 0.75rem;}

        /* Smaller header */
        .custom-header .logo {font-size: 1.3rem !important;}
        .custom-header .tagline {font-size: 0.7rem !important;}

        /* Smaller caption text */
        .stCaption {font-size: 0.75rem;}
        .stMetric label {font-size: 0.8rem;}
        .stMetric div[data-testid="stMetricValue"] {font-size: 1.2rem !important;}

        /* Portfolio briefing containers stack well */
        .stContainer .stHorizontalBlock > div {min-width: 0;}

        /* Privacy expander compact */
        .streamlit-expanderContent {font-size: 0.8rem;}
        .streamlit-expanderContent li, .streamlit-expanderContent p {font-size: 0.8rem;}

        /* Footer Chai4Me badge */
        a[aria-label*="Support"] {padding: 6px 16px !important;}
        a[aria-label*="Support"] img {height: 24px !important;}

        /* Bottom cards (Portfolio + Track Record) — redesigned */
    }

    /* Cascade / Ripple Effects card */
    .card {background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:1rem;margin-bottom:1rem;}
    .card-title {font-size:1rem;font-weight:700;color:#e4e6eb;margin-bottom:0.75rem;}
    .cw {display:flex;flex-direction:column;gap:0.75rem;}
    .cd {border-bottom:1px solid rgba(255,255,255,0.04);padding-bottom:0.75rem;}
    .cd:last-child {border-bottom:none;padding-bottom:0;}
    .ch {display:flex;align-items:center;gap:0.5rem;margin-bottom:0.4rem;font-size:0.85rem;}
    .cn {color:#e4e6eb;font-weight:600;}
    .cb {font-weight:700;font-size:0.8rem;}
    .cc {color:#6b7280;font-size:0.75rem;margin-left:auto;}
    .cticks {display:flex;flex-direction:column;gap:0.25rem;}
    .ct {display:flex;align-items:center;gap:0.45rem;padding:0.2rem 0.5rem;border-radius:6px;background:rgba(255,255,255,0.02);font-size:0.8rem;}
    .cs {color:#22b573;font-weight:700;min-width:5.5rem;}
    .cco {color:#8891a0;flex:1;font-size:0.75rem;}
    .cw {color:#6b7280;font-size:0.75rem;}
    .cti {font-size:0.65rem;font-weight:700;margin-left:auto;flex-shrink:0;}

</style>""", unsafe_allow_html=True)


# ─── Rate limiter: prevents rapid-fire searches that waste yfinance quota ───
# Tracks search timestamps per session. Max 6 searches per 60 seconds.
# Resets naturally when session expires (app sleep / inactivity).
_MAX_SEARCHES = 6
_SEARCH_WINDOW = 60  # seconds


def _check_rate_limit():
    """Return True if the user may proceed, False if rate-limited.

    Maintains a rolling window of search timestamps in session_state.
    If the user exceeds _MAX_SEARCHES in _SEARCH_WINDOW seconds,
    shows a warning and returns False.
    """
    now = time.time()
    timestamps = st.session_state.setdefault("_search_timestamps", [])

    # Prune entries outside the window
    cutoff = now - _SEARCH_WINDOW
    timestamps[:] = [t for t in timestamps if t > cutoff]

    if len(timestamps) >= _MAX_SEARCHES:
        oldest = timestamps[0]
        wait_sec = int(_SEARCH_WINDOW - (now - oldest))
        st.warning(
            f"⏳ You've made {_MAX_SEARCHES} searches in the last minute. "
            f"Please wait {wait_sec}s before searching again. "
            "This limit protects shared API resources for all users."
        )
        return False

    return True


def analyze_ticker(ticker, company_name, quick=False):
    """Run full analysis pipeline for a ticker. Returns dict or None.
    
    When quick=True (briefing mode), skips expensive news search and sentiment
    analysis — just returns price-only snapshot.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Parallelize independent network calls: stock info + news + FII/DII
    with ThreadPoolExecutor(max_workers=3) as pool:
        stock_future = pool.submit(get_stock_info, ticker)
        news_future = pool.submit(search_news, ticker, company_name)
        fii_future = pool.submit(get_fii_dii_flow)
        stock_data = stock_future.result()

    if not stock_data:
        # Discard pending results if stock data failed
        news_future.cancel()
        fii_future.cancel()
        return None

    if quick:
        # Briefing mode: skip news-heavy pipeline, return price-only snapshot
        return {
            "stock_data": stock_data,
            "news_items": [],
            "headline_scores": [],
            "signal": "NEUTRAL",
            "avg_compound": 0.0,
            "signal_emoji": "⚪",
            "weighted_signal": "NEUTRAL",
            "blended_compound": 0.0,
            "weighted_emoji": "⚪",
            "source_breakdown": [],
            "num_articles": 0,
            "source_stats": {},
            "smartscore": 0.0,
            "smartscore_signal": "NEUTRAL",
            "smartscore_emoji": "⚪",
            "smartscore_components": None,
            "event_tags": [],
            "smartscore_history": [],
            "vwap": None,
            "pivot_levels": None,
            "fii_data": fii_future.result(),
            "cascade_effects": [],
        }

    use_finbert = os.environ.get("USE_FINBERT", "").strip().lower() in ("1", "true", "yes")
    pipe_finbert = None
    if use_finbert:
        from sentiment import get_finbert, analyze_headline_finbert
        pipe_finbert = get_finbert()

    sia = None if use_finbert else get_sia()
    # Retrieve news result from parallel future (already fetched above)
    news_items, cascade_pool, source_stats = news_future.result()

    # Phase 1: Sentiment scoring (FinBERT or VADER+events)
    headline_scores = []
    event_adjusted_scores = []
    event_tags = []
    for n in news_items:
        if pipe_finbert:
            score = analyze_headline_finbert(n["title"], n["body"], pipe_finbert)
            score["source"] = n.get("source")
            score["event_type"] = None
            score["event_base"] = 0.0
            score["adjusted_compound"] = score["compound"]
        else:
            score = analyze_headline_sentiment(n["title"], n["body"], sia, source=n.get("source"))
            event_type, event_base = classify_headline(n["title"], n["body"])
            adjusted = adjust_with_event(score["compound"], event_base)
            score["event_type"] = event_type
            score["event_base"] = event_base
            score["adjusted_compound"] = adjusted
        headline_scores.append(score)
        event_adjusted_scores.append(score["adjusted_compound"])
        event_tags.append(score.get("event_type"))

    # Phase 2: SmartScore composite (0-100) with EWMA + breadth + volume
    history = load_sentiment_history(ticker)
    ss_result, ss_history = compute_smartscore(headline_scores, event_adjusted_scores, history)

    # Persist today's aggregated stats to history CSV
    if event_adjusted_scores:
        save_sentiment_history(ticker, {
            "headline_count": ss_result["headline_count"],
            "pos_count": ss_result["pos_count"],
            "neg_count": ss_result["neg_count"],
            "avg_compound": sum(event_adjusted_scores) / len(event_adjusted_scores),
            "event_avg": ss_result["s_events"],
            "smartscore": ss_result["smartscore"],
        })

    # Use weighted signal as the primary (and only) signal
    weighted_signal, blended_compound, weighted_emoji, source_breakdown = get_weighted_signal(headline_scores)

    # Cascade/Ripple Tracking — scan all market news (including non-ticker articles) for commodity keywords
    cascade_effects = detect_cascade(cascade_pool, ticker_lookup=NSE_TICKERS, focus_ticker=ticker)

    # Intraday tools — skip if yfinance is rate-limited to avoid extra API pressure
    from data_fetcher import _check_rate_limited
    vwap_data = None if _check_rate_limited() else compute_vwap(ticker)

    return {
        "stock_data": stock_data,
        "news_items": news_items,
        "headline_scores": headline_scores,
        "signal": weighted_signal,
        "avg_compound": blended_compound,
        "signal_emoji": weighted_emoji,
        "weighted_signal": weighted_signal,
        "blended_compound": blended_compound,
        "weighted_emoji": weighted_emoji,
        "source_breakdown": source_breakdown,
        "num_articles": len(news_items),
        "source_stats": source_stats,
        # New SmartScore data (consumed by render.py)
        "smartscore": ss_result["smartscore"],
        "smartscore_signal": ss_result["signal"],
        "smartscore_emoji": ss_result["signal_emoji"],
        "smartscore_components": ss_result,
        "event_tags": event_tags,
        "smartscore_history": ss_history,
        # Intraday trading data
        "vwap": vwap_data,
        "pivot_levels": None,  # set after TI fetch in main flow
        # FII/DII (fetched in parallel above)
        "fii_data": fii_future.result(),
        # Cascade/ripple effects
        "cascade_effects": cascade_effects,
    }


def _fetch_portfolio_price(t):
    """Fetch price for one portfolio ticker — runs in worker thread."""
    try:
        tk = yf.Ticker(t + ".NS")
        hist = tk.history(period="2d")
        if hist is not None and not hist.empty:
            cp = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else cp
            return t, {
                "change_pct": round((cp - prev) / prev * 100, 2),
                "current_price": cp,
            }
    except Exception:
        logger.warning("_refresh_price_cache failed for %s", t)
    return t, None


def _refresh_price_cache(portfolio):
    """Fetch current prices for all portfolio stocks and cache in session state."""
    if not portfolio:
        return
    cache = st.session_state.setdefault("_stock_price_cache", {})
    missing = [t for t in portfolio if t not in cache]
    if not missing:
        return
    from concurrent.futures import ThreadPoolExecutor, as_completed

    _failed = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_fetch_portfolio_price, t): t for t in missing}
        for future in as_completed(futures):
            t, result = future.result()
            if result is not None:
                cache[t] = result
            else:
                _failed.append(t)
    if _failed:
        st.warning(f"Could not refresh price for: {', '.join(_failed)}")


def _render_portfolio_list(portfolio, entry_prices, key_prefix="side"):
    """Render portfolio listing with delete buttons for the sidebar.

    Compact single-line layout with ticker, price, P&L, and remove button.
    No heatmap, no summary stats, no briefing button.
    """
    if not portfolio:
        st.markdown(
            '<div style="color:#6b7280;font-size:0.8rem;padding:0.5rem 0">'
            'No tickers yet. Use the add form below the analysis.</div>',
            unsafe_allow_html=True,
        )
        return

    for t in portfolio:
        ep = entry_prices.get(t)
        sd_cache = st.session_state.get("_stock_price_cache", {}).get(t)
        cp = sd_cache.get("current_price") if sd_cache else None

        ep_price, ep_qty = get_entry_info(ep)

        c1, c2 = st.columns([3, 1])
        display_parts = [f"<strong>{t}</strong>"]
        if _is_valid_num(cp):
            display_parts.append(f'<span style="font-size:0.85rem;">\u20b9{cp:,.2f}</span>')
        elif sd_cache is not None:
            display_parts.append(f'<span style="font-size:0.85rem;color:#6b7280;">Price N/A</span>')
        if ep_qty > 0:
            display_parts.append(f'<span style="font-size:0.7rem;color:#6b7280;">\u00d7{ep_qty}</span>')
        if ep_price and _is_valid_num(cp):
            pnl = calc_portfolio_pnl(ep_price, cp, ep_qty)
            sign = "+" if pnl["pnl_pct"] >= 0 else ""
            display_parts.append(
                f'<span style="font-size:0.8rem;color:{"#22c55e" if pnl["pnl_pct"] >= 0 else "#ef4444"};">'
                f'{sign}{pnl["pnl_pct"]:.1f}%</span>'
            )
            display_parts.append(f'<span style="font-size:0.7rem;color:#6b7280;">ATP \u20b9{ep_price:,.0f}</span>')
        elif ep_price:
            display_parts.append(f'<span style="font-size:0.75rem;color:#6b7280;">ATP \u20b9{ep_price:,.0f}</span>')
        elif cp:
            display_parts.append(f'<span style="font-size:0.7rem;color:#6b7280;">No ATP set</span>')
        c1.markdown(
            '<div style="line-height:1.5;">' + '<br>'.join(display_parts) + '</div>',
            unsafe_allow_html=True,
        )

        if c2.button("\u2715", key=f"{key_prefix}_del_{t}", help=f"Remove {t} from portfolio"):
            portfolio.remove(t)
            save_portfolio(portfolio)
            st.session_state._skip_reanalysis = True
            st.rerun()


def _render_bottom_cards(portfolio, final_ticker, entry_prices):
    """Render the bottom Portfolio + Track Record cards section.

    Uses Streamlit native containers with glassmorphism styling for a
    premium look. Portfolio and Track Record sit side-by-side, with a
    sentiment history expander below.
    """
    _FOLDER = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
    _BAR = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>'

    bc1, bc2 = st.columns([1.6, 1])
    eprices = entry_prices

    # ─── Portfolio Card ───
    with bc1:
        # Add ticker form (Streamlit widgets, outside card)
        ac1, ac2, ac3, ac4 = st.columns([1.8, 0.8, 0.8, 0.4])
        with ac1:
            new_t = st.text_input("Ticker", placeholder="RELIANCE", label_visibility="collapsed",
                                  max_chars=15, key="btm_add_ticker")
        with ac2:
            ep_input = st.text_input("ATP", placeholder="ATP", label_visibility="collapsed",
                                     max_chars=10, key="btm_add_atp",
                                     help="Average trade price for P&L tracking")
        with ac3:
            qty_input = st.text_input("Qty", placeholder="Qty", label_visibility="collapsed",
                                      max_chars=6, key="btm_add_qty",
                                      help="Number of shares held")
        with ac4:
            if st.button("+", use_container_width=True, key="btm_add_btn",
                         help="Add to portfolio") and new_t.strip():
                t = new_t.strip().upper().replace(".NS", "")
                # Resolve aliases (e.g. "HDFC BANK" → "HDFCBANK")
                _rt, _rn = resolve_ticker(t)
                if _rt:
                    t = _rt
                if not re.match(r'^[A-Z0-9&-]+$', t):
                    st.warning("Invalid ticker format")
                elif t in portfolio:
                    st.warning(f"{t} already in portfolio")
                else:
                    portfolio.append(t)
                    save_portfolio(portfolio)
                    qty_val = 1
                    if qty_input.strip():
                        try:
                            qty_val = int(qty_input.strip().replace(",", ""))
                        except ValueError:
                            pass
                    if ep_input.strip():
                        try:
                            save_entry_price(t, float(ep_input.strip().replace(",", "")), qty_val)
                        except ValueError:
                            st.warning("Could not parse ATP -- stock added without entry price")
                    else:
                        save_entry_price(t, 0, qty_val)
                    st.session_state._skip_reanalysis = True
                    st.rerun()

        # Portfolio rows (static HTML card)
        if portfolio:
            row_parts = []
            for t in portfolio:
                ep = eprices.get(t)
                sd = st.session_state.get("_stock_price_cache", {}).get(t)
                cp = sd.get("current_price") if sd else None

                ep_price, ep_qty = get_entry_info(ep)

                ticker_html = f'<span style="font-weight:600;font-size:0.85rem;color:#f0f2f5;min-width:3.5rem">{t}</span>'
                parts = [ticker_html]

                if _is_valid_num(cp):
                    parts.append(f'<span style="font-size:0.8rem;color:#c0c5ce">\u20b9{cp:,.2f}</span>')

                if ep_qty > 0:
                    parts.append(f'<span style="font-size:0.7rem;color:#6b7280">\u00d7{ep_qty}</span>')

                if ep_price and _is_valid_num(cp):
                    pnl = calc_portfolio_pnl(ep_price, cp, ep_qty)
                    pnl_color = "#22c55e" if pnl["pnl_pct"] >= 0 else "#ef4444"
                    pnl_sign = "+" if pnl["pnl_pct"] >= 0 else ""
                    parts.append(f'<span style="font-size:0.78rem;font-weight:600;color:{pnl_color}">{pnl_sign}{pnl["pnl_pct"]:.1f}%</span>')
                    parts.append(f'<span style="font-size:0.7rem;color:#6b7280">ATP \u20b9{ep_price:,.0f}</span>')
                elif ep_price:
                    parts.append(f'<span style="font-size:0.7rem;color:#6b7280">ATP \u20b9{ep_price:,.0f}</span>')

                row_parts.append(
                    f'<div style="display:flex;align-items:center;gap:0.5rem;padding:0.4rem 0;'
                    f'border-bottom:1px solid rgba(42,46,58,0.4);line-height:1.3">'
                    f'{"".join(parts)}</div>'
                )

            # Summary stats (qty-weighted)
            total_invested = sum(
                get_entry_info(eprices.get(t))[0] * get_entry_info(eprices.get(t))[1]
                for t in portfolio if eprices.get(t)
            )
            total_current = sum(
                sd.get("current_price", 0) * get_entry_info(eprices.get(t))[1]
                for t in portfolio
                if (sd := st.session_state.get("_stock_price_cache", {}).get(t))
                and _is_valid_num(sd.get("current_price"))
            )
            n_with_prices = sum(
                1 for t in portfolio
                if st.session_state.get("_stock_price_cache", {}).get(t)
            )
            day_chg = sum(
                sd.get("change_pct", 0) or 0
                for t in portfolio
                if (sd := st.session_state.get("_stock_price_cache", {}).get(t))
            )
            day_avg = day_chg / n_with_prices if n_with_prices else 0
            total_pnl = total_current - total_invested if total_invested and total_current else None
            total_pnl_pct = (total_pnl / total_invested * 100) if total_pnl is not None else None

            sum_items = []
            if total_invested:
                sum_items.append(f'<span style="font-size:0.75rem;color:#8891a0">Invested <span style="font-weight:600;color:#c0c5ce">\u20b9{total_invested:,.0f}</span></span>')
            if total_current:
                sum_items.append(f'<span style="font-size:0.75rem;color:#8891a0">Current <span style="font-weight:600;color:#c0c5ce">\u20b9{total_current:,.0f}</span></span>')
            if total_pnl_pct is not None:
                pnl_color = "#22c55e" if total_pnl >= 0 else "#ef4444"
                pnl_sign = "+" if total_pnl >= 0 else ""
                sum_items.append(f'<span style="font-size:0.75rem;color:#8891a0">P&amp;L <span style="font-weight:600;color:{pnl_color}">{pnl_sign}{total_pnl_pct:.1f}%</span></span>')
            if day_avg:
                day_color = "#22c55e" if day_avg >= 0 else "#ef4444"
                day_sign = "+" if day_avg >= 0 else ""
                sum_items.append(f'<span style="font-size:0.75rem;color:#8891a0">Day <span style="font-weight:600;color:{day_color}">{day_sign}{day_avg:.1f}%</span></span>')

            summary_html = ""
            if sum_items:
                summary_html = (
                    f'<div style="display:flex;gap:1rem;padding:0.5rem 0 0.15rem;'
                    f'border-top:1px solid #2a2e3a;margin-top:0.3rem;flex-wrap:wrap">'
                    f'{"".join(sum_items)}</div>'
                )

            rows_html = "".join(row_parts)
            card_html = (
                f'<div style="background:rgba(19,21,26,0.85);backdrop-filter:blur(20px);'
                f'-webkit-backdrop-filter:blur(20px);border:1px solid rgba(30,32,40,0.8);'
                f'border-radius:12px;padding:1.25rem;margin-bottom:1rem;'
                f'box-shadow:0 1px 3px rgba(0,0,0,0.2);transition:border-color 0.2s ease,box-shadow 0.2s ease">'
                f'<div style="display:flex;align-items:center;gap:0.5rem;font-size:0.9rem;'
                f'font-weight:600;color:#f0f2f5;margin-bottom:0.75rem">{_FOLDER} Portfolio</div>'
                f'{rows_html}{summary_html}</div>'
            )
        else:
            card_html = (
                f'<div style="background:rgba(19,21,26,0.85);backdrop-filter:blur(20px);'
                f'-webkit-backdrop-filter:blur(20px);border:1px solid rgba(30,32,40,0.8);'
                f'border-radius:12px;padding:1.25rem;margin-bottom:1rem;'
                f'box-shadow:0 1px 3px rgba(0,0,0,0.2);transition:border-color 0.2s ease,box-shadow 0.2s ease">'
                f'<div style="display:flex;align-items:center;gap:0.5rem;font-size:0.9rem;'
                f'font-weight:600;color:#f0f2f5;margin-bottom:0.75rem">{_FOLDER} Portfolio</div>'
                f'<div style="color:#6b7280;font-size:0.8rem;padding:0.5rem 0">No holdings yet. Add a ticker above.</div>'
                f'</div>'
            )
        st.markdown(card_html, unsafe_allow_html=True)
        if portfolio:
            if st.button("Clear all holdings", key="clear_portfolio_main",
                          type="secondary", use_container_width=True):
                save_portfolio([])
                ENTRY_PRICES_FILE.write_text("{}", encoding="utf-8")
                st.session_state._skip_reanalysis = True
                st.rerun()

    with bc2:
        recs = load_track_record()
        voted = [r for r in recs if r.get("vote") is not None]
        acc = sum(1 for r in voted if r["vote"] is True) if voted else 0
        acc_pct = acc / len(voted) * 100 if voted else 0

        if voted:
            acc_color = "#22c55e" if acc_pct >= 60 else "#f59e0b" if acc_pct >= 40 else "#ef4444"
            acc_html = (
                f'<div style="text-align:center;margin:0.5rem 0">'
                f'<div style="font-size:2rem;font-weight:800;color:{acc_color};line-height:1">{acc_pct:.0f}%</div>'
                f'<div style="font-size:0.75rem;color:#8891a0;margin-top:0.15rem">{acc}/{len(voted)} correct</div></div>'
                f'<div style="height:6px;background:#1a1a2e;border-radius:3px;overflow:hidden;margin:0.4rem 0">'
                f'<div style="height:100%;width:{acc_pct:.0f}%;background:{acc_color};border-radius:3px;transition:width 0.4s"></div></div>'
            )
        else:
            acc_html = (
                '<div style="text-align:center;padding:0.5rem 0;color:#6b7280;font-size:0.85rem">'
                'No votes yet. Search a ticker and vote on the signal.</div>'
            )

        stats_html = (
            f'<div style="display:flex;justify-content:space-around;padding:0.3rem 0">'
            f'<div style="text-align:center"><div style="font-size:1.1rem;font-weight:700;color:#f0f2f5">{len(recs)}</div>'
            f'<div style="font-size:0.7rem;color:#8891a0">Scans</div></div>'
            f'<div style="text-align:center"><div style="font-size:1.1rem;font-weight:700;color:#22c55e">{acc}</div>'
            f'<div style="font-size:0.7rem;color:#8891a0">Right</div></div>'
            f'<div style="text-align:center"><div style="font-size:1.1rem;font-weight:700;color:#ef4444">{len(voted) - acc}</div>'
            f'<div style="font-size:0.7rem;color:#8891a0">Wrong</div></div>'
            f'</div>'
        )

        st.markdown(
            f'<div style="background:rgba(19,21,26,0.85);backdrop-filter:blur(20px);'
            f'-webkit-backdrop-filter:blur(20px);border:1px solid rgba(30,32,40,0.8);'
            f'border-radius:12px;padding:1.25rem;margin-bottom:1rem;'
            f'box-shadow:0 1px 3px rgba(0,0,0,0.2);transition:border-color 0.2s ease,box-shadow 0.2s ease">'
            f'<div style="display:flex;align-items:center;gap:0.5rem;font-size:0.9rem;'
            f'font-weight:600;color:#f0f2f5;margin-bottom:0.75rem">{_BAR} Track Record</div>'
            f'{acc_html}{stats_html}</div>',
            unsafe_allow_html=True,
        )

    # ─── Institutional Flow Card ───
    fiidii_hist = load_fiidii_history()
    if not fiidii_hist:
        # No saved history yet — try fetching current data to create first snapshot
        fii_data = get_fii_dii_flow()
        if fii_data:
            save_fiidii_snapshot(fii_data)
            fiidii_hist = load_fiidii_history()

    if fiidii_hist:
        _INST = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>'
        latest = fiidii_hist[-1]
        fii_val = latest.get("fii_net", 0)
        dii_val = latest.get("dii_net", 0)
        net_val = fii_val + dii_val

        fii_color = "#22c55e" if fii_val >= 0 else "#ef4444"
        dii_color = "#22c55e" if dii_val >= 0 else "#ef4444"
        net_color = "#22c55e" if net_val >= 0 else "#ef4444"

        st.markdown(
            f'<div style="background:rgba(19,21,26,0.85);backdrop-filter:blur(20px);'
            f'-webkit-backdrop-filter:blur(20px);border:1px solid rgba(30,32,40,0.8);'
            f'border-radius:12px;padding:1.25rem;margin-bottom:1rem;'
            f'box-shadow:0 1px 3px rgba(0,0,0,0.2)">'
            f'<div style="display:flex;align-items:center;gap:0.5rem;font-size:0.9rem;'
            f'font-weight:600;color:#f0f2f5;margin-bottom:0.75rem">{_INST} Institutional Flow</div>'
            f'<div style="display:flex;gap:1.5rem;justify-content:space-around">'
            f'<div style="text-align:center"><div style="font-size:1.1rem;font-weight:700;color:{fii_color}">'
            f'\u20b9{fii_val:+,.0f} Cr</div>'
            f'<div style="font-size:0.7rem;color:#8891a0">FII/FPI</div></div>'
            f'<div style="text-align:center"><div style="font-size:1.1rem;font-weight:700;color:{dii_color}">'
            f'\u20b9{dii_val:+,.0f} Cr</div>'
            f'<div style="font-size:0.7rem;color:#8891a0">DII</div></div>'
            f'<div style="text-align:center;padding:0 0.5rem;border-left:1px solid #2a2e3a"><div style="font-size:1.1rem;font-weight:700;color:{net_color}">'
            f'\u20b9{net_val:+,.0f} Cr</div>'
            f'<div style="font-size:0.7rem;color:#8891a0">Net</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Recent history compact table
        if len(fiidii_hist) >= 2:
            recent = fiidii_hist[-7:]  # last 7 entries
            rows = ""
            for entry in reversed(recent):
                date = entry.get("date", "")
                f = entry.get("fii_net", 0)
                d = entry.get("dii_net", 0)
                n = f + d
                fc = "#22c55e" if f >= 0 else "#ef4444"
                dc = "#22c55e" if d >= 0 else "#ef4444"
                nc = "#22c55e" if n >= 0 else "#ef4444"
                rows += (
                    f'<div style="display:grid;grid-template-columns:1.5fr 1fr 1fr 1fr;'
                    f'gap:0.5rem;padding:0.3rem 0;font-size:0.75rem;'
                    f'border-bottom:1px solid rgba(42,46,58,0.3)">'
                    f'<span style="color:#8891a0">{date}</span>'
                    f'<span style="color:{fc};text-align:right">\u20b9{f:+,.0f}</span>'
                    f'<span style="color:{dc};text-align:right">\u20b9{d:+,.0f}</span>'
                    f'<span style="color:{nc};text-align:right;font-weight:600">\u20b9{n:+,.0f}</span>'
                    f'</div>'
                )
            if rows:
                st.markdown(
                    f'<div style="background:rgba(19,21,26,0.85);backdrop-filter:blur(20px);'
                    f'-webkit-backdrop-filter:blur(20px);border:1px solid rgba(30,32,40,0.8);'
                    f'border-radius:12px;padding:0.75rem 1rem;margin:-0.5rem 0 1rem">'
                    f'<div style="display:grid;grid-template-columns:1.5fr 1fr 1fr 1fr;'
                    f'gap:0.5rem;padding:0.3rem 0;font-size:0.7rem;color:#6b7280;'
                    f'border-bottom:1px solid rgba(42,46,58,0.3)">'
                    f'<span>Date</span><span style="text-align:right">FII/FPI</span>'
                    f'<span style="text-align:right">DII</span>'
                    f'<span style="text-align:right;font-weight:600">Net</span></div>'
                    f'{rows}</div>',
                    unsafe_allow_html=True,
                )

    # ─── Sentiment History (collapsed by default) ───
    history = load_sentiment_history(final_ticker)
    if history:
        with st.expander("Sentiment History", expanded=False):
            df = pd.DataFrame(history)
            if "smartscore" in df.columns:
                df["smartscore"] = pd.to_numeric(df["smartscore"], errors="coerce")
                df = df.dropna(subset=["smartscore"])
                if not df.empty:
                    df = df.copy()
                    df["date"] = pd.to_datetime(df["date"], errors="coerce")
                    df = df.dropna(subset=["date"])
                    if not df.empty:
                        chart_df = df.set_index("date")[["smartscore"]]
                        st.line_chart(chart_df, y="smartscore", use_container_width=True)
            csv_data = history_to_csv(final_ticker, history)
            st.download_button(
                label="Export CSV",
                data=csv_data,
                file_name=f"{final_ticker}_sentiment_history.csv",
                mime="text/csv",
                use_container_width=True,
            )


# ─── Sidebar ───
with st.sidebar:
    portfolio = load_portfolio()
    entry_prices = load_entry_prices()
    _refresh_price_cache(portfolio)

    # ─── Portfolio list ───
    if portfolio:
        _FOLDER = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:0.4rem;font-size:0.85rem;'
            f'font-weight:600;color:#f0f2f5;margin-bottom:0.5rem">{_FOLDER} Portfolio ({len(portfolio)})</div>',
            unsafe_allow_html=True,
        )
        _render_portfolio_list(portfolio, entry_prices, key_prefix="side")

        if st.button("Clear all holdings", key="clear_portfolio", type="secondary",
                     use_container_width=True):
            save_portfolio([])
            # Clear entry prices too
            ENTRY_PRICES_FILE.write_text("{}", encoding="utf-8")
            st.session_state._skip_reanalysis = True
            st.rerun()
    else:
        st.markdown(
            '<div style="color:#6b7280;font-size:0.8rem;padding:0.5rem 0">'
            'No holdings yet. Add tickers in the analysis section below.</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ─── Changelog & Feedback ───
    _FILE_TEXT_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/></svg>'
    st.markdown(f'<details class="hermes-expander"><summary>{_CARET}{_FILE_TEXT_SVG} What\'s New</summary>', unsafe_allow_html=True)
    try:
        if "_changelog_cache" not in st.session_state:
            with open("CHANGELOG.md", encoding="utf-8") as f:
                st.session_state._changelog_cache = f.readlines()
        lines = st.session_state._changelog_cache
        st.markdown("".join(lines[:40]), unsafe_allow_html=True)
        if len(lines) > 40:
            st.caption("... see CHANGELOG.md for full history")
    except FileNotFoundError:
        st.caption("Changelog coming soon")
    st.markdown('</details>', unsafe_allow_html=True)
    st.markdown(
        f'<div style="text-align:center;font-size:0.8rem;color:#6b7280;">'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/></svg>'
        f' Feature requests: <a href="mailto:{CONTACT["email"]}" '
        f'style="color:#22b573;text-decoration:none;">{CONTACT["email"]}</a> · '
        f'<a href="{CONTACT["x_url"]}" '
        f'style="color:#22b573;text-decoration:none;">{CONTACT["x_handle"]}</a></div>',
        unsafe_allow_html=True,
    )

# ─── Main UI ───

# ─── Premium header ───
st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;
    padding:0.5rem 0 1.5rem 0;border-bottom:1px solid #1e2028;margin-bottom:1.5rem;">
    <div style="display:flex;align-items:center;gap:0.75rem;">
        <div>
            <div style="font-size:1.25rem;font-weight:700;letter-spacing:-0.02em;
                background:linear-gradient(135deg,#22b573,#0d9488);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                background-clip:text;">NSE Bull/Bear Edge<span style="font-weight:400;color:#6b7280;"> — AI-Powered Sentiment Analyzer</span></div>
            <div style="font-size:0.8rem;color:#6b7280;margin-top:0.15rem;">
                Live price · Multi-source sentiment · Technical indicators</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ─── Market Pulse & VIX ───
if "market_pulse" not in st.session_state:
    st.session_state.market_pulse = get_market_pulse()
if "vix" not in st.session_state:
    st.session_state.vix = get_vix()

pulse_d = st.session_state.market_pulse
vix_d = st.session_state.vix
_has_pulse = pulse_d and pulse_d.get("nifty_price") is not None
_has_vix = vix_d and vix_d.get("vix") is not None

if _has_pulse or _has_vix:
    st.markdown("---")
    # ─── Section label ───
    st.markdown(
        '<div style="display:flex;align-items:center;gap:0.4rem;font-size:0.85rem;'
        'font-weight:600;color:#f0f2f5;margin-bottom:0.5rem">'
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>'
        ' Market Pulse</div>',
        unsafe_allow_html=True,
    )

    # Compute MMI (cached in session_state)
    if "mmi_data" not in st.session_state:
        st.session_state.mmi_data = get_mmi()
    mmi_d = st.session_state.mmi_data
    _has_mmi = mmi_d and mmi_d.get("mmi") is not None

    cols = st.columns([1, 1, 1])
    # ─── Column 1: Nifty 50 ───
    if _has_pulse:
        price = pulse_d["nifty_price"]
        chg = pulse_d["nifty_change_pct"]
        arrow = "\u25b2" if chg is not None and chg >= 0 else "\u25bc"
        cols[0].metric(
            "Nifty 50",
            f"{price:,.0f}",
            f"{arrow} {chg:+.2f}%" if chg is not None else "N/A",
        )
    else:
        cols[0].metric("Nifty 50", "\u2014", "Unavailable")
    # ─── Column 2: MMI Gauge ───
    if _has_mmi:
        mmi_val = mmi_d["mmi"]
        zone = mmi_d["zone"]
        _mc = {
            "Extreme Greed": "#22b573", "Greed": "#4ade80",
            "Neutral": "#8891a0", "Fear": "#f59e0b",
            "Extreme Fear": "#f85149",
        }
        m_color = _mc.get(zone, "#8891a0")
        # MMI icon based on zone
        _icons = {
            "Extreme Greed": "\U0001f7e2",
            "Greed": "\U0001f7e2",
            "Neutral": "\u26aa",
            "Fear": "\U0001f7e0",
            "Extreme Fear": "\U0001f534",
        }
        m_icon = _icons.get(zone, "\u26aa")
        # Sub-score summary
        sub = (
            f"T:{mmi_d['trend_score']:.0f}  V:{mmi_d['vix_score']:.0f}  "
            f"F:{mmi_d['fii_score']:.0f}  B:{mmi_d['breadth_score']:.0f}"
        )
        cols[1].markdown(
            '<div style="text-align:center;padding:0.25rem 0">'
            '<div style="font-size:0.7rem;color:#8891a0;text-transform:uppercase;letter-spacing:0.04em;">MMI</div>'
            f'<div style="font-size:1.4rem;font-weight:700;color:{m_color};">{mmi_val:.0f}</div>'
            f'<div style="font-size:0.85rem;font-weight:600;color:{m_color};">{m_icon} {zone}</div>'
            f'<div style="font-size:0.6rem;color:#6b7280;margin-top:0.15rem;font-family:monospace;">{sub}</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        cols[1].markdown(
            '<div style="text-align:center;padding:0.25rem 0">'
            '<div style="font-size:0.7rem;color:#8891a0;text-transform:uppercase;letter-spacing:0.04em;">MMI</div>'
            '<div style="font-size:1rem;font-weight:700;color:#6b7280;">\u2014</div>'
            '<div style="font-size:0.65rem;color:#6b7280;margin-top:0.15rem;">Data unavailable</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    # ─── Column 3: India VIX ───
    if _has_vix:
        vix_dir = "\u2b06\ufe0f" if vix_d["change"] >= 0 else "\u2b07\ufe0f"
        cols[2].metric(
            "India VIX",
            f"{vix_d['vix']:.1f}",
            f"{vix_dir} {vix_d['change']:+.2f}",
        )
        if vix_d["level"] == "High":
            cols[2].markdown(
                '<span style="display:inline-flex;align-items:center;gap:4px;font-size:0.75rem;color:#8891a0;">'
                '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>'
                ' High VIX — sharp reversals likely. Trade with caution.</span>',
                unsafe_allow_html=True,
            )
        elif vix_d["level"] == "Low":
            cols[2].markdown(
                '<span style="display:inline-flex;align-items:center;gap:4px;font-size:0.75rem;color:#8891a0;">'
                '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#22b573" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>'
                ' Low VIX — trending markets favored.</span>',
                unsafe_allow_html=True,
            )
    else:
        cols[2].metric("India VIX", "\u2014", "Unavailable")

# ─── Ticker Input — single text field + search button ───
# ─── Shareable snapshot link: ?ticker=X bypasses normal input ───
query_ticker = st.query_params.get("ticker", "")
if query_ticker:
    query_ticker = query_ticker.strip().upper().replace(".NS", "")
    if query_ticker and re.match(r'^[A-Z0-9&-]+$', query_ticker):
        final_ticker = query_ticker
        company_name = NSE_TICKERS.get(final_ticker, final_ticker)
        with st.spinner(f"Loading analysis for {final_ticker}..."):
            result = analyze_ticker(final_ticker, company_name)
        if result:
            st.markdown(
                '<div style="text-align:right;margin-bottom:0.5rem;">'
                '<a href="/" style="color:#22b573;font-size:0.85rem;text-decoration:none;">'
                '\u2190 Back to main app</a></div>',
                unsafe_allow_html=True,
            )
            # Compute supporting data like the normal search path
            ti = get_technical_indicators(final_ticker)
            hist_cache = get_cached_history(final_ticker)
            _hist = hist_cache.tail(5) if hist_cache is not None and len(hist_cache) >= 1 else None
            result["pivot_levels"] = compute_pivot_levels(_hist)
            records = load_track_record()
            fii_data = get_fii_dii_flow()
            if fii_data:
                save_fiidii_snapshot(fii_data)
            ohlcv_json = _ohlcv_to_json(hist_cache)
            html = render_dashboard(
                result, final_ticker, company_name,
                technical_indicators=ti,
                track_record=records,
                fii_dii_data=fii_data,
                ohlcv_json=ohlcv_json,
            )
            st.components.v1.html(html, height=result.get("_height", 3000), scrolling=True)
        else:
            st.error(f"No data found for **{final_ticker}**")
        st.stop()

ticker_col, btn_col = st.columns([5, 0.6])
with ticker_col:
    ticker_input = st.text_input(
        "NSE Ticker Symbol",
        placeholder="Type ticker or company name...",
        max_chars=15,
        label_visibility="collapsed",
    )
    # Autocomplete: filter NSE_TICKERS + ALIASES as user types (local only, fast)
    _ac_query = ticker_input.strip()
    _ac_options = []
    if len(_ac_query) >= 2:
        _ac_q = _ac_query.upper()
        _ac_seen = set()
        # Pass 1: ticker symbol prefix match
        for _s, _n in NSE_TICKERS.items():
            if _s in _ac_seen:
                continue
            if _s.startswith(_ac_q):
                _ac_options.append(f"{_s} — {_n}")
                _ac_seen.add(_s)
                if len(_ac_options) >= 10:
                    break
        # Pass 2: company name contains
        if len(_ac_options) < 10:
            for _s, _n in NSE_TICKERS.items():
                if _s in _ac_seen:
                    continue
                if _ac_q in _n.upper():
                    _ac_options.append(f"{_s} — {_n}")
                    _ac_seen.add(_s)
                    if len(_ac_options) >= 10:
                        break
        # Pass 3: alias reverse lookup (e.g. "HDFC" finds "HDFC BANK" → HDFCBANK)
        if len(_ac_options) < 10:
            from data_fetcher import _ALIAS_LOOKUP
            for _ak, _at in _ALIAS_LOOKUP.items():
                if _at in _ac_seen:
                    continue
                if _ac_q in _ak or _ak.startswith(_ac_q):
                    _ac_options.append(f"{_at} — {NSE_TICKERS.get(_at, _ak)}")
                    _ac_seen.add(_at)
                    if len(_ac_options) >= 10:
                        break
    if _ac_options:
        _ac_pick = st.selectbox(
            "Select ticker",
            _ac_options,
            index=None,
            placeholder="Pick a ticker...",
            label_visibility="collapsed",
            key="ac_select",
        )
        if _ac_pick:
            ticker_input = _ac_pick.split(" — ")[0]


with btn_col:
    search_trigger_id = "svgsrch"
    st.markdown(
        f"""
        <div style="width:100%;height:38px;display:flex;align-items:center;justify-content:center;">
        <button id="{search_trigger_id}"
                style="width:38px;height:38px;background:rgba(19,21,26,0.6);
                       border:1px solid #1e2028;border-radius:8px;cursor:pointer;
                       display:flex;align-items:center;justify-content:center;
                       color:#e4e6eb;transition:all 0.2s ease;padding:0;"
                onmouseover="this.style.borderColor='rgba(34,181,115,0.3)';this.style.background='rgba(34,181,115,0.08)'"
                onmouseout="this.style.borderColor='#1e2028';this.style.background='rgba(19,21,26,0.6)'"
                title="Search ticker" aria-label="Search ticker">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"
                 viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                 style="display:block;">
                <circle cx="11" cy="11" r="8"/>
                <path d="m21 21-4.3-4.3"/>
            </svg>
        </button>
        </div>
        <script>
        document.getElementById('{search_trigger_id}').onclick = function() {{
            // Try multiple selectors — Streamlit versions differ in DOM structure
            var inp = window.parent.document.querySelector('input[placeholder*="RELIANCE"]')
                   || window.parent.document.querySelector('input[data-baseweb="input"]')
                   || window.parent.document.querySelector('section[data-testid="stTextInput"] input');
            if (!inp) return;
            // Dispatch React-compatible Enter key event
            var nativeSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            nativeSetter.call(inp, inp.value);
            inp.dispatchEvent(new Event('input', {{bubbles: true}}));
            inp.dispatchEvent(new KeyboardEvent('keydown', {{key:'Enter', keyCode:13, bubbles:true}}));
        }};
        </script>
        """,
        unsafe_allow_html=True,
    )


ticker_text = ticker_input.strip().upper().replace(".NS", "")
# Resolve final ticker: chip click (quick_action) trumps stale text, Enter key or button click works too
quick_ticker = st.session_state.pop("quick_ticker", "")
final_ticker = quick_ticker or ticker_text or st.session_state.pop("manual_search", "")

# Persist final_ticker so portfolio add/delete reruns don't drop to empty state
if final_ticker:
    st.session_state["_active_ticker"] = final_ticker
elif "_active_ticker" in st.session_state:
    final_ticker = st.session_state["_active_ticker"]

if final_ticker and final_ticker != "":
    final_ticker = final_ticker.replace(".NS", "")
    # Resolve aliases and company names (e.g. "HDFC BANK" → "HDFCBANK")
    _resolved_ticker, _resolved_name = resolve_ticker(final_ticker)
    if _resolved_ticker:
        final_ticker = _resolved_ticker
        company_name = _resolved_name
    else:
        company_name = NSE_TICKERS.get(final_ticker, final_ticker)

    # Rate limiter: block if too many searches recently
    # Skip when _skip_reanalysis is set — no API call will be made (cache hit)
    if not st.session_state.get("_skip_reanalysis"):
        if not _check_rate_limit():
            st.stop()

    # Skip re-analysis when user voted/edited portfolio (instant re-render from cache)
    if (st.session_state.get("_skip_reanalysis")
            and st.session_state.get("_last_ticker") == final_ticker
            and st.session_state.get("_last_result")):
        st.session_state._skip_reanalysis = False
        result = st.session_state._last_result
    else:
        # Record this search for rate limiting
        st.session_state.setdefault("_search_timestamps", []).append(time.time())
        with st.spinner(f"Fetching data for {final_ticker}..."):
            result = analyze_ticker(final_ticker, company_name)
        if result:
            st.session_state._last_ticker = final_ticker
            st.session_state._last_result = result
            # Cache current prices for sidebar heatmap + P&L
            sd = result["stock_data"]
            price_cache = st.session_state.setdefault("_stock_price_cache", {})
            price_cache[final_ticker] = {
                "change_pct": sd.get("change_pct"),
                "current_price": sd.get("current_price"),
            }
            # Save to track record (dedup: update last unvoted entry for same ticker, else append)
            recs = load_track_record()
            now_iso = datetime.now().isoformat(timespec="minutes")
            existing_idx = None
            for i, rec in enumerate(reversed(recs)):
                if rec.get("ticker") == final_ticker and rec.get("vote") is None:
                    existing_idx = len(recs) - 1 - i
                    break
            entry = {
                "ticker": final_ticker,
                "datetime": now_iso,
                "compound": result["avg_compound"],
                "signal": result["signal"],
                "vote": None,
            }
            if existing_idx is not None:
                recs[existing_idx] = entry
            else:
                recs.append(entry)
            save_track_record(recs)
        # Stash source breakdown for vote-based calibration
        st.session_state._last_source_breakdown = result.get("source_breakdown", []) if result else []
    if result:
        news_items = result["news_items"]

        # ─── Technical indicators ───
        # Compute technical indicators
        ti = get_technical_indicators(final_ticker)
        # Compute pivot levels from cached OHLCV (avoids separate yfinance call)
        hist_cache = get_cached_history(final_ticker)
        _hist = hist_cache.tail(5) if hist_cache is not None and len(hist_cache) >= 1 else None
        result["pivot_levels"] = compute_pivot_levels(_hist)
        # Render premium HTML dashboard
        # Section heights (desktop):
        #   price(280) + chart(420) + sentiment+smartscore(450) + dist(130) + stats(200)
        #   + techs(290) + track(180) + fiidii(200) + cal(270) + buffer(200)
        # Each news item ≈ 120px (title + meta + body text wrapping)
        # ─── Annotate news with portfolio match badges ───
        records = load_track_record()
        fii_data = result.get("fii_data")
        if fii_data:
            save_fiidii_snapshot(fii_data)

        portfolio = load_portfolio()
        if portfolio and news_items:
            for item in news_items:
                item["in_portfolio"] = any(
                    re.search(rf'(?:\b|_){re.escape(t)}(?:\b|_)', (item.get("title") or "").upper())
                    for t in portfolio
                )

        n_news = len(news_items)
        # Height is a safe default; the auto-height script in render.py
        # adjusts via postMessage once the iframe loads
        dash_height = min(2600 + n_news * 120, 6500)
        ohlcv_json = _ohlcv_to_json(hist_cache)
        st.components.v1.html(
            render_dashboard(result, final_ticker, company_name,
                             technical_indicators=ti,
                             track_record=records,
                             fii_dii_data=fii_data,
                             ohlcv_json=ohlcv_json),
            height=dash_height,
            scrolling=True,
        )

        # Track record voting (Streamlit buttons outside the iframe)
        last_rec = records[-1] if records else None
        if last_rec and last_rec["ticker"] == final_ticker and last_rec.get("vote") is None:
            st.markdown("##### Was this signal accurate?")
            vu, vd = st.columns([1, 1])
            with vu:
                if st.button("👍 Yes", key="vote_up", use_container_width=True):
                    last_rec["vote"] = True
                    save_track_record(records)
                    for src in st.session_state.get("_last_source_breakdown", []):
                        update_source_accuracy(src["source"], was_correct=True)
                    st.toast("Signal logged as accurate ✅", icon="👍")
                    st.session_state._skip_reanalysis = True
                    st.rerun()
            with vd:
                if st.button("👎 No", key="vote_down", use_container_width=True):
                    last_rec["vote"] = False
                    save_track_record(records)
                    for src in st.session_state.get("_last_source_breakdown", []):
                        update_source_accuracy(src["source"], was_correct=False)
                    st.toast("Signal logged as inaccurate ❌", icon="👎")
                    st.session_state._skip_reanalysis = True
                    st.rerun()
        elif last_rec and last_rec["ticker"] == final_ticker and last_rec.get("vote") is not None:
            _CHECK_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#22b573" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;"><polyline points="20 6 9 17 4 12"/></svg>'
            _X_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f85149" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
            st.markdown(f'<span style="font-size:0.75rem;color:#8891a0;">{" " + _CHECK_SVG + " accurate" if last_rec["vote"] else " " + _X_SVG + " inaccurate"}</span>', unsafe_allow_html=True)

        # Shareable link
        share_url = f"https://nse-sentiment-analyzer.streamlit.app/?ticker={final_ticker}"
        st.markdown(
            f'<div style="text-align:right;margin-top:0.5rem;">'
            f'<a href="{share_url}" target="_blank" style="color:#6b7280;font-size:0.8rem;text-decoration:none;">'
            '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>'
            'Share snapshot</a></div>',
            unsafe_allow_html=True,
        )

        # ─── Bottom section: Portfolio + Track Record cards ───
        _render_bottom_cards(portfolio, final_ticker, entry_prices)

    else:
        st.error(f"Could not find data for **{final_ticker}**. "
                 f"Try typing a company name (e.g. \"HDFC Bank\", \"Reliance\") — "
                 f"the search now resolves aliases automatically. "
                 f"If the ticker is correct, Yahoo Finance may be rate-limited — wait a moment and try again.")

else:
    # ─── Empty state: guided launchpad ───
    st.markdown(f"""
    <div style="text-align:center;padding:3rem 1rem 1rem">
        <div style="font-size:1.5rem;font-weight:700;color:#f0f2f5;margin-bottom:0.5rem">
            Enter a ticker to begin
        </div>
        <div style="color:#6b7280;font-size:0.95rem;max-width:400px;margin:0 auto">
            Search any NSE symbol above or try a popular one below
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ─── Cascade / Ripple Effects on home page ───
    _market_news = fetch_market_headlines()
    if _market_news:
        _cascade_results = detect_cascade(_market_news, ticker_lookup=NSE_TICKERS)
        if _cascade_results:
            _rows = ""
            _CACHE = {"arrow_up": "↑", "arrow_down": "↓"}
            for _ce in _cascade_results:
                _dr = _ce["driver"]
                _dir_icon = _CACHE["arrow_up"] if _ce["direction"] > 0 else _CACHE["arrow_down"]
                _n = _ce.get("matched_articles", 1)
                _aff = ""
                for _a in _ce["affects"]:
                    _ti = _a.get("ticker_impact", 1)
                    _t_label = "Bullish" if _ti < 0 else "Bearish"
                    _t_color = "#22b573" if _ti < 0 else "#f85149"
                    _aff += f"""<div class="ct"><span class="cs">{_a['ticker']}</span><span class="cco">{_a['company']}</span><span class="cw">{_a['reason']}</span><span class="cti" style="color:{_t_color}">{_t_label}</span></div>"""
                _rows += f"""<div class="cd"><div class="ch"><span class="cn">{_dir_icon} {_dr}</span><span class="cc">{_n} article{'s' if _n > 1 else ''}</span></div><div class="cticks">{_aff}</div></div>"""
            st.markdown(f"""<div class="card"><div class="card-title">Cascade / Ripple Effects</div><div class="cw">{_rows}</div></div>""", unsafe_allow_html=True)

    st.markdown("<div style='text-align:center;padding:0.5rem 0 1.5rem'>", unsafe_allow_html=True)
    popular = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "SBIN"]
    chip_cols = st.columns(3)
    for i, t in enumerate(popular):
        if chip_cols[i % 3].button(t, key=f"chip_{t}", use_container_width=True, type="secondary"):
            st.session_state.quick_ticker = t
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# ─── PRIVACY POLICY ───
with st.expander("🔒 Privacy & Data Policy"):
    st.markdown(f"""
    **What we collect:**
    - Ticker symbols you search (stored locally in your browser for track record)
    - No login, email, or personal information is collected

    **Third-party data sources:**
    - **Yahoo Finance** — live stock prices (public API)
    - **RSS News feeds** — publicly available headlines from Google News, Moneycontrol, Economic Times, LiveMint, NDTV Profit

    **Data retention:**
    - Your search history ("Track Record") is stored in your browser's local storage only. You can clear it at any time.
    - No data is sent to external servers beyond the API calls listed above.
    - We do not sell, share, or monetize your data.

    **Contact:** [{CONTACT["x_handle"]} on X/Twitter]({CONTACT["x_url"]})
    """)
    st.caption("Last updated: June 2026")

# ─── DISCLAIMER ───
_ALERT_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>'
st.markdown(f'<details class="hermes-expander"><summary>{_CARET}{_ALERT_SVG} Disclaimer</summary>', unsafe_allow_html=True)
st.markdown(f"""
**Not financial advice.** This tool provides data-driven sentiment analysis and technical indicators for educational and informational purposes only. Nothing on this platform constitutes investment advice, a recommendation, or a solicitation to buy or sell securities.

**No SEBI registration.** The creator is not a SEBI-registered investment advisor. All trading and investment decisions are solely your responsibility.

**Data accuracy.** Data is sourced from third-party public APIs (Yahoo Finance, RSS feeds) and may be delayed, incomplete, or inaccurate. We do not guarantee the timeliness, accuracy, or completeness of any data displayed.

**Limitations you should know:**
- **Price data** — Yahoo Finance free tier has 15-20 min delay. Not suitable for intraday trading without real-time feeds.
- **NSE intraday (VWAP)** — yfinance intraday history for Indian stocks is spotty; many tickers return incomplete data.
- **Sentiment model** — VADER is a general-purpose model, not trained on Indian financial news. However, we've expanded it with a 123-term Indian financial lexicon covering common abbreviations (NPA, PAT, EBITDA, AUM, ROE, ROCE), IPO/capital market terms (oversubscribed), banking context (slippage, provisioning, infusion), fund flows (inflow, outflow), Hinglish terms (tezi, mandi, tej, mand), and general financial context. Accuracy is improved over vanilla VADER but still below a finance-tuned model.
- **SmartScore** — This is a custom composite metric. It has not been backtested or validated against actual returns. A score of 52 vs 48 is not a meaningful difference.
- **Event classifier** — Keyword-based rules can sometimes misclassify headlines. "SEBI clears merger" is now correctly classified as regulatory approval (positive) rather than penalty.
- **News sources** — RSS headlines are often trailing the market move. DuckDuckGo fallback (used when RSS returns little) is noisy and unreliable.

**No liability.** Under no circumstances shall the creator be liable for any direct, indirect, incidental, special, or consequential damages arising from your use of this tool, including but not limited to financial losses from trading or investment decisions made based on the data provided.

**Past performance.** Historical data and past sentiment scores do not guarantee future results.

**Use at your own risk.** By using this tool, you acknowledge that you understand and accept these terms. If you do not agree, do not use the tool.

**Contact:** [{CONTACT["x_handle"]} on X/Twitter]({CONTACT["x_url"]}) | {CONTACT["email"]}
""")
st.caption("Last updated: June 2026")
st.markdown('</details>', unsafe_allow_html=True)

# ─── FOOTER ───
st.markdown("---")
st.caption("Built with Streamlit + yfinance + VADER · FinBERT · Bayesian Calibration · Financial Lexicon | Data from Yahoo Finance + RSS News")
st.markdown(
    f'<div style="text-align:center;font-size:0.85rem;color:#6b7280;margin-bottom:0.5rem;">'
    f'Feature requests: <a href="mailto:{CONTACT["email"]}" '
    f'style="color:#22b573;text-decoration:none;">{CONTACT["email"]}</a> · '
    f'<a href="{CONTACT["x_url"]}" '
    f'style="color:#22b573;text-decoration:none;">{CONTACT["x_handle"]}</a></div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<span style="display:inline-flex;align-items:center;gap:4px;font-size:0.75rem;color:#8891a0;">'
    '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>'
    ' Not financial advice. This tool is for educational purposes only. Trading stocks carries financial risk. Consult a SEBI-registered advisor before making investment decisions.</span>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div style="text-align:center;margin-bottom:0.5rem;">'
    '<span style="color:#6b7280;font-size:0.75rem;font-style:italic;">'
    'Like this tool? Support the developer with a chai.</span></div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div style="display:flex;justify-content:center;margin-top:12px">'
    f'<a href="{CONTACT["chai_url"]}" target="_blank" rel="noopener noreferrer" '
    'style="display:inline-flex;flex-direction:column;align-items:center;justify-content:center;'
    'background:#ffffff;padding:8px 32px;border-radius:16px;text-decoration:none;'
    'border:1px solid #e5e7eb;'
    'box-shadow:0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -2px rgba(0,0,0,0.05);'
    'transition:transform 0.2s;" aria-label="Support on Chai4Me">'
    '<img src="https://chai4.me/icons/wordmark.png" alt="Support on Chai4Me" style="height:32px;object-fit:contain;"/>'
    '</a></div>',
    unsafe_allow_html=True,
)
