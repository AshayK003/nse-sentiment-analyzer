"""
Technical indicators for NSE Sentiment Analyzer.
RSI(14), SMA 50/200, MACD(12,26,9) from 1yr daily data.
"""

import yfinance as yf
import pandas as pd
import time


def get_technical_indicators(ticker, hist=None):
    """Compute RSI, SMA, MACD from 1yr daily data. Accepts pre-fetched hist to avoid duplicate yfinance calls."""
    try:
        # Use supplied hist, or check data_fetcher's in-memory cache, or fetch fresh
        if hist is None:
            # ponytail: check _hist_cache from data_fetcher to reuse get_stock_info's 1y fetch
            from data_fetcher import _hist_cache
            hist = _hist_cache.get(ticker)
        if hist is None:
            # Fallback: own yfinance fetch with retry
            for attempt in range(3):
                try:
                    hist = yf.Ticker(f"{ticker}.NS").history(period="1y")
                    if hist is not None and not hist.empty:
                        break
                except Exception:
                    time.sleep(2 ** attempt + 1)
                    continue

        if hist is None or hist.empty or len(hist) < 26:  # ponytail: 26 = minimum for MACD(12,26,9); RSI(14) works too; SMAs return NaN naturally
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

        # SMA crossover detection — compare today vs yesterday
        close_now = float(close.iloc[-1])
        close_prev = float(close.iloc[-2]) if len(close) > 1 else close_now
        sma50_now = float(sma_50.iloc[-1]) if not pd.isna(sma_50.iloc[-1]) else None
        sma50_prev = float(sma_50.iloc[-2]) if not pd.isna(sma_50.iloc[-2]) else None
        sma200_now = float(sma_200.iloc[-1]) if not pd.isna(sma_200.iloc[-1]) else None
        sma200_prev = float(sma_200.iloc[-2]) if not pd.isna(sma_200.iloc[-2]) else None

        sma50_cross = None
        sma200_cross = None
        if sma50_now and sma50_prev:
            if close_prev < sma50_prev and close_now > sma50_now:
                sma50_cross = "bullish"
            elif close_prev > sma50_prev and close_now < sma50_now:
                sma50_cross = "bearish"
        if sma200_now and sma200_prev:
            if close_prev < sma200_prev and close_now > sma200_now:
                sma200_cross = "bullish"
            elif close_prev > sma200_prev and close_now < sma200_now:
                sma200_cross = "bearish"

        # Volume spike — 50-day average volume
        avg_vol_50 = float(hist["Volume"].rolling(50).mean().iloc[-1]) if len(hist) >= 50 else None

        return {
            "rsi": float(rsi.iloc[-1]),
            "sma_50": sma50_now,
            "sma_200": sma200_now,
            "close": close_now,
            "close_prev": close_prev,
            "macd_line": float(macd_line.iloc[-1]),
            "macd_signal": float(signal_line.iloc[-1]),
            "macd_hist": float(macd_hist.iloc[-1]),
            "sma50_cross": sma50_cross,
            "sma200_cross": sma200_cross,
            "avg_volume_50": avg_vol_50,
        }
    except Exception:
        return None
