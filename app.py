"""
NSE Stock Sentiment Analyzer
Enter any NSE ticker → get live price + news sentiment score + signal.
Built with Streamlit + yfinance + VADER + custom financial lexicon.
"""

import streamlit as st
import time
from datetime import datetime

from data_fetcher import (
    NSE_TICKERS, get_stock_info, search_news,
)
from sentiment import get_sia, analyze_headline_sentiment, get_overall_signal, get_weighted_signal
from indicators import get_technical_indicators
from persistence import load_portfolio, save_portfolio, load_track_record, save_track_record
from render import render_dashboard
from market_data import get_fii_dii_flow

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
    .stSelectbox [data-baseweb="select"] {border-radius: 8px;border-color: #1e2028 !important;}
    .stSelectbox [data-baseweb="select"]:focus-within {border-color: #22b573 !important;box-shadow: 0 0 0 2px rgba(34,181,115,0.1) !important;}
    .stTextInput input {border-radius: 8px;border-color: #1e2028 !important;}
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
</style>""", unsafe_allow_html=True)




def delta_str(val):
    """Format change value with +/- sign."""
    if not isinstance(val, (int, float)):
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}"


def delta_color(val):
    """Return Streamlit delta color based on sign."""
    if isinstance(val, (int, float)):
        return "normal" if val >= 0 else "inverse"
    return "off"


def fmt_price(val):
    """Format price or return N/A."""
    if isinstance(val, (int, float)):
        return f"₹{val:.2f}"
    return "N/A"


def fmt_metric(val, suffix=""):
    """Format a number with optional suffix, return N/A if missing."""
    if isinstance(val, (int, float)):
        return f"{val:,.0f}{suffix}"
    return "N/A"


def analyze_ticker(ticker, company_name):
    """Run full analysis pipeline for a ticker. Returns dict or None."""
    stock_data = get_stock_info(ticker)
    if not stock_data:
        return None
    sia = get_sia()
    news_items, source_stats = search_news(ticker, company_name)
    headline_scores = [analyze_headline_sentiment(n["title"], n["body"], sia, source=n.get("source")) for n in news_items]
    signal, avg_compound, signal_emoji = get_overall_signal(headline_scores)
    weighted_signal, blended_compound, weighted_emoji, source_breakdown = get_weighted_signal(headline_scores)
    return {
        "stock_data": stock_data,
        "news_items": news_items,
        "headline_scores": headline_scores,
        "signal": signal,
        "avg_compound": avg_compound,
        "signal_emoji": signal_emoji,
        "weighted_signal": weighted_signal,
        "blended_compound": blended_compound,
        "weighted_emoji": weighted_emoji,
        "source_breakdown": source_breakdown,
        "num_articles": len(news_items),
        "source_stats": source_stats,
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
        if st.button("➕", use_container_width=True) and new_t.strip():
            t = new_t.strip().upper().replace(".NS", "")
            if not t.isalnum():
                st.warning("Invalid ticker format")
            elif t in portfolio:
                st.warning(f"{t} already in portfolio")
            else:
                portfolio.append(t)
                save_portfolio(portfolio)
                st.rerun()

    if portfolio:
        for t in portfolio:
            c1, c2 = st.columns([3, 1])
            c1.write(f"**{t}**")
            if c2.button("✕", key=f"del_{t}"):
                portfolio.remove(t)
                save_portfolio(portfolio)
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
    <div style="display:flex;gap:0.75rem;align-items:center;">
        <a href="https://github.com/AshayK003/nse-sentiment-analyzer" target="_blank"
            style="color:#6b7280;text-decoration:none;font-size:0.8rem;display:inline-flex;align-items:center;gap:0.3rem;
            border:1px solid #1e2028;border-radius:8px;padding:0.35rem 0.75rem;transition:all 0.2s ease;"
            onmouseover="this.style.borderColor='rgba(34,181,115,0.3)';this.style.color='#e4e6eb'"
            onmouseout="this.style.borderColor='#1e2028';this.style.color='#6b7280'">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
            GitHub
        </a>
    </div>
</div>
""", unsafe_allow_html=True)

# Ticker input — popular picker + custom override
ticker = st.selectbox(
    "Select or search a popular NSE ticker:",
    options=[""] + sorted(NSE_TICKERS.keys()),
    format_func=lambda x: f"{x} — {NSE_TICKERS.get(x, '')}" if x else "Choose a ticker...",
    placeholder="Search tickers...",
)
custom_ticker = st.text_input(
    "Or type any NSE symbol (overrides the selection above):",
    placeholder="e.g., NYKAA, ZOMATO, PWL",
    max_chars=15,
    label_visibility="collapsed",
)
st.caption("Type any NSE symbol not in the list — this overrides the select box above.")

final_ticker = custom_ticker.strip().upper() if custom_ticker.strip() else ticker

if final_ticker and final_ticker != "":
    final_ticker = final_ticker.replace(".NS", "")
    company_name = NSE_TICKERS.get(final_ticker, final_ticker)

    with st.spinner(f"Fetching price data for {final_ticker}..."):
        result = analyze_ticker(final_ticker, company_name)
    if result:
        stock_data = result["stock_data"]
        news_items = result["news_items"]
        headline_scores = result["headline_scores"]
        signal = result["signal"]
        avg_compound = result["avg_compound"]
        signal_emoji = result["signal_emoji"]
        source_stats = result.get("source_stats", {})
        confidence = abs(avg_compound)

        # Save to track record
        records = load_track_record()
        records.append({
            "ticker": final_ticker,
            "datetime": datetime.now().isoformat(timespec="minutes"),
            "compound": avg_compound,
            "signal": signal,
            "vote": None,
        })
        save_track_record(records)

        # ─── PRICE CARD ───
        # Compute technical indicators
        ti = get_technical_indicators(final_ticker)
        records = load_track_record()
        fii_data = get_fii_dii_flow()

        # Render premium HTML dashboard via custom component
        st.components.v1.html(
            render_dashboard(result, final_ticker, company_name,
                             technical_indicators=ti,
                             track_record=records,
                             fii_dii_data=fii_data),
            height=3000,
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
                    st.toast("Signal logged as accurate ✅", icon="👍")
                    st.rerun()
            with vd:
                if st.button("👎 No", key="vote_down", use_container_width=True):
                    last_rec["vote"] = False
                    save_track_record(records)
                    st.toast("Signal logged as inaccurate ❌", icon="👎")
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
        for i, t in enumerate(portfolio):
            progress.progress((i) / len(portfolio), text=f"Analyzing {t} ({i+1}/{len(portfolio)})...")
            r = analyze_ticker(t, NSE_TICKERS.get(t, t))
            if r:
                results.append((t, r))
            time.sleep(0.5)
        progress.empty()

        if results:
            st.success(f"Briefed {len(results)} stocks")
            for t, r in results:
                sd = r["stock_data"]
                change_str = f"{'+' if sd['change'] >= 0 else ''}{sd['change']:.2f}" if isinstance(sd['change'], (int, float)) else "N/A"
                with st.container(border=True):
                    cols = st.columns([2, 1, 1])
                    cols[0].markdown(f"**{t}** — {fmt_price(sd['current_price'])}")
                    cols[0].caption(f"{sd['name'][:40]}")
                    cols[1].markdown(f"Change: {change_str}")
                    cols[2].markdown(f"{r['signal_emoji']} {r['signal']}")

        if st.button("← Back to Single View"):
            st.session_state.run_briefing = False
            st.rerun()

else:
    st.info("👆 Select or type an NSE ticker above to begin.")
    st.markdown("""
    ### How it works
    1. **Enter** an NSE ticker (e.g., RELIANCE, HDFCBANK, TCS)
    2. **We fetch** live price data from Yahoo Finance
    3. **We scan** recent news from the web
    4. **AI analyzes** sentiment headline-by-headline
    5. **You get** a clear BUY / HOLD / CAUTION signal

    ### Why use this?
    - **Retail traders** — check sentiment before entering a trade
    - **Swing traders** — scan your watchlist for news-driven moves
    - **Portfolio holders** — keep a pulse on your holdings
    """)

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
st.caption("Built with Streamlit + yfinance + VADER + Financial Lexicon | Data from Yahoo Finance + RSS News")
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
