"""Smoke tests for import regressions and core module wiring."""

import aggregate_sentiment
import data_fetcher
import indicators
import sentiment
from aggregate_sentiment import compute_smartscore
from cascade import detect_cascade
from data_fetcher import (
    _strip_html,
    fetch_market_headlines,
    get_cached_history,
    get_stock_info,
    resolve_ticker,
    search_news,
)
from event_classifier import adjust_with_event, classify_headline
from indicators import get_technical_indicators
from intraday import compute_pivot_levels, compute_vwap, get_vix
from market_data import get_fii_dii_flow, get_market_pulse, get_mmi
from persistence import (
    calc_portfolio_pnl,
    get_entry_info,
    history_to_csv,
    load_entry_prices,
    load_fiidii_history,
    load_portfolio,
    load_sentiment_history,
    load_track_record,
    save_entry_price,
    save_fiidii_snapshot,
    save_portfolio,
    save_sentiment_history,
    save_track_record,
    update_source_accuracy,
)
from render import _is_valid_num, render_dashboard
from sentiment import analyze_headline_sentiment, get_sia, get_weighted_signal


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
