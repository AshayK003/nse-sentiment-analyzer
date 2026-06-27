"""
Tests for cascade/ripple tracking — commodity keyword detection.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cascade import detect_cascade


class TestDetectCascade:
    """Tests for cascade detection from news items."""

    def test_empty_news_returns_empty(self):
        """No news items should return empty list."""
        assert detect_cascade([]) == []

    def test_none_news_returns_empty(self):
        """None or missing news should return empty list."""
        assert detect_cascade(None) == []

    def test_crude_oil_mentions_bpcl(self):
        """Crude oil in headlines should flag OMCs and paints."""
        news = [
            {
                "title": "Crude oil prices surge on OPEC supply cuts",
                "body": ("Brent crude jumped above $85 per barrel "
                         "after OPEC+ announced production cuts."),
            },
        ]
        results = detect_cascade(news)
        assert len(results) == 1
        assert results[0]["driver"] == "Crude Oil"
        assert results[0]["direction"] == 1
        tickers = [r[0] for r in results[0]["affects"]]
        assert "BPCL" in tickers
        assert "INDIGO" in tickers
        assert "ASIANPAINT" in tickers

    def test_crude_alternate_terms(self):
        """Brent and WTI keywords should also trigger crude cascade."""
        news = [
            {"title": "Brent crude at 3-month high", "body": ""},
        ]
        results = detect_cascade(news)
        drivers = [r["driver"] for r in results]
        assert "Crude Oil" in drivers

    def test_rupee_weakness_flags_it_stocks(self):
        """Rupee depreciation news should flag IT stocks."""
        news = [
            {"title": "Rupee weakens past 86 against US dollar", "body": ""},
        ]
        results = detect_cascade(news)
        drivers = [r["driver"] for r in results]
        assert "Rupee / USD" in drivers
        rupee_effect = [r for r in results if r["driver"] == "Rupee / USD"][0]
        tickers = [a[0] for a in rupee_effect["affects"]]
        assert "INFY" in tickers
        assert "TCS" in tickers

    def test_gold_price_triggers_goldbees(self):
        """Gold price news should flag gold-related tickers."""
        news = [
            {"title": "Gold prices surge to new highs", "body": ""},
        ]
        results = detect_cascade(news)
        drivers = [r["driver"] for r in results]
        assert "Gold" in drivers

    def test_steel_news_triggers_steel_tickers(self):
        """Steel/iron ore news should flag steel producers."""
        news = [
            {"title": "Steel prices fall on weak demand", "body": ""},
        ]
        results = detect_cascade(news)
        drivers = [r["driver"] for r in results]
        assert "Iron Ore/Steel" in drivers

    def test_unrelated_news_returns_empty(self):
        """Unrelated news should not trigger any cascade."""
        news = [
            {"title": "HDFCBANK reports strong quarterly profit", "body": ""},
        ]
        results = detect_cascade(news)
        assert results == []

    def test_multiple_commodities_detected(self):
        """News mentioning multiple commodities should detect each."""
        news = [
            {
                "title": "Crude oil rallies, gold steady, rupee flat",
                "body": "Brent crude hits $87 while gold holds steady.",
            },
        ]
        results = detect_cascade(news)
        drivers = [r["driver"] for r in results]
        assert "Crude Oil" in drivers
        assert "Gold" in drivers

    def test_company_names_resolved(self):
        """If ticker_lookup is provided, company names should resolve."""
        lookup = {"BPCL": "Bharat Petroleum Corp Ltd", "TCS": "Tata Consultancy Services"}
        news = [
            {"title": "Crude oil prices rise sharply", "body": ""},
        ]
        results = detect_cascade(news, ticker_lookup=lookup)
        assert len(results) == 1
        crude = results[0]
        # Find BPCL in affects
        bpcl_entry = [a for a in crude["affects"] if a[0] == "BPCL"]
        assert len(bpcl_entry) == 1
        _, _, company = bpcl_entry[0]
        assert company == "Bharat Petroleum Corp Ltd"

    def test_natural_gas_detection(self):
        """Natural gas price mentions should flag city gas tickers."""
        news = [
            {"title": "Natural gas prices surge on winter demand", "body": ""},
        ]
        results = detect_cascade(news)
        drivers = [r["driver"] for r in results]
        assert "Natural Gas" in drivers
        gas_effect = [r for r in results if r["driver"] == "Natural Gas"][0]
        tickers = [a[0] for a in gas_effect["affects"]]
        assert "IGL" in tickers
        assert "GUJGASLTD" in tickers

    def test_coal_detection(self):
        """Coal price mentions should flag coal and power tickers."""
        news = [
            {"title": "Coal prices rise on supply constraints", "body": ""},
        ]
        results = detect_cascade(news)
        drivers = [r["driver"] for r in results]
        assert "Coal" in drivers

    def test_direction_inferred_up_on_rise_keywords(self):
        """Commodity up keywords (surge, jump, rally) set direction=1."""
        news = [{"title": "Crude oil prices surge on supply cuts", "body": ""}]
        results = detect_cascade(news)
        assert results[0]["direction"] == 1

    def test_direction_inferred_down_on_fall_keywords(self):
        """Commodity down keywords (fall, drop, slump) set direction=-1."""
        news = [{"title": "Crude oil prices crash on demand fears", "body": ""}]
        results = detect_cascade(news)
        assert results[0]["direction"] == -1

    def test_impact_bearish_when_commodity_rise_is_bad(self):
        """Crude rising → bad for OMCs → impact=1 (Bearish)."""
        news = [{"title": "Crude oil surges, Brent jumps above $86", "body": ""}]
        results = detect_cascade(news)
        assert results[0]["impact"] == 1

    def test_impact_bullish_when_commodity_fall_is_good(self):
        """Crude crashing → good for OMCs → impact=-1 (Bullish)."""
        news = [{"title": "Crude oil prices crash on demand concerns", "body": ""}]
        results = detect_cascade(news)
        assert results[0]["impact"] == -1

    def test_impact_bearish_on_gold_fall(self):
        """Gold falling → bad for gold tickers → impact=1 (Bearish)."""
        news = [{"title": "Gold prices slump to 3-month low", "body": ""}]
        results = detect_cascade(news)
        assert results[0]["impact"] == 1

    def test_impact_bullish_on_gold_rise(self):
        """Gold surging → good for gold tickers → impact=-1 (Bullish)."""
        news = [{"title": "Gold prices rally to new record high", "body": ""}]
        results = detect_cascade(news)
        assert results[0]["impact"] == -1

    def test_direction_falls_back_to_default_when_ambiguous(self):
        """Mixed direction signals -> fall back to CASCADE_MAP default."""
        news = [
            {"title": "Crude oil prices surge on supply cuts", "body": ""},
            {"title": "Brent crude falls on demand concerns", "body": ""},
        ]
        results = detect_cascade(news)
        crude = [r for r in results if r["driver"] == "Crude Oil"][0]
        # 1 up + 1 down = tie → fall back to CASCADE_MAP +1 default
        assert crude["direction"] == 1
        assert crude["impact"] == 1

    def test_matched_articles_count(self):
        """matched_articles should reflect how many articles mentioned the commodity."""
        news = [
            {"title": "Crude oil prices surge", "body": ""},
            {"title": "HDFCBANK profit rises", "body": ""},
            {"title": "Brent crude falls on demand concerns", "body": ""},
        ]
        results = detect_cascade(news)
        crude = [r for r in results if r["driver"] == "Crude Oil"]
        assert len(crude) == 1
        assert crude[0]["matched_articles"] == 2
