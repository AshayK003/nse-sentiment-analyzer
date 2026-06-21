"""
Sentiment analysis for NSE Stock Sentiment Analyzer.
VADER + custom financial lexicon tuned for Indian markets.
"""

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import streamlit as st
from persistence import load_source_accuracy, SOURCE_WEIGHTS_PRIOR


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
    # ── Indian financial context ──
    "npa": -2.0,
    "npas": -2.0,
    "gnpa": -2.0,
    "nnpa": -1.5,
    "aum": 1.0,
    "pat": 1.0,
    "ebitda": 1.0,
    "nim": 1.0,
    "roe": 1.0,
    "roce": 1.0,
    "divestment": -1.0,
    "disinvestment": -1.0,
    "credit growth": 1.0,
    "deposit growth": 1.0,
    "asset quality": 1.0,
    # ── Hinglish / Indian English ──
    "mandi": -1.5,
    "tezi": 1.5,
    "gira": -1.5,
    "chada": 1.5,
    # ── General financial context ──
    "robust": 1.5,
    "resilient": 1.0,
    "stellar": 2.0,
    "beat": 1.5,
    "miss": -1.5,
    "avoid": -1.5,
    "headwinds": -1.5,
    "tailwinds": 1.5,
    "overbought": -1.0,
    "oversold": 1.0,
    "profit booking": -0.5,
    "accumulation": 1.0,
    "distribution": -1.0,
    # ── IPO & capital markets ──
    "oversubscribed": 1.5,
    "undersubscribed": -1.5,
    "listing": 0.5,
    # ── Banking / NPAs / credit ──
    "slippage": -1.5,
    "write-off": -1.5,
    "write off": -1.5,
    "provisioning": -0.8,
    "moratorium": -1.0,
    "recapitalization": 1.2,
    "infusion": 1.5,
    "pledged": -1.0,
    "unpledged": 1.0,
    "margin call": -2.0,
    # ── Fund flows ──
    "inflow": 1.0,
    "outflow": -1.0,
    "buying": 1.0,
    "selling": -1.0,
    # ── Results & performance ──
    "doubled": 1.5,
    "tripled": 2.0,
    "multibagger": 1.5,
    "topline": 0.5,
    "bottomline": 1.0,
    "profit warning": -2.0,
    # ── Market action ──
    "sell-off": -2.0,
    "sell off": -2.0,
    "short covering": 1.5,
    "short selling": -1.0,
    "risk-on": 1.0,
    "risk-off": -1.0,
    "upper circuit": 1.5,
    "lower circuit": -2.0,
    "circuit breaker": -0.5,
    "bear phase": -1.5,
    # ── Corporate governance ──
    "insider trading": -2.5,
    "front running": -2.0,
    "mismanagement": -2.0,
    "compliance": 0.5,
    "scrutiny": -1.0,
    # ── Corporate action ──
    "buyout": 1.0,
    "merger": 0.5,
    "acquisition": 0.5,
    "delisting": -0.5,
    "open offer": 0.5,
    # ── Macro & economy ──
    "depreciation": -1.0,
    "appreciation": 1.0,
    "deficit": -1.0,
    "GDP growth": 1.0,
    # ── More Hinglish ──
    "gire": -1.5,
    "giri": -1.5,
    "chade": 1.5,
    "chadi": 1.5,
    "tej": 1.0,
    "mand": -1.0,
}

# ─── Source weights (0.0–1.0) ───
# Confidence that a source's sentiment signal is reliable.
# Financial news > aggregators > social.
# Bayesian-calibrated from user votes via persistence.SOURCE_WEIGHTS_PRIOR.
# get_source_weights() loads the learned posterior weights at runtime.


def get_source_weights():
    """Return learned source weights from Bayesian calibration.
    Falls back to SOURCE_WEIGHTS_PRIOR defaults if calibration file missing or empty."""
    try:
        acc = load_source_accuracy()
        if acc:
            return {
                src: max(0.01, acc[src]["alpha"] / (acc[src]["alpha"] + acc[src]["beta"]))
                for src in acc
            }
        return dict(SOURCE_WEIGHTS_PRIOR)
    except Exception:
        return dict(SOURCE_WEIGHTS_PRIOR)


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


# ─── FinBERT (optional upgrade) ───
# Feature-gated via env var USE_FINBERT=true. Falls back to VADER if
# transformers/torch not installed or model download fails.

@st.cache_resource(show_spinner="Loading FinBERT model...")
def get_finbert():
    """Load FinBERT pipeline for financial sentiment. Cached — 10s first load,
    instant thereafter. Returns None if dependencies unavailable."""
    try:
        from transformers import pipeline
        return pipeline(
            "sentiment-analysis",
            model="ProsusAI/finbert",
            top_k=None,
        )
    except (ImportError, OSError) as e:
        st.warning(f"FinBERT unavailable ({e}). Using VADER.")
        return None


def analyze_headline_finbert(headline, body, pipe):
    """Score a headline using FinBERT. Returns same shape as
    analyze_headline_sentiment() for drop-in compatibility."""
    if pipe is None:
        return {"compound": 0.0}

    text = f"{headline}. {body}" if body else headline
    try:
        result = pipe(text[:512])[0]  # truncate to 512 tokens
        scores = {r["label"]: r["score"] for r in result}
        compound = scores.get("positive", 0.0) - scores.get("negative", 0.0)
        return {
            "compound": round(compound, 4),
            "positive": scores.get("positive", 0.0),
            "negative": scores.get("negative", 0.0),
            "neutral": scores.get("neutral", 0.0),
        }
    except Exception:
        return {"compound": 0.0}


def get_weighted_signal(headline_scores, source_weights=None):
    """Compute source-weighted blended signal.

    headline_scores: list of {"compound": float, "source": str}
    source_weights: optional dict of {source: weight}. Defaults to Bayesian-calibrated weights.
    Returns (signal, blended_compound, emoji, per_source_breakdown).

    per_source_breakdown: list of {"source": str, "weight": float, "avg": float, "count": int}
    """
    if not headline_scores:
        return "NEUTRAL ⚪", 0.0, "⚪", []

    if source_weights is None:
        source_weights = get_source_weights()

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
        weight = source_weights.get(src, 0.5)
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
