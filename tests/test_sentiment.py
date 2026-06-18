"""
Tests for NSE Sentiment Analyzer.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sentiment import (
    get_sia,
    analyze_headline_sentiment,
    get_overall_signal,
    get_sentiment_emoji,
    FINANCIAL_BOOSTERS,
)
from data_fetcher import (
    _is_numeric,
    format_large_num,
    NSE_TICKERS,
)


# ─── Sentiment Tests ───


class TestSentiment:
    @classmethod
    def setup_class(cls):
        cls.sia = get_sia()

    def test_sia_initializes(self):
        assert self.sia is not None

    def test_lexicon_boosters_loaded(self):
        for word, score in FINANCIAL_BOOSTERS.items():
            assert word in self.sia.lexicon, f"Missing booster: {word}"
            assert self.sia.lexicon[word] == score, f"Wrong score for {word}"

    def test_bullish_headline(self):
        result = analyze_headline_sentiment("Stock surges on bullish outlook", "", self.sia)
        assert result["compound"] > 0

    def test_bearish_headline(self):
        result = analyze_headline_sentiment("Stock crashes on negative results", "", self.sia)
        assert result["compound"] < -0.2  # VADER normalization bounds this

    def test_neutral_headline(self):
        result = analyze_headline_sentiment("Company to hold board meeting next week", "", self.sia)
        # Neutral text should have compound near 0
        assert -0.3 < result["compound"] < 0.3

    def test_get_sentiment_emoji(self):
        assert get_sentiment_emoji(0.5) == "🟢"
        assert get_sentiment_emoji(-0.5) == "🔴"
        assert get_sentiment_emoji(0) == "⚪"
        assert get_sentiment_emoji(0.2) == "⚪"

    def test_get_overall_signal_bullish(self):
        scores = [{"compound": 0.8}, {"compound": 0.5}, {"compound": 0.1}]
        signal, compound, emoji = get_overall_signal(scores)
        assert "BULLISH" in signal
        assert "🟢" in signal

    def test_get_overall_signal_bearish(self):
        scores = [{"compound": -0.8}, {"compound": -0.5}, {"compound": -0.1}]
        signal, compound, emoji = get_overall_signal(scores)
        assert "BEARISH" in signal
        assert "🔴" in signal

    def test_get_overall_signal_neutral(self):
        scores = [{"compound": 0.1}, {"compound": -0.1}, {"compound": 0.05}]
        signal, compound, emoji = get_overall_signal(scores)
        assert "NEUTRAL" in signal

    def test_get_overall_signal_empty(self):
        signal, compound, emoji = get_overall_signal([])
        assert signal == "NEUTRAL ⚪"

    def test_get_overall_signal_mixed(self):
        scores = [{"compound": 0.8}, {"compound": -0.8}, {"compound": 0.05}]
        signal, compound, emoji = get_overall_signal(scores)
        # Mixed with strong both sides → neutral
        assert "NEUTRAL" in signal or "BULLISH" in signal  # depends on weights


# ─── Weighted Signal Tests ───


from sentiment import get_weighted_signal, SOURCE_WEIGHTS, LOCAL_ONLY_SOURCES


class TestWeightedSignal:
    def test_empty_scores(self):
        signal, compound, emoji, breakdown = get_weighted_signal([])
        assert signal == "NEUTRAL ⚪"
        assert compound == 0.0

    def test_single_source(self):
        scores = [{"compound": 0.8, "source": "Economic Times"},
                  {"compound": 0.6, "source": "Economic Times"}]
        signal, compound, emoji, breakdown = get_weighted_signal(scores)
        assert compound > 0.5
        assert len(breakdown) == 1
        assert breakdown[0]["source"] == "Economic Times"

    def test_weighted_blend(self):
        """High-weight optimistic source should dominate low-weight pessimistic one."""
        scores = [{"compound": 0.8, "source": "Economic Times"},   # weight 1.0
                  {"compound": -0.8, "source": "DuckDuckGo"}]      # weight 0.5
        signal, compound, emoji, breakdown = get_weighted_signal(scores)
        # Weighted: (1.0 * 0.8 + 0.5 * -0.8) / 1.5 = 0.267 → positive
        assert compound > 0
        assert "BULLISH" in signal or "NEUTRAL" in signal

    def test_weighted_blend_negative(self):
        """Low-weight positive source should not overpower high-weight negative one."""
        scores = [{"compound": -0.7, "source": "Economic Times"},  # weight 1.0
                  {"compound": 0.9, "source": "DuckDuckGo"}]       # weight 0.5
        signal, compound, emoji, breakdown = get_weighted_signal(scores)
        # Weighted: (1.0 * -0.7 + 0.5 * 0.9) / 1.5 = -0.167 → slightly negative/neutral
        assert compound < 0

    def test_missing_source_defaults(self):
        scores = [{"compound": 0.5, "source": "Unknown Source"},
                  {"compound": -0.5, "source": "Unknown Source"}]
        signal, compound, emoji, breakdown = get_weighted_signal(scores)
        assert len(breakdown) == 1
        # Unknown sources get weight 0.5
        assert breakdown[0]["weight"] == 0.5

    def test_source_breakdown_order(self):
        """Breakdown should be sorted by weight descending."""
        scores = [{"compound": 0.1, "source": "DuckDuckGo"},
                  {"compound": 0.2, "source": "Economic Times"},
                  {"compound": 0.3, "source": "Reddit"}]
        signal, compound, emoji, breakdown = get_weighted_signal(scores)
        weights = [s["weight"] for s in breakdown]
        assert weights == sorted(weights, reverse=True), "Breakdown not sorted by weight"

    def test_local_only_sources_defined(self):
        # Reddit is local-only unless OAuth env vars are set
        import os
        reddit_local = not (os.environ.get("REDDIT_CLIENT_ID") and os.environ.get("REDDIT_CLIENT_SECRET"))
        assert ("Reddit" in LOCAL_ONLY_SOURCES) == reddit_local
        assert isinstance(LOCAL_ONLY_SOURCES, set)

    def test_source_weights_defined(self):
        for src in ["Economic Times", "Moneycontrol", "LiveMint", "DuckDuckGo", "Reddit"]:
            assert src in SOURCE_WEIGHTS, f"Missing weight for {src}"


# ─── Data / Formatting Tests ───


class TestDataFetcher:
    def test_nse_tickers_populated(self):
        assert len(NSE_TICKERS) > 80
        assert "RELIANCE" in NSE_TICKERS
        assert "HDFCBANK" in NSE_TICKERS
        assert "TCS" in NSE_TICKERS

    def test_is_numeric(self):
        assert _is_numeric(42)
        assert _is_numeric(3.14)
        assert not _is_numeric("N/A")
        assert not _is_numeric(None)
        assert not _is_numeric(True)

    def test_format_large_num(self):
        assert "Cr" in format_large_num(100_00_000)
        assert "L" in format_large_num(1_00_000)
        assert "₹" in format_large_num(1000)
        assert "N/A" in format_large_num(None)
        assert "N/A" in format_large_num("N/A")
