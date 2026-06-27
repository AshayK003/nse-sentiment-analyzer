"""
Cascade/Ripple Tracking — commodity → affected-sector detection.

When news mentions a commodity (crude oil, gold, rupee, iron ore),
this module flags which NSE tickers are indirectly affected and why.

Design:
  - CASCADE_MAP defines each commodity driver, its direction (rise/fall),
    and the tickers it impacts with a human-readable reason.
  - Keyword matching happens against news text that is *already fetched*
    by the sentiment pipeline — no extra network calls.
  - detect_cascade() returns simple dicts consumed by render.py.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ─── Lookup: NSE_TICKERS should be passed in for name resolution ───

# (commodity_key, direction, keywords, [ (ticker, reason), ... ])
# direction: +1 = commodity rise is bad for ticker, -1 = commodity fall is bad
# Each commodity's tickers are a list of (symbol, impact_reason).
# Impact_reason is a short sentence fragment shown in the UI.
# direction_up / direction_down are scanned in matched article text to infer
# whether the commodity is RISING or FALLING. If no direction keywords match,
# the default CASCADE_MAP direction is used as a fallback (arrow up + Bearish).
CASCADE_MAP = [
    {
        "driver": "Crude Oil",
        "direction": +1,  # crude rises → negative for consumers
        "keywords": [
            r"\bcrude\s*oil\b",
            r"\bcrude\b",
            r"\bbrent\b",
            r"\b(?:WTI|NYMEX)\b",
            r"\boil\s+prices?\b",
            r"\bpetrol(?:ium)?\s+prices?\b",
        ],
        "affects": [
            ("BPCL", "Higher input cost — OMC margins compress when crude rises"),
            ("IOC", "Higher input cost — OMCs absorb retail losses"),
            ("HINDPETRO", "Higher input cost — OMC margins follow crude"),
            ("INDIGO", "ATF (jet fuel) cost rises — airline margins squeeze"),
            ("ASIANPAINT", "Raw material (solvents/resins) linked to crude"),
            ("BERGEPAINT", "Paint raw materials track crude derivatives"),
            ("KANSAINER", "Paint raw materials track crude derivatives"),
        ],
    },
    {
        "driver": "Rupee / USD",
        "direction": +1,  # rupee fall (USD rise) → negative for importers
        "keywords": [
            r"\bRupee\b",
            r"\b(?:Indian\s+)?rupee\b",
            r"\bUSD[-/]INR\b",
            r"\b(?:dollar|INR)\s+(?:weakens?|falls?|strengthens?|rises?|rallies?|declines?)",
            r"\bforex\b",
        ],
        "affects": [
            ("INFY", "Weaker rupee = higher USD revenue value — positive for IT exports"),
            ("TCS", "Weaker rupee = higher USD revenue value — positive for IT exports"),
            ("HCLTECH", "Weaker rupee = higher USD revenue value — positive for IT exports"),
            ("WIPRO", "Weaker rupee = higher USD revenue value — positive for IT exports"),
            ("TECHM", "Weaker rupee = higher USD revenue value — positive for IT exports"),
            ("LTIM", "Weaker rupee = higher USD revenue value — positive for IT exports"),
        ],
    },
    {
        "driver": "Gold",
        "direction": -1,  # gold falls → negative for gold ETFs/jewellers
        "keywords": [
            r"\bgold\s+prices?\b",
            r"\bgold\s+rates?\b",
            r"\b(?:gold|yellow\s+metal)\s+(?:surges?|falls?|rallies?|declines?|steady)",
            r"\bspot\s+gold\b",
        ],
        "affects": [
            ("GOLDBEES", "Gold price movement directly tracks the underlying metal"),
            ("TITAN", "Jewellery demand & inventory value tracks gold prices"),
        ],
    },
    {
        "driver": "Iron Ore/Steel",
        "direction": -1,  # steel/iron falls → negative for steel producers
        "keywords": [
            r"\biron\s+ore\b",
            r"\bsteel\s+prices?\b",
            r"\bcoking\s+coal\b",
            r"\b(?:HRC|CRC)\s+steel\b",
        ],
        "affects": [
            ("TATASTEEL", "Steel price realisations directly impact revenue"),
            ("JSWSTEEL", "Steel price realisations directly impact revenue"),
            ("SAIL", "Steel price realisations directly impact revenue"),
            ("JINDALSTEL", "Steel price realisations directly impact revenue"),
        ],
    },
    {
        "driver": "Natural Gas",
        "direction": +1,  # gas rises → negative for users
        "keywords": [
            r"\bnatural\s+gas\b",
            r"\b(?:LNG|CNG)\s+prices?\b",
            r"\bgas\s+prices?\b",
        ],
        "affects": [
            ("GUJGASLTD", "Higher gas procurement cost — city gas margins compress"),
            ("IGL", "Higher gas procurement cost — CNG/piped gas margins compress"),
            ("MGL", "Higher gas procurement cost — city gas margins compress"),
            ("GAIL", "Higher gas prices — transmission margins benefit but volume may drop"),
        ],
    },
    {
        "driver": "Coal",
        "direction": +1,  # coal rises → negative for power/steel
        "keywords": [
            r"\bcoal\s+prices?\b",
            r"\bthermal\s+coal\b",
        ],
        "affects": [
            ("COALINDIA", "Higher coal prices — revenue positive for Coal India"),
            ("NTPC", "Higher fuel cost — power generation margins compress"),
            ("TATAPOWER", "Higher fuel cost — power generation margins may compress"),
        ],
    },
]

# Direction indicators — words that signal commodity price direction.
# Scanned in articles that already matched a commodity keyword.
# High-precision only — avoid common words like "high", "up", "lower" that
# create false positives in non-price contexts.
_DIR_UP = re.compile(
    r"\b(?:surges?|surged|jumps?|jumped|climbs?|climbed|"
    r"rally|rallies|rallied|soars?|soared|rebounds?|rebounded|"
    r"spikes?|spiked|hikes?|hiked|gains?|gained|rises?|rising)\b",
    re.IGNORECASE,
)
_DIR_DOWN = re.compile(
    r"\b(?:falls?|fell|drops?|dropped|declines?|declined|"
    r"slumps?|slumped|plunges?|plunged|tumbles?|tumbled|"
    r"sinks?|sank|crash(?:es|ed)?|collapses?|collapsed|"
    r"weakens?|weakened|slides?|sliding)\b",
    re.IGNORECASE,
)

# Pre-compile patterns for performance — keyed by driver name
_COMPILED_PATTERNS = None


def _get_compiled():
    global _COMPILED_PATTERNS
    if _COMPILED_PATTERNS is None:
        _COMPILED_PATTERNS = {
            entry["driver"]: [re.compile(p, re.IGNORECASE) for p in entry["keywords"]]
            for entry in CASCADE_MAP
        }
    return _COMPILED_PATTERNS


def detect_cascade(news_items, ticker_lookup=None):
    """Scan a list of news items for commodity/macro keywords.

    Args:
        news_items: list of dicts with 'title' and 'body' keys.
        ticker_lookup: optional dict {ticker→company_name} for name resolution.
                       Falls back to the ticker symbol if not provided.

    Returns:
        list of dicts:
            driver: str — commodity name (e.g. "Crude Oil")
            direction: +1 (rise) or -1 (fall) — semantic direction
            affects: list of (ticker, reason, company_name)
            matched_articles: int — how many news items triggered
    """
    if not news_items:
        return []

    patterns = _get_compiled()
    # Build combined text from all news items (deduplicated)
    texts = []
    for item in news_items:
        text = (item.get("title") or "") + " " + (item.get("body") or "")
        texts.append(text)

    results = []

    for entry in CASCADE_MAP:
        driver = entry["driver"]
        driver_patterns = patterns[driver]
        # Find which articles mention this commodity
        matching_texts = []
        for text in texts:
            for pat in driver_patterns:
                if pat.search(text):
                    matching_texts.append(text)
                    break  # one match per article counted once

        if not matching_texts:
            continue

        # Infer commodity price direction from matched articles
        up_count = 0
        down_count = 0
        for text in matching_texts:
            if _DIR_UP.search(text):
                up_count += 1
            if _DIR_DOWN.search(text):
                down_count += 1

        if up_count > down_count:
            direction = 1  # commodity price rose
        elif down_count > up_count:
            direction = -1  # commodity price fell
        else:
            # No clear direction — fall back to CASCADE_MAP default
            direction = entry["direction"]

        # Net impact on ticker: +1 = Bad (Bearish), -1 = Good (Bullish)
        impact = direction * entry["direction"]

        # Resolve company names for affected tickers
        resolved = []
        for ticker, reason in entry["affects"]:
            company = (ticker_lookup or {}).get(ticker, ticker)
            resolved.append((ticker, reason, company))

        results.append({
            "driver": driver,
            "direction": direction,
            "impact": impact if impact in (1, -1) else 1,
            "affects": resolved,
            "matched_articles": len(matching_texts),
        })

    return results
