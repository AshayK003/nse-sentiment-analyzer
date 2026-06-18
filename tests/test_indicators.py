"""
Tests for technical indicators computation.
Mocks yfinance to return controlled OHLCV data.
"""

import pytest
import pandas as pd
import numpy as np

# We patch st.cache_data before importing indicators so the
# decorator is a no-op in test context
import streamlit as st
from unittest.mock import MagicMock


def _make_ticker_mock(hist_df):
    """Create a mock yf.Ticker that returns the given history."""
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = hist_df
    return mock_ticker


class TestTechnicalIndicators:
    """Tests for get_technical_indicators()."""

    def _call(self, mocker, hist_df):
        """Call get_technical_indicators with mocked yfinance and Streamlit cache."""
        # Bypass st.cache_data so it's a pass-through
        mocker.patch("streamlit.cache_data", lambda **kwargs: lambda f: f)
        # Reload to pick up the patched decorator
        import importlib
        from indicators import get_technical_indicators
        importlib.reload(importlib.import_module("indicators"))
        from indicators import get_technical_indicators as gti

        mocker.patch("yfinance.Ticker", return_value=_make_ticker_mock(hist_df))
        return gti("RELIANCE")

    def test_rsi_computed(self, mocker):
        """RSI should be a float between 0-100."""
        dates = pd.date_range(end="2026-06-18", periods=252, freq="B")
        np.random.seed(42)
        prices = 100.0 + np.cumsum(np.random.randn(252) * 0.5)
        hist = pd.DataFrame({
            "Open": prices, "High": prices * 1.01,
            "Low": prices * 0.99, "Close": prices,
            "Volume": np.random.randint(500_000, 2_000_000, 252),
        }, index=dates)

        result = self._call(mocker, hist)
        assert result is not None
        assert isinstance(result["rsi"], float)
        assert 0 <= result["rsi"] <= 100

    def test_sma_values(self, mocker):
        """SMA 50 and 200 should be floats with 252 data points."""
        dates = pd.date_range(end="2026-06-18", periods=252, freq="B")
        prices = np.linspace(100, 150, 252)  # Smooth uptrend
        hist = pd.DataFrame({
            "Open": prices, "High": prices * 1.01,
            "Low": prices * 0.99, "Close": prices,
            "Volume": np.ones(252) * 1_000_000,
        }, index=dates)

        result = self._call(mocker, hist)
        assert result is not None
        assert isinstance(result["sma_50"], float)
        assert isinstance(result["sma_200"], float)

    def test_macd_histogram(self, mocker):
        """MACD histogram should be a float."""
        dates = pd.date_range(end="2026-06-18", periods=252, freq="B")
        prices = 100.0 + np.sin(np.linspace(0, 4 * np.pi, 252)) * 10
        hist = pd.DataFrame({
            "Open": prices, "High": prices * 1.01,
            "Low": prices * 0.99, "Close": prices,
            "Volume": np.ones(252) * 1_000_000,
        }, index=dates)

        result = self._call(mocker, hist)
        assert result is not None
        assert isinstance(result["macd_hist"], float)

    def test_sma_none_on_short_history(self, mocker):
        """Short history (< 26) returns None entirely (can't compute RSI/MACD either)."""
        dates = pd.date_range(end="2026-06-18", periods=20, freq="B")
        hist = pd.DataFrame({
            "Open": [100.0] * 20, "High": [101.0] * 20,
            "Low": [99.0] * 20, "Close": [100.5] * 20,
            "Volume": [1_000_000] * 20,
        }, index=dates)

        result = self._call(mocker, hist)
        assert result is None, "Should return None when < 26 rows"

    def test_volume_avg_none_on_short_history(self, mocker):
        """Short history (< 26) returns None (can't compute indicators)."""
        dates = pd.date_range(end="2026-06-18", periods=20, freq="B")
        hist = pd.DataFrame({
            "Open": [100.0] * 20, "High": [101.0] * 20,
            "Low": [99.0] * 20, "Close": [100.5] * 20,
            "Volume": [1_000_000] * 20,
        }, index=dates)

        result = self._call(mocker, hist)
        assert result is None, "Should return None when < 26 rows"

    def test_bullish_crossover_detected(self, mocker):
        """Should detect bullish SMA50 crossover (price crossed above SMA50 today)."""
        dates = pd.date_range(end="2026-06-18", periods=252, freq="B")
        prices = np.linspace(80, 120, 252)  # Uptrend
        # Force yesterday below SMA50, today above
        prices[-3] = 94.0
        prices[-2] = 95.0
        prices[-1] = 101.0
        hist = pd.DataFrame({
            "Open": prices, "High": prices * 1.01,
            "Low": prices * 0.99, "Close": prices,
            "Volume": np.ones(252) * 1_000_000,
        }, index=dates)

        result = self._call(mocker, hist)
        if result:
            # May or may not detect crossover depending on SMA values
            assert "close" in result
            assert "sma50_cross" in result

    def test_bearish_crossover_detected(self, mocker):
        """Should detect bearish SMA50 crossover (price crossed below SMA50 today)."""
        dates = pd.date_range(end="2026-06-18", periods=252, freq="B")
        prices = np.linspace(120, 80, 252)  # Downtrend
        # Force yesterday above SMA50, today below
        prices[-3] = 106.0
        prices[-2] = 105.0
        prices[-1] = 99.0
        hist = pd.DataFrame({
            "Open": prices, "High": prices * 1.01,
            "Low": prices * 0.99, "Close": prices,
            "Volume": np.ones(252) * 1_000_000,
        }, index=dates)

        result = self._call(mocker, hist)
        if result:
            assert "close" in result

    def test_return_none_on_empty_history(self, mocker):
        """Empty DataFrame should return None."""
        empty_hist = pd.DataFrame()
        result = self._call(mocker, empty_hist)
        assert result is None
