"""
Tests for NSE Sentiment Analyzer.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sentiment import (
    get_sia,
    analyze_headline_sentiment,
    FINANCIAL_BOOSTERS,
)
from data_fetcher import (
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




# ─── Weighted Signal Tests ───


from sentiment import get_weighted_signal


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
                  {"compound": 0.3, "source": "DuckDuckGo"}]
        signal, compound, emoji, breakdown = get_weighted_signal(scores)
        weights = [s["weight"] for s in breakdown]
        assert weights == sorted(weights, reverse=True), "Breakdown not sorted by weight"

    def test_source_weights_defined(self):
        from persistence import SOURCE_WEIGHTS_PRIOR
        for src in ["Economic Times", "Moneycontrol", "LiveMint", "DuckDuckGo"]:
            assert src in SOURCE_WEIGHTS_PRIOR, f"Missing weight for {src}"


# ─── Data / Formatting Tests ───


class TestDataFetcher:
    def test_nse_tickers_populated(self):
        assert len(NSE_TICKERS) > 80
        assert "RELIANCE" in NSE_TICKERS
        assert "HDFCBANK" in NSE_TICKERS
        assert "TCS" in NSE_TICKERS
