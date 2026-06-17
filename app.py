"""
NSE Stock Sentiment Analyzer — AI Tool #1
Enter any NSE ticker → get live price + news sentiment score + signal.
Built with Streamlit + yfinance + VADER + FinBERT sentiment.
"""

import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from duckduckgo_search import DDGS
import feedparser
import json
from pathlib import Path
import time

# ─── Page config ───
st.set_page_config(
    page_title="NSE Sentiment Analyzer",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ─── Constants ───
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


# ─── Data directory ───
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
TRACK_FILE = DATA_DIR / "track_record.json"
CACHE_FILE = DATA_DIR / "cache.json"
CACHE_TTL = 15 * 60  # 15 minutes

# ─── Financial sentiment augmentations ───
# Words that VADER doesn't score well for finance
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
}

# ─── Cache VADER ───
@st.cache_resource
def get_sia():
    sia = SentimentIntensityAnalyzer()
    sia.lexicon.update(FINANCIAL_BOOSTERS)
    return sia


# ─── FinBERT (domain-adapted financial sentiment) ───
@st.cache_resource
def get_finbert():
    try:
        from transformers import pipeline
        return pipeline("sentiment-analysis", model="ProsusAI/finbert")
    except Exception:
        return None


def _num(v, to_type=float):
    """Convert a value to a native Python number; return "N/A" if None or non-numeric."""
    if v is None:
        return "N/A"
    if isinstance(v, str):
        return v
    return to_type(v)


def get_stock_info(ticker):
    """Fetch stock data from yfinance."""
    cached = cache_get(f"stock_{ticker}")
    if cached:
        return cached
    try:
        stock = yf.Ticker(f"{ticker}.NS")
        info = stock.info
        hist = stock.history(period="5d")

        if not hist.empty:
            current_price = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current_price
            change = float(current_price - prev_close)
            change_pct = float((change / prev_close) * 100)
            day_high = float(hist["High"].iloc[-1])
            day_low = float(hist["Low"].iloc[-1])
            volume = int(hist["Volume"].iloc[-1])
        else:
            current_price = _num(info.get("currentPrice") or info.get("regularMarketPrice"))
            change = _num(info.get("regularMarketChange"))
            change_pct = _num(info.get("regularMarketChangePercent"))
            day_high = _num(info.get("dayHigh"))
            day_low = _num(info.get("dayLow"))
            volume = _num(info.get("volume"), int)

        result = {
            "name": info.get("longName", info.get("shortName", ticker)),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "market_cap": _num(info.get("marketCap"), int),
            "pe_ratio": _num(info.get("trailingPE")),
            "current_price": current_price,
            "change": change,
            "change_pct": change_pct,
            "day_high": day_high,
            "day_low": day_low,
            "volume": volume,
            "52w_high": _num(info.get("fiftyTwoWeekHigh")),
            "52w_low": _num(info.get("fiftyTwoWeekLow")),
        }
        cache_set(f"stock_{ticker}", result)
        return result
    except Exception as e:
        st.error(f"Could not fetch data for {ticker}: {e}")
        return None


def _parse_date(d):
    """Parse RSS date string to ISO format, return empty string on failure."""
    try:
        return datetime(*d[:6]).isoformat()[:10]
    except Exception:
        return ""


def search_news(ticker, company_name, max_results=10):
    """Fetch news from RSS feeds (primary), fallback to DuckDuckGo."""
    cached = cache_get(f"news_{ticker}")
    if cached:
        return cached[:max_results]

    seen_urls = set()
    all_results = []

    # RSS feed sources (no API keys needed)
    rss_urls = [
        f"https://finance.yahoo.com/rss/headline?s={ticker}.NS",
        f"https://news.google.com/rss/search?q={ticker}+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en",
    ]
    if company_name != ticker:
        rss_urls.append(
            f"https://news.google.com/rss/search?q={company_name}+NSE&hl=en-IN&gl=IN&ceid=IN:en"
        )

    for url in rss_urls:
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
                    })
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
                            })
                    time.sleep(0.3)
                    if len(all_results) >= max_results:
                        break
        except Exception:
            pass

    all_results.sort(key=lambda x: x["date"], reverse=True)
    cache_set(f"news_{ticker}", all_results)
    if not all_results:
        st.info("ℹ️ News feed unavailable. Showing price data only.")
    return all_results[:max_results]


def analyze_headline_sentiment(headline, body, sia, finbert=None):
    """Get VADER + optional FinBERT sentiment for a headline."""
    text = f"{headline}. {body}" if body else headline
    vader = sia.polarity_scores(text)
    result = {"compound": vader["compound"], "vader": vader, "finbert": None}
    if finbert:
        try:
            fb = finbert(text[:512])[0]
            compound = fb["score"] if fb["label"] == "positive" else -fb["score"] if fb["label"] == "negative" else 0.0
            result["finbert"] = compound
            result["compound"] = compound  # prefer FinBERT
        except Exception:
            pass
    return result


def get_overall_signal(headline_scores):
    """Determine overall signal from headline scores."""
    if not headline_scores:
        return "NEUTRAL", 0.0, "⚪"

    avg_compound = sum(s["compound"] for s in headline_scores) / len(headline_scores)
    pos_count = sum(1 for s in headline_scores if s["compound"] >= 0.3)
    neg_count = sum(1 for s in headline_scores if s["compound"] <= -0.3)

    if avg_compound >= 0.2 and pos_count > neg_count:
        return "BULLISH 🟢", avg_compound, "🟢"
    elif avg_compound <= -0.2 and neg_count > pos_count:
        return "BEARISH 🔴", avg_compound, "🔴"
    else:
        return "NEUTRAL ⚪", avg_compound, "⚪"


def format_large_num(n):
    """Format large numbers for display."""
    if isinstance(n, (int, float)):
        if n >= 1_00_00_000:  # 1 Crore
            return f"₹{n / 1_00_00_000:.2f}Cr"
        elif n >= 1_00_000:  # 1 Lakh
            return f"₹{n / 1_00_000:.2f}L"
        elif n >= 1_000:
            return f"₹{n:,.0f}"
        else:
            return f"₹{n}"
    return "N/A"


def get_sentiment_emoji(compound):
    if compound >= 0.3:
        return "🟢"
    elif compound <= -0.3:
        return "🔴"
    return "⚪"


# ─── Persistence ───
def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

def load_portfolio():
    return load_json(PORTFOLIO_FILE, [])

def save_portfolio(tickers):
    save_json(PORTFOLIO_FILE, tickers)

def load_track_record():
    return load_json(TRACK_FILE, [])

def save_track_record(records):
    save_json(TRACK_FILE, records)


# ─── Cache ───
def load_cache():
    return load_json(CACHE_FILE, {})

def save_cache(cache):
    save_json(CACHE_FILE, cache)

def cache_get(key):
    cache = load_cache()
    entry = cache.get(key)
    if entry:
        age = (datetime.now() - datetime.fromisoformat(entry["cached_at"])).total_seconds()
        if age < CACHE_TTL:
            return entry["data"]
    return None

def cache_set(key, data):
    cache = load_cache()
    cache[key] = {"data": data, "cached_at": datetime.now().isoformat()}
    save_cache(cache)


def analyze_ticker(ticker, company_name):
    """Run full analysis pipeline for a ticker. Returns dict or None."""
    stock_data = get_stock_info(ticker)
    if not stock_data:
        return None
    sia = get_sia()
    finbert = get_finbert()
    news_items = search_news(ticker, company_name)
    headline_scores = [analyze_headline_sentiment(n["title"], n["body"], sia, finbert) for n in news_items]
    signal, avg_compound, signal_emoji = get_overall_signal(headline_scores)
    return {
        "stock_data": stock_data,
        "news_items": news_items,
        "headline_scores": headline_scores,
        "signal": signal,
        "avg_compound": avg_compound,
        "signal_emoji": signal_emoji,
        "num_articles": len(news_items),
        "using_finbert": finbert is not None,
    }


# ─── Sidebar ───
with st.sidebar:
    st.header("📁 My Portfolio")
    portfolio = load_portfolio()

    add_c1, add_c2 = st.columns([3, 1])
    with add_c1:
        new_t = st.text_input("Ticker", placeholder="RELIANCE", label_visibility="collapsed",
                              max_chars=15, key="portfolio_add")
    with add_c2:
        if st.button("➕", use_container_width=True) and new_t.strip():
            t = new_t.strip().upper().replace(".NS", "")
            if not t.isalnum():
                st.warning("Invalid ticker format")
            elif t in portfolio:
                st.warning(f"{t} already in portfolio")
            else:
                portfolio.append(t)
                save_portfolio(portfolio)
                st.rerun()

    if portfolio:
        for t in portfolio:
            c1, c2 = st.columns([3, 1])
            c1.write(f"**{t}**")
            if c2.button("✕", key=f"del_{t}"):
                portfolio.remove(t)
                save_portfolio(portfolio)
                st.rerun()

        if st.button("📡 Run Portfolio Briefing", type="primary", use_container_width=True):
            st.session_state.run_briefing = True

    # ─── Track Record Stats ───
    st.markdown("---")
    st.header("📊 Track Record")
    records = load_track_record()
    total = len(records)
    voted = [r for r in records if r.get("vote") is not None]
    accurate = sum(1 for r in voted if r["vote"] is True)
    if voted:
        st.metric("Accuracy", f"{accurate/len(voted)*100:.0f}%", help=f"{accurate}/{len(voted)} signals rated")
    st.metric("Total Scans", total)
    st.caption("👍 = signal was right, 👎 = wrong")

# ─── UI ───

st.title("📊 NSE Stock Sentiment Analyzer")
st.markdown("Enter an NSE stock ticker to see **live price + news sentiment** in one place.")

# Ticker input with autocomplete-like selector
col1, col2 = st.columns([3, 1])
with col1:
    ticker = st.selectbox(
        "Select or type an NSE ticker:",
        options=[""] + sorted(NSE_TICKERS.keys()),
        format_func=lambda x: f"{x} — {NSE_TICKERS.get(x, '')}" if x else "Select a ticker...",
        placeholder="Search tickers...",
    )
with col2:
    custom_ticker = st.text_input("Or enter custom:", placeholder="NYKAA", max_chars=15)

# Determine final ticker
final_ticker = custom_ticker.strip().upper() if custom_ticker.strip() else ticker

if final_ticker and final_ticker != "":
    # Clean ticker — remove .NS if user accidentally typed it
    final_ticker = final_ticker.replace(".NS", "")
    company_name = NSE_TICKERS.get(final_ticker, final_ticker)

    result = analyze_ticker(final_ticker, company_name)
    if result:
        stock_data = result["stock_data"]
        news_items = result["news_items"]
        headline_scores = result["headline_scores"]
        signal = result["signal"]
        avg_compound = result["avg_compound"]
        signal_emoji = result["signal_emoji"]
        using_finbert = result.get("using_finbert", False)
        confidence = abs(avg_compound)

        # Save to track record
        records = load_track_record()
        records.append({
            "ticker": final_ticker,
            "datetime": datetime.now().isoformat(timespec="minutes"),
            "compound": avg_compound,
            "signal": signal,
            "vote": None,
        })
        save_track_record(records)

        # ─── PRICE CARD ───
        st.markdown("---")
        col_p1, col_p2, col_p3, col_p4 = st.columns(4)

        with col_p1:
            change_str = f"+{stock_data['change']:.2f}" if isinstance(stock_data['change'], (int, float)) and stock_data['change'] >= 0 else f"{stock_data['change']:.2f}" if isinstance(stock_data['change'], (int, float)) else "N/A"
            change_pct_str = f"+{stock_data['change_pct']:.2f}%" if isinstance(stock_data['change_pct'], (int, float)) and stock_data['change_pct'] >= 0 else f"{stock_data['change_pct']:.2f}%" if isinstance(stock_data['change_pct'], (int, float)) else "N/A"
            delta_color = "normal" if isinstance(stock_data['change'], (int, float)) and stock_data['change'] >= 0 else "inverse"

            st.metric(
                label=f"{final_ticker} — {stock_data['name'][:30]}",
                value=f"₹{stock_data['current_price']:.2f}" if isinstance(stock_data['current_price'], (int, float)) else str(stock_data['current_price']),
                delta=f"{change_str} ({change_pct_str})",
                delta_color=delta_color,
            )

        with col_p2:
            st.metric("Day Range", f"₹{stock_data['day_low']:.2f} — ₹{stock_data['day_high']:.2f}" if isinstance(stock_data['day_low'], (int, float)) else "N/A")

        with col_p3:
            vol_str = f"{stock_data['volume']:,.0f}" if isinstance(stock_data['volume'], (int, float)) else "N/A"
            st.metric("Volume", vol_str)

        with col_p4:
            pe_str = f"{stock_data['pe_ratio']:.2f}" if isinstance(stock_data['pe_ratio'], (int, float)) else "N/A"
            st.metric("P/E Ratio", pe_str)

        # ─── SENTIMENT CARD ───
        st.markdown("---")
        st.subheader("📰 News Sentiment Analysis")

        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            st.markdown(f"### {signal_emoji} {signal}")
            model_tag = "🧠 FinBERT" if using_finbert else "📐 VADER"
            st.caption(f"Based on {len(news_items)} news articles · {model_tag}")

        with col_s2:
            confidence_pct = min(confidence * 100, 99)
            st.markdown(f"### {confidence_pct:.0f}%")
            st.caption("Confidence Score")

        with col_s3:
            if "🟢" in signal:
                rec = "✅ BUY / HOLD — Positive sentiment dominates"
                st.success(rec)
            elif "🔴" in signal:
                rec = "⚠️ CAUTION / SELL — Negative sentiment detected"
                st.warning(rec)
            else:
                rec = "💤 HOLD — Mixed or neutral sentiment"
                st.info(rec)

        # Thumbs up/down for track record
        records = load_track_record()
        last_rec = records[-1] if records else None
        if last_rec and last_rec["ticker"] == final_ticker and last_rec.get("vote") is None:
            st.markdown("##### Was this signal accurate?")
            vu, vd = st.columns([1, 1])
            with vu:
                if st.button("👍 Yes", key="vote_up", use_container_width=True):
                    last_rec["vote"] = True
                    save_track_record(records)
                    st.rerun()
            with vd:
                if st.button("👎 No", key="vote_down", use_container_width=True):
                    last_rec["vote"] = False
                    save_track_record(records)
                    st.rerun()
        elif last_rec and last_rec.get("vote") is not None:
            st.caption(f"You marked this signal as {'✅ accurate' if last_rec['vote'] else '❌ inaccurate'}")

        # ─── SENTIMENT METER ───
        st.markdown("---")
        st.subheader("📈 Sentiment Distribution")

        if headline_scores:
            pos_pct = sum(1 for s in headline_scores if s["compound"] >= 0.3) / len(headline_scores) * 100
            neg_pct = sum(1 for s in headline_scores if s["compound"] <= -0.3) / len(headline_scores) * 100
            neu_pct = 100 - pos_pct - neg_pct

            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                st.markdown(f"🟢 **Positive:** {pos_pct:.0f}%")
                st.progress(pos_pct / 100)
            with col_m2:
                st.markdown(f"🔴 **Negative:** {neg_pct:.0f}%")
                st.progress(neg_pct / 100)
            with col_m3:
                st.markdown(f"⚪ **Neutral:** {neu_pct:.0f}%")
                st.progress(neu_pct / 100)

        # ─── NEWS HEADLINES ───
        st.markdown("---")
        st.subheader(f"📋 Recent News ({len(news_items)} articles)")

        for i, (item, scores) in enumerate(zip(news_items, headline_scores)):
            emoji = get_sentiment_emoji(scores["compound"])
            sentiment_label = "Positive" if scores["compound"] >= 0.3 else "Negative" if scores["compound"] <= -0.3 else "Neutral"

            with st.container(border=True):
                cols = st.columns([0.05, 0.75, 0.2])
                with cols[0]:
                    st.markdown(f"**{emoji}**")
                with cols[1]:
                    st.markdown(f"**{item['title']}**")
                    if item.get("body"):
                        st.caption(item["body"][:200])
                with cols[2]:
                    st.markdown(f"*{sentiment_label}*")
                    if item.get("date"):
                        st.caption(item["date"][:10])

        # ─── KEY STATS ───
        st.markdown("---")
        with st.expander("📊 Additional Stats"):
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                st.markdown(f"**Sector:** {stock_data['sector']}")
                st.markdown(f"**Industry:** {stock_data['industry']}")
                mk = stock_data['market_cap']
                st.markdown(f"**Market Cap:** {format_large_num(mk) if isinstance(mk, (int, float)) else 'N/A'}")
            with col_a2:
                st.markdown(f"**52W High:** ₹{stock_data['52w_high']:.2f}" if isinstance(stock_data['52w_high'], (int, float)) else "N/A")
                st.markdown(f"**52W Low:** ₹{stock_data['52w_low']:.2f}" if isinstance(stock_data['52w_low'], (int, float)) else "N/A")
                st.markdown(f"**P/E Ratio:** {stock_data['pe_ratio']:.2f}" if isinstance(stock_data['pe_ratio'], (int, float)) else "N/A")

    else:
        st.error(f"Could not find data for **{final_ticker}**. Try a different ticker (e.g., RELIANCE, HDFCBANK, TCS).")

elif st.session_state.get("run_briefing"):
    # ─── PORTFOLIO BRIEFING MODE ───
    portfolio = load_portfolio()
    if not portfolio:
        st.warning("No tickers in your portfolio. Add some from the sidebar.")
    else:
        st.subheader(f"📡 Portfolio Briefing — {len(portfolio)} stocks")
        results = []
        progress = st.progress(0, text="Starting...")
        for i, t in enumerate(portfolio):
            progress.progress((i) / len(portfolio), text=f"Analyzing {t} ({i+1}/{len(portfolio)})...")
            r = analyze_ticker(t, NSE_TICKERS.get(t, t))
            if r:
                results.append((t, r))
        progress.empty()

        if results:
            st.success(f"Briefed {len(results)} stocks")
            for t, r in results:
                sd = r["stock_data"]
                change_str = f"{'+' if sd['change'] >= 0 else ''}{sd['change']:.2f}" if isinstance(sd['change'], (int, float)) else "N/A"
                with st.container(border=True):
                    cols = st.columns([2, 1, 1])
                    cols[0].markdown(f"**{t}** — ₹{sd['current_price']:.2f}" if isinstance(sd['current_price'], (int, float)) else f"**{t}**")
                    cols[0].caption(f"{sd['name'][:40]}")
                    cols[1].markdown(f"Change: {change_str}")
                    cols[2].markdown(f"{r['signal_emoji']} {r['signal']}")

        if st.button("← Back to Single View"):
            st.session_state.run_briefing = False
            st.rerun()

else:
    st.info("👆 Select or type an NSE ticker above to begin.")
    st.markdown("""
    ### How it works
    1. **Enter** an NSE ticker (e.g., RELIANCE, HDFCBANK, TCS)
    2. **We fetch** live price data from Yahoo Finance
    3. **We scan** recent news from the web
    4. **AI analyzes** sentiment headline-by-headline
    5. **You get** a clear BUY / HOLD / CAUTION signal

    ### Why use this?
    - **Retail traders** — check sentiment before entering a trade
    - **Swing traders** — scan your watchlist for news-driven moves
    - **Portfolio holders** — keep a pulse on your holdings
    """)

# ─── FOOTER ───
st.markdown("---")
st.caption("⚡ Tool #1 of 52 — Built with Streamlit + yfinance + VADER | Data from Yahoo Finance + DuckDuckGo News")
st.caption("📌 Not financial advice. Always do your own research.")
st.markdown(
    '<div style="display:flex;justify-content:center;margin-top:12px">'
    '<a href="https://chai4.me/darkcharon3301" target="_blank" title="Support darkcharon3301 on Chai4Me" '
    'style="display:inline-flex;flex-direction:column;align-items:center;justify-content:center;'
    'background:#ffffff;padding:8px 32px;border-radius:16px;text-decoration:none;'
    'border:1px solid #e5e7eb;'
    'box-shadow:0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -2px rgba(0,0,0,0.05);'
    'transition:transform 0.2s;">'
    '<img src="https://chai4.me/icons/wordmark.png" alt="Chai4Me" style="height:32px;object-fit:contain;"/>'
    '</a></div>',
    unsafe_allow_html=True,
)
