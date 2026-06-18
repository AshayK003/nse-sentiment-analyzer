"""Pure HTML/CSS dashboard renderer for NSE Sentiment Analyzer.

Replaces Streamlit display widgets with a custom premium template
rendered via st.components.v1.html().
"""

import html
import json
import secrets
from datetime import datetime


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


def render_dashboard(result, ticker, company_name, technical_indicators=None,
                     track_record=None, fii_dii_data=None):
    """Return a complete premium HTML dashboard as a string."""
    stock = result["stock_data"]
    news_items = result["news_items"]
    headline_scores = result["headline_scores"]
    signal = result["signal"]
    avg_compound = result["avg_compound"]
    primary_signal = result.get("weighted_signal", signal)
    primary_compound = result.get("blended_compound", avg_compound)
    primary_emoji = result.get("weighted_emoji", result["signal_emoji"])
    source_breakdown = result.get("source_breakdown", [])
    source_stats = result.get("source_stats", {})

    # Sentiment class
    if "BULLISH" in str(primary_signal):
        sent_class = "bullish"
        rec_text = "BUY / HOLD"
        rec_detail = "Positive sentiment dominates"
        rec_icon = "\u2705"
    elif "BEARISH" in str(primary_signal):
        sent_class = "bearish"
        rec_text = "CAUTION / SELL"
        rec_detail = "Negative sentiment detected"
        rec_icon = "\u26a0\ufe0f"
    else:
        sent_class = "neutral"
        rec_text = "HOLD"
        rec_detail = "Mixed or neutral sentiment"
        rec_icon = "\U0001f4a4"

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
        if ti.get("sma50_cross") == "bullish":
            cross_50_html = '<span class="cross-badge bullish">🟢 SMA50 bullish crossover</span>'
        elif ti.get("sma50_cross") == "bearish":
            cross_50_html = '<span class="cross-badge bearish">🔴 SMA50 bearish crossover</span>'
        if ti.get("sma200_cross") == "bullish":
            cross_200_html = '<span class="cross-badge bullish">🟢 SMA200 bullish crossover</span>'
        elif ti.get("sma200_cross") == "bearish":
            cross_200_html = '<span class="cross-badge bearish">🔴 SMA200 bearish crossover</span>'

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
    <div class="card-title">📊 Signal Track Record</div>
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
        fii_html = f"""<div class="card">
    <div class="card-title">🏦 Institutional Flow ({fi.get("date", "Latest")})</div>
    <div class="fii-grid">
        <div class="fii-item {'bearish' if fi['fii_net'] < 0 else ''}">
            <div class="fii-label">FII / FPI</div>
            <div class="fii-value">{fmt_large(fi['fii_net'])}</div>
            <div class="fii-sub">{fi['fii_action']}</div>
        </div>
        <div class="fii-item {'bearish' if fi['dii_net'] < 0 else ''}">
            <div class="fii-label">DII</div>
            <div class="fii-value">{fmt_large(fi['dii_net'])}</div>
            <div class="fii-sub">{fi['dii_action']}</div>
        </div>
        <div class="fii-item {'bearish' if comb < 0 else ''}">
            <div class="fii-label">Combined Net</div>
            <div class="fii-value">{fmt_large(comb)}</div>
            <div class="fii-sub">{'🟢 Institutions net buying' if comb >= 0 else '🔴 Institutions net selling'}</div>
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
    source_health = f'<div class="source-health">📡 Sources: {sources_str}</div>' if sources_str else ""
    ti_section = f'<div class="ti-preview">{ti_preview}</div>' if ti_preview else ""

    # ponytail: random CSP nonce for the auto-height script blocks
    # any injected inline scripts from RSS/Reddit content
    _nonce = secrets.token_urlsafe(16)
    auto_height_script = f"""<script nonce="{_nonce}">
(function(){{var o=document.referrer?new URL(document.referrer).origin:'*';function h(){{var d=document.body.scrollHeight;parent.postMessage({{type:'streamit:setFrameHeight',height:d}},o);}}window.addEventListener('load',h);window.addEventListener('resize',h);}})();
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
        font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.08em; color: #8891a0; margin-bottom: 0.75rem;
    }}

    /* Company header */
    .company-header {{
        display: flex; justify-content: space-between; align-items: flex-start;
        margin-bottom: 1rem;
    }}
    .company-name {{ font-size: 1.1rem; font-weight: 700; }}
    .company-ticker {{ color: #8891a0; font-size: 0.85rem; }}

    /* Price grid */
    .price-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; }}
    .price-cell {{
        background: #1a1d26;
        border: 1px solid #2a2e3a;
        border-radius: 10px;
        padding: 0.75rem 1rem;
    }}
    .price-cell .label {{ font-size: 0.72rem; color: #8891a0; margin-bottom: 0.25rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    .price-cell .value {{ font-size: 1.1rem; font-weight: 700; }}
    .price-cell .delta {{ font-size: 0.85rem; font-weight: 600; }}
    .price-cell .delta.up {{ color: #22b573; }}
    .price-cell .delta.down {{ color: #f85149; }}

    /* Sentiment hero */
    .sentiment-row {{ display: grid; grid-template-columns: 1fr auto; gap: 1rem; align-items: center; margin-bottom: 0.75rem; }}
    .sentiment-hero {{ font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.2; }}
    .sentiment-hero.bullish {{ background: linear-gradient(135deg,#22b573,#0d9488); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
    .sentiment-hero.bearish {{ background: linear-gradient(135deg,#f85149,#da3633); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
    .sentiment-hero.neutral {{ background: linear-gradient(135deg,#8891a0,#6b7280); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
    .sentiment-caption {{ font-size: 0.8rem; color: #8891a0; }}
    .confidence-box {{ text-align: center; }}
    .confidence-num {{ font-size: 2rem; font-weight: 800; letter-spacing: -0.03em; line-height: 1; background: linear-gradient(135deg,#22b573,#0d9488); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
    .confidence-label {{ font-size: 0.72rem; color: #8891a0; text-transform: uppercase; letter-spacing: 0.05em; }}

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
        font-size: 0.75rem; font-weight: 500;
        border: 1px solid #2a2e3a;
        background: rgba(255,255,255,0.06);
        margin: 0.15rem; white-space: nowrap;
    }}
    .source-badge.bullish {{ border-color: rgba(34,181,115,0.35); color: #2ecc71; }}
    .source-badge.bearish {{ border-color: rgba(248,81,73,0.35); color: #ff6b6b; }}
    .source-badge.neutral {{ border-color: rgba(136,145,160,0.15); color: #8891a0; }}
    .badge-meta {{ opacity: 0.7; color: #8891a0; }}
    .source-health {{ font-size: 0.75rem; color: #8891a0; margin-top: 0.5rem; }}

    /* Distribution bar */
    .dist-bar {{
        display: flex; height: 8px; border-radius: 4px; overflow: hidden; margin: 0.5rem 0;
    }}
    .dist-bar .pos {{ background: #22b573; }}
    .dist-bar .neg {{ background: #f85149; }}
    .dist-bar .neu {{ background: #4b5563; }}
    .dist-labels {{ display: flex; justify-content: space-around; font-size: 0.8rem; }}
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
    .news-meta {{ font-size: 0.75rem; color: #8891a0; margin-top: 0.25rem; display: flex; flex-wrap: wrap; gap: 0.25rem; align-items: center; }}
    .news-body {{ font-size: 0.8rem; color: #8891a0; margin-top: 0.25rem; line-height: 1.4; }}
    .sentiment-tag {{
        display: inline-block; padding: 0.1rem 0.45rem; border-radius: 100px;
        font-size: 0.65rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.03em;
    }}
    .sentiment-tag.bullish {{ background: rgba(34,181,115,0.15); color: #22b573; }}
    .sentiment-tag.bearish {{ background: rgba(248,81,73,0.15); color: #f85149; }}
    .sentiment-tag.neutral {{ background: rgba(136,145,160,0.15); color: #8891a0; }}

    /* Stats grid */
    .stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; }}
    .stat-item {{ padding: 0.5rem 0; }}
    .stat-label {{ font-size: 0.72rem; color: #8891a0; text-transform: uppercase; letter-spacing: 0.04em; }}
    .stat-value {{ font-size: 0.9rem; font-weight: 500; display: block; margin-top: 0.15rem; }}

    /* Technical indicators */
    .ti-preview {{ font-size: 0.85rem; color: #8891a0; margin-bottom: 0.75rem; }}
    .ti-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; }}
    .ti-item {{ padding: 0.5rem; text-align: center; }}
    .ti-label {{ font-size: 0.72rem; color: #8891a0; text-transform: uppercase; letter-spacing: 0.04em; display: block; }}
    .ti-value {{ font-size: 1rem; font-weight: 700; display: block; margin-top: 0.15rem; }}
    .ti-sub {{ font-size: 0.75rem; color: #8891a0; display: block; margin-top: 0.1rem; }}

    /* Cross-over badges */
    .cross-badge {{
        display: inline-block; padding: 0.25rem 0.65rem; border-radius: 6px;
        font-size: 0.75rem; font-weight: 600; margin-right: 0.5rem; margin-top: 0.5rem;
    }}
    .cross-badge.bullish {{ background: rgba(34,181,115,0.12); color: #2ecc71; border: 1px solid rgba(34,181,115,0.25); }}
    .cross-badge.bearish {{ background: rgba(248,81,73,0.12); color: #ff6b6b; border: 1px solid rgba(248,81,73,0.25); }}

    /* Volume spike badges */
    .spike-badge {{
        display: inline-block; padding: 0.25rem 0.65rem; border-radius: 6px;
        font-size: 0.75rem; font-weight: 600;
    }}
    .spike-badge.huge {{ background: rgba(248,81,73,0.15); color: #ff6b6b; border: 1px solid rgba(248,81,73,0.3); }}
    .spike-badge.high {{ background: rgba(245,158,11,0.15); color: #fbbf24; border: 1px solid rgba(245,158,11,0.3); }}
    .spike-badge.mid {{ background: rgba(34,181,115,0.1); color: #2ecc71; border: 1px solid rgba(34,181,115,0.2); }}

    /* Proximity badges */
    .prox-badge {{
        display: inline-block; padding: 0.2rem 0.55rem; border-radius: 6px;
        font-size: 0.7rem; font-weight: 500; margin-top: 0.35rem;
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
    .fii-label {{ font-size: 0.7rem; color: #8891a0; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.35rem; }}
    .fii-value {{ font-size: 1.05rem; font-weight: 700; }}
    .fii-item.bearish .fii-value {{ color: #ff6b6b; }}
    .fii-item:not(.bearish) .fii-value {{ color: #2ecc71; }}
    .fii-sub {{ font-size: 0.72rem; color: #8891a0; margin-top: 0.2rem; }}

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
<div class="dashboard">

    <!-- ═══ PRICE CARD ═══ -->
    <div class="card">
        <div class="card-title">\U0001f4c8 Live Price</div>
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
                <div class="value">{fmt_price(price)}</div>
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
        <div class="card-title">\U0001f4f0 News Sentiment Analysis</div>
        <div class="sentiment-row">
            <div>
                <div class="sentiment-hero {sent_class}">{primary_emoji} {primary_signal}</div>
                <div class="sentiment-caption">Based on {len(news_items)} articles \u00b7 Weighted across {len(source_breakdown)} sources</div>
                <div class="rec-callout {sent_class}">{rec_icon} {rec_text} \u2014 {rec_detail}</div>
            </div>
            <div class="confidence-box">
                <div class="confidence-num">{confidence_pct:.0f}%</div>
                <div class="confidence-label">Weighted Confidence</div>
            </div>
        </div>
        {badge_section}
        {source_health}
    </div>

    <!-- ═══ SENTIMENT DISTRIBUTION ═══ -->
    <div class="card">
        <div class="card-title">\U0001f4c8 Sentiment Distribution</div>
        <div class="dist-bar">
            <div class="pos" style="width:{pos_pct:.1f}%"></div>
            <div class="neu" style="width:{neu_pct:.1f}%"></div>
            <div class="neg" style="width:{neg_pct:.1f}%"></div>
        </div>
        <div class="dist-labels">
            <span class="pos">\U0001f7e2 Positive: {pos_pct:.0f}%</span>
            <span class="neu">\u26aa Neutral: {neu_pct:.0f}%</span>
            <span class="neg">\U0001f534 Negative: {neg_pct:.0f}%</span>
        </div>
    </div>

    <!-- ═══ NEWS HEADLINES ═══ -->
    <div class="card">
        <div class="card-title">\U0001f4cb Recent News ({len(news_items)} articles)</div>
        {news_html}
    </div>

    <!-- ═══ ADDITIONAL STATS ═══ -->
    <div class="card">
        <div class="card-title">\U0001f4ca Additional Stats</div>
        {stats_rows}
    </div>

    <!-- ═══ TECHNICAL INDICATORS ═══ -->
    <div class="card">
        <div class="card-title">📈 Technical Indicators</div>
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
