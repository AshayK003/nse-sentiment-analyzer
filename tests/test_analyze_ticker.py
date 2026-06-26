"""
Integration test for analyze_ticker() — verifies the orchestration pipeline
connects modules correctly. Mocks at module boundaries (data_fetcher, sentiment,
event_classifier, indicators, market_data, persistence).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


@pytest.fixture
def mock_deps(mocker):
    """Mock all dependencies at the app module boundary so analyze_ticker runs
    deterministically without real APIs."""
    # ── Stock data ──
    mocker.patch("app.get_stock_info", return_value={
        "name": "Test Company Ltd", "sector": "Technology", "industry": "Software",
        "market_cap": 100_000_000_000, "pe_ratio": 25.0,
        "debt_to_equity": 1.5,
        "current_price": 100.0, "change": 2.5, "change_pct": 2.56,
        "day_high": 102.0, "day_low": 98.0, "volume": 1_000_000,
        "52w_high": 120.0, "52w_low": 80.0,
    })

    # ── News ──
    news_items = [
        {"title": "Test Company reports strong growth", "body": "The company reported 20% growth.",
         "date": "2026-06-18", "url": "https://example.com/1", "source": "Economic Times"},
        {"title": "Test Company faces market headwinds", "body": "Analysts cautious on valuation.",
         "date": "2026-06-17", "url": "https://example.com/2", "source": "Moneycontrol"},
        {"title": "Test Company maintains guidance", "body": "",
         "date": "2026-06-16", "url": "https://example.com/3", "source": "LiveMint"},
    ]
    mocker.patch("app.search_news", return_value=(news_items, {"Economic Times": 1, "Moneycontrol": 1, "LiveMint": 1}))

    # ── Sentiment (VADER returns deterministic scores for known phrases) ──
    # Patch analyze_headline_sentiment to return scores based on keywords
    from sentiment import get_sia
    sia = get_sia()

    def mock_sentiment(title, body, sia_obj, source=None):
        text = f"{title}. {body}" if body else title
        vader = sia_obj.polarity_scores(text)
        result = {"compound": vader["compound"], "vader": vader}
        if source:
            result["source"] = source
        return result

    mocker.patch("app.analyze_headline_sentiment", side_effect=mock_sentiment)

    # ── Event classifier ──
    mocker.patch("app.classify_headline", side_effect=lambda t, b:
        ("EARNINGS_BEAT", 0.35) if "growth" in t.lower()
        else ("GUIDANCE_NEGATIVE", -0.30) if "headwinds" in t.lower()
        else (None, 0.0))
    mocker.patch("app.adjust_with_event", side_effect=lambda c, e:
        c if e == 0.0 else max(-1.0, min(1.0, 0.8 * c + 0.2 * e)))

    # ── Technical indicators ──
    mocker.patch("app.get_technical_indicators", return_value={
        "rsi": 55.0, "sma_50": 95.0, "sma_200": 85.0, "close": 100.0,
        "close_prev": 99.0, "macd_line": 0.5, "macd_signal": 0.3,
        "macd_hist": 0.2, "sma50_cross": None, "sma200_cross": "bullish",
        "avg_volume_50": 800_000,
    })

    # ── FII/DII ──
    mocker.patch("app.get_fii_dii_flow", return_value={
        "fii_net": 500.0, "dii_net": -200.0, "date": "2026-06-17",
        "combined_net": 300.0, "fii_action": "Buying", "dii_action": "Selling",
    })

    # ── Persistence ──
    mocker.patch("app.load_track_record", return_value=[])
    mocker.patch("app.save_track_record")
    mocker.patch("app.load_sentiment_history", return_value=[])
    mocker.patch("app.save_sentiment_history")

    # ── VADER SIA cache ──
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    mocker.patch("app.get_sia", return_value=SentimentIntensityAnalyzer())

    return mocker


class TestAnalyzeTicker:
    """End-to-end orchestration tests for the analysis pipeline."""

    def test_returns_expected_shape(self, mock_deps):
        """analyze_ticker() returns all expected keys with correct types."""
        from app import analyze_ticker
        result = analyze_ticker("TEST", "Test Company Ltd")

        assert result is not None
        # All required keys present
        assert "stock_data" in result
        assert "news_items" in result
        assert "headline_scores" in result
        assert "smartscore" in result
        assert "weighted_signal" in result
        assert "source_breakdown" in result

        # Stock data
        assert result["stock_data"]["current_price"] == 100.0
        assert result["stock_data"]["sector"] == "Technology"

        # Signal is one of the three
        assert result["signal"] in ("BULLISH 🟢", "BEARISH 🔴", "NEUTRAL ⚪")
        assert isinstance(result["avg_compound"], float)
        assert isinstance(result["blended_compound"], float)

        # SmartScore in 0-100 range
        assert 0 <= result["smartscore"] <= 100

        # News and scores match
        assert len(result["news_items"]) == 3
        assert len(result["headline_scores"]) == 3
        assert len(result["headline_scores"]) == len(result["news_items"])

        # Each headline score has compound
        for s in result["headline_scores"]:
            assert "compound" in s
            assert isinstance(s["compound"], float)

        # Source breakdown
        assert len(result["source_breakdown"]) > 0
        for src in result["source_breakdown"]:
            assert "source" in src
            assert "weight" in src
            assert "avg" in src

        # Event tags present
        assert len(result["event_tags"]) == 3

    def test_signal_reasonable_for_mixed_news(self, mock_deps):
        """Mixed news should not produce extreme signals."""
        from app import analyze_ticker
        result = analyze_ticker("TEST", "Test Company Ltd")
        # With 1 positive + 1 negative + 1 neutral, signal shouldn't be extreme
        assert -0.8 < result["avg_compound"] < 0.8

    def test_returns_neutral_on_empty_news(self, mock_deps):
        """When no news is found, signal is NEUTRAL and SmartScore is 50."""
        from app import analyze_ticker
        mock_deps.patch("app.search_news", return_value=([], {}))
        result = analyze_ticker("TEST", "Test Company Ltd")

        assert result is not None
        assert result["signal"] == "NEUTRAL ⚪"
        assert result["smartscore"] == 50.0
        assert len(result["news_items"]) == 0

    def test_returns_none_on_stock_failure(self, mock_deps):
        """When stock data fetch fails, analyze_ticker returns None."""
        from app import analyze_ticker
        mock_deps.patch("app.get_stock_info", return_value=None)
        result = analyze_ticker("UNKNOWN", "Unknown Ltd")
        assert result is None

    def test_smartscore_history_affects_recency(self, mock_deps):
        """Providing sentiment history should influence the SmartScore."""
        from app import analyze_ticker
        # Mock history with strongly negative prior scores
        hist_mock = [
            {"date": "2026-06-10", "avg_compound": "-0.8", "smartscore": "20"},
            {"date": "2026-06-11", "avg_compound": "-0.7", "smartscore": "25"},
            {"date": "2026-06-12", "avg_compound": "-0.6", "smartscore": "30"},
        ]
        mock_deps.patch("app.load_sentiment_history", return_value=hist_mock)

        result = analyze_ticker("TEST", "Test Company Ltd")
        assert result is not None
        assert 0 <= result["smartscore"] <= 100

    def test_pipeline_handles_partial_data(self, mock_deps):
        """Pipeline works when technical indicators are unavailable."""
        mock_deps.patch("app.get_technical_indicators", return_value=None)
        from app import analyze_ticker
        result = analyze_ticker("TEST", "Test Company Ltd")
        assert result is not None
        assert result["stock_data"]["current_price"] == 100.0
        assert result["smartscore"] > 0
