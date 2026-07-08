"""
SmartScore aggregation for NSE Sentiment Analyzer.

Computes a 0-100 composite index from recency-weighted sentiment (EWMA),
event-adjusted sentiment, headline breadth, and news volume.

Described system formula:
    SmartScore = 0.45*S_recency + 0.25*S_events + 0.20*S_breadth + 0.10*S_volume

Interpretation:
    70+  → strong positive tone and momentum
    50–69 → neutral to mildly positive
    <50  → negative or weak sentiment tone
"""

import logging
import math
from datetime import datetime

logger = logging.getLogger(__name__)

# ─── SmartScore weights ───
W_RECENCY = 0.45
W_EVENTS = 0.25
W_BREADTH = 0.20
W_VOLUME = 0.10

# EWMA half-life in hours (36h ≈ 1.5 days)
HALF_LIFE_HOURS = 36

# Max headlines for volume normalization (log-saturated at ~20 articles)
MAX_HEADLINES = 20

# Signal thresholds
BULLISH_THRESHOLD = 65
BEARISH_THRESHOLD = 40


# ─── EWMA helpers ───


def _ewma_weight(days_ago):
    """Compute EWMA decay weight for a score N days ago.

    Half-life ≈ 36h means a score from 1.5 days ago weighs 50%.
    λ = 0.5^(24/36) ≈ 0.63 per day.
    """
    hours_ago = days_ago * 24
    return math.exp(-math.log(2) * hours_ago / HALF_LIFE_HOURS)


def _compute_ewma(daily_averages):
    """Compute EWMA over a list of (days_ago, score) pairs."""
    if not daily_averages:
        return 0.0

    total_weight = 0.0
    weighted_sum = 0.0
    for days_ago, score in daily_averages:
        w = _ewma_weight(days_ago)
        weighted_sum += w * score
        total_weight += w

    return weighted_sum / total_weight if total_weight > 0 else daily_averages[0][1]


def _map_minus1_1_to_0_1(val):
    """Map a value in [-1, 1] to [0, 1]."""
    return (val + 1) / 2


# ─── Main computation ───


def compute_smartscore(headline_scores, event_adjusted_scores, history=None):
    """Compute the SmartScore (0–100) using four normalized sentiment components.

SmartScore combines multiple signals into a single metric that summarizes
overall market sentiment.

Components
----------
1. Recency (45%)
    Exponentially Weighted Moving Average (EWMA) of recent daily
    event-adjusted sentiment using a 36-hour half-life.

2. Event-adjusted Sentiment (25%)
    Average of today's event-adjusted headline sentiment scores.

3. Headline Breadth (20%)
    Measures whether positive headlines outnumber negative headlines.

4. News Volume (10%)
    Log-normalized headline count to reward broader news coverage
    without allowing volume to dominate the score.

Formula
-------
SmartScore = 100 × (
    0.45 × S_recency +
    0.25 × S_events +
    0.20 × S_breadth +
    0.10 × S_volume
)

The final score is clamped to the range 0–100.

Signal Thresholds
-----------------
SmartScore >= 65      → BULLISH
40 <= SmartScore < 65 → NEUTRAL
SmartScore < 40       → BEARISH

Args:
    headline_scores:
        List of dictionaries containing raw VADER compound scores.

    event_adjusted_scores:
        List of event-adjusted compound sentiment scores.

    history:
        Optional historical daily sentiment records used for EWMA
        calculation.

Returns:
    Dictionary containing the SmartScore, individual component scores,
    headline statistics, market signal, and historical SmartScore values.
    """
    n = len(headline_scores)

    if n == 0:
        return _empty_result([] if history else None)

    # ── S_events: today's event-adjusted sentiment ──
    avg_event_adj = sum(event_adjusted_scores) / n
    s_events = _map_minus1_1_to_0_1(avg_event_adj)

    # ── S_breadth: ratio of positive vs negative headlines (event-adjusted) ──
    pos = sum(1 for adj in event_adjusted_scores if adj >= 0.3)
    neg = sum(1 for adj in event_adjusted_scores if adj <= -0.3)
    raw_breadth = (pos - neg) / n  # [-1, 1]
    s_breadth = _map_minus1_1_to_0_1(raw_breadth)

    # ── S_volume: log-normalized news count ──
    s_volume = min(math.log1p(n) / math.log1p(MAX_HEADLINES), 1.0)

    # ── S_recency: EWMA over event-adjusted daily averages ──
    daily_averages = []
    today_raw = avg_event_adj
    daily_averages.append((0, today_raw))

    if history:
        for h in history:
            avg_str = h.get("avg_compound")
            if avg_str is not None and avg_str != "":
                try:
                    d = datetime.strptime(h["date"], "%Y-%m-%d")
                    days_ago = (datetime.now() - d).days
                    # Only include if within reasonable range
                    if 0 < days_ago <= 30:
                        daily_averages.append((days_ago, float(avg_str)))
                except (ValueError, TypeError):
                    continue

    recency_raw = _compute_ewma(daily_averages)
    s_recency = _map_minus1_1_to_0_1(recency_raw)

    # ── Composite SmartScore (0-100) ──
    smartscore = (
        W_RECENCY * s_recency * 100
        + W_EVENTS * s_events * 100
        + W_BREADTH * s_breadth * 100
        + W_VOLUME * s_volume * 100
    )
    smartscore = max(0.0, min(100.0, smartscore))

    # ── Signal from SmartScore ──
    if smartscore >= BULLISH_THRESHOLD:
        signal = "BULLISH"
        signal_emoji = "🟢"
    elif smartscore < BEARISH_THRESHOLD:
        signal = "BEARISH"
        signal_emoji = "🔴"
    else:
        signal = "NEUTRAL"
        signal_emoji = "⚪"

    # ── History scores for sparkline ──
    history_scores = []
    if history:
        history_scores = [
            float(h["smartscore"])
            for h in history
            if h.get("smartscore") is not None and h["smartscore"] != ""
        ]
    history_scores.append(round(smartscore, 1))

    return {
        "smartscore": round(smartscore, 1),
        "s_recency": round(s_recency, 3),
        "s_events": round(s_events, 3),
        "s_breadth": round(s_breadth, 3),
        "s_volume": round(s_volume, 3),
        "headline_count": n,
        "pos_count": pos,
        "neg_count": neg,
        "signal": signal,
        "signal_emoji": signal_emoji,
    }, history_scores


def _empty_result(history_scores):
    """Return neutral result when no headlines available."""
    hs = list(history_scores) if history_scores else []
    hs.append(50.0)
    return {
        "smartscore": 50.0,
        "s_recency": 0.5,
        "s_events": 0.5,
        "s_breadth": 0.5,
        "s_volume": 0.0,
        "headline_count": 0,
        "pos_count": 0,
        "neg_count": 0,
        "signal": "NEUTRAL",
        "signal_emoji": "⚪",
    }, hs
