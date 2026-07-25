"""
Sentiment analysis strategy — VADER + financial lexicon + Bayesian blending.
Pure strategy layer: no I/O, no external calls.
"""

from __future__ import annotations

import logging
from typing import Optional

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from ..contracts import Headline, NewsArticle, SentimentScore, EventType
from .classifier import classify_headline

log = logging.getLogger(__name__)

# Financial lexicon for VADER augmentation
FINANCIAL_LEXICON = {
    # Positive
    "bullish": 2.0, "bull": 1.5, "rally": 1.5, "surge": 1.8, "soar": 1.8,
    "beat": 1.5, "exceed": 1.5, "outperform": 1.3, "upgrade": 1.5,
    "buyback": 1.2, "dividend": 0.8, "profit": 1.0, "growth": 0.8,
    "expansion": 0.8, "contract": 0.8, "win": 1.0, "strong": 0.8,
    "record": 1.0, "high": 0.5, "gain": 0.8, "rise": 0.8, "up": 0.5,
    "positive": 0.8, "optimistic": 0.8, "confident": 0.7, "robust": 0.8,
    "healthy": 0.7, "solid": 0.7, "improve": 0.8, "improvement": 0.8,
    "recover": 0.8, "recovery": 0.8, "bounce": 0.8, "rebound": 0.8,
    "momentum": 0.7, "breakout": 1.2, "breakthrough": 1.2,

    # Negative
    "bearish": -2.0, "bear": -1.5, "crash": -2.0, "plunge": -1.8, "tumble": -1.5,
    "miss": -1.5, "disappoint": -1.5, "underperform": -1.3, "downgrade": -1.5,
    "sell": -1.0, "loss": -1.0, "decline": -0.8, "fall": -0.8, "drop": -0.8,
    "down": -0.5, "negative": -0.8, "pessimistic": -0.8, "concern": -0.7,
    "risk": -0.5, "weak": -0.8, "poor": -0.8, "deteriorate": -0.8,
    "warn": -0.7, "warning": -0.7, "caution": -0.6, "volatile": -0.5,
    "uncertain": -0.5, "pressure": -0.5, "headwind": -0.6, "drag": -0.6,

    # Events (mild positive)
    "earnings": 0.3, "merger": 0.5, "acquisition": 0.5, "ipo": 0.3,
    "split": 0.1, "buyback": 0.5, "dividend": 0.3, "guidance": 0.2,
    "regulatory": -0.3, "lawsuit": -0.5, "investigation": -0.5,
    "scandal": -1.0, "fraud": -1.5, "bankruptcy": -2.0, "default": -1.5,
}

# Source credibility weights
SOURCE_WEIGHTS = {
    "economictimes": 1.2,
    "moneycontrol": 1.1,
    "livemint": 1.1,
    "business-standard": 1.0,
    "thehindu-business": 1.0,
    "zeebiz": 0.9,
    "financialexpress": 1.0,
    "bseindia": 1.0,
    "yahoo finance": 0.9,
    "reuters": 1.3,
    "bloomberg": 1.3,
    "cnbc": 1.1,
    "marketwatch": 1.0,
}

_analyzer: Optional[SentimentIntensityAnalyzer] = None


def get_analyzer() -> SentimentIntensityAnalyzer:
    """Get or create VADER analyzer with financial lexicon."""
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentIntensityAnalyzer()
        _analyzer.lexicon.update(FINANCIAL_LEXICON)
    return _analyzer


def _source_weight(source: str) -> float:
    """Get credibility weight for news source."""
    key = source.lower().replace(" ", "").replace("-", "")
    return SOURCE_WEIGHTS.get(key, 1.0)


def analyze_headline(headline: Headline) -> SentimentScore:
    """
    Analyze sentiment of a single headline.

    Args:
        headline: Headline with title, summary, source

    Returns:
        SentimentScore with compound, pos/neg/neu, confidence, event
    """
    analyzer = get_analyzer()
    text = headline.text

    # VADER scores
    scores = analyzer.polarity_scores(text)
    compound = scores["compound"]
    pos = scores["pos"]
    neg = scores["neg"]
    neu = scores["neu"]

    # Source credibility weight
    weight = _source_weight(headline.source)

    # Text length confidence (longer = more reliable)
    length_conf = min(len(text) / 200, 1.0)

    # Combined confidence
    confidence = (weight * 0.6 + length_conf * 0.4)

    # Event classification
    event_type = classify_headline(headline)
    event_conf = 0.8 if event_type != EventType.UNKNOWN else 0.0

    return SentimentScore(
        compound=compound,
        positive=pos,
        negative=neg,
        neutral=neu,
        confidence=confidence,
        event_type=event_type,
        event_confidence=event_conf,
    )


def analyze_articles(articles: list[NewsArticle]) -> list[SentimentScore]:
    """Analyze sentiment for multiple articles."""
    return [analyze_headline(Headline(
        title=a.title,
        summary=a.summary,
        url=a.url,
        source=a.source,
        published=a.published,
        ticker=a.ticker,
    )) for a in articles]


def aggregate_sentiment(scores: list[SentimentScore]) -> SentimentScore:
    """
    Aggregate multiple sentiment scores using weighted average.

    Weights by confidence and article count.
    """
    if not scores:
        return SentimentScore(
            compound=0.0, positive=0.0, negative=0.0, neutral=1.0,
            confidence=0.0, event_type=EventType.UNKNOWN, event_confidence=0.0
        )

    total_weight = sum(s.confidence for s in scores)
    if total_weight == 0:
        total_weight = 1.0

    weighted_compound = sum(s.compound * s.confidence for s in scores) / total_weight
    weighted_pos = sum(s.positive * s.confidence for s in scores) / total_weight
    weighted_neg = sum(s.negative * s.confidence for s in scores) / total_weight
    weighted_neu = sum(s.neutral * s.confidence for s in scores) / total_weight
    avg_conf = sum(s.confidence for s in scores) / len(scores)

    # Most common event type
    events = [s.event_type for s in scores if s.event_type != EventType.UNKNOWN]
    event_type = max(set(events), key=events.count) if events else EventType.UNKNOWN
    event_conf = sum(s.event_confidence for s in scores) / len(scores)

    return SentimentScore(
        compound=weighted_compound,
        positive=weighted_pos,
        negative=weighted_neg,
        neutral=weighted_neu,
        confidence=avg_conf,
        event_type=event_type,
        event_confidence=event_conf,
    )


def get_weighted_signal(sentiment: SentimentScore, threshold: float = 0.1) -> tuple[str, float]:
    """
    Convert sentiment to trading signal.

    Returns:
        (signal, strength) where signal in {"BUY", "SELL", "HOLD"}
    """
    compound = sentiment.compound
    conf = sentiment.confidence

    if compound > threshold and conf > 0.3:
        return "BUY", min(abs(compound) * conf, 1.0)
    elif compound < -threshold and conf > 0.3:
        return "SELL", min(abs(compound) * conf, 1.0)
    else:
        return "HOLD", 0.0