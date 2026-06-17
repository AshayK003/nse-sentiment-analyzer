"""Shared fixtures and Streamlit mock."""
import sys
import pytest
from unittest.mock import MagicMock

# Mock streamlit before any test imports app.py
st_mock = MagicMock()

# Streamlit decorators and config can run at module level
st_mock.cache_resource = lambda f=None, **kw: f if f else (lambda x: x)
st_mock.set_page_config = lambda **kw: None

# Module-level UI calls need to return unpackable values
st_mock.columns.side_effect = lambda n: tuple(MagicMock() for _ in range(n if isinstance(n, int) else len(n)))
st_mock.selectbox.return_value = ""
st_mock.text_input.return_value = ""
st_mock.button.return_value = False
st_mock.checkbox.return_value = False
st_mock.write.return_value = None
st_mock.markdown.return_value = None
st_mock.caption.return_value = None
st_mock.subheader.return_value = None
st_mock.header.return_value = None
st_mock.metric.return_value = None
st_mock.progress.return_value = None
st_mock.success.return_value = None
st_mock.warning.return_value = None
st_mock.info.return_value = None
st_mock.error.return_value = None
st_mock.spinner.return_value.__enter__.return_value = None
st_mock.spinner.return_value.__exit__.return_value = None
st_mock.container.return_value.__enter__.return_value = None
st_mock.container.return_value.__exit__.return_value = None
st_mock.expander.return_value.__enter__.return_value = None
st_mock.expander.return_value.__exit__.return_value = None
st_mock.sidebar.columns.return_value = (MagicMock(), MagicMock())
st_mock.sidebar.text_input.return_value = ""
st_mock.sidebar.button.return_value = False
st_mock.sidebar.write.return_value = None
st_mock.sidebar.markdown.return_value = None
st_mock.sidebar.caption.return_value = None
st_mock.sidebar.header.return_value = None
st_mock.sidebar.metric.return_value = None
st_mock.sidebar.subheader.return_value = None

sys.modules["streamlit"] = st_mock

# Mock yfinance
yf_mock = MagicMock()
sys.modules["yfinance"] = yf_mock

# Mock vaderSentiment
sys.modules["vaderSentiment"] = MagicMock()
sys.modules["vaderSentiment.vaderSentiment"] = MagicMock()

# Mock duckduckgo_search
sys.modules["duckduckgo_search"] = MagicMock()
sys.modules["duckduckgo_search.DDGS"] = MagicMock()

from app import (
    get_overall_signal,
    format_large_num,
    get_sentiment_emoji,
    analyze_headline_sentiment,
    get_stock_info,
    search_news,
    analyze_ticker,
    cache_get,
    cache_set,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before each test that touches it."""
    from app import CACHE_FILE
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    yield
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()


@pytest.fixture
def mock_sia():
    """Return a predictable VADER-like analyzer."""
    sia = MagicMock()
    def polarity_scores(text):
        pos_words = ["bullish", "surge", "profit", "positive", "upgrade", "growth"]
        neg_words = ["bearish", "plunge", "loss", "negative", "downgrade", "crash"]
        text_lower = text.lower()
        pos = sum(1 for w in pos_words if w in text_lower)
        neg = sum(1 for w in neg_words if w in text_lower)
        compound = min(0.9, 0.3 * pos) if pos > neg else max(-0.9, -0.3 * neg)
        return {"compound": compound, "pos": max(0, compound), "neg": max(0, -compound), "neu": 1 - abs(compound)}
    sia.polarity_scores = polarity_scores
    return sia
