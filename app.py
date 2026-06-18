"""
NSE Stock Sentiment Analyzer
Enter any NSE ticker → get live price + news sentiment score + signal.
Built with Streamlit + yfinance + VADER + custom financial lexicon.
"""

import streamlit as st
import pandas as pd
import time
from datetime import datetime

from data_fetcher import (
    NSE_TICKERS, get_stock_info, search_news,
    format_price, format_large_num,
)
from sentiment import get_sia, analyze_headline_sentiment, get_overall_signal, get_sentiment_emoji, get_weighted_signal, LOCAL_ONLY_SOURCES
from indicators import get_technical_indicators
from persistence import load_portfolio, save_portfolio, load_track_record, save_track_record

# ─── Page config ───
st.set_page_config(
    page_title="NSE Sentiment Analyzer",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ─── Premium CSS (glassmorphism, Inter font, custom widgets) ───
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    * { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }

    /* ── Hide Streamlit chrome ── */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stAppToolbar {display: none;}
    header {visibility: hidden;}

    /* ── Custom scrollbar ── */
    ::-webkit-scrollbar {width: 6px;}
    ::-webkit-scrollbar-track {background: #0a0b0f;}
    ::-webkit-scrollbar-thumb {background: #1e2028; border-radius: 3px;}
    ::-webkit-scrollbar-thumb:hover {background: #2a2d35;}

    /* ── Refined palette ── */
    :root {
        --accent: #22b573;
        --accent-dim: #0d9488;
        --bg-deep: #0a0b0f;
        --bg-card: #13151a;
        --border: #1e2028;
        --text-primary: #e4e6eb;
        --text-muted: #6b7280;
        --red: #f85149;
    }

    /* ── Glassmorphism cards ── */
    .card, [data-testid="stVerticalBlock"] > .stContainer {
        background: rgba(19, 21, 26, 0.85);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(30, 32, 40, 0.8);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.2);
    }
    [data-testid="stVerticalBlock"] > .stContainer:hover {
        border-color: rgba(34, 181, 115, 0.15);
        box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    }

    /* ── Card title ── */
    .card-title {
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--text-muted);
        margin-bottom: 0.75rem;
    }

    /* ── Metric containers ── */
    [data-testid="metric-container"] {
        background: rgba(19, 21, 26, 0.6);
        backdrop-filter: blur(10px);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 0.75rem 1rem;
        transition: border-color 0.2s ease;
    }
    [data-testid="metric-container"]:hover {
        border-color: rgba(34, 181, 115, 0.2);
    }
    /* Override default Streamlit metric red/green */
    [data-testid="metric-container"] [data-testid="stMetricDelta"] svg {
        display: none;
    }

    /* ── Sentiment hero (gradient text) ── */
    .sentiment-hero {
        font-size: 1.75rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        line-height: 1.2;
    }
    .sentiment-hero.bullish {
        background: linear-gradient(135deg, #22b573, #0d9488);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .sentiment-hero.bearish {
        background: linear-gradient(135deg, #f85149, #da3633);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .sentiment-hero.neutral {
        background: linear-gradient(135deg, #868e96, #6b7280);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    /* ── Confidence number ── */
    .confidence-num {
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        line-height: 1;
        background: linear-gradient(135deg, #22b573, #0d9488);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    /* ── Progress bars ── */
    .stProgress > div > div {
        background: var(--border) !important;
        border-radius: 4px;
        height: 8px !important;
    }
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, var(--accent), var(--accent-dim)) !important;
        border-radius: 4px;
    }

    /* ── Selectbox ── */
    .stSelectbox [data-baseweb="select"] {
        border-radius: 8px !important;
        border: 1px solid var(--border) !important;
        background: rgba(19, 21, 26, 0.6) !important;
        transition: border-color 0.2s ease;
    }
    .stSelectbox [data-baseweb="select"]:focus-within {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 2px rgba(34, 181, 115, 0.1) !important;
    }

    /* ── Text input ── */
    .stTextInput input {
        border-radius: 8px !important;
        border: 1px solid var(--border) !important;
        background: rgba(19, 21, 26, 0.6) !important;
        color: var(--text-primary) !important;
        transition: border-color 0.2s ease;
    }
    .stTextInput input:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 2px rgba(34, 181, 115, 0.1) !important;
    }

    /* ── Buttons ── */
    .stButton button {
        border-radius: 8px !important;
        border: 1px solid var(--border) !important;
        background: rgba(19, 21, 26, 0.6) !important;
        color: var(--text-primary) !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
    }
    .stButton button:hover {
        border-color: rgba(34, 181, 115, 0.3) !important;
        background: rgba(34, 181, 115, 0.08) !important;
    }

    /* ── Source badges ── */
    .source-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.25rem 0.75rem;
        border-radius: 100px;
        font-size: 0.75rem;
        font-weight: 500;
        border: 1px solid var(--border);
        background: rgba(255,255,255,0.03);
        margin: 0.15rem;
        white-space: nowrap;
        transition: all 0.2s ease;
    }
    .source-badge:hover { transform: translateY(-1px); }
    .source-badge.bullish { border-color: rgba(34,181,115,0.3); color: #22b573; }
    .source-badge.bearish { border-color: rgba(255,75,75,0.3); color: #ff4b4b; }
    .source-badge.neutral { border-color: rgba(255,255,255,0.1); color: var(--text-muted); }

    /* ── Skeleton shimmer ── */
    @keyframes shimmer {
        0% { background-position: -400px 0; }
        100% { background-position: 400px 0; }
    }
    .skeleton {
        background: linear-gradient(90deg, #1e2028 25%, #2a2d35 50%, #1e2028 75%);
        background-size: 800px 100%;
        animation: shimmer 1.5s infinite;
        border-radius: 8px;
        height: 1rem;
        margin-bottom: 0.5rem;
    }
    .skeleton-h2 { height: 1.75rem; width: 60%; }
    .skeleton-metric { height: 3rem; width: 100%; }
    .skeleton-news { height: 2.5rem; width: 100%; }

    /* ── Focus ring (WCAG 2.4.7) ── */
    *:focus-visible {
        outline: 2px solid var(--accent) !important;
        outline-offset: 2px !important;
        border-radius: 4px;
    }

    /* ── Responsive ── */
    @media (max-width: 640px) {
        div.row-widget.stHorizontal > div { min-width: 50% !important; }
        [data-testid="column"] .card { padding: 0.75rem; }
    }
</style>
""", unsafe_allow_html=True)


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
        with st.container(border=True):
            st.markdown('<div class="card-title">📈 Live Price</div>', unsafe_allow_html=True)
            col_p1, col_p2, col_p3, col_p4 = st.columns(4)

            with col_p1:
                price = stock_data['current_price']
                change_val = stock_data['change']
                change_pct = stock_data['change_pct']
                st.metric(
                    label=f"{final_ticker} — {stock_data['name'][:30]}",
                    value=fmt_price(price),
                    delta=f"{delta_str(change_val)} ({delta_str(change_pct)}%)",
                    delta_color=delta_color(change_val),
                )

            with col_p2:
                st.metric("Day Range",
                          f"₹{stock_data['day_low']:.2f} — ₹{stock_data['day_high']:.2f}"
                          if isinstance(stock_data['day_low'], (int, float)) else "N/A")

            with col_p3:
                st.metric("Volume", fmt_metric(stock_data['volume']))

            with col_p4:
                pe = stock_data['pe_ratio']
                st.metric("P/E Ratio", f"{pe:.2f}" if isinstance(pe, (int, float)) else "N/A")

        # ─── SENTIMENT CARD ───
        with st.container(border=True):
            st.markdown('<div class="card-title">📰 News Sentiment Analysis</div>', unsafe_allow_html=True)

            # Use weighted signal as primary, show flat average for comparison
            primary_signal = result.get("weighted_signal", signal)
            primary_compound = result.get("blended_compound", avg_compound)
            primary_emoji = result.get("weighted_emoji", signal_emoji)
            source_breakdown = result.get("source_breakdown", [])
            confidence = abs(primary_compound)

            # Sentiment hero row
            s_col1, s_col2 = st.columns([1, 1])

            with s_col1:
                # Determine sentiment CSS class
                if "BULLISH" in str(primary_signal):
                    sent_class = "bullish"
                    rec = "✅ BUY / HOLD — Positive sentiment dominates"
                elif "BEARISH" in str(primary_signal):
                    sent_class = "bearish"
                    rec = "⚠️ CAUTION / SELL — Negative sentiment detected"
                else:
                    sent_class = "neutral"
                    rec = "💤 HOLD — Mixed or neutral sentiment"

                st.markdown(
                    f'<div class="sentiment-hero {sent_class}">{primary_emoji} {primary_signal}</div>',
                    unsafe_allow_html=True,
                )
                st.caption(f"Based on {len(news_items)} articles · Weighted across {len(source_breakdown)} sources")
                if "BULLISH" in str(primary_signal):
                    st.success(rec)
                elif "BEARISH" in str(primary_signal):
                    st.warning(rec)
                else:
                    st.info(rec)

            with s_col2:
                # Confidence score
                confidence_pct = min(confidence * 100, 99)
                st.markdown(
                    f'<div class="confidence-num">{confidence_pct:.0f}%</div>',
                    unsafe_allow_html=True,
                )
                st.caption("Weighted Confidence Score")

            # Per-source sentiment as badges (not columns — prevents breakage at 5+)
            if source_breakdown:
                st.markdown("##### Source Breakdown")
                badge_html = ""
                for src in source_breakdown:
                    if src["avg"] >= 0.3:
                        badge_class = "bullish"
                        emoji = "🟢"
                    elif src["avg"] <= -0.3:
                        badge_class = "bearish"
                        emoji = "🔴"
                    else:
                        badge_class = "neutral"
                        emoji = "⚪"
                    local_badge = " ⚡" if src["source"] in LOCAL_ONLY_SOURCES else ""
                    badge_html += (
                        f'<span class="source-badge {badge_class}">'
                        f'{emoji} {src["source"]}{local_badge}'
                        f' <span style="opacity:0.6">w={src["weight"]:.1f}</span>'
                        f' <span style="opacity:0.6">· {src["count"]} art.</span>'
                        f'</span> '
                )
                st.markdown(f'<div>{badge_html}</div>', unsafe_allow_html=True)

            # News source health indicator
            if source_stats:
                parts = []
                for s, n in sorted(source_stats.items()):
                    icon = "⚡" if s in LOCAL_ONLY_SOURCES else ""
                    parts.append(f"{s} ({n}){icon}")
                sources_str = " · ".join(parts)
                st.caption(f"📡 Sources responded: {sources_str}")
                if any(s in LOCAL_ONLY_SOURCES for s in source_stats):
                    st.caption("⚡ = local-only (not available on Streamlit Cloud)")

        # Thumbs up/down for track record
        records = load_track_record()
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

        # ─── SENTIMENT DISTRIBUTION ───
        with st.container(border=True):
            st.markdown('<div class="card-title">📈 Sentiment Distribution</div>', unsafe_allow_html=True)

            if headline_scores:
                pos_pct = sum(1 for s in headline_scores if s["compound"] >= 0.3) / len(headline_scores) * 100
                neg_pct = sum(1 for s in headline_scores if s["compound"] <= -0.3) / len(headline_scores) * 100
                neu_pct = 100 - pos_pct - neg_pct

                col_m1, col_m2, col_m3 = st.columns(3)
                with col_m1:
                    st.markdown(f"🟢 **Positive:** {pos_pct:.0f}%")
                    st.progress(pos_pct / 100)
                with col_m2:
                    st.markdown(f"🔴 **Negative:** {neg_pct:.0f}%")
                    st.progress(neg_pct / 100)
                with col_m3:
                    st.markdown(f"⚪ **Neutral:** {neu_pct:.0f}%")
                    st.progress(neu_pct / 100)

        # ─── NEWS HEADLINES ───
        with st.container(border=True):
            st.markdown(f'<div class="card-title">📋 Recent News ({len(news_items)} articles)</div>', unsafe_allow_html=True)

            for i, (item, scores) in enumerate(zip(news_items, headline_scores)):
                emoji = get_sentiment_emoji(scores["compound"])
                sentiment_label = "Positive" if scores["compound"] >= 0.3 else "Negative" if scores["compound"] <= -0.3 else "Neutral"

                with st.container(border=True):
                    # Title with emoji
                    if item.get("url"):
                        st.markdown(f"{emoji} **[{item['title']}]({item['url']})**")
                    else:
                        st.markdown(f"{emoji} **{item['title']}**")
                    # Meta row: source + date + sentiment
                    meta_parts = []
                    if item.get("source"):
                        meta_parts.append(f"📡 {item['source']}")
                    if item.get("date"):
                        meta_parts.append(f"📅 {item['date'][:10]}")
                    meta_parts.append(f"*{sentiment_label}*")
                    # Attribution for Reddit posts (required by Reddit Developer Terms)
                    if item.get("source") == "Reddit" and item.get("author"):
                        sub = f"r/{item['subreddit']}/" if item.get("subreddit") else ""
                        meta_parts.append(f"by u/{item['author']} on {sub}Reddit")
                    st.caption(" · ".join(meta_parts))
                    # Body excerpt (non-Reddit)
                    if item.get("source") != "Reddit" and item.get("body"):
                        st.caption(item["body"][:200])

        # ─── KEY STATS ───
        with st.container(border=True):
            st.markdown('<div class="card-title">📊 Additional Stats</div>', unsafe_allow_html=True)
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                st.markdown(f"**Sector:** {stock_data['sector']}")
                st.markdown(f"**Industry:** {stock_data['industry']}")
                st.markdown(f"**Market Cap:** {format_large_num(stock_data['market_cap'])}")
            with col_a2:
                st.markdown(
                    f"**52W High:** {fmt_price(stock_data['52w_high'])}"
                )
                st.markdown(
                    f"**52W Low:** {fmt_price(stock_data['52w_low'])}"
                )
                pe = stock_data['pe_ratio']
                st.markdown(f"**P/E Ratio:** {f'{pe:.2f}' if isinstance(pe, (int, float)) else 'N/A'}")

        # ─── TECHNICAL INDICATORS ───
        ti = get_technical_indicators(final_ticker)
        preview = ""
        if ti:
            rsi = ti["rsi"]
            rsi_label = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
            price = ti["close"]
            above_50 = "🟢" if price > ti["sma_50"] else "🔴" if not pd.isna(ti["sma_50"]) else "—"
            above_200 = "🟢" if price > ti["sma_200"] else "🔴" if not pd.isna(ti["sma_200"]) else "—"
            macd = "🟢 Bullish" if ti["macd_hist"] > 0 else "🔴 Bearish"
            preview = f"RSI {rsi:.1f} ({rsi_label}) · SMA50 {above_50} · SMA200 {above_200} · MACD {macd}"
        with st.container(border=True):
            st.markdown('<div class="card-title">📈 Technical Indicators</div>', unsafe_allow_html=True)
            if preview:
                st.caption(f"📌 {preview}")
            if ti:
                col_t1, col_t2, col_t3, col_t4 = st.columns(4)
                with col_t1:
                    st.metric("RSI (14)", f"{rsi:.1f}", rsi_label, delta_color="inverse")
                with col_t2:
                    trend = f"{'🟢' if above_50 == '🟢' else '🔴'} SMA50" if above_50 in ("🟢", "🔴") else "N/A"
                    st.metric("vs SMA 50", f"₹{ti['sma_50']:.0f}" if not pd.isna(ti["sma_50"]) else "N/A", trend)
                with col_t3:
                    trend200 = f"{'🟢' if above_200 == '🟢' else '🔴'} SMA200" if above_200 in ("🟢", "🔴") else "N/A"
                    st.metric("vs SMA 200", f"₹{ti['sma_200']:.0f}" if not pd.isna(ti["sma_200"]) else "N/A", trend200)
                with col_t4:
                    st.metric("MACD Hist", f"{ti['macd_hist']:.2f}", macd)
            else:
                st.caption("Not enough data to compute technical indicators (need 1yr+).")
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
            time.sleep(0.5)  # Rate limiting to avoid yfinance throttling
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
