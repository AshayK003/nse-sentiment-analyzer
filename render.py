"""Pure HTML/CSS dashboard renderer for NSE Sentiment Analyzer.

Replaces Streamlit display widgets with a custom premium template
rendered via st.components.v1.html().
"""

from pathlib import Path

import html
import logging
import math
import secrets
import itertools

logger = logging.getLogger(__name__)

# ─── Bayesian source calibration ───
# Shows per-source Beta distributions from user voting data.
# Loaded once per dashboard render — no DB impact per ticker.
from persistence import load_source_accuracy
from indicators import detect_volume_spike

# ─── Inline SVG icons (Lucide, MIT-licensed, stroke-based) ───
# Inline SVGs avoid a 100KB+ icon library for ~15 icons
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

# Dashboard CSS — loaded once at module init
_DASHBOARD_CSS = (Path(__file__).parent / "static" / "dashboard.css").read_text(encoding="utf-8")

# Counter for unique sparkline gradient IDs
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
    """Escape a string for safe HTML output (content or attribute)."""
    if s is None:
        return ""
    return html.escape(str(s), quote=True).replace("'", "&#39;")


def _is_valid_num(val):
    """Return True if val is a finite number (not NaN, not None)."""
    if isinstance(val, (int, float)):
        return not math.isnan(val) and math.isfinite(val)
    return False


def _pct(v):
    """Map a 0-1 ratio to a 0-100 percentage, clamped."""
    return max(0, min(100, v * 100))


def _session_quality_badge():
    """Return a session quality warning badge based on current IST.
    
    Returns empty string during optimal trading windows.
    """
    from datetime import datetime, timezone, timedelta
    ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    h, m = ist.hour, ist.minute
    mins_since_open = (h - 9) * 60 + (m - 15)  # market opens 9:15 IST
    
    if 135 <= mins_since_open < 225:  # 11:30-13:00 lunch lull
        return '<span class="session-badge warn"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg> Lunch lull — sentiment less reliable</span>'
    if mins_since_open < 15:  # 9:15-9:30 opening volatility
        return '<span class="session-badge info"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg> Opening volatility — use with caution</span>'
    if 225 <= mins_since_open < 285:  # 13:00-14:00 low liquidity
        return '<span class="session-badge info"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg> Low liquidity window</span>'
    if mins_since_open < 0 or mins_since_open >= 375:  # Before open or after close
        return '<span class="session-badge muted"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="12" x2="12" y2="12"/></svg> Market closed — data may be stale</span>'
    return ""


def fmt_price(val):
    if _is_valid_num(val):
        return f"\u20b9{val:,.2f}"
    return "N/A"


def fmt_vol(val):
    if _is_valid_num(val):
        if val >= 1e7:
            return f"{val/1e7:.1f}Cr"
        if val >= 1e5:
            return f"{val/1e5:.1f}L"
        return f"{val:,.0f}"
    return "N/A"


def fmt_delta(val):
    if _is_valid_num(val):
        sign = "+" if val >= 0 else ""
        return f"{sign}{val:.2f}"
    return "N/A"


def fmt_large(val):
    if _is_valid_num(val):
        if val >= 1e7:
            return f"\u20b9{val/1e7:.1f}Cr"
        if val >= 1e5:
            return f"\u20b9{val/1e5:.1f}L"
        return f"\u20b9{val:,.0f}"
    return "N/A"


def fmt_de(de_val, sector=None):
    """Format Debt-to-Equity ratio with risk badge.

    Banks/Financial services naturally have high D/E (customer deposits
    count as liabilities) so the badge is suppressed for that sector.
    """
    if not _is_valid_num(de_val):
        return "N/A"

    is_financial = sector and ("financial" in sector.lower() or "bank" in sector.lower())

    if is_financial:
        return f'<span class="de-note">~{de_val:.2f}</span>'

    if de_val < 0:
        badge = '<span class="stat-badge danger">Negative</span>'
    elif de_val > 3.0:
        badge = '<span class="stat-badge danger">High</span>'
    elif de_val > 1.5:
        badge = '<span class="stat-badge warn">Elevated</span>'
    elif de_val >= 0.5:
        badge = '<span class="stat-badge ok">Normal</span>'
    else:
        badge = '<span class="stat-badge ok">Low</span>'

    return f'{de_val:.2f} {badge}'


def get_sentiment_svg(compound):
    if compound >= 0.3:
        return _ICON["bullish"]
    if compound <= -0.3:
        return _ICON["bearish"]
    return _ICON["neutral"]


def render_sparkline(values, width=160, height=32, color="#22b573"):
    """Render an inline SVG sparkline from a list of 0-100 values.

    Shows a flat line for 1 value. Returns empty string if None or empty list.
    """
    if not values:
        return ""

    # Single value → flat horizontal line at that value
    if len(values) == 1:
        y = height - ((values[0] / 100) * (height - 6)) - 3
        return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"
    style="vertical-align:middle;display:inline-block;">
    <polyline points="0,{y} {width},{y}" fill="none" stroke="{color}"
    stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="4,3"/>
    <circle cx="{width}" cy="{y}" r="2.5" fill="{color}"/>
    </svg>"""

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


def _render_cascade_html(cascade_effects):
    """Build the cascade/ripple effects HTML section.

    Shows commodity drivers detected in news and the tickers they affect.
    Returns empty string if no cascade effects match.
    """
    if not cascade_effects:
        return ""

    driver_rows = ""
    for effect in cascade_effects:
        driver = effect["driver"]
        direction = effect["direction"]
        impact = effect.get("impact", 1)
        n_articles = effect.get("matched_articles", 1)
        icon = _ICON["arrow_up"] if direction > 0 else _ICON["arrow_down"]
        if impact > 0:
            dir_label = "Bearish"
            dir_color = "#f85149"
        else:
            dir_label = "Bullish"
            dir_color = "#22b573"
        affected_rows = ""
        for ticker, reason, company in effect["affects"]:
            affected_rows += f"""
            <div class="cascade-ticker">
                <span class="cascade-sym">{h(ticker)}</span>
                <span class="cascade-co">{h(company)}</span>
                <span class="cascade-why">{h(reason)}</span>
            </div>"""
        driver_rows += f"""
        <div class="cascade-driver">
            <div class="cascade-header">
                <span class="cascade-name">{icon} {h(driver)}</span>
                <span class="cascade-bias" style="color:{dir_color}">{dir_label}</span>
                <span class="cascade-count">{n_articles} article{'s' if n_articles > 1 else ''}</span>
            </div>
            <div class="cascade-tickers">
                {affected_rows}
            </div>
        </div>"""

    return f"""<div class="card">
    <div class="card-title">{_ICON["layout"]} Cascade / Ripple Effects</div>
    <div class="cascade-wrap">{driver_rows}</div>
</div>"""


def _render_pivot_html(pivot_data):
    """Render classic pivot points as an HTML string."""
    if not pivot_data or not any(pivot_data.get(k) for k in ("pivot", "resistance", "support")):
        return ""
    pivot = pivot_data.get("pivot")
    r1 = pivot_data.get("resistance")
    s1 = pivot_data.get("support")
    parts = []
    if s1 is not None:
        parts.append(f'<span style="color:#f85149">S1 {fmt_price(s1)}</span>')
    if pivot is not None:
        parts.append(f'<span style="color:#8891a0">Pivot {fmt_price(pivot)}</span>')
    if r1 is not None:
        parts.append(f'<span style="color:#22b573">R1 {fmt_price(r1)}</span>')
    if not parts:
        return ""
    return (
        '<div style="margin-top:0.5rem;font-size:0.8rem;color:#8891a0;">'
        + " · ".join(parts)
        + "</div>"
    )


def _build_chart_script(ohlcv_json, nonce):
    """Build TradingView Lightweight Charts script with Bollinger + SMA overlays.
    Returns empty string if no data.
    """
    if not ohlcv_json or ohlcv_json == "[]":
        return ""
    import json as _json
    _ohlc = _json.loads(ohlcv_json) if isinstance(ohlcv_json, str) else ohlcv_json
    _bb_upper, _bb_lower, _sma200 = "[]", "[]", "[]"
    if len(_ohlc) >= 20:
        _closes = [d["close"] for d in _ohlc]
        _bb_u, _bb_l = [], []
        for i in range(19, len(_closes)):
            _window = _closes[i-19:i+1]
            _mean = sum(_window) / 20
            _var = sum((x - _mean) ** 2 for x in _window) / 20
            _std = math.sqrt(_var)
            _bb_u.append({"time": _ohlc[i]["time"], "value": round(_mean + 2 * _std, 2)})
            _bb_l.append({"time": _ohlc[i]["time"], "value": round(_mean - 2 * _std, 2)})
        _bb_upper = _json.dumps(_bb_u)
        _bb_lower = _json.dumps(_bb_l)
    if len(_ohlc) >= 200:
        _closes_200 = [d["close"] for d in _ohlc]
        _sma = []
        for i in range(199, len(_closes_200)):
            _sma.append({"time": _ohlc[i]["time"], "value": round(sum(_closes_200[i-199:i+1]) / 200, 2)})
        _sma200 = _json.dumps(_sma)

    _bb_upper_s = _json.dumps(_bb_upper) if isinstance(_bb_upper, (list, dict)) else _bb_upper
    _bb_lower_s = _json.dumps(_bb_lower) if isinstance(_bb_lower, (list, dict)) else _bb_lower
    _sma200_s = _json.dumps(_sma200) if isinstance(_sma200, (list, dict)) else _sma200

    return f"""<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js" nonce="{nonce}"></script>
<script nonce="{nonce}">
(function(){{
  var data = {ohlcv_json};
  var bbUpperData = {_bb_upper_s};
  var bbLowerData = {_bb_lower_s};
  var sma200Data = {_sma200_s};
  if (!data || !data.length) return;
  var container = document.getElementById('tvchart');
  if (!container) return;
  var chart = LightweightCharts.createChart(container, {{
    width: container.clientWidth,
    height: container.clientHeight || 380,
    layout: {{ background: {{ color: '#15181f' }}, textColor: '#8891a0' }},
    grid: {{ vertLines: {{ color: 'rgba(42,46,58,0.4)' }}, horzLines: {{ color: 'rgba(42,46,58,0.4)' }} }},
    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
    rightPriceScale: {{ borderColor: '#2a2e3a' }},
    timeScale: {{ borderColor: '#2a2e3a', timeVisible: false }},
  }});
  var candleSeries = chart.addCandlestickSeries({{
    upColor: '#22b573', downColor: '#f85149',
    borderUpColor: '#22b573', borderDownColor: '#f85149',
    wickUpColor: '#22b573', wickDownColor: '#f85149',
  }});
  candleSeries.setData(data);
  var volumeSeries = chart.addHistogramSeries({{
    color: 'rgba(34,181,115,0.3)',
    priceFormat: {{ type: 'volume' }},
    priceScaleId: '',
  }});
  volumeSeries.setData(data.map(function(d){{
    return {{ time: d.time, value: d.volume, color: d.close >= d.open ? 'rgba(34,181,115,0.3)' : 'rgba(248,81,73,0.3)' }};
  }}));
  // 50-day SMA
  if (data.length >= 50) {{
    var sma = [];
    for (var i = 49; i < data.length; i++) {{
      var sum = 0;
      for (var j = i - 49; j <= i; j++) sum += data[j].close;
      sma.push({{ time: data[i].time, value: sum / 50 }});
    }}
    var smaSeries = chart.addLineSeries({{
      color: 'rgba(96,165,250,0.6)', lineWidth: 1,
      priceLineVisible: false, lastValueVisible: false,
    }});
    smaSeries.setData(sma);
  }}
  // 200-day SMA
  if (sma200Data.length) {{
    var sma200Series = chart.addLineSeries({{
      color: 'rgba(251,191,36,0.5)', lineWidth: 1,
      priceLineVisible: false, lastValueVisible: false,
      lineStyle: 2,
    }});
    sma200Series.setData(sma200Data);
  }}
  // Bollinger Bands (20, 2)
  if (bbUpperData.length) {{
    var bbUpperSeries = chart.addLineSeries({{
      color: 'rgba(168,85,247,0.4)', lineWidth: 1,
      priceLineVisible: false, lastValueVisible: false,
      lineStyle: 2,
    }});
    bbUpperSeries.setData(bbUpperData);
    var bbLowerSeries = chart.addLineSeries({{
      color: 'rgba(168,85,247,0.4)', lineWidth: 1,
      priceLineVisible: false, lastValueVisible: false,
      lineStyle: 2,
    }});
    bbLowerSeries.setData(bbLowerData);
  }}
  chart.timeScale().fitContent();
  new ResizeObserver(function(){{ chart.applyOptions({{ width: container.clientWidth }}); }}).observe(container);
}})();
</script>"""


def render_dashboard(result, ticker, company_name, technical_indicators=None,
                     track_record=None, fii_dii_data=None, ohlcv_json=None):
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
    primary_emoji_svg = get_signal_icon(primary_emoji)
    source_breakdown = result.get("source_breakdown", [])
    source_stats = result.get("source_stats", {})
    vwap_data = result.get("vwap", {})
    pivot_data = result.get("pivot_levels", {})
    cascade_effects = result.get("cascade_effects", [])

    # Sentiment class
    _sent_map = {
        "BULLISH": ("bullish", "BUY / HOLD", "Positive sentiment dominates", _ICON["check"]),
        "BEARISH": ("bearish", "CAUTION / SELL", "Negative sentiment detected", _ICON["alert"]),
    }
    sent_class, rec_text, rec_detail, rec_icon = _sent_map.get(
        primary_signal, ("neutral", "HOLD", "Mixed or neutral sentiment", _ICON["minus"])
    )

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
    pe_str = f"{pe:.2f}" if _is_valid_num(pe) else "N/A"

    # 52-week proximity badge
    price_now = stock["current_price"]
    high_52 = stock.get("52w_high")
    low_52 = stock.get("52w_low")
    proximity_msg = ""
    proximity_class = ""
    if _is_valid_num(price_now) and _is_valid_num(high_52) and high_52 > 0:
        pct_of_high = (price_now / high_52) * 100
        proximity_msg = f"{pct_of_high:.0f}% of 52W High"
        proximity_class = "high" if pct_of_high > 90 else "mid" if pct_of_high > 70 else "low"
    elif _is_valid_num(price_now) and _is_valid_num(low_52) and low_52 > 0:
        pct_above_low = ((price_now - low_52) / low_52) * 100
        proximity_msg = f"{pct_above_low:.0f}% above 52W Low"
        proximity_class = "low" if pct_above_low < 10 else "mid"

    # Circuit breaker proximity check — within 2% of ±10% circuit
    circuit_html = ""
    if _is_valid_num(price_now) and _is_valid_num(stock.get("change")):
        prev_close = price_now - stock["change"]
        if prev_close > 0:
            upper_circuit = prev_close * 1.10
            lower_circuit = prev_close * 0.90
            if price_now >= upper_circuit * 0.98:
                circuit_html = '<span class="session-badge warn"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;"><circle cx="12" cy="12" r="10"/><path d="M12 8v8"/><path d="m8 12 4 4 4-4"/></svg> Near upper circuit — sentiment may be unreliable</span>'
            elif price_now <= lower_circuit * 1.02:
                circuit_html = '<span class="session-badge warn"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;"><circle cx="12" cy="12" r="10"/><path d="M12 8v8"/><path d="m8 12 4 4 4-4"/></svg> Near lower circuit — sentiment may be unreliable</span>'

    # VWAP badge
    vwap_html = ""
    if vwap_data and vwap_data.get("vwap") is not None:
        vwap_val = vwap_data["vwap"]
        dev = vwap_data["deviation_pct"]
        if dev is not None:
            if dev >= 0:
                vwap_html += f'<span class="vwap-badge bull">{_ICON["arrow_up"]} VWAP: ₹{vwap_val:,.2f} ({dev:+.2f}% above)</span>'
            else:
                vwap_html += f'<span class="vwap-badge bear">{_ICON["arrow_down"]} VWAP: ₹{vwap_val:,.2f} ({dev:+.2f}% below)</span>'

    # Volume spike badge
    vol_now = stock["volume"]
    vol_spike_html = ""
    vol_quality_html = ""
    if technical_indicators and isinstance(vol_now, (int, float)):
        avg_vol_50 = technical_indicators.get("avg_volume_50")
        # Volume quality gate — flag suspicious zero/low volume
        if vol_now == 0 and avg_vol_50 and avg_vol_50 > 0:
            vol_quality_html = '<span class="session-badge warn"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;"><circle cx="12" cy="12" r="10"/><path d="M12 8v8"/><path d="m8 12 4 4 4-4"/></svg> Volume is 0 — check data quality</span>'
        elif avg_vol_50 and avg_vol_50 > 0 and vol_now < avg_vol_50 * 0.1:
            vol_quality_html = '<span class="session-badge info"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;"><circle cx="12" cy="12" r="10"/><path d="M12 8v8"/><path d="m8 12 4 4 4-4"/></svg> Suspiciously low volume</span>'
        spike_result = detect_volume_spike(vol_now, avg_vol_50, threshold=1.5)
        if spike_result["spike"]:
            ratio = spike_result["ratio"]
            if ratio >= 3:
                vol_spike_html = '<span class="spike-badge huge"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg> 3x volume surge!</span>'
            elif ratio >= 2:
                vol_spike_html = f'<span class="spike-badge high">{ratio:.1f}x normal volume</span>'
            else:
                vol_spike_html = f'<span class="spike-badge mid">{ratio:.1f}x avg volume</span>'

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

    # Bayesian source calibration card
    cal_html = ""
    try:
        src_acc = load_source_accuracy()
        if src_acc:
            active = {s: d for s, d in src_acc.items() if d.get("alpha", 1) + d.get("beta", 1) > 10}
            if active:
                rows = []
                for src, dist in sorted(active.items()):
                    a = dist.get("alpha", 1)
                    b = dist.get("beta", 1)
                    total_votes = a + b - 10
                    pct = a / (a + b) * 100 if (a + b) > 0 else 50
                    sd = math.sqrt((a * b) / ((a + b) ** 2 * (a + b + 1))) if (a + b > 1) else 0.5
                    ci_lo = max(0, (pct / 100 - 1.96 * sd) * 100)
                    ci_hi = min(100, (pct / 100 + 1.96 * sd) * 100)
                    acc_class = "good" if pct >= 65 else "ok" if pct >= 50 else "poor"
                    rows.append(f"""
            <div class="cal-row">
                <div class="cal-src">{src}</div>
                <div class="cal-track"><div class="cal-fill {acc_class}" style="width:{pct:.0f}%"></div></div>
                <div class="cal-pct">{pct:.0f}%</div>
                <div class="cal-votes">{total_votes:.0f} vote{"s" if total_votes != 1 else ""}</div>
                <div class="cal-beta">a={a:.0f} b={b:.0f}</div>
            </div>""")
                if rows:
                    cal_html = f"""<div class="card">
    <div class="card-title">{_ICON["target"]} Source Calibration (Bayesian Beta)</div>
    <div class="cal-section">{" ".join(rows)}</div>
    <div class="cal-footnote">Per-source Beta(a,b) posterior from user votes. 95% CI shown.</div>
</div>"""
    except Exception:
        pass

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
        _up_dot = _ICON["dot_green"]
        _down_dot = _ICON["dot_red"]
        above_50 = _up_dot if (sma50 is not None and close > sma50) else _down_dot if (sma50 is not None and close < sma50) else "\u2014"
        above_200 = _up_dot if (sma200 is not None and close > sma200) else _down_dot if (sma200 is not None and close < sma200) else "\u2014"
        macd_hist = ti["macd_hist"]
        macd_label = _up_dot + " Bullish" if macd_hist > 0 else _down_dot + " Bearish"
        adx = ti.get("adx")
        adx_label = f"Trending (ADX {adx:.0f})" if (adx is not None and adx >= 25) else "Ranging" if (adx is not None and adx < 25) else "N/A"
        ti_preview = f"RSI {rsi:.1f} ({rsi_label}) \u00b7 SMA50 {above_50} \u00b7 SMA200 {above_200} \u00b7 MACD {macd_label}"
        if adx is not None:
            ti_preview += f" \u00b7 ADX {adx:.1f} ({'Strong' if adx >= 25 else 'Weak'})"
        ti_rows = f"""
        <div class="ti-grid">
            <div class="ti-item"><span class="ti-label">RSI (14)</span><span class="ti-value">{rsi:.1f}</span><span class="ti-sub">{rsi_label}</span></div>
            <div class="ti-item"><span class="ti-label">vs SMA 50</span><span class="ti-value">{fmt_price(sma50) if sma50 else "N/A"}</span><span class="ti-sub">{above_50}</span></div>
            <div class="ti-item"><span class="ti-label">vs SMA 200</span><span class="ti-value">{fmt_price(sma200) if sma200 else "N/A"}</span><span class="ti-sub">{above_200}</span></div>
            <div class="ti-item"><span class="ti-label">MACD Hist</span><span class="ti-value">{macd_hist:.4f}</span><span class="ti-sub">{macd_label}</span></div>
            <div class="ti-item"><span class="ti-label">ADX (14)</span><span class="ti-value">{f"{adx:.1f}" if adx is not None else "N/A"}</span><span class="ti-sub">{adx_label}</span></div>
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
        <div class="stat-item"><span class="stat-label">D/E Ratio</span><span class="stat-value">{fmt_de(stock.get("debt_to_equity"), stock.get("sector"))}</span></div>
    </div>"""

    badge_html = ""
    # Source badges — SVG dots
    _src_dot_green = _ICON["dot_green"]
    _src_dot_red = _ICON["dot_red"]
    _src_dot_grey = _ICON["dot_grey"]
    for src in source_breakdown:
        if src["avg"] >= 0.3:
            b_class = "bullish"
            b_emoji = _src_dot_green
        elif src["avg"] <= -0.3:
            b_class = "bearish"
            b_emoji = _src_dot_red
        else:
            b_class = "neutral"
            b_emoji = _src_dot_grey
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
        ss_icon = get_signal_icon(result.get("smartscore_emoji", "⚪"))

        # Component mini-bars
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
        emoji = get_sentiment_svg(scores["compound"])
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
            f'<a href="{h(item.get("url", ""))}" target="_blank" rel="noopener">{h(item.get("title", ""))}</a>'
            if item.get("url")
            else h(item.get("title", ""))
        )
        meta_parts = []
        if item.get("source"):
            meta_parts.append(f"{_ICON['wifi']} {h(item['source'])}")
        if item.get("date"):
            meta_parts.append(f"{h(item['date'][:10])}")
        body = ""
        if item.get("body"):
            body = h(item["body"][:200])

        in_portfolio = item.get("in_portfolio", False)
        port_badge = '<span class="port-badge">\U0001f4cc In portfolio</span>' if in_portfolio else ""
        news_html += f"""
        <div class="news-item">
            <div class="news-emoji">{emoji}</div>
            <div class="news-content">
                <div class="news-title">{title_html}</div>
                <div class="news-meta">{' · '.join(meta_parts)} {port_badge}<span class="sentiment-tag {s_class}">{s_label}</span></div>
                {'<div class="news-body">' + body + '</div>' if body else ''}
            </div>
        </div>"""

    # Source badges section (pre-computed to avoid nested f-string issues)
    badge_section = f'<div class="badge-wrap">{badge_html}</div>' if badge_html else ""
    source_health = f'<div class="source-health">{_ICON["wifi"]} Sources: {sources_str}</div>' if sources_str else ""
    ti_section = f'<div class="ti-preview">{ti_preview}</div>' if ti_preview else ""

    # Session quality badge
    session_badge = _session_quality_badge()

    # Random CSP nonce for the auto-height script blocks
    # any injected inline scripts from RSS content
    _nonce = secrets.token_urlsafe(16)
    auto_height_script = f"""<script nonce="{_nonce}">
(function(){{var o=document.referrer?new URL(document.referrer).origin:'*';function h(){{var d=document.body.scrollHeight;parent.postMessage({{type:'streamlit:setFrameHeight',height:d}},o);}}window.addEventListener('load',h);window.addEventListener('resize',h);}})();
</script>"""

    # ─── TradingView Lightweight Charts — candlestick + volume + overlays ───
    _chart_script = _build_chart_script(ohlcv_json, _nonce)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'nonce-{_nonce}' https://unpkg.com; style-src 'unsafe-inline'; font-src fonts.gstatic.com fonts.googleapis.com; img-src *; connect-src 'self' https://query1.finance.yahoo.com https://query2.finance.yahoo.com https://news.google.com https://www.moneycontrol.com https://economictimes.indiatimes.com https://www.livemint.com https://feeds.feedburner.com;">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{_DASHBOARD_CSS}</style>
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
                {circuit_html}
            </div>
        </div>
        <div class="price-grid">
            <div class="price-cell">
                <div class="label">{h(ticker[:6])}</div>
                <div class="value price-main">{fmt_price(price)}</div>
                <div class="delta {'up' if _is_valid_num(change_val) and change_val >= 0 else 'down' if _is_valid_num(change_val) else 'neutral'}" style="margin-bottom:0.15rem">{fmt_delta(change_val) if _is_valid_num(change_val) else "N/A"} ({fmt_delta(change_pct) if _is_valid_num(change_pct) else "N/A"}%)</div>
                {vwap_html}
            </div>
            <div class="price-cell">
                <div class="label">Day Range</div>
                <div class="value" style="font-size:0.9rem">{day_range}</div>
            </div>
            <div class="price-cell">
                <div class="label">Volume{vol_spike_html}</div>
                <div class="value" style="font-size:1rem">{volume}</div>
                {vol_quality_html}
            </div>
            <div class="price-cell">
                <div class="label">P/E Ratio</div>
                <div class="value" style="font-size:1rem">{pe_str}</div>
            </div>
        </div>
        <div style="margin-top:0.75rem;border-top:1px solid #2a2e3a;padding-top:0.75rem">
            {stats_rows}
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
                <div class="confidence-num {sent_class}">{confidence_pct:.0f}%</div>
                <div class="confidence-label">Weighted Confidence</div>
            </div>
        </div>
        {ss_html}
        <div class="dist-inline">
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
        {badge_section}
        {source_health}
        {session_badge}
    </div>

    <!-- ═══ NEWS HEADLINES ═══ -->
    <div class="card">
        <div class="card-title">{_ICON["file_text"]} Recent News ({len(news_items)} articles)</div>
        {news_html if news_html else '<div class="ss-comp-label" style="padding:0.75rem 0;color:#8891a0">No articles found for this ticker</div>'}
    </div>

    <!-- ═══ TECHNICAL INDICATORS ═══ -->
    <div class="card">
        <div class="card-title">{_ICON["signal"]} Technical Indicators</div>
        {ti_section}
        {ti_rows}
        <div style="margin-top:0.5rem">{cross_50_html}{cross_200_html}</div>
        {_render_pivot_html(pivot_data)}
    </div>

{_render_cascade_html(cascade_effects)}

    <!-- ═══ PRICE CHART ═══ -->
    <div class="card">
        <div class="card-title">{_ICON["bar_chart"]} Price Chart (2Y)</div>
        <div style="display:flex;gap:0.75rem;flex-wrap:wrap;margin-bottom:0.5rem;font-size:0.72rem;color:#8891a0">
            <span><span style="display:inline-block;width:12px;height:2px;background:rgba(96,165,250,0.6);vertical-align:middle;margin-right:3px"></span>SMA 50</span>
            <span><span style="display:inline-block;width:12px;height:2px;background:rgba(251,191,36,0.5);vertical-align:middle;margin-right:3px;border-top:1px dashed rgba(251,191,36,0.5)"></span>SMA 200</span>
            <span><span style="display:inline-block;width:12px;height:2px;background:rgba(168,85,247,0.4);vertical-align:middle;margin-right:3px;border-top:1px dashed rgba(168,85,247,0.4)"></span>Bollinger (20,2)</span>
        </div>
        <div id="tvchart" class="chart-container"></div>
    </div>

{acc_html}

{cal_html}

{fii_html}

</div>
{_chart_script}
{auto_height_script}
</body>
</html>"""
