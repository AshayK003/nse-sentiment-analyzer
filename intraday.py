"""Intraday trading tools — VWAP, pivot levels, India VIX.

All functions are pure-data: they take inputs, return dicts, and have zero
Streamlit dependencies. Designed to be testable with mocked yfinance calls.
"""

import math


def compute_vwap(ticker):
    """Compute VWAP + deviation from intraday 5-min data.

    Fetches today's 5-min OHLCV via yfinance. Returns current price relative
    to VWAP as a % deviation. Positive = price above VWAP (bullish bias),
    negative = below VWAP (bearish bias).

    Args:
        ticker: NSE ticker symbol (e.g. 'RELIANCE', '^INDIAVIX')

    Returns:
        dict with keys: vwap (float|None), price (float|None), deviation_pct (float|None)
    """
    import yfinance as yf

    # Indices (^ prefix) don't get .NS suffix; stocks do
    symbol = f"{ticker}.NS" if not ticker.startswith("^") else ticker
    data = yf.download(symbol, period="1d", interval="5m", progress=False, auto_adjust=True)

    if data is None or data.empty or len(data) < 2:
        return {"vwap": None, "price": None, "deviation_pct": None}

    # VWAP = Σ(typical_price * volume) / Σ(volume)
    typ_price = (data["High"] + data["Low"] + data["Close"]) / 3
    vol = data["Volume"]
    vol_sum = vol.sum()
    if vol_sum == 0:
        return {"vwap": None, "price": None, "deviation_pct": None}

    vwap_val = (typ_price * vol).sum() / vol_sum
    current_price = float(data["Close"].iloc[-1])
    deviation = ((current_price - vwap_val) / vwap_val) * 100 if vwap_val else 0.0

    return {
        "vwap": round(float(vwap_val), 2),
        "price": round(current_price, 2),
        "deviation_pct": round(float(deviation), 2),
    }


def compute_pivot_levels(hist):
    """Compute classic pivot points from daily OHLCV history.

    Uses the last bar's High, Low, Close to compute:
        Pivot  = (H + L + C) / 3
        R1     = 2 × Pivot − L
        S1     = 2 × Pivot − H

    Args:
        hist: pd.DataFrame with 'High', 'Low', 'Close' columns, or None.

    Returns:
        dict with keys: pivot (float|None), resistance (float|None), support (float|None)
    """
    if hist is None or hist.empty:
        return {"pivot": None, "resistance": None, "support": None}

    high = float(hist["High"].iloc[-1])
    low = float(hist["Low"].iloc[-1])
    close = float(hist["Close"].iloc[-1])

    pivot = (high + low + close) / 3
    r1 = 2 * pivot - low
    s1 = 2 * pivot - high

    return {
        "pivot": round(pivot, 2),
        "resistance": round(r1, 2),
        "support": round(s1, 2),
    }


def get_vix():
    """Fetch India VIX level and daily change.

    Returns:
        dict with keys:
            vix (float|None) — latest VIX close
            change (float) — point change from previous day
            level (str) — 'Low' (<15), 'Medium' (15-20), 'High' (>20), or 'N/A'
    """
    import yfinance as yf

    data = yf.download("^INDIAVIX", period="5d", progress=False, auto_adjust=True)

    if data is None or data.empty or len(data) < 2:
        return {"vix": None, "change": 0.0, "level": "N/A"}

    closes = data["Close"].dropna()
    if len(closes) < 2:
        return {"vix": None, "change": 0.0, "level": "N/A"}

    latest = float(closes.iloc[-1])
    prev = float(closes.iloc[-2])
    change = round(latest - prev, 2)

    if latest > 20:
        level = "High"
    elif latest > 15:
        level = "Medium"
    else:
        level = "Low"

    return {"vix": round(latest, 2), "change": change, "level": level}
