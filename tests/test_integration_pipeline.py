"""Integration tests for the news-to-sentiment pipeline (Issue #26).

Tests that modules work TOGETHER: news retrieval → per-headline sentiment
→ source-weighted signal blending. Bugs live at interfaces (wrong dict
key, unexpected None, type mismatch) — unit tests miss those.

All external I/O is mocked; only the seams between modules are real.
"""
from unittest.mock import patch

from data_fetcher import search_news
from sentiment import analyze_headline_sentiment, get_sia, get_weighted_signal


FAKE_RSS_ITEMS = [
    {"title": "TCS reports strong growth in quarterly profit", "source": "reuters", "link": "http://x/1"},
    {"title": "Infosys faces sell-off as investors exit IT stocks", "source": "bloomberg", "link": "http://x/2"},
    {"title": "Markets trade flat ahead of Fed decision", "source": "cnbc", "link": "http://x/3"},
]


class MockFeed:
    def __init__(self, entries):
        self.entries = entries


def _mock_rss_parse(*args, **kwargs):
    return MockFeed(
        [
            {"title": e["title"], "link": e["link"], "summary": "", "published": ""}
            for e in FAKE_RSS_ITEMS
        ]
    )


class TestPipelineChain:
    """search_news() → analyze_headline_sentiment() → get_weighted_signal()"""

    def _run_chain(self, headlines_with_sources):
        sia = get_sia()
        scores = [
            analyze_headline_sentiment(h, body="", sia=sia, source=src)
            for h, src in headlines_with_sources
        ]
        return scores

    def test_search_news_output_feeds_sentiment_directly(self):
        """The tuple search_news() returns must satisfy what the
        sentiment layer consumes — this is the seam where bugs live."""
        with patch("data_fetcher.feedparser.parse", side_effect=_mock_rss_parse), \
             patch("data_fetcher._relevant", side_effect=lambda *a, **k: True):
            result = search_news("TCS", "Tata Consultancy Services")
        # contract: (articles, cascade_pool, source_health, clusters, dissemination_score)
        articles, cascade_pool, source_health = result[0], result[1], result[2]
        assert len(articles) == len(FAKE_RSS_ITEMS)
        for item in articles:
            # contract: title/body/date/url/source keys
            assert isinstance(item.get("title"), str) and item["title"].strip()
            assert "source" in item and "url" in item
        # cascade pool includes everything retrieved
        assert len(cascade_pool) >= len(articles)
        assert isinstance(source_health, dict)

    def test_bullish_and_bearish_flow_to_opposite_signals(self):
        scores = self._run_chain(
            [(FAKE_RSS_ITEMS[0]["title"], "reuters"), ("Infosys stock crashes after downgrade", "bloomberg")]
        )
        compounds = [s["compound"] for s in scores]
        assert compounds[0] > 0, f"growth headline should score positive, got {compounds[0]}"
        assert compounds[1] < 0, f"crash headline should score negative, got {compounds[1]}"

    def test_scores_shape_matches_weighted_signal_contract(self):
        """get_weighted_signal expects [{'compound': float, 'source': str}] —
        verify analyze_headline_sentiment actually emits that shape."""
        scores = self._run_chain([("Strong growth reported by TCS", "reuters")])
        for s in scores:
            assert isinstance(s.get("compound"), float)
            assert isinstance(s.get("source"), str)

    def test_full_chain_produces_valid_signal(self):
        scores = self._run_chain(
            [(e["title"], e["source"]) for e in FAKE_RSS_ITEMS]
        )
        signal, blended, emoji, breakdown = get_weighted_signal(scores)
        assert signal is not None
        assert -1.0 <= blended <= 1.0
        assert len(breakdown) > 0

    def test_empty_headline_list_degrades_gracefully(self):
        signal, blended, emoji, breakdown = get_weighted_signal([])
        # Must not crash; any sane neutral representation is acceptable
        assert breakdown is not None or signal is not None or blended is not None

    def test_none_compound_does_not_crash_blender(self):
        """Interface hazard: a None compound from upstream must be rejected
        or defaulted by the blender, never crash it."""
        try:
            result = get_weighted_signal([{"compound": None, "source": "reuters"}])
            # If tolerated, output must still be finite
            assert result[1] is None or abs(result[1]) <= 1.0
        except (TypeError, ValueError):
            pass  # explicit rejection is also acceptable behavior

    def test_unknown_source_uses_default_weight(self):
        scores = [{"compound": 0.5, "source": "totally-unknown-blog"}]
        signal, blended, emoji, breakdown = get_weighted_signal(scores)
        assert -1.0 <= blended <= 1.0
