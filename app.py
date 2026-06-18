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

st.title("📊 NSE Stock Sentiment Analyzer")
st.markdown("Enter an NSE stock ticker to see **live price + news sentiment** in one place.")

# Ticker input
col1, col2 = st.columns([3, 1])
with col1:
    ticker = st.selectbox(
        "Select or type an NSE ticker:",
        options=[""] + sorted(NSE_TICKERS.keys()),
        format_func=lambda x: f"{x} — {NSE_TICKERS.get(x, '')}" if x else "Select a ticker...",
        placeholder="Search tickers...",
    )
with col2:
    custom_ticker = st.text_input("Or enter custom:", placeholder="NYKAA", max_chars=15)

final_ticker = custom_ticker.strip().upper() if custom_ticker.strip() else ticker

if final_ticker and final_ticker != "":
    final_ticker = final_ticker.replace(".NS", "")
    company_name = NSE_TICKERS.get(final_ticker, final_ticker)

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
        st.markdown("---")
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
        st.markdown("---")
        st.subheader("📰 News Sentiment Analysis")

        # Use weighted signal as primary, show flat average for comparison
        primary_signal = result.get("weighted_signal", signal)
        primary_compound = result.get("blended_compound", avg_compound)
        primary_emoji = result.get("weighted_emoji", signal_emoji)
        source_breakdown = result.get("source_breakdown", [])
        confidence = abs(primary_compound)

        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            st.markdown(f"### {primary_emoji} {primary_signal}")
            st.caption(f"Based on {len(news_items)} articles · Weighted across {len(source_breakdown)} sources")

        with col_s2:
            confidence_pct = min(confidence * 100, 99)
            st.markdown(f"### {confidence_pct:.0f}%")
            st.caption("Weighted Confidence Score")

        with col_s3:
            if "🟢" in str(primary_signal):
                rec = "✅ BUY / HOLD — Positive sentiment dominates"
                st.success(rec)
            elif "🔴" in str(primary_signal):
                rec = "⚠️ CAUTION / SELL — Negative sentiment detected"
                st.warning(rec)
            else:
                rec = "💤 HOLD — Mixed or neutral sentiment"
                st.info(rec)

        # Per-source sentiment breakdown
        if source_breakdown:
            st.markdown("##### Source Breakdown")
            src_cols = st.columns(len(source_breakdown))
            for i, src in enumerate(source_breakdown):
                with src_cols[i]:
                    emoji = "🟢" if src["avg"] >= 0.3 else "🔴" if src["avg"] <= -0.3 else "⚪"
                    local_badge = " ⚡" if src["source"] in LOCAL_ONLY_SOURCES else ""
                    st.markdown(f"**{src['source']}{local_badge}**")
                    st.markdown(f"{emoji} `{src['avg']:.2f}`")
                    st.caption(f"w={src['weight']:.1f} · {src['count']} articles")

        # News source health indicator
        if source_stats:
            # Mark local-only sources with ⚡
            parts = []
            for s, n in sorted(source_stats.items()):
                icon = "⚡" if s in LOCAL_ONLY_SOURCES else ""
                parts.append(f"{s} ({n}){icon}")
            sources_str = " · ".join(parts)
            st.caption(f"📡 Sources: {sources_str}")
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
                    st.rerun()
            with vd:
                if st.button("👎 No", key="vote_down", use_container_width=True):
                    last_rec["vote"] = False
                    save_track_record(records)
                    st.rerun()
        elif last_rec and last_rec.get("vote") is not None:
            st.caption(f"You marked this signal as {'✅ accurate' if last_rec['vote'] else '❌ inaccurate'}")

        # ─── SENTIMENT DISTRIBUTION ───
        st.markdown("---")
        st.subheader("📈 Sentiment Distribution")

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

        # ─── NEWS HEADLINES (with clickable links) ───
        st.markdown("---")
        st.subheader(f"📋 Recent News ({len(news_items)} articles)")

        for i, (item, scores) in enumerate(zip(news_items, headline_scores)):
            emoji = get_sentiment_emoji(scores["compound"])
            sentiment_label = "Positive" if scores["compound"] >= 0.3 else "Negative" if scores["compound"] <= -0.3 else "Neutral"

            with st.container(border=True):
                cols = st.columns([0.05, 0.75, 0.2])
                with cols[0]:
                    st.markdown(f"**{emoji}**")
                with cols[1]:
                    # Title is now a clickable link
                    if item.get("url"):
                        st.markdown(f"**[{item['title']}]({item['url']})**")
                    else:
                        st.markdown(f"**{item['title']}**")
                    if item.get("body"):
                        st.caption(item["body"][:200])
                with cols[2]:
                    st.markdown(f"*{sentiment_label}*")
                    if item.get("date"):
                        st.caption(item["date"][:10])

        # ─── KEY STATS ───
        st.markdown("---")
        with st.expander("📊 Additional Stats"):
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
        st.markdown("---")
        with st.expander("📈 Technical Indicators"):
            ti = get_technical_indicators(final_ticker)
            if ti:
                col_t1, col_t2, col_t3, col_t4 = st.columns(4)
                with col_t1:
                    rsi = ti["rsi"]
                    rsi_label = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
                    st.metric("RSI (14)", f"{rsi:.1f}", rsi_label, delta_color="inverse")
                with col_t2:
                    price = ti["close"]
                    above_50 = price > ti["sma_50"]
                    trend = f"{'🟢' if above_50 else '🔴'} SMA50" if not pd.isna(ti["sma_50"]) else "N/A"
                    st.metric("vs SMA 50", f"₹{ti['sma_50']:.0f}" if not pd.isna(ti["sma_50"]) else "N/A", trend)
                with col_t3:
                    above_200 = price > ti["sma_200"]
                    trend200 = f"{'🟢' if above_200 else '🔴'} SMA200" if not pd.isna(ti["sma_200"]) else "N/A"
                    st.metric("vs SMA 200", f"₹{ti['sma_200']:.0f}" if not pd.isna(ti["sma_200"]) else "N/A", trend200)
                with col_t4:
                    macd_status = "🟢 Bullish" if ti["macd_hist"] > 0 else "🔴 Bearish"
                    st.metric("MACD Hist", f"{ti['macd_hist']:.2f}", macd_status)
            else:
                st.caption("Not enough data to compute technical indicators (need 1yr+).")
    else:
        st.error(f"Could not find data for **{final_ticker}**. Try a different ticker (e.g., RELIANCE, HDFCBANK, TCS).")

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

# ─── FOOTER ───
st.markdown("---")
st.caption("Built with Streamlit + yfinance + VADER + Financial Lexicon | Data from Yahoo Finance + RSS News")
st.caption("📌 Not financial advice. Always do your own research.")
st.markdown(
    '<div style="display:flex;justify-content:center;margin-top:12px">'
    '<a href="https://chai4.me/darkcharon3301" target="_blank" title="Support darkcharon3301 on Chai4Me" '
    'style="display:inline-flex;flex-direction:column;align-items:center;justify-content:center;'
    'background:#ffffff;padding:8px 32px;border-radius:16px;text-decoration:none;'
    'border:1px solid #e5e7eb;'
    'box-shadow:0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -2px rgba(0,0,0,0.05);'
    'transition:transform 0.2s;">'
    '<img src="https://chai4.me/icons/wordmark.png" alt="Chai4Me" style="height:32px;object-fit:contain;"/>'
    '</a></div>',
    unsafe_allow_html=True,
)
