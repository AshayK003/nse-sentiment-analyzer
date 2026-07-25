"""
NSE Sentiment Analyzer — Refactored Architecture
Four-layer: Data → Strategy → Orchestrator → Dashboard
"""

from __future__ import annotations

import streamlit as st

# Page config FIRST
st.set_page_config(
    page_title="NSE Sentiment Analyzer",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ─── Imports ───
from src.engine import analyze, AnalysisRequest
from src.contracts import Verdict, Signal

# ─── UI Constants ───
DOT_GREEN = '<svg width="12" height="12" viewBox="0 0 24 24" fill="#22b573" stroke="none"><circle cx="12" cy="12" r="6"/></svg>'
DOT_RED = '<svg width="12" height="12" viewBox="0 0 24 24" fill="#f85149" stroke="none"><circle cx="12" cy="12" r="6"/></svg>'
DOT_ORANGE = '<svg width="12" height="12" viewBox="0 0 24 24" fill="#f59e0b" stroke="none"><circle cx="12" cy="12" r="6"/></svg>'
DOT_GREY = '<svg width="12" height="12" viewBox="0 0 24 24" fill="#8891a0" stroke="none"><circle cx="12" cy="12" r="6"/></svg>'

ARROW_UP = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 7-7 7 7"/><path d="M12 19V5"/></svg>'
ARROW_DOWN = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="m19 12-7 7-7-7"/></svg>'

# ─── CSS ───
st.markdown("""
<style>
details.news-expander {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px;
    padding: 0.5rem 0.75rem;
    margin-bottom: 0.5rem;
}
details.news-expander summary {
    cursor: pointer;
    display: flex; align-items: center; gap: 6px;
    font-weight: 600; font-size: 0.95rem; color: #e4e6eb;
    list-style: none;
}
details.news-expander summary::-webkit-details-marker { display: none; }
.caret { transition: transform 0.2s; }
details.news-expander[open] summary .caret { transform: rotate(90deg); }
.signal-badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 999px; font-weight: 700; font-size: 0.85rem;
}
.signal-BUY { background: rgba(34,181,115,0.15); color: #22b573; border: 1px solid rgba(34,181,115,0.3); }
.signal-SELL { background: rgba(248,81,73,0.15); color: #f85149; border: 1px solid rgba(248,81,73,0.3); }
.signal-HOLD { background: rgba(245,158,11,0.15); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); }
.metric-card { padding: 0.5rem; background: rgba(255,255,255,0.02); border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ─── Helpers ───
def _signal_badge(signal: Signal, confidence: int) -> str:
    return f'<span class="signal-badge signal-{signal.value}">{signal.value} · {confidence}%</span>'

def _trend_badge(trend: str) -> str:
    if trend == "bullish":
        return f'{DOT_GREEN} <span style="color:#22b573">Bullish</span>'
    elif trend == "bearish":
        return f'{DOT_RED} <span style="color:#f85149">Bearish</span>'
    return f'{DOT_GREY} <span style="color:#8891a0">Neutral</span>'

def _change_str(change_pct: float) -> str:
    if change_pct > 0:
        return f'{ARROW_UP} +{change_pct:.2f}%'
    elif change_pct < 0:
        return f'{ARROW_DOWN} {change_pct:.2f}%'
    return f'{DOT_GREY} 0.00%'

def _event_label(event_type) -> str:
    if hasattr(event_type, 'value'):
        return event_type.value.replace('_', ' ').title()
    return str(event_type).replace('_', ' ').title()

# ─── App ───
def main():
    st.title("📈 NSE Sentiment Analyzer")
    st.caption("Live price + news sentiment + technical signals — four-layer architecture")

    # Input
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        ticker = st.text_input("Ticker", placeholder="RELIANCE, TCS, HDFCBANK...", label_visibility="collapsed")
    with col2:
        period = st.selectbox("Period", ["1y", "6mo", "3mo", "1mo", "5d"], index=0, label_visibility="collapsed")
    with col3:
        force_refresh = st.checkbox("Refresh", value=False, label_visibility="collapsed")

    if not ticker:
        st.info("Enter an NSE ticker (e.g., RELIANCE, TCS, INFY)")
        return

    # Run analysis
    with st.spinner(f"Analyzing {ticker.upper()}..."):
        request = AnalysisRequest(
            ticker=ticker.upper(),
            period=period,
            include_news=True,
            force_refresh=force_refresh,
        )
        result = analyze(request)

    v: Verdict = result.verdict

    # ─── Header Card ───
    st.markdown("---")
    hdr1, hdr2, hdr3, hdr4 = st.columns([2, 1, 1, 1])

    with hdr1:
        st.markdown(f"### {v.ticker}")
        if v.price_data:
            st.markdown(f"**₹{v.price_data.current_price:,.2f}** · {_change_str(v.price_data.change_pct)}")

    with hdr2:
        st.markdown(_signal_badge(v.signal, v.confidence), unsafe_allow_html=True)

    with hdr3:
        if v.price_data:
            st.markdown(_trend_badge(v.indicators.trend.value), unsafe_allow_html=True)

    with hdr4:
        if v.cascade:
            cas = v.cascade
            badge = DOT_GREEN if cas.direction.value == "bullish" else DOT_RED
            st.markdown(f'{badge} <span style="color:{"#22b573" if cas.direction.value=="bullish" else "#f85149"}">Cascade: {cas.direction.value.title()}</span>', unsafe_allow_html=True)

    # ─── Rationale ───
    if v.rationale:
        st.info(f"**Rationale:** {v.rationale}")

    # ─── Key Metrics Row ───
    if v.price_data:
        m1, m2, m3, m4 = st.columns(4)
        ind = v.indicators

        with m1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("RSI (14)", f"{ind.rsi_14:.1f}")
            st.caption(">70 overbought · <30 oversold")
            st.markdown('</div>', unsafe_allow_html=True)

        with m2:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            macd_diff = ind.macd - ind.macd_signal
            st.metric("MACD", f"{ind.macd:.3f}", f"{macd_diff:+.3f}")
            st.caption("Signal: " + ("Bullish" if macd_diff > 0 else "Bearish"))
            st.markdown('</div>', unsafe_allow_html=True)

        with m3:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            sma200 = ind.sma_200
            if sma200 > 0 and v.price_data.current_price > 0:
                dist = ((v.price_data.current_price - sma200) / sma200) * 100
                st.metric("vs 200 SMA", f"{dist:+.1f}%")
            else:
                st.metric("vs 200 SMA", "N/A")
            st.caption("Price distance from 200-day avg")
            st.markdown('</div>', unsafe_allow_html=True)

        with m4:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("Volume Ratio", f"{ind.volume_ratio:.2f}x")
            st.caption("Current / 20-day avg")
            st.markdown('</div>', unsafe_allow_html=True)

    # ─── Sentiment Section ───
    st.markdown("---")
    st.subheader("📰 News Sentiment")

    s = v.sentiment
    if s.article_count == 0:
        st.info("No recent news articles found")
    else:
        se1, se2, se3 = st.columns(3)
        with se1:
            st.metric("Compound", f"{s.compound:+.3f}")
            st.caption("VADER score: -1 (bearish) → +1 (bullish)")
        with se2:
            st.metric("Confidence", f"{s.confidence:.0%}")
            st.caption("Source weight + text length")
        with se3:
            st.metric("Event", _event_label(s.event_type))
            st.caption(f"Confidence: {s.event_confidence:.0%}")

    # Sentiment breakdown
    st.progress((s.compound + 1) / 2, text=f"Negative {s.negative:.0%} · Neutral {s.neutral:.0%} · Positive {s.positive:.0%}")

    # ─── Articles ───
    if result.raw_headlines:
        with st.expander(f"📄 Articles ({len(result.raw_headlines)})", expanded=False):
            for h in result.raw_headlines[:15]:
                sentiment_val = getattr(h, 'sentiment', 0.0) if hasattr(h, 'sentiment') else 0.0
                dot = DOT_GREEN if sentiment_val > 0.1 else (DOT_RED if sentiment_val < -0.1 else DOT_ORANGE)
                st.markdown(
                    f'<details class="news-expander"><summary>{dot} <strong>{h.title[:80]}...</strong> '
                    f'<span style="color:#8891a0;font-size:0.85rem">{h.source} · {h.published.strftime("%d %b %Y")}</span></summary>'
                    f'<div style="margin-top:0.5rem;color:#b0b3b8;font-size:0.9rem">{h.summary[:200]}...</div>'
                    f'<div style="margin-top:0.5rem"><a href="{h.url}" target="_blank" style="color:#00b4ff">Read full article →</a></div>'
                    f'</details>',
                    unsafe_allow_html=True
                )

    # ─── Technical Details ───
    with st.expander("🔧 Technical Details", expanded=False):
        if v.price_data:
            td1, td2 = st.columns(2)
            ind = v.indicators

            with td1:
                st.markdown("**Moving Averages**")
                st.write(f"SMA 20: ₹{ind.sma_20:.2f}")
                st.write(f"SMA 50: ₹{ind.sma_50:.2f}")
                st.write(f"SMA 200: ₹{ind.sma_200:.2f}")
                st.write(f"EMA 20: ₹{ind.ema_20:.2f}")

                st.markdown("**Bollinger Bands**")
                st.write(f"Upper: ₹{ind.bollinger_upper:.2f}")
                st.write(f"Middle: ₹{ind.bollinger_middle:.2f}")
                st.write(f"Lower: ₹{ind.bollinger_lower:.2f}")

            with td2:
                st.markdown("**Momentum & Volatility**")
                st.write(f"MACD: {ind.macd:.3f} (Signal: {ind.macd_signal:.3f}, Hist: {ind.macd_hist:.3f})")
                st.write(f"ATR (14): {ind.atr_14:.2f}")
                st.write(f"ADX: {ind.adx_14:.1f}")

    # ─── Footer ───
    st.markdown("---")
    st.caption(
        f"Data: yfinance · News: RSS feeds + Yahoo · Cache: {result.fetch_duration_ms}ms · "
        f"Architecture: Data → Strategy → Engine → UI · "
        f'<a href="https://github.com/AshayK003/nse-sentiment-analyzer" target="_blank">GitHub</a> · '
        f'<a href="https://chai4.me/ashaykushwaha003" target="_blank">☕ Support</a>',
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()