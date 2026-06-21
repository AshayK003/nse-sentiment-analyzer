"""
NSE Stock Sentiment Analyzer
Enter any NSE ticker → get live price + news sentiment score + signal.
Built with Streamlit + yfinance + VADER + custom financial lexicon.
"""

import streamlit as st
import os
import re
import time
import pandas as pd
from datetime import datetime

# ─── Contact / feature request info (single source of truth) ───
CONTACT = {
    "email": "darkcharon3301@gmail.com",
    "x_url": "https://x.com/sentinelcipher",
    "x_handle": "@sentinelcipher",
    "chai_url": "https://chai4.me/darkcharon3301",
}

from data_fetcher import (
    NSE_TICKERS, get_stock_info, search_news,
)
from sentiment import get_sia, analyze_headline_sentiment, get_weighted_signal
from event_classifier import classify_headline, adjust_with_event
from indicators import get_technical_indicators
from persistence import load_portfolio, save_portfolio, load_track_record, save_track_record, load_sentiment_history, save_sentiment_history, history_to_csv, update_source_accuracy, load_entry_prices, save_entry_price, calc_portfolio_pnl
from render import render_dashboard, get_signal_icon, _is_valid_num
from market_data import get_fii_dii_flow
from aggregate_sentiment import compute_smartscore
from intraday import compute_vwap, compute_pivot_levels, get_vix

# ─── Page config ───
st.set_page_config(
    page_title="NSE Sentiment Analyzer",
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

# ─── Streamlit chrome CSS (Inter, hide chrome, widget overrides) ───
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
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
    .stTextInput input:focus {border-color: #22b573 !important;box-shadow: 0 0 0 2px rgba(34,181,115,0.1) !important;}
    .stButton button {border-radius: 8px;border: 1px solid #1e2028;background: rgba(19,21,26,0.6);color: #e4e6eb;font-weight: 500;transition: all 0.2s ease;}
    .stButton button:hover {border-color: rgba(34,181,115,0.3);background: rgba(34,181,115,0.08);}
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

        /* Bottom cards (Portfolio + Track Record) */
        .btm-card{background:#15181f;border:1px solid #2a2e3a;border-radius:12px;padding:1rem;height:100%}
        .btm-title{display:flex;align-items:center;gap:0.4rem;font-size:0.9rem;font-weight:600;color:#f0f2f5;margin-bottom:0.6rem}
        .btm-muted{color:#8891a0;font-size:0.75rem;line-height:1.4}
        .btm-link{color:#22b573;text-decoration:none}
        .btm-heat{display:grid;grid-template-columns:1fr 1fr 1fr;gap:3px;margin:4px 0}
        .btm-heat-item{background:#1a1a2e;border-radius:5px;padding:2px 6px;text-align:center;font-size:0.65rem}
        .btm-heat-tick{font-weight:600;color:#e4e6eb}
    }
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
    analysis — just returns stock data with a cached/neutral signal.
    """
    stock_data = get_stock_info(ticker)
    if not stock_data:
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
        }

    use_finbert = os.environ.get("USE_FINBERT", "").strip().lower() in ("1", "true", "yes")
    pipe_finbert = None
    if use_finbert:
        from sentiment import get_finbert, analyze_headline_finbert
        pipe_finbert = get_finbert()

    sia = None if use_finbert else get_sia()
    news_items, source_stats = search_news(ticker, company_name)

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
    }


def _render_portfolio_list(portfolio, entry_prices, key_prefix="side",
                            brief_btn_label="📡 Run Portfolio Briefing",
                            heatmap_css=None):
    """Shared portfolio heatmap + listing + delete component.

    Used by sidebar and bottom card sections to avoid ~100 lines of
    duplicated Streamlit widget code. The key_prefix ensures unique
    widget keys per usage (e.g. 'side' → side_heat, 'btm' → btm_heat).
    """
    # ─── Market Heatmap (compact 3-col grid) ───
    heat_parts = []
    for t in portfolio:
        sd_cache = st.session_state.get("_stock_price_cache", {}).get(t)
        if sd_cache is not None:
            chg = sd_cache.get("change_pct") or 0
            color = "#22c55e" if chg >= 0 else "#ef4444"
        else:
            chg = 0
            color = "#6b7280"
        if heatmap_css:
            heat_parts.append(
                f'<div class="{heatmap_css}-item"><div class="{heatmap_css}-tick">{t}</div>'
                f'<div style="color:{color};">{chg:+.1f}%</div></div>'
            )
        else:
            heat_parts.append(
                f'<div style="background:#1a1a2e;border-radius:6px;padding:4px;text-align:center;font-size:0.65rem;">'
                f'<div style="font-weight:600;color:#e4e6eb;">{t}</div><div style="color:{color};">{chg:+.1f}%</div></div>'
            )
    if heat_parts:
        h_class = f' class="{heatmap_css}"' if heatmap_css else ''
        st.markdown(f'<div{h_class}>{"".join(heat_parts)}</div>', unsafe_allow_html=True)
        if not heatmap_css:
            st.markdown(
                '<span style="display:inline-flex;align-items:center;gap:4px;font-size:0.75rem;color:#8891a0;">'
                '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#22b573" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="6"/></svg>'
                ' Day gain'
                '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#f85149" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="6"/></svg>'
                ' Day loss'
                '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#6b7280" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="6"/></svg>'
                ' No data</span>',
                unsafe_allow_html=True,
            )

    # ─── Portfolio listing with P&L + delete ───
    for t in portfolio:
        c1, c2 = st.columns([3, 1] if key_prefix == "side" else [3, 0.6])
        ep = entry_prices.get(t)
        sd_cache = st.session_state.get("_stock_price_cache", {}).get(t)
        cp = sd_cache.get("current_price") if sd_cache else None

        if key_prefix == "side":
            display_parts = [f"<strong>{t}</strong>"]
            if _is_valid_num(cp):
                display_parts.append(f'<span style="font-size:0.85rem;">₹{cp:,.2f}</span>')
            elif sd_cache is not None:
                display_parts.append(f'<span style="font-size:0.85rem;color:#6b7280;">Price N/A</span>')
            if ep and _is_valid_num(cp):
                pnl = calc_portfolio_pnl(ep, cp)
                sign = "+" if pnl["pnl_pct"] >= 0 else ""
                display_parts.append(
                    f'<span style="font-size:0.8rem;color:{"#22c55e" if pnl["pnl_pct"] >= 0 else "#ef4444"};">'
                    f'{sign}{pnl["pnl_pct"]:.1f}%</span>'
                )
                display_parts.append(f'<span style="font-size:0.7rem;color:#6b7280;">ATP: ₹{ep:,.0f}</span>')
            elif ep:
                display_parts.append(f'<span style="font-size:0.75rem;color:#6b7280;">ATP: ₹{ep:,.0f}</span>')
            elif cp:
                display_parts.append(f'<span style="font-size:0.7rem;color:#6b7280;">No ATP set</span>')
            c1.markdown(
                '<div style="line-height:1.5;">' + '<br>'.join(display_parts) + '</div>',
                unsafe_allow_html=True,
            )
        else:
            pts = [f"**{t}**"]
            if _is_valid_num(cp):
                pts.append(f"₹{cp:,.2f}")
            if ep and _is_valid_num(cp):
                pnl = calc_portfolio_pnl(ep, cp)
                sn = "+" if pnl["pnl_pct"] >= 0 else ""
                pts.append(f"{sn}{pnl['pnl_pct']:.1f}%")
            c1.markdown(" · ".join(pts), help=f"P&L for {t}")

        if c2.button("✕", key=f"{key_prefix}_del_{t}", help=f"Remove {t} from portfolio"):
            portfolio.remove(t)
            save_portfolio(portfolio)
            st.session_state._skip_reanalysis = True
            st.rerun()

    # ─── Briefing button ───
    if st.button(brief_btn_label, type="primary", use_container_width=True,
                 key=f"{key_prefix}_brief",
                 disabled=st.session_state.get("_briefing_running", False)):
        st.session_state.run_briefing = True
        st.session_state._briefing_running = True
        st.rerun()


# ─── Sidebar ───
with st.sidebar:
    portfolio = load_portfolio()
    entry_prices = load_entry_prices()

    # ─── India VIX ───
    st.markdown("---")
    if "vix" not in st.session_state:
        st.session_state.vix = get_vix()
    vix_d = st.session_state.vix
    if vix_d and vix_d.get("vix") is not None:
        col1, col2 = st.columns([1, 1])
        vix_dir = "⬆️" if vix_d["change"] >= 0 else "⬇️"
        col1.metric("India VIX", f"{vix_d['vix']:.1f}", f"{vix_dir} {vix_d['change']:+.2f}")
        col2.metric("Volatility", vix_d["level"])
        if vix_d["level"] == "High":
            st.markdown(
                '<span style="display:inline-flex;align-items:center;gap:4px;font-size:0.75rem;color:#8891a0;">'
                '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>'
                ' High VIX (&gt;20) — sharp reversals likely. Trade with caution.</span>',
                unsafe_allow_html=True,
            )
        elif vix_d["level"] == "Low":
            st.markdown(
                '<span style="display:inline-flex;align-items:center;gap:4px;font-size:0.75rem;color:#8891a0;">'
                '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#22b573" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>'
                ' Low VIX (&lt;15) — trending markets favored.</span>',
                unsafe_allow_html=True,
            )

    # ─── Changelog & Feedback ───
    _FILE_TEXT_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/></svg>'
    st.markdown(f'<details class="hermes-expander"><summary>{_CARET}{_FILE_TEXT_SVG} What\'s New</summary>', unsafe_allow_html=True)
    try:
        with open("CHANGELOG.md") as f:
            lines = f.readlines()
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
                background-clip:text;">NSE Sentiment Analyzer</div>
            <div style="font-size:0.8rem;color:#6b7280;margin-top:0.15rem;">
                Live price · Multi-source sentiment · Technical indicators</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

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
            html = render_dashboard(
                result, final_ticker, company_name,
                technical_indicators=result.get("technical_indicators"),
                vwap_data=result.get("vwap"),
                pivot_levels=result.get("pivot_levels"),
                fii_data=result.get("fii_dii"),
                records=result.get("records"),
            )
            st.components.v1.html(html, height=result.get("_height", 3000), scrolling=False)
        else:
            st.error(f"No data found for **{final_ticker}**")
        st.stop()

ticker_col, btn_col = st.columns([4, 1])
with ticker_col:
    ticker_input = st.text_input(
        "NSE Ticker Symbol",
        placeholder="e.g., RELIANCE, HDFCBANK, TCS, NYKAA, ZOMATO",
        max_chars=15,
        label_visibility="collapsed",
    )
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
            var inp = window.parent.document.querySelector('input[placeholder*="RELIANCE"]');
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

# When briefing is active, ignore stale ticker text to let the briefing block run
if st.session_state.get("run_briefing"):
    final_ticker = ""

if final_ticker and final_ticker != "":
    final_ticker = final_ticker.replace(".NS", "")
    company_name = NSE_TICKERS.get(final_ticker, final_ticker)

    # Rate limiter: block if too many searches recently
    if not _check_rate_limit():
        st.stop()

    # ponytail: skip re-analysis when user voted/edited portfolio (instant re-render from cache)
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
        from data_fetcher import get_cached_history
        hist_cache = get_cached_history(final_ticker)
        _hist = hist_cache.tail(5) if hist_cache is not None and len(hist_cache) >= 1 else None
        result["pivot_levels"] = compute_pivot_levels(_hist)
        records = load_track_record()
        fii_data = get_fii_dii_flow()

        # Render premium HTML dashboard — estimate height dynamically
        # Section heights (desktop):
        #   price(280) + sentiment+smartscore(450) + dist(130) + stats(200)
        #   + techs(290) + track(180) + fiidii(200) + cal(270) + buffer(200)
        # Each news item ≈ 120px (title + meta + body text wrapping)
        # ─── Annotate news with portfolio match badges ───
        portfolio = load_portfolio()
        if portfolio and news_items:
            for item in news_items:
                item["in_portfolio"] = any(
                    re.search(rf'(?:\b|_){re.escape(t)}(?:\b|_)', (item.get("title") or "").upper())
                    for t in portfolio
                )

        n_news = len(news_items)
        dash_height = min(2200 + n_news * 120, 6000)
        st.components.v1.html(
            render_dashboard(result, final_ticker, company_name,
                             technical_indicators=ti,
                             track_record=records,
                             fii_dii_data=fii_data),
            height=dash_height,
            scrolling=False,
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

        # ─── Bottom section: Portfolio + Track Record cards (after analysis results) ───
        # Lucide SVGs used in markdown (safe) — button labels use plain text
        _FOLDER = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
        _BAR = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>'
        _CHECK = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
        _X = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'

        bc1, bc2 = st.columns([1.6, 1])
        eprices = load_entry_prices()

        with bc1:
            st.markdown(f'<div class="btm-card"><div class="btm-title">{_FOLDER} Portfolio</div>', unsafe_allow_html=True)
            # ─── Add Stock form ───
            ac1, ac2, ac3 = st.columns([2, 1, 0.6])
            with ac1:
                new_t = st.text_input("Ticker", placeholder="RELIANCE", label_visibility="collapsed",
                                      max_chars=15, key="btm_add_ticker")
            with ac2:
                ep_input = st.text_input("ATP", placeholder="ATP", label_visibility="collapsed",
                                         max_chars=10, key="btm_add_atp",
                                         help="Optional: average trade price for P&L tracking")
            with ac3:
                if st.button("➕", use_container_width=True, key="btm_add_btn", help="Add to portfolio") and new_t.strip():
                    t = new_t.strip().upper().replace(".NS", "")
                    if not re.match(r'^[A-Z0-9&-]+$', t):
                        st.warning("Invalid ticker format")
                    elif t in portfolio:
                        st.warning(f"{t} already in portfolio")
                    else:
                        portfolio.append(t)
                        save_portfolio(portfolio)
                        if ep_input.strip():
                            try:
                                save_entry_price(t, float(ep_input.strip().replace(",", "")))
                            except ValueError:
                                st.warning(f"Could not parse ATP — stock added without entry price")
                        st.session_state._skip_reanalysis = True
                        st.rerun()
            _render_portfolio_list(portfolio, eprices, key_prefix="btm",
                                   brief_btn_label="⚡ Briefing",
                                   heatmap_css="btm-heat")
            st.markdown('</div>', unsafe_allow_html=True)

        with bc2:
            st.markdown(f'<div class="btm-card"><div class="btm-title">{_BAR} Track Record</div>', unsafe_allow_html=True)
            recs = load_track_record()
            voted = [r for r in recs if r.get("vote") is not None]
            if voted:
                acc = sum(1 for r in voted if r["vote"] is True)
                st.metric("Accuracy", f"{acc/len(voted)*100:.0f}%", help=f"{acc}/{len(voted)} correct")
            st.metric("Total Scans", len(recs))
            st.markdown(f'<div class="btm-muted">{_CHECK} right · {_X} wrong</div></div>', unsafe_allow_html=True)

        # ─── Historical Sentiment Archive ───
        history = load_sentiment_history(final_ticker)
        if history:
            _TREND_UP = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>'
            st.markdown(f'<details class="hermes-expander"><summary>{_CARET}{_TREND_UP} Sentiment History</summary>', unsafe_allow_html=True)
            df = pd.DataFrame(history)
            if "smartscore" in df.columns:
                df["smartscore"] = pd.to_numeric(df["smartscore"], errors="coerce")
                df = df.dropna(subset=["smartscore"])
                if not df.empty:
                    st.line_chart(df.set_index("date")["smartscore"])
            csv_data = history_to_csv(final_ticker, history)
            st.download_button(
                label="Export CSV",
                data=csv_data,
                file_name=f"{final_ticker}_sentiment_history.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.markdown('</details>', unsafe_allow_html=True)

    else:
        st.error(f"Could not find data for **{final_ticker}**. "
                 f"Check the spelling — try removing .NS or using the full name (e.g., RELIANCE, HDFCBANK, TCS). "
                 f"If the ticker is correct, Yahoo Finance may be rate-limited — wait a moment and try again.")

elif st.session_state.get("run_briefing"):
    # ─── PORTFOLIO BRIEFING MODE ───
    portfolio = load_portfolio()
    if not portfolio:
        st.warning("No tickers in your portfolio. Add some above.")
    else:
        _SATELLITE = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 7 9 3 5 7l4 4"/><path d="m17 11 4 4-4 4-4-4"/><path d="m8 12 4 4 6-6-4-4Z"/><path d="m16 16-4 4"/><path d="m12 20 4-4"/></svg>'
        st.markdown(f'<div style="display:flex;align-items:center;gap:0.5rem;font-size:1.25rem;font-weight:600;">{_SATELLITE} Portfolio Briefing — {len(portfolio)} stocks</div>', unsafe_allow_html=True)
        st.caption("Live prices · signals from previous analysis (news skipped for speed)")
        results = []
        progress = st.progress(0, text="Starting...")
        # ponytail: parallel portfolio briefing with ThreadPoolExecutor;
        # 5 parallel workers for price-only briefing (lightweight, no news fetching)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=min(len(portfolio), 5)) as pool:
            futures = {pool.submit(analyze_ticker, t, NSE_TICKERS.get(t, t), True): t for t in portfolio}
            for i, future in enumerate(as_completed(futures)):
                t = futures[future]
                progress.progress((i + 1) / len(portfolio), text=f"Analyzing {t} ({i+1}/{len(portfolio)})...")
                r = future.result()
                if r:
                    results.append((t, r))
        progress.empty()

        if results:
            st.success(f"Briefed {len(results)} stocks")
            for t, r in results:
                sd = r["stock_data"]
                change_str = f"{'+' if sd['change'] >= 0 else ''}{sd['change']:.2f}" if isinstance(sd['change'], (int, float)) else "N/A"
                with st.container(border=True):
                    cols = st.columns([1, 1, 1])
                    price_str = f"₹{sd['current_price']:,.2f}" if isinstance(sd['current_price'], (int, float)) else "N/A"
                    cols[0].markdown(f"**{t}** — {price_str}")
                    cols[0].caption(f"{sd['name'][:40]}")
                    cols[1].markdown(f"Change: {change_str}")
                    cols[2].markdown(f"""<span style="display:inline-flex;align-items:center;gap:4px">{get_signal_icon(r.get('signal_emoji', ''))} <span style="font-weight:600">{r['signal'].rstrip(' 🟢🔴⚪')}</span></span>""", unsafe_allow_html=True)

        if st.button("← Back to Single View"):
            st.session_state.run_briefing = False
            st.rerun()

    # Back button for empty portfolio case too
    if not portfolio:
        if st.button("← Back"):
            st.session_state.run_briefing = False
            st.rerun()

    st.session_state._briefing_running = False

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

    # Quick-action chips for popular tickers — 3 per row; wraps nicely on all screens
    st.markdown("<div style='text-align:center;padding:0.5rem 0 1.5rem'>", unsafe_allow_html=True)
    popular = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "SBIN"]
    chip_cols = st.columns(3)
    for i, t in enumerate(popular):
        if chip_cols[i % 3].button(t, key=f"chip_{t}", use_container_width=True, type="secondary"):
            st.session_state.quick_ticker = t
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # Portfolio shortcut
    portfolio = load_portfolio()
    if portfolio:
        st.markdown(
            f"<div style='text-align:center;color:#6b7280;font-size:0.9rem'>"
            f"📁 Portfolio: {', '.join(portfolio[:8])}{'…' if len(portfolio) > 8 else ''}"
            f" — manage below</div>",
            unsafe_allow_html=True,
        )

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
