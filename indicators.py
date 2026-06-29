"""
Technical indicators for NSE Sentiment Analyzer.
RSI(14), SMA 50/200, MACD(12,26,9) from 1yr daily data.
"""

import logging
import yfinance as yf
import pandas as pd
import time

logger = logging.getLogger(__name__)


def _wilders_smooth(series, period=14):
    """Wilder's smoothing (exponential moving alpha=1/period)."""
    return series.ewm(alpha=1/period, adjust=False).mean()


def detect_volume_spike(current_vol, avg_vol, threshold=2.0):
    """Compare current volume to average. Returns {spike: bool, ratio: float}."""
    ratio = 0.0
    if avg_vol and current_vol and avg_vol > 0 and current_vol > 0:
        ratio = current_vol / avg_vol
    return {"spike": ratio >= threshold, "ratio": round(ratio, 2)}


def get_technical_indicators(ticker, hist=None):
    """Compute RSI, SMA, MACD from 1yr daily data. Accepts pre-fetched hist to avoid duplicate yfinance calls."""
    try:
        # Use supplied hist, or check data_fetcher's in-memory cache, or fetch fresh
        if hist is None:
            from data_fetcher import get_cached_history
            hist = get_cached_history(ticker)
        if hist is None:
            # Fallback: own yfinance fetch with retry, trying .NS → .BO → bare
            for suffix in [".NS", ".BO", ""]:
                stock = yf.Ticker(f"{ticker}{suffix}")
                for attempt in range(3):
                    try:
                        hist = stock.history(period="2y")
                        if hist is not None and not hist.empty:
                            break
                    except Exception:
                        time.sleep(2 ** attempt + 1)
                        continue
                if hist is not None and not hist.empty:
                    break

        if hist is None or hist.empty or len(hist) < 26:  # 26 = minimum for MACD(12,26,9); RSI(14) works too; SMAs return NaN naturally
            return None
        close = hist["Close"]

        # RSI (14) — Wilder's smoothing
        delta = close.diff()
        gain = _wilders_smooth(delta.where(delta > 0, 0), 14)
        loss = _wilders_smooth((-delta.where(delta < 0, 0)), 14)
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        # Guard: if gain=loss=0 (flat), RSI=NaN → neutral 50; if loss=0 → RSI=100
        rsi = rsi.replace([float('inf'), float('-inf')], 100.0).fillna(50.0)

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

        # ADX (14) — trend strength
        adx = None
        if len(hist) >= 28:  # need enough data for 2×ADX period
            high = hist["High"]
            low = hist["Low"]
            # +DM and -DM
            up_move = high.diff()
            down_move = -low.diff()
            plus_dm = pd.Series(0.0, index=high.index)
            minus_dm = pd.Series(0.0, index=high.index)
            mask_up = (up_move > down_move) & (up_move > 0)
            mask_down = (down_move > up_move) & (down_move > 0)
            plus_dm[mask_up] = up_move[mask_up]
            minus_dm[mask_down] = down_move[mask_down]
            # True Range
            prev_close = close.shift(1)
            tr = pd.concat([
                (high - low).abs(),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ], axis=1).max(axis=1)
            # Wilder's smoothing (period=14)
            atr = _wilders_smooth(tr)
            s_plus_dm = _wilders_smooth(plus_dm)
            s_minus_dm = _wilders_smooth(minus_dm)
            # +DI, -DI
            plus_di = 100 * s_plus_dm / atr
            minus_di = 100 * s_minus_dm / atr
            # DX
            dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float('nan'))
            # ADX = smoothed DX
            adx_val = _wilders_smooth(dx)
            adx = float(adx_val.iloc[-1]) if not pd.isna(adx_val.iloc[-1]) else None

        # Volume spike — 50-day average volume
        avg_vol_raw = hist["Volume"].rolling(50).mean().iloc[-1] if len(hist) >= 50 else None
        avg_vol_50 = None if avg_vol_raw is None or pd.isna(avg_vol_raw) else float(avg_vol_raw)

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
            "adx": adx,
        }
    except Exception:
        return None
