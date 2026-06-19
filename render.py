"""Pure HTML/CSS dashboard renderer for NSE Sentiment Analyzer.

Replaces Streamlit display widgets with a custom premium template
rendered via st.components.v1.html().
"""

import html
import secrets
import itertools

# ─── Inline SVG icons (Lucide, MIT-licensed, stroke-based) ───
# ponytail: inline SVGs avoid a 100KB+ icon library for ~15 icons
_ICON = {}

def _svg(path, view_box="0 0 24 24"):
    """Build a 16x16 inline SVG icon with currentColor stroke."""
    return f'<svg class="icon" width="16" height="16" viewBox="{view_box}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{path}</svg>'

_ICON["trending_up"] = _svg('<path d="M16 7h6v6"/><path d="m22 7-8.5 8.5-5-5L2 17"/>')
_ICON["newspaper"] = _svg('<path d="M15 18h-5"/><path d="M18 14h-8"/><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-4 0v-9a2 2 0 0 1 2-2h2"/><rect width="8" height="4" x="10" y="6" rx="1"/>')
_ICON["bar_chart"] = _svg('<path d="M5 21v-6"/><path d="M12 21V3"/><path d="M19 21V9"/>')
_ICON["file_text"] = _svg('<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/><path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>')
_ICON["bank"] = _svg('<path d="M10 18v-7"/><path d="M11.119 2.205a2 2 0 0 1 1.762 0l7.84 3.846A.5.5 0 0 1 20.5 7h-17a.5.5 0 0 1-.22-.949z"/><path d="M14 18v-7"/><path d="M18 18v-7"/><path d="M3 22h18"/><path d="M6 18v-7"/>')
_ICON["signal"] = _svg('<path d="M2 20h.01"/><path d="M7 20v-4"/><path d="M12 20v-8"/><path d="M17 20V8"/><path d="M22 4v16"/>')
_ICON["target"] = _svg('<circle cx="12" cy="12" r="10"/><line x1="22" x2="18" y1="12" y2="12"/><line x1="6" x2="2" y1="12" y2="12"/><line x1="12" x2="12" y1="6" y2="2"/><line x1="12" x2="12" y1="22" y2="18"/>')
_ICON["check"] = _svg('<path d="M20 6 9 17l-5-5"/>')
_ICON["alert"] = _svg('<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>')
_ICON["minus"] = _svg('<path d="M5 12h14"/>')
_ICON["dot_green"] = _svg('<circle cx="12" cy="12" r="4" fill="#22b573" stroke="none"/>')
_ICON["dot_red"] = _svg('<circle cx="12" cy="12" r="4" fill="#f85149" stroke="none"/>')
_ICON["dot_grey"] = _svg('<circle cx="12" cy="12" r="4" fill="#8891a0" stroke="none"/>')
_ICON["arrow_up"] = _svg('<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>')
_ICON["arrow_down"] = _svg('<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>')
_ICON["wifi"] = _svg('<path d="M12 20h.01"/><path d="M2 8.82a15 15 0 0 1 20 0"/><path d="M5 12.859a10 10 0 0 1 14 0"/><path d="M8.5 16.429a5 5 0 0 1 7 0"/>')
_ICON["layout"] = _svg('<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>')
# Signal indicator icons (colored filled circles with symbol — larger than dots)
_ICON["bullish"] = _svg('<circle cx="12" cy="12" r="10" fill="#22b573" stroke="none"/><path d="M12 7 8 15h8z" fill="#f0f0f0" stroke="none"/>')
_ICON["bearish"] = _svg('<circle cx="12" cy="12" r="10" fill="#f85149" stroke="none"/><path d="M8 9h8l-4 8z" fill="#f0f0f0" stroke="none"/>')
_ICON["neutral"] = _svg('<circle cx="12" cy="12" r="10" fill="#8891a0" stroke="none"/><path d="M7 12h10" stroke="#f0f0f0" stroke-width="2.5" stroke-linecap="round" fill="none"/>')

# ponytail: counter for unique sparkline gradient IDs (avoids id() which can collide across renders)
_sparkline_counter = itertools.count()


def get_signal_icon(emoji):
    """Return the 16x16 Lucide SVG icon for a signal emoji string.
    
    Used by app.py for Streamlit-native rendering (outside the iframe).
    Maps emoji strings (🟢/🔴/⚪) to their SVG counterparts.
    """
    return {
        "🟢": _ICON["bullish"],
        "🔴": _ICON["bearish"],
        "⚪": _ICON["neutral"],
    }.get(emoji, _ICON["neutral"])


def h(s):
    """Escape a string for safe HTML output."""
    if s is None:
        return ""
    return html.escape(str(s), quote=True)


def h_attr(s):
    """Escape a string for safe insertion into an HTML attribute value."""
    if s is None:
        return ""
    return html.escape(str(s), quote=True)


def fmt_price(val):
    if isinstance(val, (int, float)):
        return f"\u20b9{val:,.2f}"
    return "N/A"


def fmt_vol(val):
    if isinstance(val, (int, float)):
        if val >= 1e7:
            return f"{val/1e7:.1f}Cr"
        if val >= 1e5:
            return f"{val/1e5:.1f}L"
        return f"{val:,.0f}"
    return "N/A"


def fmt_delta(val):
    if isinstance(val, (int, float)):
        sign = "+" if val >= 0 else ""
        return f"{sign}{val:.2f}"
    return "N/A"


def fmt_large(val):
    if isinstance(val, (int, float)):
        if val >= 1e7:
            return f"\u20b9{val/1e7:.1f}Cr"
        if val >= 1e5:
            return f"\u20b9{val/1e5:.1f}L"
        return f"\u20b9{val:,.0f}"
    return "N/A"


def get_sentiment_emoji(compound):
    if compound >= 0.3:
        return "\U0001f7e2"
    if compound <= -0.3:
        return "\U0001f534"
    return "\u26aa"


def render_sparkline(values, width=160, height=32, color="#22b573"):
    """Render an inline SVG sparkline from a list of 0-100 values.

    Returns empty string if < 2 values.
    """
    if not values or len(values) < 2:
        return ""

    min_v = min(values)
    max_v = max(values)
    rng = max_v - min_v if max_v > min_v else 1

    points = []
    for i, v in enumerate(values):
        x = (i / (len(values) - 1)) * width
        y = height - ((v - min_v) / rng) * (height - 6) - 3
        points.append(f"{x:.1f},{y:.1f}")

    # Gradient from latest (right side) to oldest (left)
    grad_id = f"spark-{next(_sparkline_counter)}"
    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"
    style="vertical-align:middle;display:inline-block;">
    <defs>
        <linearGradient id="{grad_id}" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="{color}" stop-opacity="0.2"/>
            <stop offset="100%" stop-color="{color}" stop-opacity="0.8"/>
        </linearGradient>
    </defs>
    <polyline points="{' '.join(points)}" fill="none" stroke="url(#{grad_id})"
    stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""


def render_dashboard(result, ticker, company_name, technical_indicators=None,
                     track_record=None, fii_dii_data=None):
    """Return a complete premium HTML dashboard as a string."""
    stock = result["stock_data"]
    news_items = result["news_items"]
    headline_scores = result["headline_scores"]
    signal = result["signal"]
    avg_compound = result["avg_compound"]
    primary_signal = result.get("weighted_signal", signal)
    # Strip trailing emoji from signal text since we now use SVG icons
    if isinstance(primary_signal, str):
        primary_signal = primary_signal.rstrip(" 🟢🔴⚪")
    primary_compound = result.get("blended_compound", avg_compound)
    primary_emoji = result.get("weighted_emoji", result["signal_emoji"])
    _emoji_to_icon = {"🟢": _ICON["bullish"], "🔴": _ICON["bearish"], "⚪": _ICON["neutral"]}
    primary_emoji_svg = _emoji_to_icon.get(primary_emoji, _ICON["neutral"])
    source_breakdown = result.get("source_breakdown", [])
    source_stats = result.get("source_stats", {})

    # Sentiment class
    if "BULLISH" in str(primary_signal):
        sent_class = "bullish"
        rec_text = "BUY / HOLD"
        rec_detail = "Positive sentiment dominates"
        rec_icon = _ICON["check"]
    elif "BEARISH" in str(primary_signal):
        sent_class = "bearish"
        rec_text = "CAUTION / SELL"
        rec_detail = "Negative sentiment detected"
        rec_icon = _ICON["alert"]
    else:
        sent_class = "neutral"
        rec_text = "HOLD"
        rec_detail = "Mixed or neutral sentiment"
        rec_icon = _ICON["minus"]

    confidence_pct = min(abs(primary_compound) * 100, 99)

    # Sentiment distribution
    n = len(headline_scores)
    if n > 0:
        pos_pct = sum(1 for s in headline_scores if s["compound"] >= 0.3) / n * 100
        neg_pct = sum(1 for s in headline_scores if s["compound"] <= -0.3) / n * 100
        neu_pct = 100 - pos_pct - neg_pct
    else:
        pos_pct = neg_pct = neu_pct = 0.0

    # Price vars
    price = stock["current_price"]
    change_val = stock["change"]
    change_pct = stock["change_pct"]
    day_range = (
        f"\u20b9{stock['day_low']:,.2f} \u2014 \u20b9{stock['day_high']:,.2f}"
        if isinstance(stock.get("day_low"), (int, float))
        else "N/A"
    )
    volume = fmt_vol(stock["volume"])
    pe = stock.get("pe_ratio")
    pe_str = f"{pe:.2f}" if isinstance(pe, (int, float)) else "N/A"

    # 52-week proximity badge
    price_now = stock["current_price"]
    high_52 = stock.get("52w_high")
    low_52 = stock.get("52w_low")
    proximity_msg = ""
    proximity_class = ""
    if isinstance(high_52, (int, float)) and high_52 > 0:
        pct_of_high = (price_now / high_52) * 100
        proximity_msg = f"{pct_of_high:.0f}% of 52W High"
        proximity_class = "high" if pct_of_high > 90 else "mid" if pct_of_high > 70 else "low"
    elif isinstance(low_52, (int, float)) and low_52 > 0:
        pct_above_low = ((price_now - low_52) / low_52) * 100
        proximity_msg = f"{pct_above_low:.0f}% above 52W Low"
        proximity_class = "low" if pct_above_low < 10 else "mid"

    # Volume spike badge
    vol_now = stock["volume"]
    vol_spike_html = ""
    if technical_indicators and technical_indicators.get("avg_volume_50"):
        avg_vol_50 = technical_indicators["avg_volume_50"]
        if isinstance(vol_now, (int, float)) and avg_vol_50 > 0:
            vol_ratio = vol_now / avg_vol_50
            if vol_ratio >= 3:
                vol_spike_html = '<span class="spike-badge huge">🚨 3x volume surge!</span>'
            elif vol_ratio >= 2:
                vol_spike_html = f'<span class="spike-badge high">{vol_ratio:.1f}x normal volume</span>'
            elif vol_ratio >= 1.5:
                vol_spike_html = f'<span class="spike-badge mid">{vol_ratio:.1f}x avg volume</span>'

    # SMA crossover badges
    cross_50_html = ""
    cross_200_html = ""
    if technical_indicators:
        ti = technical_indicators
        _up_icon = _ICON["arrow_up"]
        _down_icon = _ICON["arrow_down"]
        if ti.get("sma50_cross") == "bullish":
            cross_50_html = '<span class="cross-badge bullish">' + _up_icon + ' SMA50 bullish crossover</span>'
        elif ti.get("sma50_cross") == "bearish":
            cross_50_html = '<span class="cross-badge bearish">' + _down_icon + ' SMA50 bearish crossover</span>'
        if ti.get("sma200_cross") == "bullish":
            cross_200_html = '<span class="cross-badge bullish">' + _up_icon + ' SMA200 bullish crossover</span>'
        elif ti.get("sma200_cross") == "bearish":
            cross_200_html = '<span class="cross-badge bearish">' + _down_icon + ' SMA200 bearish crossover</span>'

    # Track record accuracy
    acc_html = ""
    if track_record:
        voted = [r for r in track_record if r.get("vote") is not None]
        if voted:
            correct = sum(1 for r in voted if r["vote"])
            total = len(voted)
            acc_pct = (correct / total) * 100
            bar_c = "good" if acc_pct >= 70 else "ok" if acc_pct >= 50 else "poor"
            acc_html = f"""<div class="card">
    <div class="card-title">{_ICON["target"]} Signal Track Record</div>
    <div class="acc-row">
        <div class="acc-circle {bar_c}">{acc_pct:.0f}%</div>
        <div>
            <div class="acc-num">{correct}/{total} accurate</div>
            <div class="acc-desc">Track record across {total} past signal{'s' if total != 1 else ''}</div>
        </div>
    </div>
</div>"""

    # FII/DII institutional flow
    fii_html = ""
    if fii_dii_data:
        fi = fii_dii_data
        comb = fi["combined_net"]
        fii_icon = _ICON["dot_green"] if comb >= 0 else _ICON["dot_red"]
        fii_stance = "Institutions net buying" if comb >= 0 else "Institutions net selling"
        fii_html = f"""<div class="card">
    <div class="card-title">{_ICON["bank"]} Institutional Flow ({fi.get("date", "Latest")})</div>
    <div class="fii-grid">
        <div class="fii-item {'bearish' if fi['fii_net'] < 0 else ''}">
            <div class="fii-label">FII / FPI</div>
            <div class="fii-value">₹{fi['fii_net']:,.0f} Cr</div>
            <div class="fii-sub">{fi['fii_action']}</div>
        </div>
        <div class="fii-item {'bearish' if fi['dii_net'] < 0 else ''}">
            <div class="fii-label">DII</div>
            <div class="fii-value">₹{fi['dii_net']:,.0f} Cr</div>
            <div class="fii-sub">{fi['dii_action']}</div>
        </div>
        <div class="fii-item {'bearish' if comb < 0 else ''}">
            <div class="fii-label">Combined Net</div>
            <div class="fii-value">₹{comb:,.0f} Cr</div>
            <div class="fii-sub">{fii_icon} {fii_stance}</div>
        </div>
    </div>
</div>"""

    # Technical indicators
    ti_preview = ""
    ti_rows = ""
    if technical_indicators:
        ti = technical_indicators
        rsi = ti["rsi"]
        rsi_label = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
        close = ti["close"]
        sma50 = ti.get("sma_50")
        sma200 = ti.get("sma_200")
        above_50 = "\U0001f7e2" if (sma50 is not None and close > sma50) else "\U0001f534" if (sma50 is not None and close < sma50) else "\u2014"
        above_200 = "\U0001f7e2" if (sma200 is not None and close > sma200) else "\U0001f534" if (sma200 is not None and close < sma200) else "\u2014"
        macd_hist = ti["macd_hist"]
        macd_label = "\U0001f7e2 Bullish" if macd_hist > 0 else "\U0001f534 Bearish"
        ti_preview = f"RSI {rsi:.1f} ({rsi_label}) \u00b7 SMA50 {above_50} \u00b7 SMA200 {above_200} \u00b7 MACD {macd_label}"
        ti_rows = f"""
        <div class="ti-grid">
            <div class="ti-item"><span class="ti-label">RSI (14)</span><span class="ti-value">{rsi:.1f}</span><span class="ti-sub">{rsi_label}</span></div>
            <div class="ti-item"><span class="ti-label">vs SMA 50</span><span class="ti-value">{fmt_price(sma50) if sma50 else "N/A"}</span><span class="ti-sub">{above_50}</span></div>
            <div class="ti-item"><span class="ti-label">vs SMA 200</span><span class="ti-value">{fmt_price(sma200) if sma200 else "N/A"}</span><span class="ti-sub">{above_200}</span></div>
            <div class="ti-item"><span class="ti-label">MACD Hist</span><span class="ti-value">{macd_hist:.4f}</span><span class="ti-sub">{macd_label}</span></div>
        </div>"""
    else:
        ti_preview = "Not enough data to compute (need 1yr+)."

    # Additional stats
    stats_rows = f"""
    <div class="stats-grid">
        <div class="stat-item"><span class="stat-label">Sector</span><span class="stat-value">{h(stock.get("sector", "N/A"))}</span></div>
        <div class="stat-item"><span class="stat-label">Industry</span><span class="stat-value">{h(stock.get("industry", "N/A"))}</span></div>
        <div class="stat-item"><span class="stat-label">Market Cap</span><span class="stat-value">{fmt_large(stock.get("market_cap"))}</span></div>
        <div class="stat-item"><span class="stat-label">52W High</span><span class="stat-value">{fmt_price(stock.get("52w_high"))}</span></div>
        <div class="stat-item"><span class="stat-label">52W Low</span><span class="stat-value">{fmt_price(stock.get("52w_low"))}</span></div>
        <div class="stat-item"><span class="stat-label">P/E Ratio</span><span class="stat-value">{pe_str}</span></div>
    </div>"""

    # Source badges
    badge_html = ""
    for src in source_breakdown:
        if src["avg"] >= 0.3:
            b_class = "bullish"
            b_emoji = "\U0001f7e2"
        elif src["avg"] <= -0.3:
            b_class = "bearish"
            b_emoji = "\U0001f534"
        else:
            b_class = "neutral"
            b_emoji = "\u26aa"
        badge_html += (
            f'<span class="source-badge {b_class}">'
            f'{b_emoji} {src["source"]}'
            f' <span class="badge-meta">w={src["weight"]:.1f} \u00b7 {src["count"]} art.</span>'
            f"</span> "
        )

    # Source health
    parts = []
    for s, n in sorted(source_stats.items()):
        parts.append(f"{s} ({n})")
    sources_str = " \u00b7 ".join(parts)

    # ── SmartScore display ──
    smartscore_val = result.get("smartscore")
    ss_html = ""
    if smartscore_val is not None:
        ss = result.get("smartscore_components", {})
        ss_components = ss
        ss_history = result.get("smartscore_history", [])
        ss_signal_raw = result.get("smartscore_signal", "NEUTRAL")
        # Strip trailing emoji — the raw string is "BULLISH 🟢" etc.
        ss_signal = ss_signal_raw.rstrip(" 🟢🔴⚪") if isinstance(ss_signal_raw, str) else "NEUTRAL"
        ss_color = "#22b573" if ss_signal == "BULLISH" else "#f85149" if ss_signal == "BEARISH" else "#8891a0"
        # SVG icon for the signal
        ss_icon = _emoji_to_icon.get(result.get("smartscore_emoji", "⚪"), _ICON["neutral"])

        # Component mini-bars
        def _pct(v):
            return max(0, min(100, v * 100))

        comp_bars = ""
        comps = [
            ("Recency", ss_components.get("s_recency", 0.5)),
            ("Events", ss_components.get("s_events", 0.5)),
            ("Breadth", ss_components.get("s_breadth", 0.5)),
            ("Volume", ss_components.get("s_volume", 0.5)),
        ]
        for label, val in comps:
            pct = _pct(val)
            comp_bars += f"""
            <div class="ss-comp">
                <div class="ss-comp-label">{label}</div>
                <div class="ss-comp-track">
                    <div class="ss-comp-fill" style="width:{pct:.0f}%;background:{ss_color};"></div>
                </div>
                <div class="ss-comp-val">{pct:.0f}%</div>
            </div>"""

        sparkline_svg = render_sparkline(ss_history, width=140, height=28, color=ss_color)

        ss_html = f"""
        <div class="ss-section">
            <div class="ss-main">
                <div class="ss-score" style="color:{ss_color}">{smartscore_val:.0f}</div>
                <div class="ss-label">SmartScore</div>
                <div class="ss-qual">{ss_icon} {ss_signal}</div>
            </div>
            <div class="ss-comps">
                {comp_bars}
            </div>
            <div class="ss-spark">
                <div class="ss-spark-label">Trend</div>
                {sparkline_svg}
            </div>
        </div>"""

    # News items
    news_html = ""
    for item, scores in zip(news_items, headline_scores):
        emoji = get_sentiment_emoji(scores["compound"])
        if scores["compound"] >= 0.3:
            s_label = "Positive"
            s_class = "bullish"
        elif scores["compound"] <= -0.3:
            s_label = "Negative"
            s_class = "bearish"
        else:
            s_label = "Neutral"
            s_class = "neutral"

        title_html = (
            f'<a href="{h_attr(item.get("url", ""))}" target="_blank" rel="noopener">{h(item.get("title", ""))}</a>'
            if item.get("url")
            else h(item.get("title", ""))
        )
        meta_parts = []
        if item.get("source"):
            meta_parts.append(f"\U0001f4e1 {h(item['source'])}")
        if item.get("date"):
            meta_parts.append(f"\U0001f4c5 {h(item['date'][:10])}")
        if item.get("source") == "Reddit" and item.get("author"):
            sub = f"r/{h(item['subreddit'])}/" if item.get("subreddit") else ""
            meta_parts.append(f"by u/{h(item['author'])} on {sub}Reddit")
        body = ""
        if item.get("source") != "Reddit" and item.get("body"):
            body = h(item["body"][:200])

        news_html += f"""
        <div class="news-item">
            <div class="news-emoji">{emoji}</div>
            <div class="news-content">
                <div class="news-title">{title_html}</div>
                <div class="news-meta">{' · '.join(meta_parts)} <span class="sentiment-tag {s_class}">{s_label}</span></div>
                {'<div class="news-body">' + body + '</div>' if body else ''}
            </div>
        </div>"""

    # Source badges section (pre-computed to avoid nested f-string issues)
    badge_section = f'<div class="badge-wrap">{badge_html}</div>' if badge_html else ""
    source_health = f'<div class="source-health">{_ICON["wifi"]} Sources: {sources_str}</div>' if sources_str else ""
    ti_section = f'<div class="ti-preview">{ti_preview}</div>' if ti_preview else ""

    # ponytail: random CSP nonce for the auto-height script blocks
    # any injected inline scripts from RSS/Reddit content
    _nonce = secrets.token_urlsafe(16)
    auto_height_script = f"""<script nonce="{_nonce}">
(function(){{var o=document.referrer?new URL(document.referrer).origin:'*';function h(){{var d=document.body.scrollHeight;parent.postMessage({{type:'streamlit:setFrameHeight',height:d}},o);}}window.addEventListener('load',h);window.addEventListener('resize',h);}})();
</script>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'nonce-{_nonce}'; style-src 'unsafe-inline'; font-src fonts.gstatic.com fonts.googleapis.com; img-src *; connect-src *;">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    .sr-only {{ position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }}
    .icon {{ vertical-align: middle; margin-right: 0.15rem; }}
    body {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        font-display: swap;
        background: #0a0b0f; color: #f0f2f5;
        padding: 0; line-height: 1.5;
    }}
    .dashboard {{ max-width: 820px; margin: 0 auto; padding: 0; }}
    ::-webkit-scrollbar {{ width: 6px; }}
    ::-webkit-scrollbar-track {{ background: #0a0b0f; }}
    ::-webkit-scrollbar-thumb {{ background: #2a2e3a; border-radius: 3px; }}

    /* Cards */
    .card {{
        background: #15181f;
        border: 1px solid #2a2e3a;
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.25);
    }}
    .card-title {{
        font-size: 0.8rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.08em; color: #8891a0; margin-bottom: 0.75rem;
    }}

    /* Company header */
    .company-header {{
        display: flex; justify-content: space-between; align-items: flex-start;
        margin-bottom: 1rem;
    }}
    .company-name {{ font-size: 1.35rem; font-weight: 700; }}
    .company-ticker {{ color: #8891a0; font-size: 0.9rem; }}

    /* Price grid */
    .price-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; }}
    .price-cell {{
        background: #1a1d26;
        border: 1px solid #2a2e3a;
        border-radius: 10px;
        padding: 0.75rem 1rem;
    }}
    .price-cell .label {{ font-size: 0.78rem; color: #8891a0; margin-bottom: 0.25rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    .price-cell .value {{ font-size: 1.1rem; font-weight: 700; }}
    .price-cell .value.price-main {{ font-size: 2rem; }}
    .price-cell .delta {{ font-size: 0.9rem; font-weight: 600; }}
    .price-cell .delta.up {{ color: #22b573; }}
    .price-cell .delta.down {{ color: #f85149; }}

    /* Sentiment hero */
    .sentiment-row {{ display: grid; grid-template-columns: 1fr auto; gap: 1rem; align-items: center; margin-bottom: 0.75rem; }}
    .sentiment-hero {{ font-size: 1.2rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.2; }}
    .sentiment-hero.bullish {{ background: linear-gradient(135deg,#22b573,#0d9488); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
    .sentiment-hero.bearish {{ background: linear-gradient(135deg,#f85149,#da3633); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
    .sentiment-hero.neutral {{ background: linear-gradient(135deg,#8891a0,#6b7280); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
    .sentiment-caption {{ font-size: 0.8rem; color: #8891a0; }}
    .confidence-box {{ text-align: center; }}
    .confidence-num {{ font-size: 1.2rem; font-weight: 800; letter-spacing: -0.03em; line-height: 1; background: linear-gradient(135deg,#22b573,#0d9488); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
    .confidence-label {{ font-size: 0.75rem; color: #8891a0; text-transform: uppercase; letter-spacing: 0.05em; }}

    /* Recommendation callout */
    .rec-callout {{
        display: inline-flex; align-items: center; gap: 0.5rem;
        padding: 0.5rem 1rem; border-radius: 8px; font-weight: 600; font-size: 0.85rem;
        margin-top: 0.5rem;
    }}
    .rec-callout.bullish {{ background: rgba(34,181,115,0.12); color: #2ecc71; border: 1px solid rgba(34,181,115,0.25); }}
    .rec-callout.bearish {{ background: rgba(248,81,73,0.12); color: #ff6b6b; border: 1px solid rgba(248,81,73,0.25); }}
    .rec-callout.neutral {{ background: rgba(136,145,160,0.1); color: #8891a0; border: 1px solid rgba(136,145,160,0.2); }}

    /* Source badges */
    .badge-wrap {{ margin-top: 0.75rem; }}
    .source-badge {{
        display: inline-flex; align-items: center; gap: 0.35rem;
        padding: 0.3rem 0.75rem; border-radius: 100px;
        font-size: 0.8rem; font-weight: 500;
        border: 1px solid #2a2e3a;
        background: rgba(255,255,255,0.06);
        margin: 0.15rem; white-space: nowrap;
    }}
    .source-badge.bullish {{ border-color: rgba(34,181,115,0.35); color: #2ecc71; }}
    .source-badge.bearish {{ border-color: rgba(248,81,73,0.35); color: #ff6b6b; }}
    .source-badge.neutral {{ border-color: rgba(136,145,160,0.15); color: #8891a0; }}
    .badge-meta {{ opacity: 0.7; color: #8891a0; }}
    .source-health {{ font-size: 0.8rem; color: #8891a0; margin-top: 0.5rem; }}

    /* SmartScore section */
    .ss-section {{
        display: flex; align-items: stretch; gap: 1rem;
        margin: 0.75rem 0 0.5rem 0;
        padding: 0.75rem;
        background: linear-gradient(135deg, rgba(21,24,31,0.8), rgba(26,29,38,0.6));
        border: 1px solid #2a2e3a;
        border-radius: 10px;
    }}
    .ss-main {{ text-align: center; min-width: 72px; flex-shrink: 0; }}
    .ss-score {{ font-size: 1.5rem; font-weight: 800; letter-spacing: -0.03em; line-height: 1; }}
    .ss-label {{ font-size: 0.72rem; color: #8891a0; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 0.2rem; }}
    .ss-qual {{ font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 0.1rem; }}
    .ss-comps {{ flex: 1; display: flex; flex-direction: column; gap: 0.3rem; justify-content: center; }}
    .ss-comp {{ display: flex; align-items: center; gap: 0.4rem; }}
    .ss-comp-label {{ font-size: 0.72rem; color: #8891a0; min-width: 3.2rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    .ss-comp-track {{ flex: 1; height: 4px; background: #1a1d26; border-radius: 2px; overflow: hidden; }}
    .ss-comp-fill {{ height: 100%; border-radius: 2px; transition: width 0.3s ease; }}
    .ss-comp-val {{ font-size: 0.7rem; color: #8891a0; min-width: 2rem; text-align: right; }}
    .ss-spark {{ display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.25rem; min-width: 100px; }}
    .ss-spark-label {{ font-size: 0.65rem; color: #8891a0; text-transform: uppercase; letter-spacing: 0.06em; }}

    /* Distribution bar */
    .dist-bar {{
        display: flex; height: 8px; border-radius: 4px; overflow: hidden; margin: 0.5rem 0;
    }}
    .dist-bar .pos {{ background: #22b573; }}
    .dist-bar .neg {{ background: #f85149; }}
    .dist-bar .neu {{ background: #4b5563; }}
    .dist-labels {{ display: flex; justify-content: space-around; font-size: 0.85rem; }}
    .dist-labels span {{ display: flex; align-items: center; gap: 0.35rem; }}
    .dist-labels .pos {{ color: #2ecc71; }}
    .dist-labels .neg {{ color: #ff6b6b; }}
    .dist-labels .neu {{ color: #8891a0; }}

    /* News items */
    .news-item {{
        display: flex; gap: 0.75rem; padding: 0.75rem 0;
        border-bottom: 1px solid rgba(42,46,58,0.4);
    }}
    .news-item:last-child {{ border-bottom: none; }}
    .news-emoji {{ font-size: 1.2rem; flex-shrink: 0; margin-top: 0.15rem; }}
    .news-content {{ flex: 1; min-width: 0; }}
    .news-title {{ font-size: 0.9rem; font-weight: 600; line-height: 1.4; }}
    .news-title a {{ color: #f0f2f5; text-decoration: none; }}
    .news-title a:hover {{ color: #22b573; text-decoration: underline; }}
    .news-meta {{ font-size: 0.8rem; color: #8891a0; margin-top: 0.25rem; display: flex; flex-wrap: wrap; gap: 0.25rem; align-items: center; }}
    .news-body {{ font-size: 0.85rem; color: #8891a0; margin-top: 0.25rem; line-height: 1.5; }}
    .sentiment-tag {{
        display: inline-block; padding: 0.1rem 0.45rem; border-radius: 100px;
        font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.03em;
    }}
    .sentiment-tag.bullish {{ background: rgba(34,181,115,0.15); color: #22b573; }}
    .sentiment-tag.bearish {{ background: rgba(248,81,73,0.15); color: #f85149; }}
    .sentiment-tag.neutral {{ background: rgba(136,145,160,0.15); color: #8891a0; }}

    /* Stats grid */
    .stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; }}
    .stat-item {{ padding: 0.5rem 0; }}
    .stat-label {{ font-size: 0.78rem; color: #8891a0; text-transform: uppercase; letter-spacing: 0.04em; }}
    .stat-value {{ font-size: 0.9rem; font-weight: 500; display: block; margin-top: 0.15rem; }}

    /* Technical indicators */
    .ti-preview {{ font-size: 0.85rem; color: #8891a0; margin-bottom: 0.75rem; }}
    .ti-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; }}
    .ti-item {{ padding: 0.5rem; text-align: center; }}
    .ti-label {{ font-size: 0.78rem; color: #8891a0; text-transform: uppercase; letter-spacing: 0.04em; display: block; }}
    .ti-value {{ font-size: 1rem; font-weight: 700; display: block; margin-top: 0.15rem; }}
    .ti-sub {{ font-size: 0.8rem; color: #8891a0; display: block; margin-top: 0.1rem; }}

    /* Cross-over badges */
    .cross-badge {{
        display: inline-block; padding: 0.25rem 0.65rem; border-radius: 6px;
        font-size: 0.8rem; font-weight: 600; margin-right: 0.5rem; margin-top: 0.5rem;
    }}
    .cross-badge.bullish {{ background: rgba(34,181,115,0.12); color: #2ecc71; border: 1px solid rgba(34,181,115,0.25); }}
    .cross-badge.bearish {{ background: rgba(248,81,73,0.12); color: #ff6b6b; border: 1px solid rgba(248,81,73,0.25); }}

    /* Volume spike badges */
    .spike-badge {{
        display: inline-block; padding: 0.25rem 0.65rem; border-radius: 6px;
        font-size: 0.8rem; font-weight: 600;
    }}
    .spike-badge.huge {{ background: rgba(248,81,73,0.15); color: #ff6b6b; border: 1px solid rgba(248,81,73,0.3); }}
    .spike-badge.high {{ background: rgba(245,158,11,0.15); color: #fbbf24; border: 1px solid rgba(245,158,11,0.3); }}
    .spike-badge.mid {{ background: rgba(34,181,115,0.1); color: #2ecc71; border: 1px solid rgba(34,181,115,0.2); }}

    /* Proximity badges */
    .prox-badge {{
        display: inline-block; padding: 0.2rem 0.55rem; border-radius: 6px;
        font-size: 0.78rem; font-weight: 500; margin-top: 0.35rem;
    }}
    .prox-badge.high {{ background: rgba(248,81,73,0.12); color: #ff6b6b; border: 1px solid rgba(248,81,73,0.2); }}
    .prox-badge.mid {{ background: rgba(34,181,115,0.1); color: #2ecc71; border: 1px solid rgba(34,181,115,0.2); }}
    .prox-badge.low {{ background: rgba(136,145,160,0.1); color: #8891a0; border: 1px solid rgba(136,145,160,0.2); }}

    /* Track record accuracy */
    .acc-row {{ display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }}
    .acc-circle {{
        width: 64px; height: 64px; border-radius: 50%; display: flex;
        align-items: center; justify-content: center;
        font-size: 1.05rem; font-weight: 800; flex-shrink: 0;
    }}
    .acc-circle.good {{ background: rgba(34,181,115,0.15); color: #2ecc71; border: 2px solid rgba(34,181,115,0.4); }}
    .acc-circle.ok {{ background: rgba(245,158,11,0.15); color: #fbbf24; border: 2px solid rgba(245,158,11,0.4); }}
    .acc-circle.poor {{ background: rgba(248,81,73,0.12); color: #ff6b6b; border: 2px solid rgba(248,81,73,0.3); }}
    .acc-num {{ font-weight: 600; font-size: 0.95rem; }}
    .acc-desc {{ font-size: 0.8rem; color: #8891a0; }}

    /* FII/DII grid */
    .fii-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; }}
    .fii-item {{ padding: 0.75rem; text-align: center; border-radius: 8px; border: 1px solid #2a2e3a; background: #1a1d26; }}
    .fii-item.bearish {{ border-color: rgba(248,81,73,0.25); }}
    .fii-label {{ font-size: 0.75rem; color: #8891a0; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.35rem; }}
    .fii-value {{ font-size: 1.05rem; font-weight: 700; }}
    .fii-item.bearish .fii-value {{ color: #ff6b6b; }}
    .fii-item:not(.bearish) .fii-value {{ color: #2ecc71; }}
    .fii-sub {{ font-size: 0.78rem; color: #8891a0; margin-top: 0.2rem; }}

    /* Responsive */
    @media (max-width: 640px) {{
        .price-grid {{ grid-template-columns: repeat(2, 1fr); }}
        .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
        .ti-grid {{ grid-template-columns: repeat(2, 1fr); }}
        .fii-grid {{ grid-template-columns: 1fr; }}
        .sentiment-row {{ grid-template-columns: 1fr; text-align: center; }}
        .card {{ padding: 0.85rem; }}
    }}
</style>
</head>
<body>
<div class="dashboard" role="region" aria-label="NSE Stock Analysis Dashboard for {h(ticker)}">
    <h1 class="sr-only">NSE Stock Analysis Dashboard for {h(ticker)}</h1>

    <!-- ═══ PRICE CARD ═══ -->
    <div class="card">
        <div class="card-title">{_ICON["trending_up"]} Live Price</div>
        <div class="company-header">
            <div>
                <div class="company-name">{h(company_name)}</div>
                <div class="company-ticker">{h(ticker)} · NSE</div>
                {f'<span class="prox-badge {proximity_class}">{h(proximity_msg)}</span>' if proximity_msg else ''}
            </div>
        </div>
        <div class="price-grid">
            <div class="price-cell">
                <div class="label">{h(ticker[:6])}</div>
                <div class="value price-main">{fmt_price(price)}</div>
                <div class="delta {'up' if isinstance(change_val, (int, float)) and change_val >= 0 else 'down' if isinstance(change_val, (int, float)) else 'neutral'}">{fmt_delta(change_val) if isinstance(change_val, (int, float)) else "N/A"} ({fmt_delta(change_pct) if isinstance(change_pct, (int, float)) else "N/A"}%)</div>
            </div>
            <div class="price-cell">
                <div class="label">Day Range</div>
                <div class="value" style="font-size:0.9rem">{day_range}</div>
            </div>
            <div class="price-cell">
                <div class="label">Volume{vol_spike_html}</div>
                <div class="value" style="font-size:1rem">{volume}</div>
            </div>
            <div class="price-cell">
                <div class="label">P/E Ratio</div>
                <div class="value" style="font-size:1rem">{pe_str}</div>
            </div>
        </div>
    </div>

    <!-- ═══ SENTIMENT CARD ═══ -->
    <div class="card">
        <div class="card-title">{_ICON["newspaper"]} News Sentiment Analysis</div>
        <div class="sentiment-row">
            <div>
                <div class="sentiment-hero {sent_class}">{primary_emoji_svg} {primary_signal}</div>
                <div class="sentiment-caption">Based on {len(news_items)} articles \u00b7 Weighted across {len(source_breakdown)} sources</div>
                <div class="rec-callout {sent_class}">{rec_icon} {rec_text} \u2014 {rec_detail}</div>
            </div>
            <div class="confidence-box">
                <div class="confidence-num">{confidence_pct:.0f}%</div>
                <div class="confidence-label">Weighted Confidence</div>
            </div>
        </div>
        {ss_html}
        {badge_section}
        {source_health}
    </div>

    <!-- ═══ SENTIMENT DISTRIBUTION ═══ -->
    <div class="card">
        <div class="card-title">{_ICON["bar_chart"]} Sentiment Distribution</div>
        <div class="dist-bar">
            <div class="pos" style="width:{pos_pct:.1f}%"></div>
            <div class="neu" style="width:{neu_pct:.1f}%"></div>
            <div class="neg" style="width:{neg_pct:.1f}%"></div>
        </div>
        <div class="dist-labels">
            <span class="pos">{_ICON["dot_green"]} Positive: {pos_pct:.0f}%</span>
            <span class="neu">{_ICON["dot_grey"]} Neutral: {neu_pct:.0f}%</span>
            <span class="neg">{_ICON["dot_red"]} Negative: {neg_pct:.0f}%</span>
        </div>
    </div>

    <!-- ═══ NEWS HEADLINES ═══ -->
    <div class="card">
        <div class="card-title">{_ICON["file_text"]} Recent News ({len(news_items)} articles)</div>
        {news_html}
    </div>

    <!-- ═══ ADDITIONAL STATS ═══ -->
    <div class="card">
        <div class="card-title">{_ICON["layout"]} Additional Stats</div>
        {stats_rows}
    </div>

    <!-- ═══ TECHNICAL INDICATORS ═══ -->
    <div class="card">
        <div class="card-title">{_ICON["signal"]} Technical Indicators</div>
        {ti_section}
        {ti_rows}
        <div style="margin-top:0.5rem">{cross_50_html}{cross_200_html}</div>
    </div>

{acc_html}

{fii_html}

</div>
{auto_height_script}
</body>
</html>"""
