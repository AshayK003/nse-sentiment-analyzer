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

import math
from datetime import datetime

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
    """Compute SmartScore (0-100) from headline scores and optional history.

    Args:
        headline_scores: list of dicts with 'compound' key (raw VADER scores)
        event_adjusted_scores: list of floats (event-blended compound scores)
        history: optional list of past daily dicts from sentiment_history.csv.
                 Each dict must have 'date' and 'avg_compound' keys.
                 Sorted oldest-first.

    Returns:
        dict with keys:
            smartscore: float 0-100
            s_recency: float 0-1
            s_events: float 0-1
            s_breadth: float 0-1
            s_volume: float 0-1
            headline_count: int
            pos_count: int
            neg_count: int
            signal: str — "BULLISH", "NEUTRAL", or "BEARISH"
            signal_emoji: str
            history_scores: list of float — past SmartScores for sparkline
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
