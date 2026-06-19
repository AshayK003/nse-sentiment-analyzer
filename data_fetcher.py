"""
Data fetching for NSE Sentiment Analyzer.
Stock data via yfinance + news via RSS + DuckDuckGo fallback.
"""

import yfinance as yf
import requests
import feedparser
import html
import time
import streamlit as st
import subprocess
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# ─── Company name aliases for RSS headline matching ───
# Maps common names/abbreviations → ticker symbols.
# RSS headlines rarely use official company names ("SBI" not "State Bank of India").
ALIASES = {
    "HCL TECH": "HCLTECH",
    "HCL TECHNOLOGIES": "HCLTECH",
    "HDFC": "HDFCBANK",
    "SBI": "SBIN",
    "STATE BANK": "SBIN",
    "HUL": "HINDUNILVR",
    "HINDUSTAN UNILEVER": "HINDUNILVR",
    "L&T": "LT",
    "LARSEN": "LT",
    "NESTLE": "NESTLEIND",
    "DMART": "DMART",
    "HERO": "HEROMOTOCO",
    "HERO HONDA": "HEROMOTOCO",
    "DIVIS": "DIVISLAB",
    "DIVI": "DIVISLAB",
    "JSW STEEL": "JSWSTEEL",
    "TATA MOTORS": "TATAMOTORS",
    "TATA STEEL": "TATASTEEL",
    "TATA CONSUMER": "TATACONSUM",
    "BHARTI": "BHARTIARTL",
    "AIRTEL": "BHARTIARTL",
    "MARUTI SUZUKI": "MARUTI",
    "TECH MAHINDRA": "TECHM",
    "INDUSIND": "INDUSINDBK",
    "POWER GRID": "POWERGRID",
    "COAL INDIA": "COALINDIA",
    "HIND UNILEVER": "HINDUNILVR",
    "SUN PHARMA": "SUNPHARMA",
    "DR REDDY": "DRREDDY",
    "DR. REDDY": "DRREDDY",
    "BAJAJ FINANCE": "BAJFINANCE",
    "ADANI ENTERPRISES": "ADANIENT",
    "ADANI PORTS": "ADANIPORTS",
    "ADANI GREEN": "ADANIGREEN",
    "ADANI POWER": "ADANIPOWER",
    "ADANI TRANS": "ADANITRANS",
    "ULTRATECH": "ULTRACEMCO",
    "ASIAN PAINTS": "ASIANPAINT",
    "APOLLO HOSPITALS": "APOLLOHOSP",
    "APOLLO": "APOLLOHOSP",
    "TORRENT PHARMA": "TORNTPHARM",
    "JUBILANT": "JUBLFOOD",
    "TVS": "TVSMOTOR",
    "VARUN BEVERAGES": "VBL",
    "YES BANK": "YESBANK",
    "BANK OF BARODA": "BANKBARODA",
    "MAHINDRA": "M&M",
    "INDIAN OIL": "IOC",
    "BHARAT PETROLEUM": "BPCL",
    "HINDUSTAN AERONAUTICS": "HAL",
    "BHARAT ELECTRONICS": "BEL",
    "POWER FINANCE": "PFC",
    "SOLAR INDUSTRIES": "SOLARINDS",
    "BALKRISHNA": "BALKRISIND",
    "PW LAKSHMI": "PWL",
    "VEDANTA": "VEDL",
    "REC": "RECLTD",
    "Pidilite": "PIDILITIND",
    "HAVELLS": "HAVELLS",
    "SIEMENS": "SIEMENS",
    "POLYCAB": "POLYCAB",
    "DIXON": "DIXON",
    "ASTRAL": "ASTRAL",
    "IDFC": "IDFCFIRSTB",
    "EICHER": "EICHERMOT",
    "MARICO": "MARICO",
    "DABUR": "DABUR",
    "GODREJ": "GODREJCP",
    "CIPLA": "CIPLA",
    "LUPIN": "LUPIN",
    "BIOCON": "BIOCON",
}

# ponytail: in-memory 1y price history cache, populated by get_stock_info,
# consumed by get_technical_indicators to avoid duplicate yfinance calls
_hist_cache = {}


def _is_numeric(v):
    """Check if value is a number (int or float, not bool, not None)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _strip_html(text):
    """Strip HTML tags + unescape entities for clean text analysis & display."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.split())


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
    """Fetch stock data from yfinance with retry and backoff.

    Two-phase approach:
      1. info (metadata: name, sector, PE, 52w) — best-effort, not blocking.
         If it fails, defaults are used.
      2. history (price data: close, change, volume) — required.
         Falls back to .BO suffix if .NS fails, then bare ticker.
    """
    cached = cache_get(f"stock_{ticker}")
    if cached:
        return cached

    import random
    import math

    def _retry_fetch(max_attempts=3, base_wait=1, backoff=2):
        """Generator that yields (attempt_num, wait_seconds) for retry loops.
        Uses exponential backoff with full jitter (AWS retry style).
        """
        for attempt in range(max_attempts):
            yield attempt
            if attempt < max_attempts - 1:
                sleep = base_wait * (backoff ** attempt)
                jitter = sleep * 0.5 * random.random()
                time.sleep(sleep + jitter)

    suffixes = [".NS", ".BO", ""]
    info = None
    hist = None
    name_fallback = ticker

    try:
        # ── Phase 1: info (best-effort metadata) ──
        for suffix in suffixes:
            stock = yf.Ticker(f"{ticker}{suffix}")
            for attempt in _retry_fetch(max_attempts=3, base_wait=1):
                try:
                    raw = stock.info
                    if raw and isinstance(raw, dict) and len(raw) > 10:
                        info = raw
                        name_fallback = info.get("longName", info.get("shortName", ticker))
                        break
                except Exception:
                    continue  # retry same suffix with backoff before trying next
            if info:
                break  # found valid info, stop trying suffixes

        # ── Phase 2: history (required price data) ──
        for suffix in suffixes if not hist else []:
            stock = yf.Ticker(f"{ticker}{suffix}")
            for attempt in _retry_fetch(max_attempts=3, base_wait=2):
                try:
                    raw = stock.history(period="1y")
                    if raw is not None and not raw.empty:
                        hist = raw
                        break
                except Exception:
                    continue  # retry with backoff
            if hist is not None:
                break  # found valid history

        # ── Phase 2b: retry info if it failed (rate-limit may have cleared
        #    during the history phase which took ~3-6s) ──
        if info is None and hist is not None:
            for suffix in suffixes:
                stock = yf.Ticker(f"{ticker}{suffix}")
                try:
                    raw = stock.info
                    if raw and isinstance(raw, dict) and len(raw) > 10:
                        info = raw
                        name_fallback = info.get("longName", info.get("shortName", ticker))
                        break
                except Exception:
                    continue

        # ── Build result dict ──
        if hist is not None and not hist.empty:
            _hist_cache[ticker] = hist
            current_price = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current_price
            change = float(current_price - prev_close)
            change_pct = float((change / prev_close) * 100)
            day_high = float(hist["High"].iloc[-1])
            day_low = float(hist["Low"].iloc[-1])
            volume = int(hist["Volume"].iloc[-1]) if not math.isnan(hist["Volume"].iloc[-1]) else 0
        elif info:
            # No history but info is available — use info fields for price
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            change = info.get("regularMarketChange")
            change_pct = info.get("regularMarketChangePercent")
            day_high = info.get("dayHigh")
            day_low = info.get("dayLow")
            volume = info.get("volume")
        else:
            # Neither info nor history — give up
            st.error(
                f"Could not fetch data for {ticker}. "
                "Yahoo Finance may be rate-limited — wait a moment and try again."
            )
            return None

        result = {
            "name": info.get("longName", info.get("shortName", name_fallback)) if info else name_fallback,
            "sector": info.get("sector", "N/A") if info else "N/A",
            "industry": info.get("industry", "N/A") if info else "N/A",
            "market_cap": info.get("marketCap") if info else None,
            "pe_ratio": info.get("trailingPE") if info else None,
            "current_price": current_price,
            "change": change,
            "change_pct": change_pct,
            "day_high": day_high,
            "day_low": day_low,
            "volume": volume,
            "52w_high": info.get("fiftyTwoWeekHigh") if info else None,
            "52w_low": info.get("fiftyTwoWeekLow") if info else None,
        }
        if info:
            cache_set(f"stock_{ticker}", result)
        else:
            # Info failed — use shorter TTL so next call retries metadata
            cache_set(f"stock_{ticker}", result, ttl=120)  # 2 min
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


def _alias_terms(ticker):
    """Get additional search terms from ALIASES dict for a ticker.

    E.g., for ticker='SBIN', returns {'sbi', 'state', 'bank'}
    since ALIASES has 'SBI' -> 'SBIN' and 'STATE BANK' -> 'SBIN'.
    """
    terms = set()
    for alias_key, alias_ticker in ALIASES.items():
        if alias_ticker == ticker:
            terms.update(alias_key.lower().split())
    return terms


def _relevant(ticker, company_name, title, body):
    """Check if a headline is relevant to the given ticker/company.

    Searches ticker name, company name, AND known aliases.
    """
    text = (title + " " + (body or "")).lower()
    words = set(ticker.lower().split()) | set(company_name.lower().split())
    words.update(_alias_terms(ticker))
    return any(re.search(r'\b' + re.escape(w) + r'\b', text) for w in words if len(w) > 2)


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


# ─── Reddit: OAuth API (cloud-compatible) + rdt-cli (local fallback) ───

_REDDIT_TOKEN = None
_REDDIT_TOKEN_EXPIRY = 0


def _reddit_oauth_token(client_id, client_secret):
    """Get a Reddit OAuth token with lazy refresh (tokens expire after 1 hour)."""
    global _REDDIT_TOKEN, _REDDIT_TOKEN_EXPIRY
    if _REDDIT_TOKEN and time.time() < _REDDIT_TOKEN_EXPIRY:
        return _REDDIT_TOKEN
    try:
        auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
        headers = {"User-Agent": "NSE-Sentiment-Analyzer/1.0 (by /u/AshayK003)"}
        data = {"grant_type": "client_credentials", "scope": "read"}
        resp = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=auth, headers=headers, data=data, timeout=10,
        )
        if resp.status_code != 200:
            return None
        token = resp.json().get("access_token")
        if token:
            _REDDIT_TOKEN = token
            _REDDIT_TOKEN_EXPIRY = time.time() + 3300  # 55 min (tokens last 1 hr)
        return token
    except Exception:
        return None


def _fetch_reddit_oauth(ticker, company_name, max_results=5):
    """Fetch Reddit posts via OAuth API (works on cloud)."""
    client_id = os.environ.get("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return []

    token = _reddit_oauth_token(client_id, client_secret)
    if not token:
        return []

    headers = {
        "Authorization": f"bearer {token}",
        "User-Agent": "NSE-Sentiment-Analyzer/1.0 (by /u/AshayK003)",
    }
    queries = [
        f"{ticker} NSE stock",
        f"{company_name} stock",
    ]

    posts = []
    seen_urls = set()
    for query in queries:
        try:
            resp = requests.get(
                "https://oauth.reddit.com/search",
                params={"q": query, "limit": max_results, "sort": "new", "t": "week"},
                headers=headers, timeout=10,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            for child in data.get("data", {}).get("children", []):
                item = child.get("data", {})
                title = item.get("title", "")
                if not title or len(title) < 5:
                    continue
                url = "https://www.reddit.com" + item.get("permalink", "")
                if url in seen_urls:
                    continue
                if not _relevant(ticker, company_name, title, ""):
                    continue
                seen_urls.add(url)
                posts.append({
                    "title": title,
                    "body": item.get("selftext", ""),
                    "date": datetime.fromtimestamp(item.get("created_utc", 0)).strftime("%Y-%m-%d"),
                    "url": url,
                    "author": item.get("author", ""),
                    "subreddit": item.get("subreddit", ""),
                    "source": "Reddit",
                })
                if len(posts) >= max_results:
                    break
        except Exception:
            continue
        time.sleep(0.5)
        if len(posts) >= max_results:
            break

    return posts


def fetch_reddit_news(ticker, company_name, max_results=5):
    """Fetch Reddit posts for a stock ticker.
    
    Uses OAuth API (cloud-compatible) when REDDIT_CLIENT_ID and 
    REDDIT_CLIENT_SECRET env vars are set. Falls back to local rdt-cli.
    """
    # Try OAuth API path (works on cloud and locally)
    oauth_posts = _fetch_reddit_oauth(ticker, company_name, max_results)
    if oauth_posts:
        return oauth_posts

    # Fall back to rdt-cli (local only)
    return _fetch_reddit_rdtcli(ticker, company_name, max_results)


def _fetch_reddit_rdtcli(ticker, company_name, max_results=5):
    """Fetch Reddit posts via rdt-cli (local-only fallback)."""
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
                        "body": _strip_html(entry.get("summary", "")),
                        "date": _parse_date(entry.get("published_parsed")),
                        "url": link,
                        "source": "Google News",
                    })
                    source_stats["Google News"] = source_stats.get("Google News", 0) + 1
        except Exception:
            continue

    # Indian market RSS feeds (filtered by relevance) — fetched concurrently
    def _parse_rss_feed(source_name, url):
        """Parse one RSS feed in a worker thread — no shared state mutation."""
        label = SOURCE_LABELS.get(source_name.lower().replace("_", " "), source_name)
        items = []
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:7]:
                link = entry.get("link", "")
                title = entry.get("title", "")
                body = _strip_html(entry.get("summary", ""))
                if link and _relevant(ticker, company_name, title, body):
                    items.append({
                        "title": title,
                        "body": body,
                        "date": _parse_date(entry.get("published_parsed")),
                        "url": link,
                        "source": label,
                    })
        except Exception:
            pass
        return items, label

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_parse_rss_feed, name, url): name for name, url in INDIA_RSS_FEEDS}
        for future in as_completed(futures):
            items, label = future.result()
            for item in items:
                link = item["url"]
                if link not in seen_urls:
                    seen_urls.add(link)
                    all_results.append(item)
                    source_stats[label] = source_stats.get(label, 0) + 1

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
