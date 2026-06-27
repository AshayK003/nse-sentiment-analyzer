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
# Per-ticker direction relative to commodity price rise:
#   +1 = commodity rise is BAD for this ticker (Bearish on rise)
#   -1 = commodity rise is GOOD for this ticker (Bullish on rise)
# 4-tuple: (ticker, direction, bad_reason, good_reason)
CASCADE_MAP = [
    {
        "driver": "Crude Oil",
        "direction": +1,  # crude rises → negative for consumers
        "keywords": [
            r"\bcrude\s*oil\b",
            r"\bcrude\b(?!\s+steel\b)",
            r"\bbrent\b",
            r"\b(?:WTI|NYMEX)\b",
            r"\boil\s+prices?\b",
            r"\bpetrol(?:ium)?\s+prices?\b",
        ],
        "affects": [
            ("BPCL", +1, "Higher input cost — OMC margins compress when crude rises", "Lower input cost — OMC margins expand when crude falls"),
            ("IOC", +1, "Higher input cost — OMCs absorb retail losses", "Lower input cost — OMCs benefit from falling crude"),
            ("HINDPETRO", +1, "Higher input cost — OMC margins follow crude", "Lower input cost — OMC margins recover as crude falls"),
            ("ONGC", -1, "Crude price decline hurts upstream realizations", "Crude price rally boosts upstream realizations"),
            ("INDIGO", +1, "ATF (jet fuel) cost rises — airline margins squeeze", "ATF (jet fuel) cost falls — airline margins improve"),
            ("ASIANPAINT", +1, "Raw material (solvents/resins) linked to crude", "Raw material costs ease with falling crude"),
            ("BERGEPAINT", +1, "Paint raw materials track crude derivatives", "Paint raw material costs ease with crude"),
            ("KANSAINER", +1, "Paint raw materials track crude derivatives", "Paint raw material costs ease with crude"),
        ],
    },
    {
        "driver": "Rupee / USD",
        "direction": +1,  # rupee fall (USD rise) → negative for importers
        "keywords": [
            r"\b(?:Indian\s+)?rupee\b",
            r"\bUSD[-/]INR\b",
            r"\b(?:dollar|INR)\s+(?:weakens?|falls?|strengthens?|rises?|rallies?|declines?)",
            r"\bforex\b",
        ],
        "affects": [
            ("INFY", +1, "Stronger rupee reduces INR value of USD revenue", "Weaker rupee = higher USD revenue value — positive for IT exports"),
            ("TCS", +1, "Stronger rupee reduces INR value of USD revenue", "Weaker rupee = higher USD revenue value — positive for IT exports"),
            ("HCLTECH", +1, "Stronger rupee reduces INR value of USD revenue", "Weaker rupee = higher USD revenue value — positive for IT exports"),
            ("WIPRO", +1, "Stronger rupee reduces INR value of USD revenue", "Weaker rupee = higher USD revenue value — positive for IT exports"),
            ("TECHM", +1, "Stronger rupee reduces INR value of USD revenue", "Weaker rupee = higher USD revenue value — positive for IT exports"),
            ("LTIM", +1, "Stronger rupee reduces INR value of USD revenue", "Weaker rupee = higher USD revenue value — positive for IT exports"),
            ("SUNPHARMA", +1, "Stronger rupee reduces INR value of USD pharma revenue", "Weaker rupee = higher USD pharma revenue value — positive for exports"),
            ("DRREDDY", +1, "Stronger rupee reduces INR value of USD pharma revenue", "Weaker rupee = higher USD pharma revenue value — positive for exports"),
            ("CIPLA", +1, "Stronger rupee reduces INR value of USD pharma revenue", "Weaker rupee = higher USD pharma revenue value — positive for exports"),
            ("DIVISLAB", +1, "Stronger rupee reduces INR value of USD pharma revenue", "Weaker rupee = higher USD pharma revenue value — positive for exports"),
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
            ("GOLDBEES", -1, "Gold price decline impacts metal value", "Gold price rally benefits metal holdings"),
            ("TITAN", -1, "Gold price decline impacts jewellery demand & inventory", "Gold price rally boosts jewellery demand & inventory value"),
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
            ("TATASTEEL", -1, "Steel price decline compresses revenue realisations", "Steel price rise boosts revenue realisations"),
            ("JSWSTEEL", -1, "Steel price decline compresses revenue realisations", "Steel price rise boosts revenue realisations"),
            ("SAIL", -1, "Steel price decline compresses revenue realisations", "Steel price rise boosts revenue realisations"),
            ("JINDALSTEL", -1, "Steel price decline compresses revenue realisations", "Steel price rise boosts revenue realisations"),
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
            ("GUJGASLTD", +1, "Higher gas procurement cost — city gas margins compress", "Lower gas procurement cost — city gas margins expand"),
            ("IGL", +1, "Higher gas procurement cost — CNG/piped gas margins compress", "Lower gas procurement cost — CNG/piped gas margins expand"),
            ("MGL", +1, "Higher gas procurement cost — city gas margins compress", "Lower gas procurement cost — city gas margins expand"),
            ("GAIL", +1, "Higher gas prices — transmission margins benefit but volume may drop", "Higher gas prices — transmission margins benefit but volume may drop"),
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
            ("COALINDIA", -1, "Lower coal prices — revenue declines for Coal India", "Higher coal prices — revenue positive for Coal India"),
            ("NTPC", +1, "Higher fuel cost — power generation margins compress", "Lower fuel cost — power generation margins recover"),
            ("TATAPOWER", +1, "Higher fuel cost — power generation margins may compress", "Lower fuel cost — power generation margins may recover"),
        ],
    },
    {
        "driver": "Sugar",
        "direction": -1,  # sugar falls → bad for mills
        "keywords": [
            r"\bsugar\s+prices?\b",
            r"\bsugar\s+rates?\b",
            r"\bsugar\s+(?:production|output|supply)\b",
            r"\b(?:sugar|sweetener)\s+(?:surges?|falls?|rallies?|declines?|steady)",
        ],
        "affects": [
            ("BAJAJHIND", -1, "Sugar price decline compresses mill realizations", "Sugar price rally boosts mill realizations"),
            ("BALRAMPUR", -1, "Sugar price decline compresses mill realizations", "Sugar price rally boosts mill realizations"),
            ("DHAMPUR", -1, "Sugar price decline compresses mill realizations", "Sugar price rally boosts mill realizations"),
            ("TRIVENI", -1, "Sugar price decline compresses mill realizations", "Sugar price rally boosts mill realizations"),
            ("DCMSHRIRAM", -1, "Sugar price decline compresses mill realizations", "Sugar price rally boosts mill realizations"),
        ],
    },
    {
        "driver": "Aluminum",
        "direction": -1,  # aluminum falls → bad for producers
        "keywords": [
            r"\balumi(?:num|nium)\s+prices?\b",
            r"\b(?:LME|CME)\s+alumi(?:num|nium)\b",
        ],
        "affects": [
            ("HINDALCO", -1, "Aluminum price decline compresses revenue realizations", "Aluminum price rally boosts revenue realizations"),
            ("NATIONALUM", -1, "Aluminum price decline compresses revenue realizations", "Aluminum price rally boosts revenue realizations"),
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
    r"spikes?|spiked|hikes?|hiked|gains?|gained|rises?|rising|"
    r"skyrockets?|skyrocketed|appreciates?|strengthens?|strengthened)\b",
    re.IGNORECASE,
)
_DIR_DOWN = re.compile(
    r"\b(?:falls?|fell|drops?|dropped|declines?|declined|"
    r"slumps?|slumped|plunges?|plunged|tumbles?|tumbled|"
    r"sinks?|sank|crash(?:es|ed)?|collapses?|collapsed|"
    r"weakens?|weakened|slides?|sliding|"
    r"plummets?|plummeted|tanks?|tanked|nosedives?|nosedived|"
    r"depreciates?)\b",
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


def detect_cascade(news_items, ticker_lookup=None, focus_ticker=None):
    """Scan a list of news items for commodity/macro keywords.

    Args:
        news_items: list of dicts with 'title' and 'body' keys.
        ticker_lookup: optional dict {ticker→company_name} for name resolution.
                       Falls back to the ticker symbol if not provided.
        focus_ticker: optional str — if set, that ticker's commodity is
                      sorted first and highlighted in the results.

    Returns:
        list of dicts:
            driver: str — commodity name (e.g. "Crude Oil")
            direction: +1 (rise) or -1 (fall) — semantic direction
            impact: +1 (Bearish/bad), -1 (Bullish/good)
            affects: list of dicts with keys: ticker, reason, company, searched
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

    focus_ticker = (focus_ticker or "").upper()
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

        # Build per-ticker mention patterns (word-boundary ticker + company name)
        ticker_pats = {}
        for ticker, ticker_dir, bad_reason, good_reason in entry["affects"]:
            company = (ticker_lookup or {}).get(ticker, "")
            pats = [re.compile(rf"\b{re.escape(ticker)}\b", re.IGNORECASE)]
            if company:
                pats.append(re.compile(rf"\b{re.escape(company)}\b", re.IGNORECASE))
            ticker_pats[ticker] = pats

        # Check each ticker against all matching articles
        ticker_mentioned = {}
        for ticker in ticker_pats:
            for text in matching_texts:
                if any(p.search(text) for p in ticker_pats[ticker]):
                    ticker_mentioned[ticker] = True
                    break

        # Build resolved list — compute per-ticker impact, pick reason, mark searched
        any_mentioned = False
        resolved = []
        for ticker, ticker_dir, bad_reason, good_reason in entry["affects"]:
            company = (ticker_lookup or {}).get(ticker, ticker)
            ticker_impact = direction * ticker_dir
            reason = good_reason if ticker_impact < 0 else bad_reason
            mentioned = ticker_mentioned.get(ticker, False)
            if mentioned:
                any_mentioned = True
            resolved.append({
                "ticker": ticker,
                "reason": reason,
                "company": company,
                "mentioned": mentioned,
                "searched": ticker == focus_ticker,
                "ticker_impact": ticker_impact,
            })

        # Filter to mentioned tickers only (fallback to all if none mentioned)
        if any_mentioned:
            resolved = [a for a in resolved if a["mentioned"]]

        # Sort: searched ticker first, then alphabetical
        resolved.sort(key=lambda a: (0 if a["searched"] else 1, a["ticker"]))

        # Remove mention flag from output (internal only)
        for a in resolved:
            del a["mentioned"]

        # Skip commodities that don't affect the searched ticker (when known)
        if focus_ticker and not any(a["searched"] for a in resolved):
            continue

        results.append({
            "driver": driver,
            "direction": direction,
            "impact": impact if impact in (1, -1) else 1,
            "affects": resolved,
            "matched_articles": len(matching_texts),
        })

    # Sort: focus ticker's commodity first
    if focus_ticker:
        results.sort(key=lambda r: 0 if any(a["searched"] for a in r["affects"]) else 1)

    return results
