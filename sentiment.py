"""
Sentiment analysis for NSE Stock Sentiment Analyzer.
VADER + custom financial lexicon tuned for Indian markets.
"""

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import streamlit as st


# ─── Financial sentiment augmentations ───
# Words VADER doesn't score well for finance
FINANCIAL_BOOSTERS = {
    "bullish": 2.5,
    "bearish": -2.5,
    "outperform": 2.0,
    "underperform": -2.0,
    "overweight": 1.5,
    "underweight": -1.5,
    "upside": 1.8,
    "downside": -1.8,
    "buy": 1.5,
    "accumulate": 1.2,
    "reduce": -1.2,
    "sell": -2.0,
    "downgrade": -2.0,
    "upgrade": 2.0,
    "positive": 1.0,
    "negative": -1.0,
    "surge": 1.5,
    "plunge": -2.0,
    "rally": 1.5,
    "crash": -2.5,
    "record": 1.0,
    "decline": -1.0,
    "profit": 1.0,
    "loss": -1.0,
    "dividend": 1.0,
    "expansion": 1.0,
    "growth": 1.0,
    "slowdown": -1.5,
    "momentum": 1.0,
    "volatility": -0.5,
    "correction": -1.0,
    "breakout": 1.5,
    "breakdown": -1.5,
    "resistance": -0.3,
    "support": 0.3,
    "all-time high": 2.0,
    "52-week high": 1.5,
    "52-week low": -1.5,
}

# ─── Source weights (0.0–1.0) ───
# Confidence that a source's sentiment signal is reliable.
# Financial news > aggregators > social.
SOURCE_WEIGHTS = {
    "Economic Times": 1.0,
    "Moneycontrol": 0.9,
    "LiveMint": 0.8,
    "NDTV Profit": 0.7,
    "Google News": 0.6,
    "DuckDuckGo": 0.5,
    "Reddit": 0.4,
}

# Local-only sources (require CLI tools, only available when running locally)
LOCAL_ONLY_SOURCES = {"Reddit"}



@st.cache_resource
def get_sia():
    """Initialize VADER with custom financial lexicon."""
    sia = SentimentIntensityAnalyzer()
    sia.lexicon.update(FINANCIAL_BOOSTERS)
    return sia


def analyze_headline_sentiment(headline, body, sia, source=None):
    """Score a headline using VADER + financial lexicon."""
    text = f"{headline}. {body}" if body else headline
    vader = sia.polarity_scores(text)
    result = {"compound": vader["compound"], "vader": vader}
    if source:
        result["source"] = source
    return result


def get_overall_signal(headline_scores):
    """Determine overall signal from headline scores."""
    if not headline_scores:
        return "NEUTRAL ⚪", 0.0, "⚪"

    avg_compound = sum(s["compound"] for s in headline_scores) / len(headline_scores)
    pos_count = sum(1 for s in headline_scores if s["compound"] >= 0.3)
    neg_count = sum(1 for s in headline_scores if s["compound"] <= -0.3)

    if avg_compound >= 0.2 and pos_count > neg_count:
        return "BULLISH 🟢", avg_compound, "🟢"
    elif avg_compound <= -0.2 and neg_count > pos_count:
        return "BEARISH 🔴", avg_compound, "🔴"
    else:
        return "NEUTRAL ⚪", avg_compound, "⚪"


def get_sentiment_emoji(compound):
    if compound >= 0.3:
        return "🟢"
    elif compound <= -0.3:
        return "🔴"
    return "⚪"


def get_weighted_signal(headline_scores):
    """Compute source-weighted blended signal.

    headline_scores: list of {"compound": float, "source": str}
    Returns (signal, blended_compound, emoji, per_source_breakdown).

    per_source_breakdown: list of {"source": str, "weight": float, "avg": float, "count": int}
    """
    if not headline_scores:
        return "NEUTRAL ⚪", 0.0, "⚪", []

    # Group by source
    from collections import defaultdict
    by_source = defaultdict(list)
    for s in headline_scores:
        src = s.get("source", "Unknown")
        by_source[src].append(s["compound"])

    # Compute per-source averages
    source_avgs = []
    total_weight = 0.0
    weighted_sum = 0.0
    for src, compounds in by_source.items():
        avg = sum(compounds) / len(compounds)
        weight = SOURCE_WEIGHTS.get(src, 0.5)
        source_avgs.append({
            "source": src,
            "weight": weight,
            "avg": avg,
            "count": len(compounds),
        })
        weighted_sum += weight * avg
        total_weight += weight

    blended = weighted_sum / total_weight if total_weight > 0 else 0.0
    source_avgs.sort(key=lambda x: x["weight"], reverse=True)

    # Determine signal from blended score
    pos_count = sum(1 for s in headline_scores if s["compound"] >= 0.3)
    neg_count = sum(1 for s in headline_scores if s["compound"] <= -0.3)

    if blended >= 0.2 and pos_count > neg_count:
        signal = "BULLISH 🟢"
        emoji = "🟢"
    elif blended <= -0.2 and neg_count > pos_count:
        signal = "BEARISH 🔴"
        emoji = "🔴"
    else:
        signal = "NEUTRAL ⚪"
        emoji = "⚪"

    return signal, blended, emoji, source_avgs
