"""Tests for intraday tools — VWAP, pivot levels, India VIX."""

import pytest
import pandas as pd
import numpy as np


class TestVWAP:
    """Tests for compute_vwap()."""

    def test_vwap_with_known_data(self, mocker):
        """Compute VWAP from known 5-min OHLCV data."""
        from intraday import compute_vwap

        # 3 bars of synthetic 5-min data
        data = pd.DataFrame({
            "High": [101.0, 102.0, 103.0],
            "Low":  [99.0,  100.0, 101.0],
            "Close":[100.0, 101.0, 102.0],
            "Volume":[1000,  2000,   3000],
        })
        mock_dl = mocker.patch("yfinance.download", return_value=data)

        result = compute_vwap("RELIANCE")

        # VWAP = Σ((H+L+C)/3 * V) / Σ(V)
        # Bar1: (101+99+100)/3 * 1000 = 100 * 1000 = 100000
        # Bar2: (102+100+101)/3 * 2000 = 101 * 2000 = 202000
        # Bar3: (103+101+102)/3 * 3000 = 102 * 3000 = 306000
        # Sum VWAP_num = 608000, Sum Vol = 6000
        # VWAP = 608000/6000 = 101.33...
        assert result["vwap"] == pytest.approx(101.33, rel=0.01)
        # Current price = last close = 102.0
        assert result["price"] == 102.0
        # Deviation = (102 - 101.33) / 101.33 * 100 ≈ +0.66%
        assert result["deviation_pct"] == pytest.approx(0.66, rel=0.1)

    def test_vwap_below_price(self, mocker):
        """Current price well below VWAP → negative deviation."""
        from intraday import compute_vwap

        data = pd.DataFrame({
            "High": [105.0, 104.0, 102.0],
            "Low":  [102.0, 101.0, 99.0],
            "Close":[104.0, 102.0, 98.0],
            "Volume":[1000,  2000,  3000],
        })
        mocker.patch("yfinance.download", return_value=data)

        result = compute_vwap("RELIANCE")

        assert result["vwap"] > result["price"]
        assert result["deviation_pct"] < 0

    def test_vwap_empty_data(self, mocker):
        """Empty yfinance response → None-safe result."""
        from intraday import compute_vwap

        empty = pd.DataFrame()
        mocker.patch("yfinance.download", return_value=empty)

        result = compute_vwap("RELIANCE")

        assert result["vwap"] is None
        assert result["deviation_pct"] is None

    def test_vwap_no_suffix_for_indices(self, mocker):
        """^INDIAVIX should not get .NS suffix."""
        from intraday import compute_vwap

        data = pd.DataFrame({
            "High": [10.0, 11.0],
            "Low":  [9.0, 10.0],
            "Close":[10.0, 11.0],
            "Volume":[100, 200],
        })
        mock_dl = mocker.patch("yfinance.download", return_value=data)

        compute_vwap("^INDIAVIX")
        # Should have been called without .NS suffix
        call_args = mock_dl.call_args[0]
        assert "INDIAVIX" in str(call_args[0])
        assert ".NS" not in str(call_args[0])


class TestPivotLevels:
    """Tests for compute_pivot_levels()."""

    def test_pivot_from_known_data(self):
        """Classic pivot formula: P=(H+L+C)/3, R1=2P-L, S1=2P-H."""
        from intraday import compute_pivot_levels

        # Last bar: H=110, L=100, C=105
        hist = pd.DataFrame({
            "High": [100, 108, 110],
            "Low":  [95,  98,  100],
            "Close":[98,  106, 105],
        })
        result = compute_pivot_levels(hist)

        # Pivot = (110+100+105)/3 = 105
        # R1 = 2*105 - 100 = 110
        # S1 = 2*105 - 110 = 100
        assert result["pivot"] == 105.0
        assert result["resistance"] == 110.0
        assert result["support"] == 100.0

    def test_pivot_none_on_empty(self):
        """None or empty DataFrame → safe result."""
        from intraday import compute_pivot_levels

        result = compute_pivot_levels(None)
        assert result["pivot"] is None
        assert result["support"] is None
        assert result["resistance"] is None

    def test_pivot_support_below_resistance(self):
        """Support must always be below resistance."""
        from intraday import compute_pivot_levels

        hist = pd.DataFrame({
            "High": [120],
            "Low":  [80],
            "Close":[100],
        })
        result = compute_pivot_levels(hist)

        assert result["support"] < result["pivot"]
        assert result["pivot"] < result["resistance"]

    def test_pivot_works_with_indicators_hist(self, pandas_hist):
        """Should handle the conftest fixture format gracefully."""
        from intraday import compute_pivot_levels

        result = compute_pivot_levels(pandas_hist)

        assert result["pivot"] is not None
        assert result["support"] is not None
        assert result["resistance"] is not None
        assert result["pivot"] > 0


class TestVIX:
    """Tests for get_vix()."""

    def test_returns_vix_value(self, mocker):
        """Should return the latest VIX close + change."""
        # We import from intraday module (unified location)
        from intraday import get_vix

        mock_df = pd.DataFrame({
            "Close": [14.0, 14.5, 15.2],
        })
        mock_dl = mocker.patch("yfinance.download", return_value=mock_df)

        result = get_vix()

        assert result["vix"] == pytest.approx(15.2)
        assert result["change"] == pytest.approx(0.7)

    def test_vix_falls_on_volatility(self, mocker):
        """VIX > 20 should flag as 'High'."""
        from intraday import get_vix

        mock_df = pd.DataFrame({
            "Close": [18.0, 19.0, 22.5],
        })
        mocker.patch("yfinance.download", return_value=mock_df)

        result = get_vix()

        assert result["vix"] == 22.5
        assert result["level"] == "High"

    def test_vix_low_volatility(self, mocker):
        """VIX < 15 should flag as 'Low'."""
        from intraday import get_vix

        mock_df = pd.DataFrame({
            "Close": [12.0, 12.5, 13.0],
        })
        mocker.patch("yfinance.download", return_value=mock_df)

        result = get_vix()

        assert result["vix"] == 13.0
        assert result["level"] == "Low"

    def test_vix_empty_response(self, mocker):
        """Empty yfinance response → None-safe result."""
        from intraday import get_vix

        mocker.patch("yfinance.download", return_value=pd.DataFrame())

        result = get_vix()

        assert result["vix"] is None
        assert result["level"] == "N/A"

    def test_uses_correct_ticker(self, mocker):
        """Should fetch ^INDIAVIX, not anything else."""
        from intraday import get_vix

        mock_df = pd.DataFrame({"Close": [15.0, 16.0]})
        mock_dl = mocker.patch("yfinance.download", return_value=mock_df)

        get_vix()

        ticker_arg = mock_dl.call_args[0][0]
        assert ticker_arg == "^INDIAVIX"
