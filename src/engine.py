"""
Orchestrator — wires Data Engine + Strategy Engine into single analysis flow.
"""

from __future__ import annotations

import time
import logging
from datetime import datetime
from typing import Optional

from .data.yahoo import fetch_ohlcv, fetch_price_data
from .data.rss import fetch_market_headlines, fetch_news_for_ticker
from .data.cache import invalidate_ticker_cache, get_cache_stats
from .strategies.sentiment import analyze_articles, aggregate_sentiment
from .strategies.indicators import compute_indicators
from .strategies.classifier import classify_headline
from .strategies.cascade import detect_cascade
from .strategies.verdict import build_verdict, get_verdict_summary
from .contracts import (
    AnalysisRequest, AnalysisResult, Verdict, PriceData,
    SentimentScore, Headline, NewsArticle, OHLCV, Indicators,
)

log = logging.getLogger(__name__)


def analyze(request: AnalysisRequest) -> AnalysisResult:
    """
    Full analysis pipeline: ticker → data → strategies → verdict.

    Args:
        request: Analysis parameters (ticker, period, options)

    Returns:
        AnalysisResult with verdict, raw data, and metadata
    """
    start_time = time.time()
    ticker = request.ticker.upper().strip()

    log.info("Starting analysis for %s (period=%s)", ticker, request.period)

    try:
        # 1. Fetch price data (OHLCV + indicators)
        log.debug("Fetching price data for %s", ticker)
        price_data = fetch_price_data(ticker, request.period)

        # 2. Fetch news
        headlines = []
        articles = []

        if request.include_news:
            log.debug("Fetching news for %s", ticker)
            # Ticker-specific news
            ticker_articles = fetch_news_for_ticker(ticker, limit=30)
            articles.extend(ticker_articles)

            # Market headlines for context
            market_headlines = fetch_market_headlines(limit=50)
            headlines.extend(market_headlines)

        # 3. Sentiment analysis
        if articles:
            log.debug("Analyzing sentiment for %d articles", len(articles))
            sentiments = analyze_articles(articles)
            aggregated_sentiment = aggregate_sentiment(sentiments)
        else:
            # Neutral sentiment if no news
            aggregated_sentiment = SentimentScore(
                compound=0.0, positive=0.0, negative=0.0, neutral=1.0,
                confidence=0.0, event_type=None, event_confidence=0.0,
            )

        # 4. Classify headlines for cascade detection
        all_headlines = headlines
        if not all_headlines and articles:
            all_headlines = [Headline(
                title=a.title, summary=a.summary, url=a.url,
                source=a.source, published=a.published, ticker=a.ticker
            ) for a in articles]

        cascade = None
        if all_headlines:
            sentiments = [analyze_headline(h) for h in all_headlines]
            cascade = detect_cascade(all_headlines, sentiments)

        # 5. Build verdict
        log.debug("Building verdict")
        verdict = build_verdict(
            ticker=ticker,
            price_data=price_data,
            sentiment=aggregated_sentiment,
            cascade=cascade,
            request=request,
        )

        fetch_duration = int((time.time() - start_time) * 1000)

        return AnalysisResult(
            verdict=verdict,
            raw_headlines=all_headlines,
            raw_articles=articles,
            cached=False,
            fetch_duration_ms=fetch_duration,
        )

    except Exception as e:
        log.error("Analysis failed for %s: %s", ticker, e)
        # Return error verdict
        from .contracts import Verdict, Signal, PriceData, Indicators, TrendDirection
        error_verdict = Verdict(
            ticker=ticker,
            signal=Signal.HOLD,
            confidence=0,
            sentiment=SentimentScore(0, 0, 0, 1, 0, None, 0),
            indicators=Indicators(
                rsi_14=50, macd=0, macd_signal=0, macd_hist=0,
                sma_20=0, sma_50=0, sma_200=0, volume_ratio=1,
                atr_14=0, trend=TrendDirection.NEUTRAL, trend_strength=0,
            ),
            rationale=f"Analysis error: {str(e)}",
        )
        return AnalysisResult(
            verdict=error_verdict,
            raw_headlines=[],
            raw_articles=[],
            cached=False,
            fetch_duration_ms=int((time.time() - start_time) * 1000),
        )


def analyze_headline(headline: Headline) -> SentimentScore:
    """Analyze single headline (for cascade detection)."""
    from .strategies.sentiment import analyze_headline as _analyze
    return _analyze(headline)


def refresh_ticker(ticker: str) -> None:
    """Force refresh all cached data for a ticker."""
    invalidate_ticker_cache(ticker)
    log.info("Cache invalidated for %s", ticker)


def get_system_stats() -> dict:
    """Get cache and system statistics."""
    return get_cache_stats()