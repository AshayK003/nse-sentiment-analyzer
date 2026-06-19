"""
Tests for SmartScore aggregation — EWMA, breadth, volume, composite.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aggregate_sentiment import compute_smartscore, _ewma_weight


class TestEWMAWeights:
    """Exponential weighted moving average decay."""

    def test_today_weight_is_1(self):
        assert _ewma_weight(0) == 1.0

    def test_decay_over_time(self):
        w0 = _ewma_weight(0)     # today
        w1 = _ewma_weight(1)     # yesterday
        w2 = _ewma_weight(2)     # 2 days ago
        assert w0 > w1 > w2 > 0

    def test_half_life_approx(self):
        """~36h half-life: ~1.5 days should weigh ~0.5."""
        w = _ewma_weight(1.5)
        assert 0.45 < w < 0.55  # Approximately 0.5

    def test_distant_past_near_zero(self):
        """30 days ago should weigh almost nothing."""
        w = _ewma_weight(30)
        assert w < 0.001


class TestSmartScore:
    """SmartScore computation from headline scores."""

    def test_empty_headlines_neutral(self):
        result, history = compute_smartscore([], [], None)
        assert result["smartscore"] == 50.0
        assert result["signal"] == "NEUTRAL"

    def test_all_positive_headlines(self):
        scores = [
            {"compound": 0.8, "source": "ET"},
            {"compound": 0.7, "source": "ET"},
            {"compound": 0.6, "source": "MC"},
            {"compound": 0.5, "source": "MC"},
        ]
        adjusted = [0.82, 0.72, 0.62, 0.52]
        result, history = compute_smartscore(scores, adjusted)
        assert result["smartscore"] >= 65
        assert result["signal"] == "BULLISH"
        assert result["pos_count"] >= 3
        assert result["neg_count"] == 0
        assert result["headline_count"] == 4

    def test_all_negative_headlines(self):
        scores = [
            {"compound": -0.8, "source": "ET"},
            {"compound": -0.7, "source": "MC"},
            {"compound": -0.9, "source": "LM"},
        ]
        adjusted = [-0.75, -0.65, -0.85]
        result, history = compute_smartscore(scores, adjusted)
        assert result["smartscore"] < 40
        assert result["signal"] == "BEARISH"
        assert result["neg_count"] == 3

    def test_mixed_headlines_neutral(self):
        scores = [
            {"compound": 0.5, "source": "ET"},
            {"compound": -0.4, "source": "MC"},
            {"compound": 0.1, "source": "LM"},
            {"compound": -0.2, "source": "DDG"},
        ]
        adjusted = [0.5, -0.4, 0.1, -0.2]
        result, history = compute_smartscore(scores, adjusted)
        # Neutral to mildly positive — all headlines are 0.1/mixed
        assert 35 <= result["smartscore"] <= 65
        assert result["signal"] == "NEUTRAL"

    def test_volume_component_scales_with_count(self):
        """More headlines should increase S_volume."""
        scores_3 = [{"compound": 0.1}] * 3
        result_3, _ = compute_smartscore(scores_3, [0.1] * 3)
        scores_15 = [{"compound": 0.1}] * 15
        result_15, _ = compute_smartscore(scores_15, [0.1] * 15)
        assert result_15["smartscore"] > result_3["smartscore"]

    def test_single_headline(self):
        scores = [{"compound": 0.4}]
        adjusted = [0.45]
        result, history = compute_smartscore(scores, adjusted)
        assert result["headline_count"] == 1
        assert 0 < result["smartscore"] < 100
        assert result["s_volume"] < 1.0  # Log-scaled, 1 headline is low volume

    def test_max_volume_saturates(self):
        """20+ headlines should give S_volume ≈ 1.0."""
        scores = [{"compound": 0.1}] * 30
        result, _ = compute_smartscore(scores, [0.1] * 30)
        assert result["s_volume"] == 1.0

    def test_history_affects_recency(self):
        """Providing history should change S_recency."""
        scores = [{"compound": 0.5}] * 5
        adjusted = [0.5] * 5

        # No history
        result_no_hist, _ = compute_smartscore(scores, adjusted)

        # With history of strong negative scores
        history = [
            {"date": "2026-06-10", "avg_compound": "-0.8"},
            {"date": "2026-06-11", "avg_compound": "-0.7"},
            {"date": "2026-06-12", "avg_compound": "-0.6"},
            {"date": "2026-06-15", "avg_compound": "-0.5"},
            {"date": "2026-06-16", "avg_compound": "-0.4"},
            {"date": "2026-06-17", "avg_compound": "-0.2"},
            {"date": "2026-06-18", "avg_compound": "-0.1"},
        ]
        result_with_hist, _ = compute_smartscore(scores, adjusted, history)

        # S_recency should be lower with negative history
        assert result_with_hist["s_recency"] < result_no_hist["s_recency"]

    def test_history_sparkline_values(self):
        """Sparkline should include history + current."""
        scores = [{"compound": 0.5}]
        adjusted = [0.5]
        history = [
            {"date": "2026-06-16", "avg_compound": "0.1", "smartscore": "55"},
            {"date": "2026-06-17", "avg_compound": "0.2", "smartscore": "60"},
            {"date": "2026-06-18", "avg_compound": "0.3", "smartscore": "62"},
        ]
        result, history_scores = compute_smartscore(scores, adjusted, history)
        # Should have 3 historical + 1 current
        assert len(history_scores) == 4
        # Last value should be current smartscore
        assert history_scores[-1] == result["smartscore"]

    def test_breadth_all_pos(self):
        """All positive headlines → high S_breadth."""
        scores = [{"compound": 0.8}, {"compound": 0.7}, {"compound": 0.9}]
        result, _ = compute_smartscore(scores, [0.8, 0.7, 0.9])
        assert result["s_breadth"] > 0.8
        assert result["pos_count"] == 3
        assert result["neg_count"] == 0

    def test_breadth_all_neg(self):
        """All negative headlines → low S_breadth."""
        scores = [{"compound": -0.8}, {"compound": -0.7}, {"compound": -0.9}]
        result, _ = compute_smartscore(scores, [-0.8, -0.7, -0.9])
        assert result["s_breadth"] < 0.2
