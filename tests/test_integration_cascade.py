"""
Integration tests for the cascade detection pipeline (cascade.py).

Unlike tests/test_cascade.py — which exercises detect_cascade() with minimal,
single-purpose fixtures — these tests feed in news items shaped like the
output of data_fetcher.fetch_market_headlines() (title/body/source/date/url)
and assert on the full, realistic result: the right drivers fire, the right
tickers are attached, and the Bullish/Bearish semantics are correct end to end.

No mocking is required: detect_cascade() is a pure transformation over the
news list plus the static CASCADE_MAP, so realistic-shaped dicts are enough.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cascade import detect_cascade


class TestCascadeIntegration:
    """Integration-style tests: realistic headlines through the full pipeline."""

    def test_crude_oil_rise_affects_ongc(self):
        # Arrange: a realistic RSS-shaped headline about a crude oil rally.
        news = [
            {
                "title": "Crude oil surges above $85 amid supply concerns",
                "body": "",
                "source": "ET",
                "date": "2026-07-10",
                "url": "https://x.com/1",
            },
        ]

        # Act
        result = detect_cascade(news, ticker_lookup=None, focus_ticker="ONGC")

        # Assert: ONGC has an inverse relationship to crude (direction -1),
        # so a crude price rise is Bullish for it, not Bearish.
        assert len(result) == 1
        crude = result[0]
        assert crude["driver"] == "Crude Oil"
        assert crude["direction"] == 1  # crude price rose

        ongc_entries = [a for a in crude["affects"] if a["ticker"] == "ONGC"]
        assert len(ongc_entries) == 1
        ongc = ongc_entries[0]
        assert ongc["searched"] is True
        # ticker_impact: +1 = Bearish, -1 = Bullish
        assert ongc["ticker_impact"] == -1
        assert "rally" in ongc["reason"].lower() or "boosts" in ongc["reason"].lower()

    def test_detect_cascade_returns_expected_fields(self):
        # Arrange: two distinct macro headlines (rupee + gold) in one batch.
        news = [
            {
                "title": "Rupee weakens to 86 against US dollar",
                "body": "",
                "source": "ET",
                "date": "2026-07-10",
                "url": "https://x.com/1",
            },
            {
                "title": "Gold prices jump on safe-haven demand",
                "body": "",
                "source": "ET",
                "date": "2026-07-10",
                "url": "https://x.com/2",
            },
        ]

        # Act
        result = detect_cascade(news)

        # Assert: both drivers detected, each with the documented shape.
        drivers = {r["driver"] for r in result}
        assert drivers == {"Rupee / USD", "Gold"}

        for driver_result in result:
            assert set(driver_result.keys()) == {
                "driver", "direction", "impact", "affects", "matched_articles",
            }
            assert driver_result["impact"] in (1, -1)
            assert driver_result["matched_articles"] >= 1
            assert len(driver_result["affects"]) > 0
            for affected in driver_result["affects"]:
                assert set(affected.keys()) == {
                    "ticker", "reason", "company", "searched", "ticker_impact",
                }
                assert affected["ticker_impact"] in (1, -1)
                assert isinstance(affected["reason"], str) and affected["reason"]

    def test_cascade_no_relevant_news(self):
        # Arrange: a headline with no commodity/macro driver keywords.
        news = [
            {
                "title": "Company board meeting on March 15",
                "body": "",
                "source": "ET",
                "date": "2026-07-10",
                "url": "https://x.com/1",
            },
        ]

        # Act
        result = detect_cascade(news)

        # Assert
        assert result == []
        assert len(result) == 0

    def test_cascade_empty_news_list(self):
        # Arrange
        news = []

        # Act
        result = detect_cascade(news)

        # Assert: empty input never crashes and yields empty output.
        assert result == []

    def test_cascade_filtered_by_focus_ticker(self):
        # Arrange: crude oil (doesn't affect HINDALCO) + aluminum fall
        # (does affect HINDALCO) in the same news batch.
        news = [
            {
                "title": "Crude oil surges above $85 amid supply concerns",
                "body": "",
                "source": "ET",
                "date": "2026-07-10",
                "url": "https://x.com/1",
            },
            {
                "title": "Aluminum prices fall on weak global demand",
                "body": "",
                "source": "ET",
                "date": "2026-07-10",
                "url": "https://x.com/2",
            },
        ]

        # Act
        result = detect_cascade(news, focus_ticker="HINDALCO")

        # Assert: only the aluminum driver survives the focus_ticker filter.
        drivers = [r["driver"] for r in result]
        assert "Aluminum" in drivers
        assert "Crude Oil" not in drivers  # CASCADE_MAP has no HINDALCO entry there

        aluminum = [r for r in result if r["driver"] == "Aluminum"][0]
        hindalco_entries = [a for a in aluminum["affects"] if a["ticker"] == "HINDALCO"]
        assert len(hindalco_entries) == 1
        hindalco = hindalco_entries[0]
        assert hindalco["searched"] is True
        # Aluminum falls (direction -1) x HINDALCO direction -1 => ticker_impact +1 (Bearish)
        assert hindalco["ticker_impact"] == 1
