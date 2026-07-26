"""
Tests for the data layer modules.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from src.contracts import OHLCV, PriceData, Indicators, TrendDirection, Headline, NewsArticle


class TestOHLCV:
    def test_ohlcv_creation(self):
        ohlcv = OHLCV(
            timestamp=datetime.now(),
            open=100.0, high=105.0, low=98.0, close=103.0, volume=1000000
        )
        assert ohlcv.open == 100.0
        assert ohlcv.high == 105.0
        assert ohlcv.typical_price == 102.0  # (105 + 98 + 103) / 3

    def test_ohlcv_rejects_nan(self):
        with pytest.raises(ValueError):
            OHLCV(
                timestamp=datetime.now(),
                open=float('nan'), high=105.0, low=98.0, close=103.0, volume=1000000
            )

    def test_ohlcv_rejects_invalid_hl(self):
        with pytest.raises(ValueError):
            OHLCV(
                timestamp=datetime.now(),
                open=100.0, high=95.0, low=98.0, close=103.0, volume=1000000
            )


class TestIndicators:
    def test_bullish_detection(self):
        ind = Indicators(
            rsi_14=60.0, macd=0.5, macd_signal=0.3, macd_hist=0.2,
            sma_20=100, sma_50=95, sma_200=90,
            volume_ratio=1.2, atr_14=2.0,
            trend=TrendDirection.BULLISH, trend_strength=0.7
        )
        assert ind.is_bullish() is True
        assert ind.is_bearish() is False

    def test_bearish_detection(self):
        ind = Indicators(
            rsi_14=40.0, macd=-0.5, macd_signal=-0.3, macd_hist=-0.2,
            sma_20=100, sma_50=105, sma_200=110,
            volume_ratio=1.2, atr_14=2.0,
            trend=TrendDirection.BEARISH, trend_strength=0.7
        )
        assert ind.is_bearish() is True
        assert ind.is_bullish() is False

    def test_neutral_trend(self):
        ind = Indicators(
            rsi_14=50.0, macd=0.0, macd_signal=0.0, macd_hist=0.0,
            sma_20=100, sma_50=100, sma_200=100,
            volume_ratio=1.0, atr_14=2.0,
            trend=TrendDirection.NEUTRAL, trend_strength=0.0
        )
        assert ind.is_bullish() is False
        assert ind.is_bearish() is False


class TestPriceData:
    def test_price_data_creation(self):
        price = PriceData(
            ohlcv=[],
            indicators=Indicators(
                rsi_14=50.0, macd=0.0, macd_signal=0.0, macd_hist=0.0,
                sma_20=100, sma_50=100, sma_200=100,
                volume_ratio=1.0, atr_14=2.0,
                trend=TrendDirection.NEUTRAL, trend_strength=0.0
            ),
            current_price=100.0, change_pct=1.5,
            high_52w=120.0, low_52w=80.0
        )
        assert price.current_price == 100.0
        assert price.change_pct == 1.5


class TestHeadline:
    def test_headline_text_property(self):
        h = Headline(
            title="Test Title",
            summary="Test summary",
            url="https://example.com",
            source="Test Source",
            published=datetime.now()
        )
        assert h.text == "Test Title. Test summary"


class TestNewsArticle:
    def test_news_article_creation(self):
        article = NewsArticle(
            title="Test News",
            url="https://example.com",
            source="Test",
            published=datetime.now(),
            ticker="RELIANCE",
            sentiment=0.5,
            summary="Summary"
        )
        assert article.ticker == "RELIANCE"
        assert article.sentiment == 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])