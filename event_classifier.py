"""
Event classification for NSE headlines.
Rule-based regex patterns → event tags with signed sentiment bias.

VADER is blind to financial context. "SEBI imposes ₹5Cr penalty" scores
neutral because no strong English sentiment words exist. Event classifier
catches the regulatory action and applies a negative bias.

Design:
  - EVENT_MAP ordered by specificity (most specific patterns first).
  - First match wins when multiple events match the same headline.
  - \\b word boundaries throughout to avoid partial-word matches.
  - .*? between verbs and nouns to handle real-world word order.

Usage:
    event_type, event_base = classify_headline("TCS wins $2B deal", "")
    # → ("ORDER_WIN", 0.30)

    adjusted = adjust_with_event(vader_compound, event_base)
    # → blends VADER score with event knowledge
"""

import logging
import re

logger = logging.getLogger(__name__)

# Each event entry: (type, base_sentiment, [patterns...])
# base_sentiment ∈ [-1, 1] — what VADER *should* give for this event type
# Used to correct VADER when it's uncertain about financial language.
# ORDER MATTERS: first match wins when multiple patterns fire.
EVENT_MAP = [
    # ── Positive events (most specific first) ──────────────

    ("BUYBACK_DIVIDEND", 0.30, [
        r"\bbuyback\b|\bbuy-back\b",
        r"\bbonus\s+issue\b|\bbonus\s+shares\b|\bbonus\s+ratio\b",
        r"\bdividend\s+(?:declared|announced|approved|interim|final|payout)\b",
        r"(?:declares|declared|announced|approved|interim|final)\s+(?:\S+\s+)?dividend\b",
        r"\bshare\s+split\b|\bstock\s+split\b",
    ]),
    ("ORDER_WIN", 0.30, [
        r"\bwins?\b\s+.*?\b(?:contract|order|deal|mandate)\b",
        r"\bbags?\b\s+.*?\b(?:order|contract)\b",
        r"\bsecure(?:s|d)?\b\s+.*?\b(?:order|contract|deal)\b",
        r"\border\s+worth\b",
        r"\bcontract\s+worth\b",
    ]),
    ("GUIDANCE_POSITIVE", 0.30, [
        r"\braises?\b\s+.*?\b(?:guidance|outlook|forecast)\b",
        r"\bupbeat\s+(?:outlook|guidance)\b",
        r"\bpositive\s+(?:outlook|guidance|view)\b",
        r"\bconfident\s+(?:outlook|guidance)\b",
    ]),
    ("EARNINGS_BEAT", 0.35, [
        r"\bprofit\s+(?:jumps?|surges?|rises?|grows?)\b",
        r"\brevenue\s+(?:jumps?|surges?|rises?|grows?)\b",
        r"\bbeat\s+(?:estimates|expectations)\b",
        r"\bstrong\s+(?:results|quarter|performance|show)\b",
        r"\brecord\s+(?:profit|revenue|income|quarter(?:ly)?)\b",
        r"\bstellar\b.*?\b(?:results?|quarter|performance|show|earnings|revenue|quarterly)\b",
        r"\bexceptional\s+(?:results|quarter|performance)\b",
    ]),
    ("PRODUCT_LAUNCH", 0.20, [
        r"\blaunch(?:es|ed)?\s+(?:new|first|india)\b",
        r"\bunveils?\s+.*?\b(?:product|service|platform|app|vehicle|phone|range|plan|strategy)\b",
        r"\bintroduces?\s+.*?\b(?:product|service|platform|app|vehicle|phone|range|plan)\b",
    ]),
    ("EXPANSION", 0.20, [
        r"\bexpansion\s+(?:plan|drive|into|mode|strategy)\b",
        r"\bnew\s+(?:plant|factory|facility|unit|venture)\b",
        r"\bacquir(?:e|es|ed)\s+.*?\b(?:stake|business|unit|majority)\b",
        r"\binvests?\b\s+.*?\d+\s*(?:cr|crore|mn|bn)\b",
        r"\bforay\s+into\b",
        r"\benters?\b\s+(?:new\s+)?(?:market|segment|geography)\b",
    ]),
    ("MANAGEMENT_POSITIVE", 0.15, [
        r"\bappoints?\b\s+(?:new\s+)?(?:CEO|CFO|MD|chairman|director|president)\b",
        r"\breappoint(?:s|ed)?\b",
        r"\bpromot(?:es?|ed)\b.*?\b(?:to|as)\s+(?:CEO|MD|director|chairman|senior|head|VP|CTO|CFO)\b",
    ]),

    # ── New positive events ──────────────

    ("REGULATORY_APPROVAL", 0.15, [
        r"\bSEBI\s+(?:approves?|clears?|allows?|okays?)\b",
        r"\bRBI\s+(?:approves?|clears?|allows?)\b",
        r"\bCCI\s+(?:approves?|clears?|allows?|okays?)\b",
        r"\bNCLT\s+(?:approves?|clears?|allows?)\b",
        r"\bgets\s+(?:SEBI|RBI|regulatory)\s+(?:approval|clearance|nod)\b",
    ]),
    ("RATING_UPGRADE", 0.20, [
        r"\bupgrad(?:e|es|ed)\s+(?:credit\s+)?(?:rating|outlook)\b",
        r"\brating\s+(?:upgraded|upgrade)\b",
        r"\boutlook\s+(?:revised\s+to\s+positive|positive\s+outlook)\b",
    ]),
    ("JV_MOU", 0.15, [
        r"\bjoint\s+venture\b|\bJV\b",
        r"\bMoU\b|\bmemorandum\s+of\s+understanding\b",
        r"\bstrategic\s+(?:alliance|partnership|collaboration|tie-up)\b",
        r"\bsigns?\s+(?:MoU|MOU|agreement|pact|deal|partnership)\b",
    ]),
    ("FUNDRAISE", 0.15, [
        r"\bQIP\b|\bFPO\b|\brights\s+issue\b",
        r"\bpreferential\s+(?:issue|allotment)\b",
    ]),

    # ── Negative events (most specific first) ──────────────

    ("DEBT_STRESS", -0.40, [
        r"\bdowngrad(?:e|es|ed)\s+(?:credit\s+)?(?:rating|outlook)\b",
        r"\bcredit\s+watch\b",
        r"\bdefault(?:s|ed)?\s+on\s+(?:debt|payment|obligation)\b",
        r"\bNPAs?\b|\bnon-performing\b",
        r"\binsolvency\b|\bbankruptcy\b",
        r"\bdebt\s+(?:trap|burden|crisis|restructuring)\b",
        r"\bliquidity\s+(?:crisis|crunch|squeeze|stress)\b",
    ]),
    ("LITIGATION", -0.35, [
        r"\b(?:imposes?|levies?|slaps?)\b.*?\bpenalty\b|\bpenalty\s+(?:of|imposed|levied)\b|\bpenalize[sd]?\b",
        r"\bfine[sd]?\b\s+(?:of\s+)?\d+",
        r"\bSEBI\s+(?:probe|investigat|notice|order|directive|slaps?|summon)\b",
        r"\bCBI\s+(?:probe|investigat|files\s+case|raids?|charge)\b",
        r"\bED\s+(?:probe|investigat|raids?|attachment)\b",
        r"\bincome\s+tax\s+(?:raids?|survey|notice|probe)\b",
        r"\bshow\s+cause\s+notice\b",
        r"\blegal\s+(?:notice|tussle|battle|dispute|hurdle)\b",
        r"\bsue[sd]?\b|\blawsuit\b|\blitigation\b",
        r"\bfraud\b|\bscam\b|\bembezzlement\b",
        r"\bSFIO\b|\bserious\s+fraud\b",
        r"\bDRI\b|\bdirectorate\s+of\s+revenue\b",
        r"\bNIA\b|\bnational\s+investigation\s+agency\b",
        r"\bregulatory\s+(?:action|restriction|sanction)\s+(?:against|on)\b",
        r"\battachment\s+of\b|\bfreeze(?:s|d)?\s+(?:bank\s+)?accounts?\b",
        r"\bboxed?\s+director\b|\bdirector\s+disqualified\b",
    ]),
    ("REGULATORY", -0.30, [
        r"\bregulatory\s+(?:crackdown|hurdle|barrier|issue|action|probe)\b",
        r"\bRBI\s+(?:restricts?|curbs?|directive|action|slaps?|penalty|frown)\b",
        r"\bcompetition\s+commission\b|\bCCI\s+(?:probe|notice)\b",
        r"\banti[- ]?trust\b",
        r"\bIRDAI\b",
        r"\bDGGI\b",
        r"\btax\s+notice\b|\bGST\s+notice\b",
        r"\bPERDA\b|\bPFRDA\b",
        r"\bRERA\b|\breal\s+estate\s+regulatory\b",
        r"\bNCLT\b|\bNCLAT\b",
        r"\bSAT\b|\bsecurities\s+appellate\b",
        r"\bDGCA\b",
        r"\bTRAI\b",
        r"\bCERC\b|\bcentral\s+electricity\b",
        r"\bDGFT\b",
        r"\bFSSAI\b",
        r"\bed\s+attaches?\b",
    ]),
    ("EARNINGS_MISS", -0.35, [
        r"\bprofit\s+(?:falls?|declines?|drops?|plunges?|slips?|tumbles)\b",
        r"\brevenue\s+(?:falls?|declines?|drops?|plunges?|slips?|tumbles)\b",
        r"\bprofit\s+(?:falls?|declines?|drops?|shrinks)\b",
        r"\bmiss(?:es)?\s+(?:estimates|expectations|target|consensus)\b",
        r"\bweak\s+(?:results|quarter|performance|show|demand)\b",
        r"\bbelow\s+(?:estimates|expectations|consensus|street)\b",
        r"\bloss\s+(?:widens?|deepens?|mounts?|swells)\b",
        r"\bdisappointing\s+(?:results|quarter|performance)\b",
    ]),
    ("GUIDANCE_NEGATIVE", -0.30, [
        r"\blowers?\b\s+.*?\b(?:guidance|outlook|forecast)\b",
        r"\bcuts?\b\s+.*?\b(?:guidance|outlook|forecast)\b",
        r"\bcautious\s+(?:outlook|guidance|view)\b",
    ]),

    # ── New negative events ──────────────

    ("CONTRACT_LOSS", -0.30, [
        r"\bloses?\b\s+.*?\b(?:contract|order|deal|mandate|client)\b",
        r"\bterminated\s+.*?\b(?:contract|order|deal)\b",
        r"\bcancell?(?:ed|ation)?\s+.*?\b(?:order|contract|deal)\b",
        r"\b(?:contract|order|deal)\s+(?:lost|terminated|cancelled)\b",
    ]),
    ("DIVESTMENT", -0.20, [
        r"\bsells?\s+(?:stake|shares|equity|business|subsidiary|unit)\b",
        r"\bdivest(?:s|ed|iture)?\b",
        r"\bpromoter\s+sells?\b",
        r"\bexits?\s+.*?\b(?:venture|business|investment)\b",
        r"\bstake\s+sale\b",
    ]),

    ("MGMT_CHANGE_NEGATIVE", -0.20, [
        r"\bresign(?:s|ed|ation)\b",
        r"\bstep(?:s)?\s+down\b",
        r"\boust(?:er|ed|s)\b",
        r"\bquit(?:s|ted)?\b\s+(?:as|from)\b",
        r"\bsack(?:ed|s)?\b",
        r"\bfir(?:e|es|ed)\b",
    ]),
]

# Cache compiled patterns for performance
_COMPILED = None


def _get_compiled():
    """Lazy-load compiled patterns."""
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = [
            (event_type, base, [re.compile(p, re.IGNORECASE) for p in patterns])
            for event_type, base, patterns in EVENT_MAP
        ]
    return _COMPILED


def classify_headline(title: str, body: str="") -> dict:
    """Classify a headline and return (event_type, event_base).

    First matching event type wins (EVENT_MAP order defines priority).

    Args:
        title: Headline text (required)
        body: Optional body/summary text

    Returns:
        event_type: str or None — e.g. "ORDER_WIN", "LITIGATION"
        event_base: float — base sentiment value [-1, 1]; 0.0 = no event
    """
    if not title:
        return None, 0.0

    text = title + " " + (body or "")

    for event_type, base, patterns in _get_compiled():
        for pattern in patterns:
            if pattern.search(text):
                return event_type, base

    return None, 0.0


def adjust_with_event(compound: float, event_base: dict | None) -> float:
    """Blend VADER compound score with event-based sentiment bias.

    When VADER is confident (|compound| > 0.3) about financial language,
    trust it mostly and nudge slightly with event knowledge.
    When VADER is uncertain (financially neutral headline like "SEBI order"),
    let the event signal dominate — this is where event classifier adds value.

    Args:
        compound: float — VADER compound score [-1, 1]
        event_base: float — event base sentiment [-1, 1], 0.0 = no event

    Returns:
        float — blended compound score [-1, 1]
    """
    if event_base == 0.0:
        return compound

    confidence = abs(compound)
    if confidence > 0.3:
        blended = 0.8 * compound + 0.2 * event_base
    else:
        blended = 0.3 * compound + 0.7 * event_base

    return max(-1.0, min(1.0, blended))
