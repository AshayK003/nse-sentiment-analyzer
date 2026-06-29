"""Market-wide data for NSE Sentiment Analyzer.
FII/DII institutional flow fetched via nsepython.
"""

import logging
import streamlit as st

logger = logging.getLogger(__name__)


def _fii_dii_action(net):
    """Classify FII/DII net flow as Buying/Selling/Flat (threshold ±200 Cr)."""
    if net > 200:
        return "Buying"
    elif net < -200:
        return "Selling"
    return "Flat"


@st.cache_data(ttl=3600)
def get_fii_dii_flow():
    """Fetch latest FII/DII net flow from NSE India.

    Returns a dict:
        {
            "fii_net": float (Cr),
            "dii_net": float (Cr),
            "date": str,
            "combined_net": float (Cr),
            "fii_action": "Buying"|"Selling"|"Flat",
            "dii_action": "Buying"|"Selling"|"Flat",
        }
    Returns None on failure.
    """
    try:
        from nsepython import nse_fiidii
        df = nse_fiidii()
        if df is None or df.empty:
            return None

        fii_row = df[df["category"].str.contains("FII|FPI", case=False, na=False)]
        dii_row = df[df["category"].str.contains("DII", case=False, na=False)]

        fii_net = float(fii_row["netValue"].iloc[0]) if not fii_row.empty else 0.0
        dii_net = float(dii_row["netValue"].iloc[0]) if not dii_row.empty else 0.0
        date = str(fii_row["date"].iloc[0]) if not fii_row.empty else str(dii_row["date"].iloc[0]) if not dii_row.empty else ""

        return {
            "fii_net": fii_net,
            "dii_net": dii_net,
            "date": date,
            "combined_net": fii_net + dii_net,
            "fii_action": _fii_dii_action(fii_net),
            "dii_action": _fii_dii_action(dii_net),
        }
    except Exception as e:
        logger.debug("get_fii_dii_flow() failed: %s", e)
        return None


def get_market_pulse():
    """Fetch Nifty 50 index and return market-level pulse + actionable verdict.

    Uses the same yfinance pattern as get_vix() for index tickers.
    Returns a verdict based on Nifty change % + VIX level (caller passes
    the already-fetched VIX since it's cached in session_state).

    Returns:
        dict with keys:
            nifty_price (float|None), nifty_change_pct (float|None),
            verdict (str), verdict_icon (str), verdict_detail (str)
    """
    try:
        import yfinance as yf
        t = yf.Ticker("^NSEI")
        data = t.history(period="5d")
    except Exception:
        return {
            "nifty_price": None, "nifty_change_pct": None,
        }

    if data is None or data.empty or len(data) < 2:
        return {
            "nifty_price": None, "nifty_change_pct": None,
        }

    try:
        closes = data["Close"].dropna()
        if len(closes) < 2:
            return {
                "nifty_price": None, "nifty_change_pct": None,
            }
        nifty_price = float(closes.iloc[-1])
        prev_close = float(closes.iloc[-2])
        nifty_change_pct = round((nifty_price - prev_close) / prev_close * 100, 2)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return {
            "nifty_price": None, "nifty_change_pct": None,
        }

    return {
        "nifty_price": nifty_price,
        "nifty_change_pct": nifty_change_pct,
    }


# ─── Market Mood Index (MMI) ─────────────────────────────────────────────

NSE_SECTOR_TICKERS = [
    "^NSEBANK", "^CNXIT", "^CNXPHARMA", "^CNXAUTO", "^CNXFMCG",
    "^CNXREALTY", "^CNXPSE", "^CNXMEDIA", "^CNXMETAL", "^CNXENERGY",
]


def _clamp(value, lo, hi):
    """Clamp value to [lo, hi] range."""
    return max(lo, min(hi, value))


def _calc_trend_score(nifty_df):
    """Trend Strength: Nifty % distance from 20-day SMA, mapped to 0-100."""
    if nifty_df is None or nifty_df.empty:
        return 50
    closes = nifty_df["Close"].dropna()
    if len(closes) < 20:
        return 50
    sma20 = closes.tail(20).mean()
    last_close = closes.iloc[-1]
    pct_from_sma = round((last_close / sma20 - 1) * 100, 2)
    # ±10% from SMA maps to 0-100 (50 = at SMA)
    return _clamp(round(50 + pct_from_sma * 5), 0, 100)


def _calc_vix_score(vix_df):
    """VIX Fear Gauge: inverted VIX mapped to 0-100."""
    if vix_df is None or vix_df.empty:
        return 50
    closes = vix_df["Close"].dropna()
    if len(closes) < 1:
        return 50
    vix_value = float(closes.iloc[-1])
    # VIX 10 → 100 (calm), VIX 40+ → 0 (extreme fear)
    return _clamp(round(100 - (vix_value - 10) / 30 * 100), 0, 100)


def _calc_fii_score():
    """FII Money Flow: compare today's FII net to 21-day trailing average.

    Uses saved FII history from persistence. Returns 0-100 score.
    """
    try:
        from persistence import load_fiidii_history

        current_fii = get_fii_dii_flow()
        fii_hist = load_fiidii_history()

        if not current_fii or not fii_hist or len(fii_hist) < 5:
            return 50

        recent = fii_hist[-21:]
        avg_abs = sum(abs(r["fii_net"]) for r in recent) / len(recent)
        today_fii = current_fii.get("fii_net", 0)

        if avg_abs <= 0:
            return 50

        # deviation = ratio of today's flow to average absolute flow
        # Buying at 2x avg → ~90, neutral → 50, selling at 2x avg → ~10
        deviation = today_fii / avg_abs
        return _clamp(round(50 + deviation * 20), 0, 100)
    except Exception:
        return 50


def _calc_breadth_score(sector_data):
    """Market Breadth: fraction of sector indices advancing, as 0-100."""
    advancing = 0
    total = 0
    for t, df in sector_data.items():
        if df is not None and not df.empty and len(df) >= 2:
            closes = df["Close"].dropna()
            if len(closes) >= 2:
                total += 1
                if float(closes.iloc[-1]) > float(closes.iloc[-2]):
                    advancing += 1
    if total == 0:
        return 50
    return round(advancing / total * 100)


def _fetch_ticker(t, period="1mo"):
    """Helper for ThreadPoolExecutor — fetch a single ticker's history."""
    import yfinance as yf
    try:
        return yf.Ticker(t).history(period=period)
    except Exception:
        return None


def get_mmi():
    """Compute Market Mood Index (MMI) 0-100 from 4 equally-weighted components.

    Components:
      1. Trend Strength — Nifty 50 vs 20-day SMA
      2. VIX Fear Gauge — inverted India VIX
      3. FII Money Flow — institutional confidence vs trailing average
      4. Market Breadth — sector-level advance/decline ratio

    Returns:
        dict with keys:
            mmi (float|None) — composite 0-100
            zone (str) — Extreme Fear / Fear / Neutral / Greed / Extreme Greed
            trend_score, vix_score, fii_score, breadth_score (float|None)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    result_base = {
        "mmi": None, "zone": "N/A",
        "trend_score": None, "vix_score": None,
        "fii_score": None, "breadth_score": None,
    }

    all_tickers = ["^NSEI", "^INDIAVIX"] + NSE_SECTOR_TICKERS
    hist_data = {}

    try:
        with ThreadPoolExecutor(max_workers=13) as ex:
            fut_map = {ex.submit(_fetch_ticker, t): t for t in all_tickers}
            for fut in as_completed(fut_map):
                t = fut_map[fut]
                try:
                    hist_data[t] = fut.result()
                except Exception:
                    hist_data[t] = None
    except Exception:
        return result_base

    # Compute components
    trend_score = _calc_trend_score(hist_data.get("^NSEI"))
    vix_score = _calc_vix_score(hist_data.get("^INDIAVIX"))
    fii_score = _calc_fii_score()

    sector_data = {t: hist_data.get(t) for t in NSE_SECTOR_TICKERS}
    breadth_score = _calc_breadth_score(sector_data)

    # Final MMI = equal-weighted average
    scores = [trend_score, vix_score, fii_score, breadth_score]
    mmi_val = sum(scores) / len(scores)

    if mmi_val >= 75:
        zone = "Extreme Greed"
    elif mmi_val >= 60:
        zone = "Greed"
    elif mmi_val >= 40:
        zone = "Neutral"
    elif mmi_val >= 25:
        zone = "Fear"
    else:
        zone = "Extreme Fear"

    return {
        "mmi": round(mmi_val, 1),
        "zone": zone,
        "trend_score": round(trend_score, 1),
        "vix_score": round(vix_score, 1),
        "fii_score": round(fii_score, 1),
        "breadth_score": round(breadth_score, 1),
    }
