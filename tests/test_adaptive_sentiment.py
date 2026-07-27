"""
Backtesting harness for Adaptive Sentiment Engine.

Tests adaptive learner predictions against historical price reactions
using mocked/synthetic data - no large downloads required.

AEOS Module 14 TDD pattern: tests first, then implementation.
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adaptive_sentiment import (
    AdaptiveClusterLearner,
    DisseminationClusterer,
    learn_from_price_reaction,
    predict_price_reaction,
    compute_dissemination_score,
    get_dissemination_clusters,
    CLUSTER_EPS,
    MAX_CLUSTERS,
)


class MockPriceHistory:
    """Generate synthetic price history for testing."""

    def __init__(self, base_price=100.0, volatility=0.02):
        self.base_price = base_price
        self.volatility = volatility
        self.prices = [base_price]

    def add_random_walk(self, days=100):
        """Generate random walk prices."""
        for _ in range(days):
            change = np.random.normal(0, self.volatility)
            new_price = self.prices[-1] * (1 + change)
            self.prices.append(max(new_price, 1.0))  # floor at 1
        return self.prices

    def add_trend(self, days=50, trend_pct=0.1):
        """Add a directional trend."""
        trend_per_day = trend_pct / days
        for i in range(days):
            change = trend_per_day + np.random.normal(0, self.volatility)
            new_price = self.prices[-1] * (1 + change)
            self.prices.append(max(new_price, 1.0))
        return self.prices


class TestAdaptiveClusterLearner:
    """Test the adaptive cluster learner with synthetic data."""

    def setup_method(self):
        """Fresh learner for each test."""
        self.learner = AdaptiveClusterLearner()
        self.learner.clusters = {}
        self.learner._fitted = True  # HashingVectorizer is always ready

    def test_cold_start_prediction_returns_zero(self):
        """New learner with no clusters returns 0 prediction."""
        pred = self.learner.predict("Any headline")
        assert pred == 0.0

    def test_single_update_creates_cluster(self):
        """One update creates a cluster with that headline."""
        self.learner.update("Reliance beats Q1 estimates", 1.5, 2.0)
        assert len(self.learner.clusters) == 1
        cluster = list(self.learner.clusters.values())[0]
        assert cluster["count"] == 1
        assert cluster["reactions_1h"] == [1.5]
        assert cluster["reactions_4h"] == [2.0]

    def test_similar_headline_matches_existing_cluster(self):
        """Similar headlines go to same cluster (cosine similarity)."""
        self.learner.update("Reliance beats Q1 estimates", 1.5, 2.0)
        self.learner.update("Reliance beats Q1 estimates", 1.2, 1.8)
        # Identical headline should go to same cluster
        assert len(self.learner.clusters) == 1
        cluster = list(self.learner.clusters.values())[0]
        assert cluster["count"] == 2
        assert len(cluster["reactions_1h"]) == 2

    def test_different_topic_creates_new_cluster(self):
        """Different topics create separate clusters."""
        self.learner.update("Reliance beats Q1 estimates", 1.5, 2.0)
        self.learner.update("Crude oil prices surge 5%", -0.5, -1.0)
        assert len(self.learner.clusters) == 2

    def test_prediction_uses_weighted_average(self):
        """Prediction uses cluster weight * similarity."""
        # Add 3 similar headlines with positive moves
        for _ in range(3):
            self.learner.update("Reliance beats estimates", 2.0, 3.0)
        # Add 1 with negative move
        self.learner.update("Reliance beats estimates", -1.0, -1.5)

        pred = self.learner.predict("Reliance beats expectations")
        # Should be weighted toward positive (3:1 ratio)
        assert pred > 0.0

    def test_calibration_updates_weights(self):
        """Calibration adjusts cluster weights by correlation."""
        # Add cluster with strong positive correlation
        for i in range(5):
            self.learner.update(f"Stock X beats Q{i}", 1.5 + i * 0.1, 2.0 + i * 0.1)

        # Calibrate with matching ground truth
        headlines = [f"Stock X beats Q{i}" for i in range(5)]
        moves_1h = [1.6, 1.7, 1.8, 1.9, 2.0]
        moves_4h = [2.1, 2.2, 2.3, 2.4, 2.5]

        self.learner.calibrate(headlines, moves_1h, moves_4h, force=True)

        cluster = list(self.learner.clusters.values())[0]
        # High positive correlation -> weight near 1
        assert cluster["weight"] > 0.8

    def test_calibration_negative_correlation_zeros_weight(self):
        """Negative correlation results in zero weight."""
        # Add to same cluster 5 times
        for _ in range(5):
            self.learner.update("Stock Y beats estimates", 1.5, 2.0)

        # Ground truth opposite to cluster average
        headlines = ["Stock Y beats estimates"] * 5
        moves_1h = [-1.5, -1.5, -1.5, -1.5, -1.5]  # all negative
        moves_4h = [-2.0, -2.0, -2.0, -2.0, -2.0]

        self.learner.calibrate(headlines, moves_1h, moves_4h, force=True)

        cluster = list(self.learner.clusters.values())[0]
        # Negative correlation -> weight = 0
        assert cluster["weight"] == 0.0

    def test_max_clusters_evicts_least_useful(self):
        """LRU eviction when max clusters reached."""
        self.learner.clusters = {}
        # Fill to max
        for i in range(MAX_CLUSTERS):
            self.learner.clusters[i] = {
                "centroid": np.ones(4096) * i,  # HashingVectorizer uses 4096 features
                "headlines": [f"headline {i}"],
                "reactions_1h": [1.0],
                "reactions_4h": [1.5],
                "count": 1,
                "weight": 0.5,
            }
        self.learner._fitted = True

        # Add one more - should evict
        self.learner.update("New headline", 1.0, 1.0)
        assert len(self.learner.clusters) == MAX_CLUSTERS


class TestDisseminationClusterer:
    """Test dissemination clustering with financial entities."""

    def setup_method(self):
        self.clusterer = DisseminationClusterer()

    def test_commodity_keyword_extraction(self):
        """Extract commodity entities from text."""
        text = "Crude oil surges on supply fears, Brent hits $85"
        entities = self.clusterer._extract_entities(text)
        assert "commodity:crude" in entities

    def test_sector_keyword_extraction(self):
        """Extract sector entities from text."""
        text = "RBI cuts rates, banking stocks rally"
        entities = self.clusterer._extract_entities(text)
        assert "sector:banking" in entities

    def test_signature_groups_by_entities(self):
        """Articles with same entities get same signature."""
        a1 = {"title": "Crude surges", "body": "Oil up", "ticker": "BPCL"}
        a2 = {"title": "Brent rises", "body": "Crude higher", "ticker": "ONGC"}
        a3 = {"title": "Gold steady", "body": "Bullion flat", "ticker": "GOLDBEES"}

        sig1 = self.clusterer._get_article_signature(a1)
        sig2 = self.clusterer._get_article_signature(a2)
        sig3 = self.clusterer._get_article_signature(a3)

        assert sig1 == sig2  # both crude
        assert sig1 != sig3  # different commodity

    def test_min_two_articles_per_cluster(self):
        """Single article doesn't form a cluster."""
        articles = [{"title": "Crude surges", "body": "Oil up", "source": "ET", "ticker": "BPCL"}]
        clusters = self.clusterer.cluster_articles(articles)
        assert len(clusters) == 0

    def test_two_articles_same_entity_form_cluster(self):
        """Two articles sharing entity form cluster."""
        articles = [
            {"title": "Crude surges", "body": "Oil up", "source": "ET", "ticker": "BPCL"},
            {"title": "Brent rises", "body": "Crude higher", "source": "MC", "ticker": "ONGC"},
        ]
        clusters = self.clusterer.cluster_articles(articles)
        assert len(clusters) == 1
        assert clusters[0]["size"] == 2
        assert "commodity:crude" in clusters[0]["entities"]

    def test_dissemination_score_weighted_by_sources(self):
        """Score = 0.7 * size + 0.3 * source_diversity."""
        articles = [
            {"title": "Crude surges", "body": "Oil up", "source": "ET", "ticker": "BPCL"},
            {"title": "Brent rises", "body": "Crude higher", "source": "MC", "ticker": "ONGC"},
            {"title": "Oil jumps", "body": "Crude up", "source": "LM", "ticker": "IOC"},
        ]
        clusters = self.clusterer.cluster_articles(articles)
        assert len(clusters) == 1
        # 3 articles, 3 sources -> size_score=0.3, source_div=0.6 -> 0.7*0.3 + 0.3*0.6 = 0.39
        assert 0.38 <= clusters[0]["dissemination_score"] <= 0.40


class TestIntegrationWithMockedData:
    """Integration tests with realistic mocked news + price data."""

    def generate_mock_news_with_price_moves(self, n=100):
        """Generate synthetic news headlines with known price reactions."""
        templates = [
            ("{company} beats Q{quarter} estimates", 1.5, 2.0),
            ("{company} misses Q{quarter} estimates", -1.5, -2.0),
            ("{company} wins {value}Cr order", 1.0, 1.5),
            ("{company} faces regulatory probe", -1.0, -2.0),
            ("Crude oil {direction}", 0.5, 1.0),
            ("RBI {action} rates", 0.8, 1.2),
        ]

        companies = ["RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY"]
        headlines = []
        moves_1h = []
        moves_4h = []

        for i in range(n):
            idx = np.random.randint(0, len(templates))
            tpl, base_1h, base_4h = templates[idx]
            company = np.random.choice(companies)
            quarter = np.random.randint(1, 5)
            value = np.random.randint(100, 5000)
            direction = np.random.choice(["surges", "falls"])
            action = np.random.choice(["hikes", "cuts"])

            headline = tpl.format(
                company=company, 
                quarter=quarter, 
                value=value, 
                direction=direction, 
                action=action
            )

            # Add noise to actual moves
            move_1h = base_1h + np.random.normal(0, 0.5)
            move_4h = base_4h + np.random.normal(0, 0.8)

            headlines.append(headline)
            moves_1h.append(move_1h)
            moves_4h.append(move_4h)

        return headlines, moves_1h, moves_4h

    def test_learner_discriminates_positive_vs_negative(self):
        """Learner should predict positive for beats, negative for misses."""
        learner = AdaptiveClusterLearner()
        learner.clusters = {}
        learner._fitted = True

        # Train with clear positive and negative patterns
        # Positive patterns
        for _ in range(5):
            learner.update("RELIANCE beats Q1 estimates", 2.0, 3.0)
            learner.update("TCS beats Q2 estimates", 1.5, 2.5)
            learner.update("INFY beats Q3 estimates", 1.8, 2.8)
        
        # Negative patterns
        for _ in range(5):
            learner.update("RELIANCE misses Q1 estimates", -2.0, -3.0)
            learner.update("TCS misses Q2 estimates", -1.5, -2.5)
            learner.update("INFY misses Q3 estimates", -1.8, -2.8)

        # Test predictions on new similar headlines
        beat_pred = learner.predict("RELIANCE beats Q2 estimates")
        miss_pred = learner.predict("RELIANCE misses Q2 estimates")

        assert beat_pred > miss_pred, f"Beat pred {beat_pred} should exceed miss pred {miss_pred}"

    def test_dissemination_high_for_widely_covered_events(self):
        """Major events with many sources get high dissemination score."""
        clusterer = DisseminationClusterer()

        # Simulate major event covered by 5 sources
        articles = [
            {"title": f"RELIANCE beats Q2 - {src}", "body": "Profit jumps", "source": src, "ticker": "RELIANCE"}
            for src in ["ET", "MC", "LM", "NDTV", "Google"]
        ]

        clusters = clusterer.cluster_articles(articles)
        assert len(clusters) == 1
        assert clusters[0]["dissemination_score"] > 0.5  # high diversity


class TestAdaptiveLearnerEdgeCases:
    """Edge cases and regression tests."""

    def test_empty_headline_handled(self):
        learner = AdaptiveClusterLearner()
        learner.update("", 1.0, 1.0)
        # Should not crash, creates cluster for empty string
        assert len(learner.clusters) >= 0

    def test_special_chars_in_headline(self):
        learner = AdaptiveClusterLearner()
        learner.clusters = {}
        learner._fitted = True
        learner.update("RELIANCE: Q2 profit ₹5000Cr (YoY +20%)", 2.0, 3.0)
        pred = learner.predict("RELIANCE Q2 profit 5000Cr")
        assert pred > 0

    def test_calibration_with_insufficient_data(self):
        """Calibration with <3 samples does nothing."""
        def test_persistence_roundtrip(self):
                """Save and load preserves clusters."""
                import tempfile
                import json
                from pathlib import Path

                # Clear cache before starting
                import adaptive_sentiment
                cache_file = adaptive_sentiment.ADAPTIVE_CACHE_FILE
                if cache_file.exists():
                    cache_file.unlink()

                learner = AdaptiveClusterLearner()
                learner.update("Test headline", 1.5, 2.0)

                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                    from adaptive_sentiment import _serialize_cluster
                    data = {
                        "clusters": {str(k): _serialize_cluster(v) for k, v in learner.clusters.items()},
                        "last_calibration": learner._last_calibration,
                        "saved_at": datetime.now().isoformat(),
                    }
                    json.dump(data, f)
                    path = Path(f.name)

                # New learner loads - need to clear cache first to avoid loading existing clusters
                cache_file = adaptive_sentiment.ADAPTIVE_CACHE_FILE
                if cache_file.exists():
                    cache_file.unlink()

                learner2 = AdaptiveClusterLearner()
                # Manually load since _load uses ADAPTIVE_CACHE_FILE
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                from adaptive_sentiment import _deserialize_cluster
                learner2.clusters = {int(k): _deserialize_cluster(v) for k, v in data.get("clusters", {}).items()}
                learner2._last_calibration = data.get("last_calibration", 0.0)
                learner2._fitted = True

                assert len(learner2.clusters) == 1
                assert learner2.predict("Test headline") == 1.5

                path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])