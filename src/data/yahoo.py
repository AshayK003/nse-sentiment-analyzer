"""
OHLCV data fetcher — yfinance wrapper with caching and error handling.
Pure data layer: no business logic, no sentiment, no strategies.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

from .cache import cached, invalidate
from ..contracts import OHLCV, PriceData, Indicators, TrendDirection

log = logging.getLogger(__name__)

# Valid periods for yfinance
VALID_PERIODS = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
VALID_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}


def _normalize_ticker(ticker: str) -> str:
    """Ensure ticker has .NS suffix for NSE."""
    ticker = ticker.strip().upper()
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        return f"{ticker}.NS"
    return ticker


def _compute_indicators(ohlcv: list[OHLCV]) -> Indicators:
    """Compute technical indicators from OHLCV data."""
    if len(ohlcv) < 2:
        return _empty_indicators()

    # Convert to pandas for calculation
    df = pd.DataFrame([{
        "timestamp": o.timestamp,
        "open": o.open,
        "high": o.high,
        "low": o.low,
        "close": o.close,
        "volume": o.volume,
    } for o in ohlcv])

    df = df.set_index("timestamp").sort_index()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # RSI 14
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))

    # MACD
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd = ema_12 - ema_26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - macd_signal

    # SMAs
    sma_20 = close.rolling(20).mean().iloc[-1]
    sma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else float("nan")
    sma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else float("nan")

    # Volume ratio
    vol_avg_20 = volume.rolling(20).mean().iloc[-1]
    vol_ratio = volume.iloc[-1] / vol_avg_20 if vol_avg_20 > 0 else 1.0

    # ATR 14
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]

    # ADX / Trend
    trend, trend_strength = _compute_trend(df)

    return Indicators(
        rsi_14=float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0,
        macd=float(macd.iloc[-1]) if not pd.isna(macd.iloc[-1]) else 0.0,
        macd_signal=float(macd_signal.iloc[-1]) if not pd.isna(macd_signal.iloc[-1]) else 0.0,
        macd_hist=float(macd_hist.iloc[-1]) if not pd.isna(macd_hist.iloc[-1]) else 0.0,
        sma_20=float(sma_20) if not pd.isna(sma_20) else close.iloc[-1],
        sma_50=float(sma_50) if not pd.isna(sma_50) else close.iloc[-1],
        sma_200=float(sma_200) if not pd.isna(sma_200) else close.iloc[-1],
        volume_ratio=float(vol_ratio) if vol_ratio else 1.0,
        atr_14=float(atr) if not pd.isna(atr) else 0.0,
        trend=trend,
        trend_strength=trend_strength,
    )


def _compute_trend(df: pd.DataFrame) -> tuple[TrendDirection, float]:
    """Determine trend direction and strength using ADX."""
    if len(df) < 20:
        return TrendDirection.NEUTRAL, 0.0

    high = df["high"]
    low = df["low"]
    close = df["close"]

    # +DI, -DI
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr.replace(0, 1e-10))
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr.replace(0, 1e-10))

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10))
    adx = dx.rolling(14).mean().iloc[-1]

    if pd.isna(adx):
        return TrendDirection.NEUTRAL, 0.0

    # Determine trend
    if plus_di.iloc[-1] > minus_di.iloc[-1] and adx > 25:
        return TrendDirection.BULLISH, min(float(adx) / 50, 1.0)
    elif minus_di.iloc[-1] > plus_di.iloc[-1] and adx > 25:
        return TrendDirection.BEARISH, min(float(adx) / 50, 1.0)
    else:
        return TrendDirection.NEUTRAL, min(float(adx) / 50, 1.0)


def _empty_indicators() -> Indicators:
    return Indicators(
        rsi_14=50.0, macd=0.0, macd_signal=0.0, macd_hist=0.0,
        sma_20=0.0, sma_50=0.0, sma_200=0.0,
        volume_ratio=1.0, atr_14=0.0,
        trend=TrendDirection.NEUTRAL, trend_strength=0.0,
    )


@cached(ttl_seconds=300, key_prefix="ohlcv:")
def fetch_ohlcv(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    _force_refresh: bool = False,
) -> list[OHLCV]:
    """
    Fetch OHLCV data from yfinance.

    Args:
        ticker: Stock symbol (e.g., "RELIANCE" or "RELIANCE.NS")
        period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        interval: Data interval (1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo)

    Returns:
        List of OHLCV bars, sorted by timestamp ascending

    Raises:
        ValueError: If period/interval invalid or no data returned
    """
    if period not in VALID_PERIODS:
        raise ValueError(f"Invalid period: {period}. Valid: {VALID_PERIODS}")
    if interval not in VALID_INTERVALS:
        raise ValueError(f"Invalid interval: {interval}. Valid: {VALID_INTERVALS}")

    ticker = _normalize_ticker(ticker)

    try:
        log.debug("Fetching OHLCV: %s period=%s interval=%s", ticker, period, interval)
        yf_ticker = yf.Ticker(ticker)
        hist = yf_ticker.history(period=period, interval=interval, auto_adjust=True)

        if hist.empty:
            raise ValueError(f"No data returned for {ticker} (period={period}, interval={interval})")

        bars = []
        for ts, row in hist.iterrows():
            bars.append(OHLCV(
                timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=int(row["Volume"]) if row["Volume"] else 0,
                ticker=ticker.replace(".NS", "").replace(".BO", ""),
            ))

        log.info("Fetched %d OHLCV bars for %s", len(bars), ticker)
        return bars

    except Exception as e:
        log.error("OHLCV fetch failed for %s: %s", ticker, e)
        raise


@cached(ttl_seconds=60, key_prefix="snapshot:")
def fetch_price_data(
    ticker: str,
    period: str = "1y",
    _force_refresh: bool = False,
) -> PriceData:
    """
    Fetch complete price data with indicators.
    TTL: 60 seconds for near-realtime feel.
    """
    ticker = _normalize_ticker(ticker)

    try:
        yf_ticker = yf.Ticker(ticker)

        # Get price from fast_info
        try:
            fast_info = yf_ticker.fast_info
            current_price = float(fast_info.get("lastPrice", fast_info.get("last_price", 0)))
            previous_close = float(fast_info.get("previousClose", fast_info.get("previous_close", 0)))
        except Exception:
            info = yf_ticker.info
            current_price = float(info.get("currentPrice", info.get("regularMarketPrice", 0)))
            previous_close = float(info.get("previousClose", info.get("regularMarketPreviousClose", 0)))

        if current_price == 0:
            raise ValueError("Zero price returned")

        change_pct = ((current_price - previous_close) / previous_close * 100) if previous_close else 0

        # Fetch OHLCV for indicators
        ohlcv = fetch_ohlcv(ticker, period=period, interval="1d", _force_refresh=_force_refresh)
        indicators = _compute_indicators(ohlcv)

        # 52-week high/low from history
        hist_1y = yf_ticker.history(period="1y", auto_adjust=True)
        high_52w = float(hist_1y["High"].max()) if not hist_1y.empty else 0.0
        low_52w = float(hist_1y["Low"].min()) if not hist_1y.empty else 0.0

        # Institutional data (FII/DII) - placeholder for now
        institutional = []

        return PriceData(
            ohlcv=ohlcv,
            indicators=indicators,
            institutional=institutional,
            current_price=current_price,
            change_pct=change_pct,
            high_52w=high_52w,
            low_52w=low_52w,
        )

    except Exception as e:
        log.error("Price data fetch failed for %s: %s", ticker, e)
        raise


def invalidate_ticker_cache(ticker: str) -> int:
    """Invalidate all cached data for a ticker."""
    ticker = _normalize_ticker(ticker).replace(".NS", "").replace(".BO", "")
    return invalidate(pattern=ticker)