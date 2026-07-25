"""
Technical indicators — pure functions computed from OHLCV data.
"""

from __future__ import annotations

import math
import pandas as pd
import numpy as np

from ..contracts import OHLCV, Indicators, TrendDirection


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI (Relative Strength Index)."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate MACD line, signal line, and histogram."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - macd_signal
    return macd, macd_signal, macd_hist


def calculate_sma(close: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return close.rolling(period).mean()


def calculate_ema(close: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return close.ewm(span=period, adjust=False).mean()


def calculate_bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands: upper, middle, lower."""
    middle = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return upper, middle, lower


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range."""
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr


def calculate_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """ADX (Average Directional Index) with +DI and -DI."""
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr.replace(0, 1e-10))
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr.replace(0, 1e-10))

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10))
    adx = dx.rolling(period).mean()

    return adx, plus_di, minus_di


def compute_indicators(ohlcv: list[OHLCV]) -> Indicators:
    """
    Compute all technical indicators from OHLCV data.
    Pure function — no I/O, no side effects.
    """
    if len(ohlcv) < 2:
        return Indicators(
            rsi_14=50.0, macd=0.0, macd_signal=0.0, macd_hist=0.0,
            sma_20=0.0, sma_50=0.0, sma_200=0.0,
            volume_ratio=1.0, atr_14=0.0,
            trend=TrendDirection.NEUTRAL, trend_strength=0.0,
        )

    # Convert to DataFrame
    df = pd.DataFrame([{
        "timestamp": o.timestamp,
        "open": o.open,
        "high": o.high,
        "low": o.low,
        "close": o.close,
        "volume": o.volume,
    } for o in ohlcv]).set_index("timestamp").sort_index()

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # RSI
    rsi_series = calculate_rsi(close, 14)
    rsi_14 = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0

    # MACD
    macd, macd_signal, macd_hist = calculate_macd(close)
    macd_val = float(macd.iloc[-1]) if not pd.isna(macd.iloc[-1]) else 0.0
    macd_sig = float(macd_signal.iloc[-1]) if not pd.isna(macd_signal.iloc[-1]) else 0.0
    macd_h = float(macd_hist.iloc[-1]) if not pd.isna(macd_hist.iloc[-1]) else 0.0

    # SMAs
    sma_20 = float(calculate_sma(close, 20).iloc[-1]) if len(close) >= 20 else close.iloc[-1]
    sma_50 = float(calculate_sma(close, 50).iloc[-1]) if len(close) >= 50 else close.iloc[-1]
    sma_200 = float(calculate_sma(close, 200).iloc[-1]) if len(close) >= 200 else close.iloc[-1]

    # Volume ratio
    vol_avg_20 = volume.rolling(20).mean().iloc[-1]
    vol_ratio = float(volume.iloc[-1] / vol_avg_20) if vol_avg_20 > 0 else 1.0

    # ATR
    atr_series = calculate_atr(high, low, close, 14)
    atr_14 = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 0.0

    # ADX / Trend
    adx, plus_di, minus_di = calculate_adx(high, low, close, 14)
    adx_val = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0
    pdi = float(plus_di.iloc[-1]) if not pd.isna(plus_di.iloc[-1]) else 0.0
    mdi = float(minus_di.iloc[-1]) if not pd.isna(minus_di.iloc[-1]) else 0.0

    if pdi > mdi and adx_val > 25:
        trend = TrendDirection.BULLISH
        strength = min(adx_val / 50, 1.0)
    elif mdi > pdi and adx_val > 25:
        trend = TrendDirection.BEARISH
        strength = min(adx_val / 50, 1.0)
    else:
        trend = TrendDirection.NEUTRAL
        strength = min(adx_val / 50, 1.0)

    return Indicators(
        rsi_14=rsi_14,
        macd=macd_val,
        macd_signal=macd_sig,
        macd_hist=macd_h,
        sma_20=sma_20,
        sma_50=sma_50,
        sma_200=sma_200,
        volume_ratio=vol_ratio,
        atr_14=atr_14,
        trend=trend,
        trend_strength=strength,
    )