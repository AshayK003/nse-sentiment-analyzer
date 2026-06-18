"""
Technical indicators for NSE Sentiment Analyzer.
RSI(14), SMA 50/200, MACD(12,26,9) from 1yr daily data.
"""

import yfinance as yf
import time
import streamlit as st


@st.cache_data(ttl=3600)
def get_technical_indicators(ticker):
    """Compute RSI, SMA, MACD from 1yr daily data. Retries on rate limit."""
    try:
        # Retry history with backoff if rate-limited
        hist = None
        for attempt in range(3):
            try:
                hist = yf.Ticker(f"{ticker}.NS").history(period="1y")
                break
            except Exception as e:
                if "Too Many" in str(e) or "429" in str(e):
                    time.sleep(2 ** attempt)
                    continue
                raise

        if hist is None or hist.empty or len(hist) < 50:
            return None
        close = hist["Close"]

        # RSI (14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        # SMA 50 & 200
        sma_50 = close.rolling(50).mean()
        sma_200 = close.rolling(200).mean()

        # MACD (12, 26, 9)
        ema_12 = close.ewm(span=12).mean()
        ema_26 = close.ewm(span=26).mean()
        macd_line = ema_12 - ema_26
        signal_line = macd_line.ewm(span=9).mean()
        macd_hist = macd_line - signal_line

        return {
            "rsi": float(rsi.iloc[-1]),
            "sma_50": float(sma_50.iloc[-1]),
            "sma_200": float(sma_200.iloc[-1]),
            "close": float(close.iloc[-1]),
            "macd_line": float(macd_line.iloc[-1]),
            "macd_signal": float(signal_line.iloc[-1]),
            "macd_hist": float(macd_hist.iloc[-1]),
        }
    except Exception:
        return None
