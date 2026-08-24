"""Smoke tests for import regressions and core module wiring."""

import aggregate_sentiment
import data_fetcher
import indicators
import sentiment
from sentiment import get_sia


def test_module_paths_not_empty():
    assert hasattr(data_fetcher, "get_stock_info")
    assert hasattr(data_fetcher, "resolve_ticker")
    assert hasattr(data_fetcher, "search_news")
    assert hasattr(sentiment, "get_sia")
    assert hasattr(sentiment, "analyze_headline_sentiment")
    assert hasattr(indicators, "get_technical_indicators")
    assert hasattr(aggregate_sentiment, "compute_smartscore")


def test_vader_lexicon_loaded():
    sia = get_sia()
    assert "bullish" in sia.lexicon
    assert "bearish" in sia.lexicon
    assert sia.lexicon["growth"] == 1.0
