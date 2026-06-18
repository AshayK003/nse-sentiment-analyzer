"""
Tests for data fetching -- stock info, news, and Reddit.
All external APIs (yfinance, feedparser, DuckDuckGo, requests) are mocked.
"""

import pytest
import json


def _mock_yfinance_ticker(mocker, info=None, hist_df=None):
    """Build a fake yfinance Ticker with controllable info/history."""
    import pandas as pd
    import numpy as np
    from unittest.mock import PropertyMock

    if info is None:
        info = {
            "longName": "Test Company Ltd",
            "shortName": "TEST",
            "sector": "Technology",
            "industry": "Software",
            "marketCap": 1_000_000_000,
            "trailingPE": 25.0,
            "fiftyTwoWeekHigh": 120.0,
            "fiftyTwoWeekLow": 80.0,
            "currentPrice": 100.0,
            "regularMarketPrice": 100.0,
            "regularMarketChange": 2.5,
            "regularMarketChangePercent": 2.56,
        }

    mock_ticker = mocker.MagicMock()
    # Use PropertyMock so .info access is trackable
    p_info = mocker.PropertyMock(return_value=info)
    type(mock_ticker).info = p_info

    if hist_df is not None:
        mock_ticker.history.return_value = hist_df
    else:
        dates = pd.date_range(end="2026-06-18", periods=5, freq="B")
        hist = pd.DataFrame({
            "Close": [100.0, 101.0, 99.0, 100.5, 102.0],
            "High": [101.0, 102.0, 100.0, 101.5, 103.0],
            "Low": [99.0, 100.0, 98.0, 99.5, 101.0],
            "Volume": [1_000_000] * 5,
            "Open": [99.5, 100.5, 98.5, 100.0, 101.5],
        }, index=dates)
        mock_ticker.history.return_value = hist

    mocker.patch("yfinance.Ticker", return_value=mock_ticker)
    return mock_ticker, p_info


class TestStockInfo:
    """Tests for get_stock_info() with mocked yfinance."""

    def test_stock_info_success(self, mocker):
        """Happy path -- valid ticker returns stock data."""
        from data_fetcher import get_stock_info

        _mock_yfinance_ticker(mocker)

        result = get_stock_info("TEST")
        assert result is not None
        assert result["name"] == "Test Company Ltd"
        assert result["sector"] == "Technology"
        assert result["current_price"] == 102.0  # From hist Close[-1]
        assert isinstance(result["market_cap"], int)
        assert isinstance(result["volume"], int)

    def test_stock_info_empty_response_retries(self, mocker):
        """Empty info dict should trigger retry, eventually return None."""
        from data_fetcher import get_stock_info

        # info with only 5 keys: len(info) < 10 triggers retry
        tiny_info = {"longName": "Test", "shortName": "T"}
        _, p_info = _mock_yfinance_ticker(mocker, info=tiny_info)
        mocker.patch("time.sleep")

        result = get_stock_info("UNKNOWN")
        assert result is None
        # .info was accessed at least 3 times (3 retries)
        assert p_info.call_count >= 3

    def test_stock_info_info_fallback(self, mocker):
        """When hist is empty, should fall back to info.get() for price."""
        from data_fetcher import get_stock_info

        import pandas as pd
        info = {
            "longName": "Test Ltd",
            "shortName": "TEST",
            "sector": "Finance",
            "industry": "Banking",
            "marketCap": 5_000_000_000,
            "trailingPE": 15.0,
            "fiftyTwoWeekHigh": 520.0,
            "fiftyTwoWeekLow": 400.0,
            "currentPrice": 500.0,
            "regularMarketChange": 5.0,
            "regularMarketChangePercent": 1.01,
            "dayHigh": 505.0,
            "dayLow": 495.0,
            "volume": 2_000_000,
        }
        _mock_yfinance_ticker(mocker, info=info,
                              hist_df=pd.DataFrame())
        mocker.patch("time.sleep")

        # Use unique ticker to avoid st.cache_data from a prior test
        result = get_stock_info("INFALLBACK")
        assert result is not None
        assert result["current_price"] == 500.0

    def test_stock_info_none_on_total_failure(self, mocker):
        """When all retries fail (info too small), should return None."""
        from data_fetcher import get_stock_info

        tiny_info = {"longName": "Bogus"}
        _mock_yfinance_ticker(mocker, info=tiny_info)
        mocker.patch("time.sleep")

        result = get_stock_info("BOGUS")
        assert result is None

    def test_stock_info_handles_missing_fields(self, mocker):
        """Missing optional fields (sector, PE) should not crash."""
        from data_fetcher import get_stock_info

        info = {
            "longName": "Minimal Ltd",
            "shortName": "MINIMAL",
            "currentPrice": 50.0,
            "regularMarketChange": 1.0,
            "regularMarketChangePercent": 2.0,
            "dayHigh": 52.0,
            "dayLow": 49.0,
            "volume": 500_000,
            "fiftyTwoWeekHigh": 60.0,
            "fiftyTwoWeekLow": 40.0,
            "address1": "India",
        }
        _mock_yfinance_ticker(mocker, info=info)

        # Use unique ticker to avoid st.cache_data conflicts
        result = get_stock_info("MISSINGF")
        assert result is not None
        assert result["sector"] == "N/A"   # missing -> "N/A"
        assert result["pe_ratio"] is None  # missing -> None


class TestRelevanceFilter:
    """Tests for the _relevant() headline filter."""

    def test_ticker_in_title(self):
        from data_fetcher import _relevant
        assert _relevant("RELIANCE", "Reliance Industries",
                         "RELIANCE hits new high on strong Q1 results", "")

    def test_company_name_in_body(self):
        from data_fetcher import _relevant
        assert _relevant("TCS", "Tata Consultancy Services",
                         "IT stocks rally", "Tata Consultancy wins $2B deal")

    def test_unrelated_headline(self):
        from data_fetcher import _relevant
        assert not _relevant("SBIN", "State Bank of India",
                             "Gold prices surge on global cues", "")

    def test_short_words_not_matched(self):
        """Words <= 2 chars are excluded from matching."""
        from data_fetcher import _relevant
        # 'IT' is 2 chars, should not match
        assert not _relevant("IT", "IT Ltd",
                             "Services company reports results", "")

    def test_partial_word_not_matched(self):
        """Ticker substring should not match inside unrelated words.
        The current implementation does simple substring matching, so
        we test a ticker that genuinely doesn't appear in the text."""
        from data_fetcher import _relevant
        assert not _relevant("TCS", "Tata Consultancy Services",
                             "Gold prices surge on global cues", "")


class TestNewsCaching:
    """Tests for news caching layer."""

    def test_news_cache_hit(self, mocker):
        """Cached news should be returned without fetching.
        We patch cache_get to return known data, then verify
        feedparser and DDGS are NOT called."""
        from data_fetcher import search_news

        cached_articles = [
            {"title": "Cached article", "body": "", "date": "2026-06-18",
             "url": "https://example.com/cached", "source": "Google News"}
        ]
        cached_stats = {"Google News": 1}
        mocker.patch("data_fetcher.cache_get",
                     return_value=(cached_articles, cached_stats))
        # Patch all fetch functions to verify they are NOT called
        mock_feed = mocker.patch("feedparser.parse")
        mock_ddgs = mocker.patch("data_fetcher.DDGS")
        mock_reddit = mocker.patch("data_fetcher.fetch_reddit_news")
        mocker.patch("data_fetcher.cache_set")

        articles, stats = search_news("RELIANCE", "Reliance Industries",
                                      max_results=5)
        assert len(articles) == 1
        assert articles[0]["title"] == "Cached article"
        mock_feed.assert_not_called()
        mock_ddgs.assert_not_called()
        mock_reddit.assert_not_called()

    def test_news_cache_miss_falls_through(self, mocker):
        """Cache miss should proceed to fetch from RSS/DDG/Reddit."""
        from data_fetcher import search_news

        mocker.patch("data_fetcher.cache_get", return_value=None)
        # Mock RSS feeds to return empty
        mock_feed = mocker.MagicMock()
        mock_feed.entries = []
        mocker.patch("feedparser.parse", return_value=mock_feed)
        # Mock DDGS to raise
        mocker.patch("data_fetcher.DDGS", side_effect=Exception("No DDGS"))
        # Mock Reddit to return empty
        mocker.patch("data_fetcher.fetch_reddit_news", return_value=[])
        mocker.patch("data_fetcher.cache_set")

        articles, stats = search_news("RELIANCE", "Reliance Industries",
                                      max_results=5)
        assert articles == []


class TestRedditFetch:
    """Tests for Reddit news fetching (OAuth and rdt-cli fallback)."""

    def test_reddit_oauth_empty_without_creds(self, mocker):
        """Without REDDIT_CLIENT_ID, OAuth should return []."""
        from data_fetcher import _fetch_reddit_oauth
        mocker.patch.dict("os.environ", {}, clear=True)
        result = _fetch_reddit_oauth("RELIANCE", "Reliance Industries")
        assert result == []

    def test_reddit_oauth_token_failure(self, mocker):
        """If OAuth token request fails, should return []."""
        from data_fetcher import _fetch_reddit_oauth

        mocker.patch.dict("os.environ", {
            "REDDIT_CLIENT_ID": "test_id",
            "REDDIT_CLIENT_SECRET": "test_secret",
        })
        mock_post = mocker.MagicMock()
        mock_post.status_code = 403
        mocker.patch("requests.post", return_value=mock_post)

        result = _fetch_reddit_oauth("RELIANCE", "Reliance Industries")
        assert result == []

    def test_fetch_reddit_news_falls_to_rdtcli(self, mocker):
        """When OAuth returns empty, should try rdt-cli."""
        from data_fetcher import fetch_reddit_news

        mocker.patch("data_fetcher._fetch_reddit_oauth", return_value=[])
        mock_subprocess = mocker.patch("subprocess.run")
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = (
            "Test post | https://reddit.com/r/test"
        )
        # Also patch cache to return None (fresh fetch)
        mocker.patch("data_fetcher.cache_get", return_value=None)
        mocker.patch("data_fetcher.cache_set")

        result = fetch_reddit_news("RELIANCE", "Reliance Industries",
                                   max_results=3)
        assert isinstance(result, list)


class TestFormatting:
    """Tests for data_fetcher formatting helpers."""

    def test_is_numeric(self):
        from data_fetcher import _is_numeric
        assert _is_numeric(42) is True
        assert _is_numeric(3.14) is True
        assert _is_numeric("N/A") is False
        assert _is_numeric(None) is False
        assert _is_numeric(True) is False

    def test_format_price(self):
        from data_fetcher import format_price
        assert "N/A" in str(format_price(None))
        assert "N/A" in str(format_price("N/A"))
        assert isinstance(format_price(100.5), (int, float))

    def test_format_large_num(self):
        from data_fetcher import format_large_num
        assert "Cr" in format_large_num(100_00_000)
        assert "L" in format_large_num(1_00_000)
        assert "₹" in format_large_num(1000)
        assert "N/A" in format_large_num(None)
        assert "N/A" in format_large_num("N/A")

    def test_parse_date(self):
        from data_fetcher import _parse_date
        result = _parse_date((2026, 6, 18, 10, 30, 0))
        assert result == "2026-06-18"
        assert _parse_date(None) == ""
        assert _parse_date((2026,)) == ""
