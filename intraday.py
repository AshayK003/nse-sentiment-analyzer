"""Intraday trading tools — VWAP, pivot levels, India VIX.

All functions are pure-data: they take inputs, return dicts, and have zero
Streamlit dependencies. Designed to be testable with mocked yfinance calls.
"""

import logging

import yfinance as yf

logger = logging.getLogger(__name__)


def compute_vwap(ticker: str) -> dict:
    """Compute VWAP + deviation from intraday 5-min data.

    Fetches today's 5-min OHLCV via yfinance. Returns current price relative
    to VWAP as a % deviation. Positive = price above VWAP (bullish bias),
    negative = below VWAP (bearish bias).

    Args:
        ticker: NSE ticker symbol (e.g. 'RELIANCE', '^INDIAVIX')

    Returns:
        dict with keys: vwap (float|None), price (float|None), deviation_pct (float|None)
    """

    # Indices (^ prefix) don't get .NS suffix; stocks do
    symbol = f"{ticker}.NS" if not ticker.startswith("^") else ticker
    data = yf.download(symbol, period="1d", interval="5m", progress=False, auto_adjust=True)

    if data is None or data.empty or len(data) < 2:
        return {"vwap": None, "price": None, "deviation_pct": None}

    try:
        # VWAP = Sigma(typical_price * volume) / Sigma(volume)
        typ_price = (data["High"] + data["Low"] + data["Close"]) / 3
        vol = data["Volume"]
        vol_sum = vol.sum()
    except (KeyError, TypeError, AttributeError):
        return {"vwap": None, "price": None, "deviation_pct": None}

    # vol_sum can be a Series from MultiIndex columns — check scalar-safe
    try:
        if float(vol_sum) == 0:
            return {"vwap": None, "price": None, "deviation_pct": None}
    except (TypeError, ValueError, AttributeError):
        return {"vwap": None, "price": None, "deviation_pct": None}

    try:
        vwap_val = (typ_price * vol).sum() / vol_sum
        current_price = float(data["Close"].iloc[-1])
    except (TypeError, ValueError, KeyError, IndexError, AttributeError):
        return {"vwap": None, "price": None, "deviation_pct": None}

    deviation = ((current_price - vwap_val) / vwap_val) * 100 if vwap_val else 0.0

    return {
        "vwap": round(float(vwap_val), 2),
        "price": round(current_price, 2),
        "deviation_pct": round(float(deviation), 2),
    }


def compute_pivot_levels(hist: object) -> dict:
    """Compute classic pivot points from daily OHLCV history.

    Uses the last bar's High, Low, Close to compute:
        Pivot  = (H + L + C) / 3
        R1     = 2 * Pivot - L
        S1     = 2 * Pivot - H

    Args:
        hist: pd.DataFrame with 'High', 'Low', 'Close' columns, or None.

    Returns:
        dict with keys: pivot (float|None), resistance (float|None), support (float|None)
    """
    if hist is None or hist.empty:
        return {"pivot": None, "resistance": None, "support": None}

    try:
        high = float(hist["High"].iloc[-1])
        low = float(hist["Low"].iloc[-1])
        close = float(hist["Close"].iloc[-1])
    except (KeyError, IndexError, TypeError, ValueError):
        return {"pivot": None, "resistance": None, "support": None}

    pivot = (high + low + close) / 3
    r1 = 2 * pivot - low
    s1 = 2 * pivot - high

    return {
        "pivot": round(pivot, 2),
        "resistance": round(r1, 2),
        "support": round(s1, 2),
    }


def get_vix() -> dict:
    """Fetch India VIX level and daily change.

    Fully wrapped in try/except — yfinance can return unexpected data shapes
    for index tickers (^INDIAVIX) across different environments. Fails
    gracefully to {'vix': None, ...} on any error.

    Returns:
        dict with keys:
            vix (float|None) - latest VIX close
            change (float) - point change from previous day
            level (str) - 'Low' (<15), 'Medium' (15-20), 'High' (>20), or 'N/A'
    """

    try:
        t = yf.Ticker("^INDIAVIX")
        data = t.history(period="5d")
    except Exception:
        return {"vix": None, "change": 0.0, "level": "N/A"}

    if data is None or data.empty or len(data) < 2:
        return {"vix": None, "change": 0.0, "level": "N/A"}

    try:
        closes = data["Close"].dropna()
        if len(closes) < 2:
            return {"vix": None, "change": 0.0, "level": "N/A"}
        latest = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return {"vix": None, "change": 0.0, "level": "N/A"}

    change = round(latest - prev, 2)

    if latest > 20:
        level = "High"
    elif latest > 15:
        level = "Medium"
    else:
        level = "Low"

    return {"vix": round(latest, 2), "change": change, "level": level}
