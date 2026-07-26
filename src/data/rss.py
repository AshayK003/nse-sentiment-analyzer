"""
News fetcher — RSS feeds + yfinance news fallback.
Pure data layer: no sentiment analysis, no classification.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import feedparser
import yfinance as yf

from .cache import cached, invalidate
from ..contracts import Headline, NewsArticle, SentimentScore

log = logging.getLogger(__name__)

# NSE-relevant RSS feeds (Indian financial news)
NSE_RSS_FEEDS = [
    ("economictimes", "https://economictimes.indiatimes.com/rssfeedsdefault.cms"),
    ("moneycontrol", "https://www.moneycontrol.com/rss/business.xml"),
    ("livemint", "https://www.livemint.com/rss/markets"),
    ("business-standard", "https://www.business-standard.com/rss/markets-106.rss"),
    ("thehindu-business", "https://www.thehindu.com/business/feeder/default.rss"),
    ("zeebiz", "https://www.zeebiz.com/rss/feed"),
    ("financialexpress", "https://www.financialexpress.com/market/rss.xml"),
    ("bseindia", "https://www.bseindia.com/rss-feeds/bse-corporate-announcements.xml"),
]

# Keywords for ticker extraction from headlines
TICKER_KEYWORDS = {
    "reliance": "RELIANCE", "tcs": "TCS", "hdfc": "HDFCBANK", "icici": "ICICIBANK",
    "infosys": "INFY", "hindustan unilever": "HINDUNILVR", "itc": "ITC",
    "bharti airtel": "BHARTIARTL", "sbi": "SBIN", "bajaj finance": "BAJFINANCE",
    "kotak": "KOTAKBANK", "larsen": "LT", "axis bank": "AXISBANK", "maruti": "MARUTI",
    "asian paints": "ASIANPAINT", "titan": "TITAN", "sun pharma": "SUNPHARMA",
    "ultratech": "ULTRACEMCO", "nestle": "NESTLEIND", "power grid": "POWERGRID",
    "ntpc": "NTPC", "ongc": "ONGC", "coal india": "COALINDIA", "tata steel": "TATASTEEL",
    "tata motors": "TATAMOTORS", "jsw steel": "JSWSTEEL", "adani ports": "ADANIPORTS",
    "adani enterprises": "ADANIENT", "britannia": "BRITANNIA", "dr reddy": "DRREDDY",
    "cipla": "CIPLA", "divis labs": "DIVISLAB", "eicher motors": "EICHERMOT",
    "grasim": "GRASIM", "hcl tech": "HCLTECH", "heromotocorp": "HEROMOTOCO",
    "hindalco": "HINDALCO", "indusind bank": "INDUSINDBK", "bajaj auto": "BAJAJ-AUTO",
    "shriram finance": "SHRIRAMFIN", "tech mahindra": "TECHM", "wipro": "WIPRO",
    "bajaj finserv": "BAJAJFINSV", "apollo hospitals": "APOLLOHOSP",
    "adani power": "ADANIPOWER", "adani green": "ADANIGREEN", "adani total gas": "ATGL",
    "adani transmission": "ADANITRANS", "jindal steel": "JINDALSTEL",
    "vedanta": "VEDL", "hindustan zinc": "HINDZINC", "national aluminium": "NATIONALUM",
    "gail": "GAIL", "iocl": "IOC", "bpcl": "BPCL", "hpcl": "HPCL",
    "ongc": "ONGC", "oil india": "OIL", "mahindra & mahindra": "M&M",
    "mahindra": "M&M", "m&m": "M&M", "pnb": "PNB", "bank of baroda": "BANKBARODA",
    "canara bank": "CANBK", "union bank": "UNIONBANK", "indian bank": "INDIANB",
    "bank of india": "BANKINDIA", "central bank": "CENTRALBK", "indian overseas": "IOB",
    "punjab & sind": "PSB", "uco bank": "UCOBANK", "maharashtra bank": "MAHABANK",
    "karur vysya": "KARURVYSYA", "city union": "CUB", "federal bank": "FEDERALBNK",
    "j&k bank": "J&KBANK", "south indian": "SOUTHBANK", "tamilnad mercantile": "TMB",
    "dhanlaxmi": "DHANBANK", "karnataka bank": "KTKBANK", "lakshmi vilas": "LAKSHVILAS",
    "rbl bank": "RBLBANK", "yes bank": "YESBANK", "idfc first": "IDFCFIRSTB",
    "bandhan bank": "BANDHANBNK", "au small finance": "AUBANK",
    "equitas": "EQUITAS", "ujjivan": "UJJIVAN", "suryoday": "SURYODAY",
    "fincare": "FINCARE", "esaf": "ESAFBANK", "north east": "NESB",
    "capital small": "CAPITALSFB", "shivalik": "SHIVALIK", "utkarsh": "UTKARSH",
}


def _extract_ticker_from_text(text: str) -> Optional[str]:
    """Extract NSE ticker from text using keyword matching."""
    text_lower = text.lower()
    for keyword, ticker in TICKER_KEYWORDS.items():
        if keyword in text_lower:
            return ticker
    return None


def _parse_rss_entry(entry: dict, source: str) -> Optional[Headline]:
    """Parse a single RSS feed entry into Headline."""
    try:
        title = entry.get("title", "").strip()
        summary = entry.get("summary", entry.get("description", "")).strip()
        url = entry.get("link", "").strip()

        if not title or not url:
            return None

        # Parse published date
        published = None
        if "published_parsed" in entry and entry["published_parsed"]:
            published = datetime(*entry["published_parsed"][:6])
        elif "updated_parsed" in entry and entry["updated_parsed"]:
            published = datetime(*entry["updated_parsed"][:6])
        else:
            published = datetime.now()

        ticker = _extract_ticker_from_text(f"{title} {summary}")

        return Headline(
            title=title,
            summary=summary,
            url=url,
            source=source,
            published=published,
            ticker=ticker or "",
        )
    except Exception as e:
        log.debug("Failed to parse RSS entry from %s: %s", source, e)
        return None


@cached(ttl_seconds=900, key_prefix="news:")
def fetch_market_headlines(
    limit: int = 50,
    _force_refresh: bool = False,
) -> list[Headline]:
    """
    Fetch market headlines from all RSS feeds.

    Args:
        limit: Maximum total headlines to return
        _force_refresh: Force cache bypass

    Returns:
        List of Headline objects, sorted by published date (newest first)
    """
    all_headlines = []

    for source_name, feed_url in NSE_RSS_FEEDS:
        try:
            log.debug("Fetching RSS: %s (%s)", source_name, feed_url)
            feed = feedparser.parse(feed_url)

            if feed.bozo and feed.bozo_exception:
                log.warning("RSS parse warning for %s: %s", source_name, feed.bozo_exception)

            for entry in feed.entries[:20]:  # Limit per feed
                headline = _parse_rss_entry(entry, source_name)
                if headline:
                    all_headlines.append(headline)

        except Exception as e:
            log.error("RSS fetch failed for %s: %s", source_name, e)
            continue

    # Sort by published date (newest first)
    all_headlines.sort(key=lambda h: h.published, reverse=True)

    log.info("Fetched %d headlines from %d RSS feeds", len(all_headlines), len(NSE_RSS_FEEDS))
    return all_headlines[:limit]


@cached(ttl_seconds=3600, key_prefix="news_ticker:")
def fetch_news_for_ticker(
    ticker: str,
    limit: int = 20,
    _force_refresh: bool = False,
) -> list[NewsArticle]:
    """
    Fetch news articles specifically for a ticker.

    Strategy:
    1. Try yfinance news (has ticker-specific news)
    2. Fallback to RSS headlines filtered by ticker
    3. Combine and deduplicate

    Args:
        ticker: Stock symbol (e.g., "RELIANCE")
        limit: Maximum articles to return
        _force_refresh: Force cache bypass

    Returns:
        List of NewsArticle with sentiment placeholder (0.0)
    """
    ticker = ticker.upper().replace(".NS", "").replace(".BO", "")
    articles = []

    # 1. yfinance news
    try:
        yf_ticker = yf.Ticker(f"{ticker}.NS")
        news = yf_ticker.news

        if news:
            for item in news[:limit]:
                title = item.get("title", "").strip()
                url = item.get("link", item.get("url", "")).strip()
                summary = item.get("summary", item.get("description", "")).strip()
                publisher = item.get("publisher", "Yahoo Finance")
                published_ts = item.get("providerPublishTime", 0)

                if title and url:
                    articles.append(NewsArticle(
                        title=title,
                        url=url,
                        source=publisher,
                        published=datetime.fromtimestamp(published_ts) if published_ts else datetime.now(),
                        ticker=ticker,
                        sentiment=0.0,  # Placeholder - strategy layer computes this
                        summary=summary,
                    ))
    except Exception as e:
        log.debug("yfinance news failed for %s: %s", ticker, e)

    # 2. RSS fallback - filter by ticker
    if len(articles) < limit:
        rss_headlines = fetch_market_headlines(limit=100, _force_refresh=_force_refresh)
        for h in rss_headlines:
            if h.ticker == ticker:
                articles.append(NewsArticle(
                    title=h.title,
                    url=h.url,
                    source=h.source,
                    published=h.published,
                    ticker=ticker,
                    sentiment=0.0,
                    summary=h.summary,
                ))

    # Deduplicate by URL
    seen = set()
    unique = []
    for a in articles:
        if a.url not in seen:
            seen.add(a.url)
            unique.append(a)

    log.info("Fetched %d news articles for %s", len(unique), ticker)
    return unique[:limit]


def invalidate_ticker_news(ticker: str) -> int:
    """Invalidate news cache for a ticker."""
    ticker = ticker.upper().replace(".NS", "").replace(".BO", "")
    return invalidate(pattern=f"news_ticker:{ticker}")