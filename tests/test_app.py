"""Tests for NSE Sentiment Analyzer.

Focus: pure functions, pipeline integration, edge cases, error paths.
Avoids testing Streamlit UI implementation details.
"""

import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from app import cache_get, cache_set


# ─── get_overall_signal() ──────────────────────────────────────

class TestGetOverallSignal:
    def test_empty_returns_neutral(self):
        from app import get_overall_signal
        signal, compound, emoji = get_overall_signal([])
        assert signal == "NEUTRAL"
        assert compound == 0.0
        assert emoji == "⚪"

    def test_all_positive_is_bullish(self):
        from app import get_overall_signal
        scores = [{"compound": 0.5}, {"compound": 0.8}, {"compound": 0.3}]
        signal, compound, emoji = get_overall_signal(scores)
        assert "BULLISH" in signal
        assert compound > 0.2
        assert emoji == "🟢"

    def test_all_negative_is_bearish(self):
        from app import get_overall_signal
        scores = [{"compound": -0.5}, {"compound": -0.8}, {"compound": -0.3}]
        signal, compound, emoji = get_overall_signal(scores)
        assert "BEARISH" in signal
        assert compound < -0.2
        assert emoji == "🔴"

    def test_mixed_with_more_positive(self):
        from app import get_overall_signal
        scores = [{"compound": 0.6}, {"compound": 0.5}, {"compound": -0.1}]
        signal, _, _ = get_overall_signal(scores)
        assert "BULLISH" in signal

    def test_mixed_with_more_negative(self):
        from app import get_overall_signal
        scores = [{"compound": -0.6}, {"compound": -0.5}, {"compound": 0.1}]
        signal, _, _ = get_overall_signal(scores)
        assert "BEARISH" in signal

    def test_all_neutral(self):
        from app import get_overall_signal
        scores = [{"compound": 0.1}, {"compound": -0.1}, {"compound": 0.0}]
        signal, _, _ = get_overall_signal(scores)
        assert "NEUTRAL" in signal

    def test_high_avg_but_equal_pos_neg_counts(self):
        # avg >= 0.2 but pos_count == neg_count → should stay NEUTRAL due to count check
        from app import get_overall_signal
        scores = [{"compound": 0.8}, {"compound": -0.5}]
        signal, _, _ = get_overall_signal(scores)
        assert "NEUTRAL" in signal

    def test_edge_positive_boundary(self):
        from app import get_overall_signal
        scores = [{"compound": 0.3}, {"compound": 0.3}]  # avg=0.3, pos=2, neg=0
        signal, _, _ = get_overall_signal(scores)
        assert "BULLISH" in signal

    def test_edge_negative_boundary(self):
        from app import get_overall_signal
        scores = [{"compound": -0.3}, {"compound": -0.3}]  # avg=-0.3, neg=2, pos=0
        signal, _, _ = get_overall_signal(scores)
        assert "BEARISH" in signal


# ─── format_large_num() ────────────────────────────────────────

class TestFormatLargeNum:
    def test_crore(self):
        from app import format_large_num
        assert "Cr" in format_large_num(150_00_000)

    def test_lakh(self):
        from app import format_large_num
        assert "L" in format_large_num(5_00_000)
        assert "Cr" not in format_large_num(5_00_000)

    def test_thousands(self):
        from app import format_large_num
        result = format_large_num(5000)
        assert "₹" in result
        assert "L" not in result
        assert "Cr" not in result

    def test_small_number(self):
        from app import format_large_num
        result = format_large_num(500)
        assert result == "₹500"

    def test_non_numeric(self):
        from app import format_large_num
        assert format_large_num("N/A") == "N/A"
        assert format_large_num(None) == "N/A"


# ─── get_sentiment_emoji() ─────────────────────────────────────

class TestGetSentimentEmoji:
    def test_positive(self):
        from app import get_sentiment_emoji
        assert get_sentiment_emoji(0.3) == "🟢"
        assert get_sentiment_emoji(0.9) == "🟢"

    def test_negative(self):
        from app import get_sentiment_emoji
        assert get_sentiment_emoji(-0.3) == "🔴"
        assert get_sentiment_emoji(-0.9) == "🔴"

    def test_neutral(self):
        from app import get_sentiment_emoji
        assert get_sentiment_emoji(0.0) == "⚪"
        assert get_sentiment_emoji(0.2) == "⚪"
        assert get_sentiment_emoji(-0.2) == "⚪"


# ─── analyze_headline_sentiment() ──────────────────────────────

class TestAnalyzeHeadlineSentiment:
    def test_positive_headline(self, mock_sia):
        from app import analyze_headline_sentiment
        result = analyze_headline_sentiment("Stock surges on profit growth", "", mock_sia)
        assert result["compound"] > 0

    def test_negative_headline(self, mock_sia):
        from app import analyze_headline_sentiment
        result = analyze_headline_sentiment("Stock plunges after loss", "", mock_sia)
        assert result["compound"] < 0

    def test_headline_with_body(self, mock_sia):
        from app import analyze_headline_sentiment
        result = analyze_headline_sentiment("Market Update", "Bullish momentum continues", mock_sia)
        assert result["compound"] != 0

    def test_empty_headline(self, mock_sia):
        from app import analyze_headline_sentiment
        result = analyze_headline_sentiment("", "", mock_sia)
        assert isinstance(result, dict)
        assert "compound" in result


# ─── search_news() (with mocks) ────────────────────────────────

class TestSearchNews:
    @patch("app.DDGS")
    def test_deduplicates_by_url(self, mock_ddgs):
        from app import search_news
        mock_ddgs.return_value.__enter__.return_value.news.return_value = [
            {"title": "A", "body": "a", "date": "2026-01-01", "url": "http://same"},
            {"title": "B", "body": "b", "date": "2026-01-01", "url": "http://same"},
        ]
        results = search_news("RELIANCE", "Reliance")
        assert len(results) == 1

    @patch("app.DDGS")
    def test_handles_all_failures_gracefully(self, mock_ddgs, capsys):
        from app import search_news
        mock_ddgs.return_value.__enter__.return_value.news.side_effect = Exception("API down")
        results = search_news("RELIANCE", "Reliance")
        assert results == []

    @patch("app.DDGS")
    def test_returns_correct_max(self, mock_ddgs):
        from app import search_news
        items = [
            {"title": str(i), "body": "", "date": f"2026-01-{i:02d}", "url": f"http://x.com/{i}"}
            for i in range(1, 20)
        ]
        mock_ddgs.return_value.__enter__.return_value.news.return_value = items
        results = search_news("RELIANCE", "Reliance", max_results=5)
        assert len(results) == 5

    @patch("app.DDGS")
    def test_caches_results(self, mock_ddgs):
        from app import search_news
        mock_ddgs.return_value.__enter__.return_value.news.return_value = [
            {"title": "X", "body": "", "date": "2026-01-01", "url": "http://x.com"}
        ]
        # First call: fetches fresh
        r1 = search_news("TESTCACHE", "Test")
        assert len(r1) == 1
        # Second call: should use cache without calling DDGS again
        mock_ddgs.reset_mock()
        r2 = search_news("TESTCACHE", "Test")
        assert len(r2) == 1
        mock_ddgs.assert_not_called()


# ─── get_stock_info() (with mocks) ─────────────────────────────

class TestGetStockInfo:
    @patch("app.yf")
    def test_returns_structured_data(self, mock_yf):
        from app import get_stock_info
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "longName": "Test Corp", "sector": "Tech", "industry": "Software",
            "marketCap": 1_00_00_000, "trailingPE": 25.0,
            "currentPrice": 500, "regularMarketPrice": 500,
            "regularMarketChange": 10, "regularMarketChangePercent": 2.0,
            "dayHigh": 510, "dayLow": 490, "volume": 100000,
            "fiftyTwoWeekHigh": 600, "fiftyTwoWeekLow": 400,
        }
        # Empty history triggers info fallback path
        mock_hist = MagicMock()
        mock_hist.empty = True
        mock_ticker.history.return_value = mock_hist
        mock_yf.Ticker.return_value = mock_ticker
        result = get_stock_info("TEST")
        assert result is not None
        assert result["name"] == "Test Corp"
        assert result["current_price"] == 500
        assert result["pe_ratio"] == 25.0

    @patch("app.yf")
    def test_returns_none_on_failure(self, mock_yf):
        from app import get_stock_info
        mock_yf.Ticker.side_effect = Exception("Connection failed")
        result = get_stock_info("INVALID")
        assert result is None

    @patch("app.yf")
    def test_caches_results(self, mock_yf):
        from app import get_stock_info
        mock_ticker = MagicMock()
        mock_ticker.info = {"longName": "Test", "sector": "", "industry": "",
            "marketCap": 0, "trailingPE": 0, "currentPrice": 100, "regularMarketPrice": 100,
            "regularMarketChange": 0, "regularMarketChangePercent": 0,
            "dayHigh": 100, "dayLow": 100, "volume": 0,
            "fiftyTwoWeekHigh": 0, "fiftyTwoWeekLow": 0}
        mock_hist = MagicMock()
        mock_hist.empty = True
        mock_ticker.history.return_value = mock_hist
        mock_yf.Ticker.return_value = mock_ticker

        r1 = get_stock_info("CACHETEST")
        assert r1 is not None
        mock_yf.reset_mock()
        r2 = get_stock_info("CACHETEST")
        assert r2 is not None
        mock_yf.Ticker.assert_not_called()


# ─── analyze_ticker() (pipeline) ───────────────────────────────

class TestAnalyzeTicker:
    def test_returns_none_when_stock_fails(self):
        with patch("app.get_stock_info", return_value=None):
            from app import analyze_ticker
            assert analyze_ticker("INVALID", "Invalid") is None

    def test_returns_complete_analysis(self):
        mock_stock = MagicMock()
        with (
            patch("app.get_stock_info", return_value=mock_stock),
            patch("app.search_news", return_value=[]),
            patch("app.get_sia"),
        ):
            from app import analyze_ticker
            result = analyze_ticker("RELIANCE", "Reliance")
            assert result is not None
            assert result["stock_data"] == mock_stock
            assert result["news_items"] == []
            assert result["headline_scores"] == []
            assert "signal" in result
            assert "avg_compound" in result
            assert "signal_emoji" in result

    def test_pipeline_handles_partial_news(self):
        mock_stock = MagicMock()
        mock_sia = MagicMock()
        mock_sia.polarity_scores.return_value = {"compound": 0.0, "pos": 0, "neg": 0, "neu": 1}
        with (
            patch("app.get_stock_info", return_value=mock_stock),
            patch("app.search_news", return_value=[{"title": "Market flat", "body": ""}]),
            patch("app.get_sia", return_value=mock_sia),
        ):
            from app import analyze_ticker
            result = analyze_ticker("RELIANCE", "Reliance")
            assert result is not None
            assert len(result["news_items"]) == 1


# ─── Cache tests ───────────────────────────────────────────────

class TestCache:
    def test_miss_on_empty(self):
        assert cache_get("missing") is None

    def test_set_and_get(self):
        cache_set("k1", {"x": 1})
        assert cache_get("k1") == {"x": 1}

    def test_expired_entry(self):
        from app import CACHE_FILE, load_json, save_json
        cache = {"old": {"data": "stale", "cached_at": (datetime.now() - timedelta(hours=1)).isoformat()}}
        save_json(CACHE_FILE, cache)
        assert cache_get("old") is None

    def test_multiple_keys_independent(self):
        cache_set("a", "alpha")
        cache_set("b", "beta")
        assert cache_get("a") == "alpha"
        assert cache_get("b") == "beta"


# ─── User flow integration ─────────────────────────────────────

class TestUserFlows:
    """End-to-end flow tests with fully mocked dependencies."""

    def test_full_single_stock_scan(self):
        """Happy path: user selects ticker → gets price + sentiment + signal."""
        mock_stock = {"name": "Test", "current_price": 100, "change": 5, "change_pct": 5.0,
            "day_high": 105, "day_low": 95, "volume": 10000, "pe_ratio": 20,
            "sector": "Tech", "industry": "SW", "market_cap": 1e7,
            "52w_high": 150, "52w_low": 50}
        news = [
            {"title": "Stock surges on profit", "body": "positive news", "date": "2026-06-17", "url": "http://x.com/1"},
            {"title": "Analyst upgrade", "body": "bullish outlook", "date": "2026-06-16", "url": "http://x.com/2"},
        ]
        mock_sia = MagicMock()
        mock_sia.polarity_scores.side_effect = lambda t: {"compound": 0.6 if "surge" in t.lower() else 0.4, "pos": 0.5, "neg": 0, "neu": 0.5}
        with (
            patch("app.get_stock_info", return_value=mock_stock),
            patch("app.search_news", return_value=news),
            patch("app.get_sia", return_value=mock_sia),
        ):
            from app import analyze_ticker
            result = analyze_ticker("TCS", "Tata Consultancy")
            assert result is not None
            assert result["stock_data"]["name"] == "Test"
            assert len(result["news_items"]) == 2
            assert "BULLISH" in result["signal"]

    def test_no_news_falls_back_to_neutral(self):
        """User sees neutral signal when no news available."""
        mock_stock = {"name": "Test", "current_price": 100, "change": 0, "change_pct": 0.0,
            "day_high": 100, "day_low": 100, "volume": 0, "pe_ratio": 0,
            "sector": "", "industry": "", "market_cap": 0, "52w_high": 0, "52w_low": 0}
        with (
            patch("app.get_stock_info", return_value=mock_stock),
            patch("app.search_news", return_value=[]),
        ):
            from app import analyze_ticker
            result = analyze_ticker("UNKNOWN", "Unknown")
            assert result is not None
            assert result["news_items"] == []
            assert "NEUTRAL" in result["signal"]

    def test_invalid_ticker_graceful_failure(self):
        """User enters invalid ticker → gets error, not a crash."""
        with patch("app.get_stock_info", return_value=None):
            from app import analyze_ticker
            assert analyze_ticker("ZZZZZ", "NonExistent") is None

    def test_mixed_sentiment_noise(self):
        """Realistic: positive + negative articles → correct aggregate."""
        mock_stock = {"name": "X", "current_price": 100, "change": 0, "change_pct": 0.0,
            "day_high": 100, "day_low": 100, "volume": 0, "pe_ratio": 0,
            "sector": "", "industry": "", "market_cap": 0, "52w_high": 0, "52w_low": 0}
        news = [
            {"title": "Record profits", "body": "bullish earnings beat", "date": "", "url": "http://x.com/1"},
            {"title": "Stock downgrade", "body": "bearish analyst call", "date": "", "url": "http://x.com/2"},
            {"title": "Market update", "body": "trading rangebound", "date": "", "url": "http://x.com/3"},
        ]
        mock_sia = MagicMock()
        mock_sia.polarity_scores.side_effect = [
            {"compound": 0.7, "pos": 0.7, "neg": 0, "neu": 0.3},
            {"compound": -0.7, "pos": 0, "neg": 0.7, "neu": 0.3},
            {"compound": 0.0, "pos": 0, "neg": 0, "neu": 1.0},
        ]
        with (
            patch("app.get_stock_info", return_value=mock_stock),
            patch("app.search_news", return_value=news),
            patch("app.get_sia", return_value=mock_sia),
        ):
            from app import analyze_ticker
            result = analyze_ticker("ITC", "ITC Ltd")
            scores = result["headline_scores"]
            pos = sum(1 for s in scores if s["compound"] >= 0.3)
            neg = sum(1 for s in scores if s["compound"] <= -0.3)
            assert pos == 1
            assert neg == 1
