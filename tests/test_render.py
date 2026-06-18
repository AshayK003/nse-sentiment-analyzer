"""
Tests for the HTML dashboard renderer (render.py).
Verifies render_dashboard handles full data, partial data, and edge cases
without crashing.
"""

import pytest


def _make_result(stock_data, news_items, headline_scores, signal="NEUTRAL",
                 avg_compound=0.0, signal_emoji="\u26aa",
                 weighted_signal="NEUTRAL", blended_compound=0.0,
                 weighted_emoji="\u26aa", source_breakdown=None,
                 num_articles=0, source_stats=None):
    """Build a result dict matching analyze_ticker's return shape."""
    return {
        "stock_data": stock_data,
        "news_items": news_items,
        "headline_scores": headline_scores,
        "signal": signal,
        "avg_compound": avg_compound,
        "signal_emoji": signal_emoji,
        "weighted_signal": weighted_signal,
        "blended_compound": blended_compound,
        "weighted_emoji": weighted_emoji,
        "source_breakdown": source_breakdown or [],
        "num_articles": num_articles,
        "source_stats": source_stats or {},
    }


class TestRenderDashboard:
    """Tests for render_dashboard()."""

    def test_renders_with_full_data(self, sample_stock_data, sample_news_items,
                                    sample_headline_scores, sample_technical_indicators,
                                    sample_fii_dii_data):
        """Full data should produce HTML with all sections."""
        from render import render_dashboard

        result = _make_result(
            sample_stock_data, sample_news_items, sample_headline_scores,
            signal="BULLISH \U0001f7e2", avg_compound=0.45,
            signal_emoji="\U0001f7e2", weighted_signal="BULLISH \U0001f7e2",
            blended_compound=0.38, weighted_emoji="\U0001f7e2",
            source_breakdown=[
                {"source": "Economic Times", "count": 2, "weight": 1.0, "avg": 0.8},
                {"source": "Moneycontrol", "count": 1, "weight": 1.0, "avg": -0.6},
            ],
            num_articles=3,
            source_stats={"Economic Times": 1, "Moneycontrol": 1, "LiveMint": 1},
        )

        html = render_dashboard(
            result, "TEST", "Test Company Ltd",
            technical_indicators=sample_technical_indicators,
            track_record=[{"ticker": "TEST", "signal": "BULLISH", "vote": True}],
            fii_dii_data=sample_fii_dii_data,
        )

        assert html is not None
        assert len(html) > 500
        # Key sections should be present
        assert "Test Company Ltd" in html
        assert "BULLISH" in html
        assert "RSI" in html or "BUY" in html  # RSI or signal
        assert "Economic Times" in html

    def test_renders_with_minimal_data(self, sample_stock_data):
        """Only stock_data, no news/technicals — should render without crash."""
        from render import render_dashboard

        result = _make_result(
            sample_stock_data, [], [],
            signal="NEUTRAL \u26aa", num_articles=0,
        )

        html = render_dashboard(
            result, "TEST", "Test Company Ltd",
            technical_indicators=None,
            track_record=None,
            fii_dii_data=None,
        )

        assert html is not None
        assert len(html) > 200
        assert "Test Company Ltd" in html

    def test_handles_missing_technicals(self, sample_stock_data, sample_news_items,
                                        sample_headline_scores):
        """technical_indicators=None should not crash the dashboard."""
        from render import render_dashboard

        result = _make_result(
            sample_stock_data, sample_news_items[:1], sample_headline_scores[:1],
            signal="BULLISH \U0001f7e2", avg_compound=0.8,
            signal_emoji="\U0001f7e2", num_articles=1,
        )

        html = render_dashboard(
            result, "TEST", "Test Company Ltd",
            technical_indicators=None,
        )

        assert html is not None
        assert "Test Company Ltd" in html
        # RSI should NOT appear when technicals are missing
        assert "RSI" not in html

    def test_handles_partial_technicals_regression(self, sample_stock_data,
                                                   partial_technical_indicators):
        """Regression: sma50/sma200=None should not crash (the '> None' TypeError)."""
        from render import render_dashboard

        result = _make_result(
            sample_stock_data, [], [],
            signal="NEUTRAL \u26aa", num_articles=0,
        )

        html = render_dashboard(
            result, "TEST", "Test Company Ltd",
            technical_indicators=partial_technical_indicators,
        )

        assert html is not None
        # Em dash for missing SMA data — verify no crash
        assert len(html) > 200

    def test_handles_missing_fii(self, sample_stock_data, sample_news_items,
                                 sample_headline_scores):
        """fii_dii_data=None should not crash."""
        from render import render_dashboard

        result = _make_result(
            sample_stock_data, sample_news_items[:1], sample_headline_scores[:1],
            signal="NEUTRAL \u26aa", num_articles=1,
        )

        html = render_dashboard(
            result, "TEST", "Test Company Ltd",
            technical_indicators=None,
            fii_dii_data=None,
        )

        assert html is not None
        assert len(html) > 200

    def test_handles_empty_news(self, sample_stock_data):
        """Empty news list should render with no items."""
        from render import render_dashboard

        result = _make_result(
            sample_stock_data, [], [],
            signal="NEUTRAL \u26aa", num_articles=0,
        )

        html = render_dashboard(
            result, "TEST", "Test Company Ltd",
        )

        assert html is not None
        assert "No articles found" in html or "news" in html.lower()

    def test_handles_missing_stock_fields(self):
        """Stock data with missing fields (sector=None, pe=None) should not crash."""
        from render import render_dashboard

        stock_data = {
            "name": "Test Ltd",
            "sector": None,
            "industry": None,
            "market_cap": None,
            "pe_ratio": None,
            "current_price": 100.0,
            "change": None,
            "change_pct": None,
            "day_high": None,
            "day_low": None,
            "volume": None,
            "52w_high": None,
            "52w_low": None,
        }
        result = _make_result(stock_data, [], [], num_articles=0)

        html = render_dashboard(result, "TEST", "Test Ltd")
        assert html is not None
        assert "Test Ltd" in html

    def test_bearish_signal(self, sample_stock_data):
        """Bearish signal should produce caution text."""
        from render import render_dashboard

        result = _make_result(
            sample_stock_data, [], [],
            signal="BEARISH \U0001f534", avg_compound=-0.6,
            signal_emoji="\U0001f534",
            weighted_signal="BEARISH \U0001f534", blended_compound=-0.5,
            weighted_emoji="\U0001f534",
        )

        html = render_dashboard(result, "TEST", "Test Ltd")
        assert html is not None
        assert "CAUTION" in html or "SELL" in html or "BEARISH" in html
