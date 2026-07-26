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

from ..cache import cached, invalidate
from ..contracts import OHLCV, PriceSnapshot

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

        # Convert to OHLCV list
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
def fetch_price_snapshot(
    ticker: str,
    _force_refresh: bool = False,
) -> PriceSnapshot:
    """
    Fetch current price snapshot with key metrics.
    TTL: 60 seconds for near-realtime feel.
    """
    ticker = _normalize_ticker(ticker)

    try:
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info

        # Get current price from fast_info (faster than info)
        try:
            fast_info = yf_ticker.fast_info
            current_price = float(fast_info.get("last_price", 0))
            previous_close = float(fast_info.get("previous_close", 0))
        except Exception:
            # Fallback to info
            current_price = float(info.get("currentPrice", info.get("regularMarketPrice", 0)))
            previous_close = float(info.get("previousClose", info.get("regularMarketPreviousClose", 0)))

        if current_price == 0:
            raise ValueError("Zero price returned")

        change_pct = ((current_price - previous_close) / previous_close * 100) if previous_close else 0

        return PriceSnapshot(
            ticker=ticker.replace(".NS", "").replace(".BO", ""),
            name=info.get("longName", info.get("shortName", ticker)),
            current_price=current_price,
            previous_close=previous_close,
            change_pct=change_pct,
            volume=int(info.get("volume", info.get("regularMarketVolume", 0))),
            market_cap=info.get("marketCap"),
            day_high=info.get("dayHigh"),
            day_low=info.get("dayLow"),
            fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
            fifty_two_week_low=info.get("fiftyTwoWeekLow"),
            avg_volume=info.get("averageVolume"),
            timestamp=datetime.now(),
        )

    except Exception as e:
        log.error("Price snapshot failed for %s: %s", ticker, e)
        raise


def invalidate_ticker_cache(ticker: str) -> int:
    """Invalidate all cached data for a ticker."""
    ticker = _normalize_ticker(ticker).replace(".NS", "").replace(".BO", "")
    return invalidate(pattern=ticker)