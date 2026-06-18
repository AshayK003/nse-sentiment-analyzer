"""
Data fetching for NSE Sentiment Analyzer.
Stock data via yfinance + news via RSS + DuckDuckGo fallback.
"""

import yfinance as yf
import requests
import feedparser
import time
import streamlit as st
import subprocess
import re
from datetime import datetime
from duckduckgo_search import DDGS
from persistence import cache_get, cache_set


# ─── yfinance: set browser User-Agent to avoid 429 rate limiting ───
_session = requests.Session()
_session.headers["User-Agent"] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
yf.utils._session = _session
# Some yfinance versions read from a module-level session
yf._session = _session

# ─── NSE Tickers ───
NSE_TICKERS = {
    "RELIANCE": "Reliance Industries",
    "HDFCBANK": "HDFC Bank",
    "TCS": "Tata Consultancy Services",
    "INFY": "Infosys",
    "ICICIBANK": "ICICI Bank",
    "SBIN": "State Bank of India",
    "BHARTIARTL": "Bharti Airtel",
    "ITC": "ITC Ltd",
    "KOTAKBANK": "Kotak Mahindra Bank",
    "LT": "Larsen & Toubro",
    "AXISBANK": "Axis Bank",
    "BAJFINANCE": "Bajaj Finance",
    "WIPRO": "Wipro Ltd",
    "TITAN": "Titan Company",
    "MARUTI": "Maruti Suzuki",
    "NTPC": "NTPC Ltd",
    "ONGC": "Oil & Natural Gas Corp",
    "POWERGRID": "Power Grid Corp",
    "HCLTECH": "HCL Technologies",
    "SUNPHARMA": "Sun Pharmaceutical",
    "ULTRACEMCO": "UltraTech Cement",
    "HINDUNILVR": "Hindustan Unilever",
    "ASIANPAINT": "Asian Paints",
    "BAJAJFINSV": "Bajaj Finserv",
    "TATAMOTORS": "Tata Motors",
    "TATASTEEL": "Tata Steel",
    "JSWSTEEL": "JSW Steel",
    "ADANIENT": "Adani Enterprises",
    "ADANIPORTS": "Adani Ports",
    "NESTLEIND": "Nestlé India",
    "DMART": "Avenue Supermarts",
    "ZOMATO": "Zomato Ltd",
    "HAL": "Hindustan Aeronautics",
    "COALINDIA": "Coal India",
    "IOC": "Indian Oil Corp",
    "BPCL": "Bharat Petroleum",
    "GRASIM": "Grasim Industries",
    "EICHERMOT": "Eicher Motors",
    "HEROMOTOCO": "Hero MotoCorp",
    "TRENT": "Trent Ltd",
    "BAJAJ-AUTO": "Bajaj Auto",
    "VEDL": "Vedanta Ltd",
    "TATACONSUM": "Tata Consumer",
    "DIVISLAB": "Divi's Laboratories",
    "CIPLA": "Cipla",
    "DRREDDY": "Dr. Reddy's Labs",
    "SBILIFE": "SBI Life Insurance",
    "HDFCLIFE": "HDFC Life Insurance",
    "BRITANNIA": "Britannia Industries",
    "TECHM": "Tech Mahindra",
    "LTIM": "LTIMindtree",
    "NIFTYBEES": "Nippon India ETF Nifty 50",
    "GOLDBEES": "Nippon India ETF Gold BeES",
    "NEXT50IETF": "Nippon India ETF Junior BeES",
    "MIDCAPETF": "Nippon India ETF Midcap 150",
    "MODEFENCE": "Mirae Asset Defence ETF",
    "MAKEINDIA": "Mirae Asset Manufacturing ETF",
    "ENERGY": "Mirae Asset Energy ETF",
    "METALETF": "Mirae Asset Metal ETF",
    "PWL": "PW Lakshmi AI & Tech Fund",
    "GROWW": "Groww Asset Management",
    "M&M": "Mahindra & Mahindra",
    "TATAPOWER": "Tata Power",
    "HINDALCO": "Hindalco Industries",
    "INDUSINDBK": "IndusInd Bank",
    "BANKBARODA": "Bank of Baroda",
    "PNB": "Punjab National Bank",
    "BEL": "Bharat Electronics",
    "MARICO": "Marico Ltd",
    "DABUR": "Dabur India",
    "GODREJCP": "Godrej Consumer Products",
    "PIDILITIND": "Pidilite Industries",
    "HAVELLS": "Havells India",
    "TORNTPHARM": "Torrent Pharmaceuticals",
    "APOLLOHOSP": "Apollo Hospitals",
    "LUPIN": "Lupin Ltd",
    "BIOCON": "Biocon Ltd",
    "INDIGO": "InterGlobe Aviation",
    "DLF": "DLF Ltd",
    "IEX": "Indian Energy Exchange",
    "IRCTC": "IRCTC",
    "JUBLFOOD": "Jubilant FoodWorks",
    "TVSMOTOR": "TVS Motor Company",
    "ABB": "ABB India",
    "SIEMENS": "Siemens India",
    "POLYCAB": "Polycab India",
    "DIXON": "Dixon Technologies",
    "VBL": "Varun Beverages",
    "YESBANK": "Yes Bank",
    "IDFCFIRSTB": "IDFC First Bank",
    "ADANIPOWER": "Adani Power",
    "ADANIGREEN": "Adani Green Energy",
    "ADANITRANS": "Adani Energy Solutions",
    "IRFC": "IRFC",
    "RVNL": "RVNL",
    "NHPC": "NHPC Ltd",
    "SOLARINDS": "Solar Industries",
    "ASTRAL": "Astral Ltd",
    "BALKRISIND": "Balkrishna Industries",
    "PFC": "Power Finance Corp",
    "RECLTD": "REC Ltd",
}


def _is_numeric(v):
    """Check if value is a number (int or float, not bool, not None)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def format_price(v):
    """Format a value for display, returning 'N/A' for missing data."""
    if v is None:
        return "N/A"
    if not _is_numeric(v):
        return str(v)
    return v


def format_large_num(n):
    """Format large numbers in Indian notation (Cr, L)."""
    if not _is_numeric(n):
        return "N/A"
    if n >= 1_00_00_000:
        return f"₹{n / 1_00_00_000:.2f}Cr"
    elif n >= 1_00_000:
        return f"₹{n / 1_00_000:.2f}L"
    elif n >= 1_000:
        return f"₹{n:,.0f}"
    return f"₹{n}"


def get_stock_info(ticker):
    """Fetch stock data from yfinance with retry and backoff."""
    cached = cache_get(f"stock_{ticker}")
    if cached:
        return cached
    try:
        stock = yf.Ticker(f"{ticker}.NS")

        # Retry info with backoff (this is the heaviest yfinance call)
        # Yahoo sometimes returns empty {} even without 429 — retry those too
        info = None
        for attempt in range(3):
            try:
                info = stock.info
                if info and len(info) > 10:
                    break
                # Empty or near-empty response — wait and retry
                wait = 2 ** attempt
                time.sleep(wait)
                info = None
            except Exception as e:
                if "Too Many" in str(e) or "429" in str(e):
                    wait = 2 ** attempt
                    time.sleep(wait)
                    continue
                raise

        if not info:
            raise Exception("Empty response from Yahoo Finance")

        # Retry history with backoff on any transient failure
        hist = None
        for attempt in range(3):
            try:
                hist = stock.history(period="5d")
                if hist is not None:
                    break
            except Exception as e:
                wait = 2 ** attempt + 1
                time.sleep(wait)
                continue

        if hist is not None and not hist.empty:
            current_price = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current_price
            change = float(current_price - prev_close)
            change_pct = float((change / prev_close) * 100)
            day_high = float(hist["High"].iloc[-1])
            day_low = float(hist["Low"].iloc[-1])
            volume = int(hist["Volume"].iloc[-1])
        else:
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            change = info.get("regularMarketChange")
            change_pct = info.get("regularMarketChangePercent")
            day_high = info.get("dayHigh")
            day_low = info.get("dayLow")
            volume = info.get("volume")

        result = {
            "name": info.get("longName", info.get("shortName", ticker)),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "current_price": current_price,
            "change": change,
            "change_pct": change_pct,
            "day_high": day_high,
            "day_low": day_low,
            "volume": volume,
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
        }
        cache_set(f"stock_{ticker}", result)
        return result
    except Exception as e:
        st.error(f"Could not fetch data for {ticker}: {e}")
        return None


def _parse_date(d):
    """Parse RSS date tuple to ISO date string."""
    try:
        return datetime(*d[:6]).isoformat()[:10]
    except Exception:
        return ""


def _relevant(ticker, company_name, title, body):
    """Check if a headline is relevant to the given ticker/company."""
    text = (title + " " + (body or "")).lower()
    words = set(ticker.lower().split()) | set(company_name.lower().split())
    return any(w in text for w in words if len(w) > 2)


# ─── RSS Feeds ───
# Yahoo Finance RSS removed (returns 429 / rate-limited on cloud IPs)
# LiveMint and Business Standard tested; BS returns 403

TICKER_RSS_FEEDS = [
    # Google News RSS for ticker-specific results
    lambda t, c: f"https://news.google.com/rss/search?q={t}+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en",
    lambda t, c: f"https://news.google.com/rss/search?q={c}+NSE&hl=en-IN&gl=IN&ceid=IN:en" if c != t else None,
]

INDIA_RSS_FEEDS = [
    ("Moneycontrol Buzzing", "https://www.moneycontrol.com/rss/buzzingstocks.xml"),
    ("Moneycontrol News", "https://www.moneycontrol.com/rss/latestnews.xml"),
    ("Moneycontrol Reports", "https://www.moneycontrol.com/rss/marketreports.xml"),
    ("Economic Times Markets", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("Economic Times Company", "https://economictimes.indiatimes.com/news/company/rssfeeds/2143429.cms"),
    ("LiveMint Markets", "https://www.livemint.com/rss/markets"),
    ("NDTV Profit", "https://feeds.feedburner.com/ndtvprofit-latest"),
]

SOURCE_LABELS = {
    "google news": "Google News",
    "moneycontrol buzzing": "Moneycontrol",
    "moneycontrol news": "Moneycontrol",
    "moneycontrol reports": "Moneycontrol",
    "economic times markets": "Economic Times",
    "economic times company": "Economic Times",
    "livemint markets": "LiveMint",
    "ndtv profit": "NDTV Profit",
    "duckduckgo": "DuckDuckGo",
    "reddit": "Reddit",
}


def fetch_reddit_news(ticker, company_name, max_results=5):
    """Fetch stock-related Reddit posts via rdt-cli (local-only, silently skipped if unavailable)."""
    try:
        query = f"{ticker} NSE stock"
        result = subprocess.run(
            ["rdt", "search", query, "--limit", str(max_results)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return []
        posts = []
        for line in result.stdout.split("\n"):
            # rdt-cli outputs lines like: "Title | Score | URL"
            if "|" not in line:
                continue
            parts = line.split("|")
            title = parts[0].strip()
            if not title or len(title) < 5:
                continue
            if not _relevant(ticker, company_name, title, ""):
                continue
            url = parts[-1].strip() if len(parts) > 2 else ""
            posts.append({
                "title": title,
                "body": "",
                "date": "",
                "url": url,
                "source": "Reddit",
            })
        return posts
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return []


def search_news(ticker, company_name, max_results=10):
    """Fetch news from RSS feeds (primary), fallback to DuckDuckGo.
    Returns (articles, source_health) where source_health tracks which sources returned results.
    """
    cached = cache_get(f"news_{ticker}")
    if cached:
        news, health = cached
        return news[:max_results], health

    seen_urls = set()
    all_results = []
    source_stats = {}  # source_name -> hit_count

    # Ticker-specific RSS feeds
    for rss_fn in TICKER_RSS_FEEDS:
        url = rss_fn(ticker, company_name)
        if url is None:
            continue
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                link = entry.get("link", "")
                if link and link not in seen_urls:
                    seen_urls.add(link)
                    all_results.append({
                        "title": entry.get("title", ""),
                        "body": entry.get("summary", ""),
                        "date": _parse_date(entry.get("published_parsed")),
                        "url": link,
                        "source": "Google News",
                    })
                    source_stats["Google News"] = source_stats.get("Google News", 0) + 1
        except Exception:
            continue

    # Indian market RSS feeds (filtered by relevance)
    for source_name, url in INDIA_RSS_FEEDS:
        label = SOURCE_LABELS.get(source_name.lower().replace("_", " "), source_name)
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:7]:
                link = entry.get("link", "")
                title = entry.get("title", "")
                body = entry.get("summary", "")
                if link and link not in seen_urls and _relevant(ticker, company_name, title, body):
                    seen_urls.add(link)
                    all_results.append({
                        "title": title,
                        "body": body,
                        "date": _parse_date(entry.get("published_parsed")),
                        "url": link,
                        "source": label,
                    })
                    source_stats[label] = source_stats.get(label, 0) + 1
        except Exception:
            continue

    # Fallback: DuckDuckGo when RSS returns little
    if len(all_results) < 3:
        try:
            with DDGS() as ddgs:
                for query in [f"{ticker} NSE", f"{company_name} stock"]:
                    try:
                        results = list(ddgs.news(query, max_results=3, timelimit="w"))
                    except Exception:
                        results = []
                    if not results:
                        try:
                            results = list(ddgs.text(query, max_results=3))
                        except Exception:
                            results = []
                    for r in results:
                        url = r.get("url", "") or r.get("link", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append({
                                "title": r.get("title", ""),
                                "body": r.get("body", ""),
                                "date": r.get("date", ""),
                                "url": url,
                                "source": "DuckDuckGo",
                            })
                            source_stats["DuckDuckGo"] = source_stats.get("DuckDuckGo", 0) + 1
                    time.sleep(0.3)
                    if len(all_results) >= max_results:
                        break
        except Exception:
            pass

    # Local-only: Reddit via rdt-cli
    reddit_posts = fetch_reddit_news(ticker, company_name, max_results=3)
    for post in reddit_posts:
        url = post.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            all_results.append(post)
            source_stats["Reddit"] = source_stats.get("Reddit", 0) + 1

    all_results.sort(key=lambda x: x["date"], reverse=True)
    cache_set(f"news_{ticker}", (all_results, source_stats))
    if not all_results:
        st.info("ℹ️ News feed unavailable. Showing price data only.")
    return all_results[:max_results], source_stats
