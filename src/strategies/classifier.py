"""
Event classification — keyword-based event type detection.
Pure strategy layer: no I/O, deterministic.
"""

from __future__ import annotations

from ..contracts import Headline, EventType

# Keyword mapping for event classification
EVENT_KEYWORDS = {
    EventType.EARNINGS: [
        "earnings", "quarterly", "q1", "q2", "q3", "q4",
        "fiscal", "results", "profit", "revenue", "eps",
        "net profit", "net income", "quarter"
    ],
    EventType.MERGER_ACQUISITION: [
        "merger", "acquisition", "acquire", "takeover",
        "m&a", "buyout", "stake", "investment"
    ],
    EventType.REGULATORY: [
        "sebi", "rbi", "regulatory", "approval", "license",
        "compliance", "circular", "notification", "guidelines"
    ],
    EventType.PRODUCT_LAUNCH: [
        "launch", "unveil", "rollout", "new product",
        "introduce", "debut"
    ],
    EventType.MANAGEMENT_CHANGE: [
        "ceo", "cfo", "chairman", "director", "md", "managing director",
        "appoint", "resign", "resignation", "stepped down"
    ],
    EventType.DIVIDEND: [
        "dividend", "payout", "interim dividend", "final dividend"
    ],
    EventType.SPLIT: [
        "split", "stock split", "share split"
    ],
    EventType.BUYBACK: [
        "buyback", "repurchase", "buy back"
    ],
    EventType.GUIDANCE: [
        "guidance", "outlook", "forecast", "projection",
        "target", "estimate"
    ],
    EventType.INSIDER: [
        "insider", "promoter", "promoter group", "stake",
        "holding", "shareholding"
    ],
    EventType.CONTRACT: [
        "contract", "order", "deal", "agreement", "mou",
        "memorandum", "partnership"
    ],
    EventType.LEGAL: [
        "court", "tribunal", "litigation", "lawsuit", "legal",
        "case", "hearing", "verdict", "judgment"
    ],
    EventType.MACRO: [
        "gdp", "inflation", "interest rate", "repo rate",
        "monetary policy", "cpi", "wpi", "iip", "pmi"
    ],
}


def classify_headline(headline: Headline) -> EventType:
    """
    Classify a headline into an event type.

    Args:
        headline: Headline with title and summary

    Returns:
        EventType enum (default UNKNOWN)
    """
    text = (headline.title + " " + headline.summary).lower()

    for event_type, keywords in EVENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return event_type

    return EventType.UNKNOWN


def classify_articles(articles: list) -> list[EventType]:
    """Classify multiple articles/headlines."""
    return [classify_headline(a) for a in articles]


def get_event_confidence(headline: Headline, event_type: EventType) -> float:
    """
    Get confidence score for an event classification.

    Higher if multiple keywords match.
    """
    text = (headline.title + " " + headline.summary).lower()

    if event_type == EventType.UNKNOWN:
        return 0.0

    keywords = EVENT_KEYWORDS.get(event_type, [])
    matches = sum(1 for kw in keywords if kw in text)

    if matches == 0:
        return 0.0
    elif matches == 1:
        return 0.6
    elif matches == 2:
        return 0.8
    else:
        return 0.95