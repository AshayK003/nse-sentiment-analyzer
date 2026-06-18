"""
Pytest configuration and fixtures for NSE Sentiment Analyzer.
"""

import os
import sys
import json
from datetime import datetime, timedelta

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── Sample Data Fixtures ───


@pytest.fixture
def sample_stock_data():
    """Minimal stock info dict returned by get_stock_info."""
    return {
        "name": "Test Company Ltd",
        "sector": "Technology",
        "industry": "Software",
        "market_cap": 1_000_000_000,
        "pe_ratio": 25.0,
        "current_price": 100.0,
        "change": 2.5,
        "change_pct": 2.56,
        "day_high": 102.0,
        "day_low": 98.0,
        "volume": 1_000_000,
        "52w_high": 120.0,
        "52w_low": 80.0,
    }


@pytest.fixture
def sample_news_items():
    """Sample news articles returned by search_news."""
    return [
        {
            "title": "Test Company reports strong quarterly profit",
            "body": "The company exceeded analyst expectations with 20% profit growth.",
            "date": "2026-06-18",
            "url": "https://example.com/news/1",
            "source": "Economic Times",
            "author": "Reporter A",
            "subreddit": "",
        },
        {
            "title": "Test Company faces regulatory headwinds",
            "body": "New regulations may impact the sector.",
            "date": "2026-06-17",
            "url": "https://example.com/news/2",
            "source": "Moneycontrol",
            "author": "",
            "subreddit": "",
        },
        {
            "title": "Analyst maintains neutral rating on Test Company",
            "body": "",
            "date": "2026-06-16",
            "url": "https://example.com/news/3",
            "source": "LiveMint",
            "author": "",
            "subreddit": "",
        },
    ]


@pytest.fixture
def sample_headline_scores():
    """Sentiment scores corresponding to sample_news_items."""
    return [
        {"compound": 0.8, "source": "Economic Times"},
        {"compound": -0.6, "source": "Moneycontrol"},
        {"compound": 0.1, "source": "LiveMint"},
    ]


@pytest.fixture
def sample_technical_indicators():
    """Full technical indicator dict as returned by get_technical_indicators."""
    return {
        "rsi": 55.0,
        "sma_50": 95.0,
        "sma_200": 85.0,
        "close": 100.0,
        "close_prev": 99.0,
        "macd_line": 0.5,
        "macd_signal": 0.3,
        "macd_hist": 0.2,
        "sma50_cross": None,
        "sma200_cross": "bullish",
        "avg_volume_50": 800_000,
    }


@pytest.fixture
def sample_fii_dii_data():
    """Sample FII/DII institutional flow data."""
    return {
        "fii_net": 500.0,
        "dii_net": -200.0,
        "date": "2026-06-17",
        "combined_net": 300.0,
        "fii_action": "Buying",
        "dii_action": "Selling",
    }


@pytest.fixture
def partial_technical_indicators():
    """Indicators with missing SMA values (short history)."""
    return {
        "rsi": 45.0,
        "sma_50": None,
        "sma_200": None,
        "close": 100.0,
        "close_prev": 99.0,
        "macd_line": 0.0,
        "macd_signal": 0.0,
        "macd_hist": 0.001,
        "sma50_cross": None,
        "sma200_cross": None,
        "avg_volume_50": None,
    }


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Point all persistence data files to a temp dir for test isolation.
    Patches DATA_DIR AND the derived file paths (PORTFOLIO_FILE, TRACK_FILE, CACHE_FILE)."""
    monkeypatch.setattr("persistence.DATA_DIR", tmp_path)
    monkeypatch.setattr("persistence.PORTFOLIO_FILE", tmp_path / "portfolio.json")
    monkeypatch.setattr("persistence.TRACK_FILE", tmp_path / "track_record.json")
    monkeypatch.setattr("persistence.CACHE_FILE", tmp_path / "cache.json")
    return tmp_path


# ─── Pandas fixture helpers (for indicators tests) ───


@pytest.fixture
def pandas_hist():
    """Create a realistic 1yr OHLCV DataFrame for testing indicators."""
    import pandas as pd
    import numpy as np
    dates = pd.date_range(end="2026-06-18", periods=252, freq="B")
    np.random.seed(42)
    base = 100.0
    prices = base + np.cumsum(np.random.randn(252) * 0.5)
    return pd.DataFrame({
        "Open": prices,
        "High": prices * 1.01,
        "Low": prices * 0.99,
        "Close": prices,
        "Volume": np.random.randint(500_000, 2_000_000, 252),
    }, index=dates)


@pytest.fixture
def short_hist():
    """Only 30 rows — insufficient for SMA 50/200."""
    import pandas as pd
    import numpy as np
    dates = pd.date_range(end="2026-06-18", periods=30, freq="B")
    return pd.DataFrame({
        "Open": 100.0, "High": 101.0, "Low": 99.0,
        "Close": 100.5, "Volume": 1_000_000,
    }, index=dates)
