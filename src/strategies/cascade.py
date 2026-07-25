"""
Cascade detection — detects sentiment cascades (self-reinforcing moves).
Pure strategy layer: no I/O, deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from ..contracts import Headline, SentimentScore, EventType, TrendDirection, CascadeEvent


@dataclass
class CascadeSignal:
    """Internal cascade detection signal."""
    direction: TrendDirection
    score: float
    events: list[EventType]
    articles: list[Headline]
    start_date: datetime
    end_date: datetime


def detect_cascade(
    headlines: list[Headline],
    sentiments: list[SentimentScore],
    lookback_days: int = 7,
    min_articles: int = 3,
    min_consistency: float = 0.6,
) -> Optional[CascadeEvent]:
    """
    Detect if there's a sentiment cascade forming.

    A cascade occurs when:
    1. Multiple articles over several days show consistent sentiment direction
    2. Supporting event types confirm the direction
    3. Confidence increases over time

    Args:
        headlines: List of headlines (chronological)
        sentiments: Corresponding sentiment scores
        lookback_days: Maximum days to look back
        min_articles: Minimum articles needed
        min_consistency: Minimum fraction agreeing on direction

    Returns:
        CascadeEvent if detected, None otherwise
    """
    if len(headlines) < min_articles or len(sentiments) < min_articles:
        return None

    # Filter to lookback window
    cutoff = datetime.now() - timedelta(days=lookback_days)
    recent = [(h, s) for h, s in zip(headlines, sentiments)
              if h.published >= cutoff and s.confidence > 0.3]

    if len(recent) < min_articles:
        return None

    # Check sentiment consistency
    compounds = [s.compound for _, s in recent]
    avg_compound = sum(compounds) / len(compounds)

    # Direction
    if avg_compound > 0.15:
        direction = TrendDirection.BULLISH
    elif avg_compound < -0.15:
        direction = TrendDirection.BEARISH
    else:
        return None  # Too neutral

    # Consistency check
    same_direction = sum(1 for c in compounds
                         if (direction == TrendDirection.BULLISH and c > 0) or
                         (direction == TrendDirection.BEARISH and c < 0))
    consistency = same_direction / len(compounds)

    if consistency < min_consistency:
        return None

    # Event confirmation
    events = [s.event_type for _, s in recent if s.event_type != EventType.UNKNOWN]
    event_types = list(set(events))

    # Must have at least 1 confirming event type
    confirming_events = _get_confirming_events(direction, event_types)
    if not confirming_events:
        return None

    # Duration
    start_date = min(h.published for h, _ in recent)
    end_date = max(h.published for h, _ in recent)
    duration = (end_date - start_date).days + 1

    # Confidence increases with more articles and higher consistency
    confidence = min(consistency * 0.7 + (len(recent) / 10) * 0.3, 1.0)

    return CascadeEvent(
        direction=direction,
        sentiment_score=avg_compound,
        confirming_events=confirming_events,
        confidence=confidence,
        start_date=start_date,
        duration_days=duration,
    )


def _get_confirming_events(direction: TrendDirection, events: list[EventType]) -> list[EventType]:
    """Get events that confirm the sentiment direction."""
    if direction == TrendDirection.BULLISH:
        bullish_events = {
            EventType.EARNINGS, EventType.MERGER_ACQUISITION,
            EventType.PRODUCT_LAUNCH, EventType.CONTRACT,
            EventType.GUIDANCE, EventType.BUYBACK, EventType.DIVIDEND,
            EventType.INSIDER, EventType.SPLIT,
        }
        return [e for e in events if e in bullish_events]
    else:  # BEARISH
        bearish_events = {
            EventType.REGULATORY, EventType.LEGAL,
            EventType.MANAGEMENT_CHANGE,
        }
        return [e for e in events if e in bearish_events]


def detect_cascade_from_articles(
    articles: list,
    lookback_days: int = 7,
) -> Optional[CascadeEvent]:
    """
    Detect cascade from news articles.

    Args:
        articles: List of NewsArticle or Headline objects
        lookback_days: Lookback window

    Returns:
        CascadeEvent if detected
    """
    from ..strategies.sentiment import analyze_articles, analyze_headline

    # Convert to headlines if needed
    headlines = []
    for a in articles:
        if hasattr(a, 'title') and hasattr(a, 'summary'):
            headlines.append(a)

    if not headlines:
        return None

    sentiments = [analyze_headline(h) for h in headlines]
    return detect_cascade(headlines, sentiments, lookback_days)