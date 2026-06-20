"""
NSE Stock Sentiment Analyzer
Enter any NSE ticker → get live price + news sentiment score + signal.
Built with Streamlit + yfinance + VADER + custom financial lexicon.
"""

import streamlit as st
import os
from datetime import datetime

from data_fetcher import (
    NSE_TICKERS, get_stock_info, search_news,
)
from sentiment import get_sia, analyze_headline_sentiment, get_weighted_signal
from event_classifier import classify_headline, adjust_with_event
from indicators import get_technical_indicators
from persistence import load_portfolio, save_portfolio, load_track_record, save_track_record, load_sentiment_history, save_sentiment_history, update_source_accuracy
from render import render_dashboard, get_signal_icon
from market_data import get_fii_dii_flow
from aggregate_sentiment import compute_smartscore

# ─── Page config ───
st.set_page_config(
    page_title="NSE Sentiment Analyzer",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

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
        .stButton button {font-size: 0.85rem; padding: 0.35rem 0.5rem;}
        .stTextInput input {font-size: 0.9rem;}
        .st-emotion-cache-16idsys {gap: 0.25rem;}
    }
</style>""", unsafe_allow_html=True)




def analyze_ticker(ticker, company_name):
    """Run full analysis pipeline for a ticker. Returns dict or None."""
    stock_data = get_stock_info(ticker)
    if not stock_data:
        return None

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
            "neg_count": ss_result["headline_count"] - ss_result["pos_count"] - ss_result["neg_count"],
            "avg_compound": sum(event_adjusted_scores) / len(event_adjusted_scores),
            "event_avg": ss_result["s_events"],
            "smartscore": ss_result["smartscore"],
        })

    # Use weighted signal as the primary (and only) signal
    weighted_signal, blended_compound, weighted_emoji, source_breakdown = get_weighted_signal(headline_scores)

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
    }


# ─── Sidebar ───
with st.sidebar:
    st.header("📁 My Portfolio")
    portfolio = load_portfolio()

    add_c1, add_c2 = st.columns([3, 1])
    with add_c1:
        new_t = st.text_input("Ticker", placeholder="RELIANCE", label_visibility="collapsed",
                              max_chars=15, key="portfolio_add")
    with add_c2:
        if st.button("➕", use_container_width=True, key="add_portfolio_btn") and new_t.strip():
            t = new_t.strip().upper().replace(".NS", "")
            if not t.isalnum():
                st.warning("Invalid ticker format")
            elif t in portfolio:
                st.warning(f"{t} already in portfolio")
            else:
                portfolio.append(t)
                save_portfolio(portfolio)
                st.session_state._skip_reanalysis = True
                st.rerun()

    if portfolio:
        for t in portfolio:
            c1, c2 = st.columns([3, 1])
            c1.write(f"**{t}**")
            if c2.button("✕", key=f"del_{t}", help=f"Remove {t} from portfolio"):
                portfolio.remove(t)
                save_portfolio(portfolio)
                st.session_state._skip_reanalysis = True
                st.rerun()

        if st.button("📡 Run Portfolio Briefing", type="primary", use_container_width=True):
            st.session_state.run_briefing = True

    # ─── Track Record Stats ───
    st.markdown("---")
    st.header("📊 Track Record")
    records = load_track_record()
    total = len(records)
    voted = [r for r in records if r.get("vote") is not None]
    accurate = sum(1 for r in voted if r["vote"] is True)
    if voted:
        st.metric("Accuracy", f"{accurate/len(voted)*100:.0f}%", help=f"{accurate}/{len(voted)} signals rated")
    st.metric("Total Scans", total)
    st.caption("👍 = signal was right, 👎 = wrong")

# ─── Main UI ───

# ─── Premium header ───
st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;
    padding:0.5rem 0 1.5rem 0;border-bottom:1px solid #1e2028;margin-bottom:1.5rem;">
    <div>
        <div style="font-size:1.25rem;font-weight:700;letter-spacing:-0.02em;
            background:linear-gradient(135deg,#22b573,#0d9488);
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;
            background-clip:text;">NSE Sentiment Analyzer</div>
        <div style="font-size:0.8rem;color:#6b7280;margin-top:0.15rem;">
            Live price · Multi-source sentiment · Technical indicators</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ─── Ticker Input — single text field + search button ───
ticker_col, btn_col = st.columns([5, 1])
with ticker_col:
    ticker_input = st.text_input(
        "NSE Ticker Symbol",
        placeholder="e.g., RELIANCE, HDFCBANK, TCS, NYKAA, ZOMATO",
        max_chars=15,
        label_visibility="collapsed",
    )
with btn_col:
    search_clicked = st.button("🔍", use_container_width=True, help="Search ticker")

ticker_text = ticker_input.strip().upper().replace(".NS", "")
# Trigger on Enter (via session state) OR button click
if search_clicked and ticker_text:
    st.session_state.manual_search = ticker_text
    st.rerun()

# Resolve final ticker: chip click (quick_action) trumps stale text, button click or Enter works too
quick_ticker = st.session_state.pop("quick_ticker", "")
final_ticker = quick_ticker or ticker_text or st.session_state.pop("manual_search", "")

if final_ticker and final_ticker != "":
    final_ticker = final_ticker.replace(".NS", "")
    company_name = NSE_TICKERS.get(final_ticker, final_ticker)

    # ponytail: skip re-analysis when user voted/edited portfolio (instant re-render from cache)
    if (st.session_state.get("_skip_reanalysis")
            and st.session_state.get("_last_ticker") == final_ticker
            and st.session_state.get("_last_result")):
        st.session_state._skip_reanalysis = False
        result = st.session_state._last_result
    else:
        with st.spinner(f"Fetching data for {final_ticker}..."):
            result = analyze_ticker(final_ticker, company_name)
        if result:
            st.session_state._last_ticker = final_ticker
            st.session_state._last_result = result
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
        st.session_state._last_source_breakdown = result.get("source_breakdown", [])
    if result:
        stock_data = result["stock_data"]
        news_items = result["news_items"]
        headline_scores = result["headline_scores"]
        signal = result["signal"]
        avg_compound = result["avg_compound"]
        signal_emoji = result["signal_emoji"]
        source_stats = result.get("source_stats", {})
        confidence = abs(avg_compound)

        # ─── PRICE CARD ───
        # Compute technical indicators
        ti = get_technical_indicators(final_ticker)
        records = load_track_record()
        fii_data = get_fii_dii_flow()

        # Render premium HTML dashboard — estimate height dynamically
        # Section heights (desktop):
        #   price(280) + sentiment+smartscore(450) + dist(130) + stats(200)
        #   + techs(290) + track(180) + fiidii(200) + cal(270) + buffer(200)
        # Each news item ≈ 120px (title + meta + body text wrapping)
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
        elif last_rec and last_rec.get("vote") is not None:
            st.caption(f"You marked this signal as {'✅ accurate' if last_rec['vote'] else '❌ inaccurate'}")

    else:
        st.error(f"Could not find data for **{final_ticker}**. "
                 f"Check the spelling — try removing .NS or using the full name (e.g., RELIANCE, HDFCBANK, TCS). "
                 f"If the ticker is correct, Yahoo Finance may be rate-limited — wait a moment and try again.")

elif st.session_state.get("run_briefing"):
    # ─── PORTFOLIO BRIEFING MODE ───
    portfolio = load_portfolio()
    if not portfolio:
        st.warning("No tickers in your portfolio. Add some from the sidebar.")
    else:
        st.subheader(f"📡 Portfolio Briefing — {len(portfolio)} stocks")
        results = []
        progress = st.progress(0, text="Starting...")
        # ponytail: parallel portfolio briefing with ThreadPoolExecutor;
        # 3 max workers to avoid yfinance rate limits
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=min(len(portfolio), 3)) as pool:
            futures = {pool.submit(analyze_ticker, t, NSE_TICKERS.get(t, t)): t for t in portfolio}
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
                    cols = st.columns([2, 1, 1])
                    price_str = f"₹{sd['current_price']:,.2f}" if isinstance(sd['current_price'], (int, float)) else "N/A"
                    cols[0].markdown(f"**{t}** — {price_str}")
                    cols[0].caption(f"{sd['name'][:40]}")
                    cols[1].markdown(f"Change: {change_str}")
                    cols[2].markdown(f"""<span style="display:inline-flex;align-items:center;gap:4px">{get_signal_icon(r.get('signal_emoji', ''))} <span style="font-weight:600">{r['signal'].rstrip(' 🟢🔴⚪')}</span></span>""", unsafe_allow_html=True)

        if st.button("← Back to Single View"):
            st.session_state.run_briefing = False
            st.rerun()

else:
    # ─── Empty state: guided launchpad ───
    st.markdown("""
    <div style="text-align:center;padding:3rem 1rem 1rem">
        <div style="font-size:1.5rem;font-weight:700;color:#f0f2f5;margin-bottom:0.5rem">
            Enter a ticker to begin
        </div>
        <div style="color:#6b7280;font-size:0.95rem;max-width:400px;margin:0 auto">
            Search any NSE symbol above or try a popular one below
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Quick-action chips for popular tickers
    st.markdown("<div style='text-align:center;padding:0.5rem 0 1.5rem'>", unsafe_allow_html=True)
    popular = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "SBIN"]
    cols = st.columns(len(popular))
    for i, t in enumerate(popular):
        if cols[i].button(t, key=f"chip_{t}", use_container_width=True, type="secondary"):
            st.session_state.quick_ticker = t
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # Portfolio shortcut
    portfolio = load_portfolio()
    if portfolio:
        st.markdown(
            f"<div style='text-align:center;color:#6b7280;font-size:0.9rem'>"
            f"📁 Portfolio: {', '.join(portfolio[:8])}{'…' if len(portfolio) > 8 else ''}"
            f" — check the sidebar for details</div>",
            unsafe_allow_html=True,
        )

# ─── PRIVACY POLICY ───
with st.expander("🔒 Privacy & Data Policy"):
    st.markdown("""
    **What we collect:**
    - Ticker symbols you search (stored locally in your browser for track record)
    - No login, email, or personal information is collected

    **Third-party data sources:**
    - **Yahoo Finance** — live stock prices (public API)
    - **Reddit** — public posts via Reddit's official API. Each Reddit post shown includes attribution (username, subreddit, link). [Reddit Privacy Policy](https://www.redditinc.com/policies/privacy-policy)
    - **RSS News feeds** — publicly available headlines from Google News, Moneycontrol, Economic Times, LiveMint, NDTV Profit

    **Data retention:**
    - Your search history ("Track Record") is stored in your browser's local storage only. You can clear it at any time.
    - No data is sent to external servers beyond the API calls listed above.
    - We do not sell, share, or monetize your data.

    **Contact:** [@sentinelcipher on X/Twitter](https://x.com/sentinelcipher)
    """)
    st.caption("Last updated: June 2026")

# ─── FOOTER ───
st.markdown("---")
st.caption("Built with Streamlit + yfinance + VADER · FinBERT · Bayesian Calibration · Financial Lexicon | Data from Yahoo Finance + RSS News")
st.caption("📌 Not financial advice. Always do your own research.")
st.markdown(
    '<div style="display:flex;justify-content:center;margin-top:12px">'
    '<a href="https://chai4.me/darkcharon3301" target="_blank" rel="noopener noreferrer" '
    'style="display:inline-flex;flex-direction:column;align-items:center;justify-content:center;'
    'background:#ffffff;padding:8px 32px;border-radius:16px;text-decoration:none;'
    'border:1px solid #e5e7eb;'
    'box-shadow:0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -2px rgba(0,0,0,0.05);'
    'transition:transform 0.2s;" aria-label="Support on Chai4Me">'
    '<img src="https://chai4.me/icons/wordmark.png" alt="Support on Chai4Me" style="height:32px;object-fit:contain;"/>'
    '</a></div>',
    unsafe_allow_html=True,
)
