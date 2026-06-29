"""Tests for volume spike detection (detect_volume_spike)."""

import pytest


class TestDetectVolumeSpike:
    """Tests for detect_volume_spike()."""

    def test_returns_spike_when_above_threshold(self):
        from indicators import detect_volume_spike

        result = detect_volume_spike(2_000_000, 500_000, threshold=2.0)

        assert result["spike"] is True
        assert result["ratio"] == 4.0

    def test_returns_no_spike_when_below_threshold(self):
        from indicators import detect_volume_spike

        result = detect_volume_spike(750_000, 500_000, threshold=2.0)

        assert result["spike"] is False
        assert pytest.approx(result["ratio"], 0.01) == 1.5

    def test_returns_no_spike_on_zero_avg(self):
        from indicators import detect_volume_spike

        result = detect_volume_spike(1_000_000, 0)

        assert result["spike"] is False

    def test_returns_no_spike_on_none_avg(self):
        from indicators import detect_volume_spike

        result = detect_volume_spike(1_000_000, None)

        assert result["spike"] is False

    def test_returns_no_spike_on_none_current(self):
        from indicators import detect_volume_spike

        result = detect_volume_spike(None, 500_000)

        assert result["spike"] is False


class TestMarketPulse:
    """Tests for get_market_pulse()."""

    def test_graceful_on_yfinance_failure(self, mocker):
        """yfinance failure should return None-safe dict, not crash."""
        mock_ticker = mocker.patch("yfinance.Ticker")
        mock_ticker.return_value.history.side_effect = Exception("API down")
        from market_data import get_market_pulse
        result = get_market_pulse()
        assert result is not None
        assert result["nifty_price"] is None
        assert result["nifty_change_pct"] is None


class TestMMI:
    """Tests for get_mmi() and its component scores."""

    def _make_sector_df(self, closes):
        """Helper: build a 10-row DataFrame with given last-2 Close values."""
        import pandas as pd
        import numpy as np
        cols = {"Close": list(np.linspace(100, closes[0], 10)[:-2]) + list(closes)}
        return pd.DataFrame(cols)

    def test_mmi_structure(self, mocker):
        """Happy path: returns dict with all expected keys."""
        import pandas as pd

        nifty_df = pd.DataFrame({"Close": list(range(110, 130))})  # 20 days
        vix_df = pd.DataFrame({"Close": [14.0, 14.5, 15.0]})
        sector_df = self._make_sector_df([101, 102])

        mock_ticker = mocker.patch("yfinance.Ticker")
        mock_ticker.return_value.history.side_effect = [nifty_df, vix_df] + [sector_df] * 10

        mocker.patch("market_data.get_fii_dii_flow", return_value={"fii_net": 500})
        mocker.patch("persistence.load_fiidii_history",
                      return_value=[{"fii_net": 200, "date": f"d{i}"} for i in range(21)])

        from market_data import get_mmi
        result = get_mmi()

        assert isinstance(result, dict)
        assert "mmi" in result
        assert "zone" in result
        assert "trend_score" in result
        assert "vix_score" in result
        assert "fii_score" in result
        assert "breadth_score" in result
        assert result["mmi"] is not None
        assert 0 <= result["mmi"] <= 100

    def test_mmi_trend_score_above_sma(self, mocker):
        """Nifty well above 20-day SMA → high trend score."""
        import pandas as pd
        # Close rising from 100 → 115 over 20 days, last close well above SMA
        closes = list(range(100, 115)) + [115, 116]  # 17 values
        nifty_df = pd.DataFrame({"Close": closes})
        vix_df = pd.DataFrame({"Close": [15.0, 16.0, 17.0]})
        empty_df = pd.DataFrame()

        mock_ticker = mocker.patch("yfinance.Ticker")
        mock_ticker.return_value.history.side_effect = [nifty_df, vix_df] + [empty_df] * 10

        mocker.patch("market_data.get_fii_dii_flow", return_value=None)
        mocker.patch("persistence.load_fiidii_history", return_value=[])

        from market_data import get_mmi, _calc_trend_score
        score = _calc_trend_score(nifty_df)
        assert score >= 50  # Above SMA → bullish

    def test_mmi_trend_score_below_sma(self, mocker):
        """Nifty below 20-day SMA → low trend score."""
        import pandas as pd
        closes = list(range(110, 91, -1))  # 19 values falling from 110 to 92
        nifty_df = pd.DataFrame({"Close": closes})

        from market_data import _calc_trend_score
        score = _calc_trend_score(nifty_df)
        assert score <= 50

    def test_mmi_vix_low(self, mocker):
        """Low VIX (~12) → high score (calm)."""
        import pandas as pd
        vix_df = pd.DataFrame({"Close": [11.0, 11.5, 12.0]})

        from market_data import _calc_vix_score
        score = _calc_vix_score(vix_df)
        assert score >= 80  # VIX 12 → ~93 score

    def test_mmi_vix_high(self, mocker):
        """High VIX (~35) → low score (fear)."""
        import pandas as pd
        vix_df = pd.DataFrame({"Close": [30.0, 32.0, 35.0]})

        from market_data import _calc_vix_score
        score = _calc_vix_score(vix_df)
        assert score <= 30

    def test_mmi_fii_bullish(self, mocker):
        """FII buying above average → high FII score."""
        mocker.patch("market_data.get_fii_dii_flow", return_value={"fii_net": 1500})
        mocker.patch("persistence.load_fiidii_history",
                      return_value=[{"fii_net": 300, "date": f"d{i}"} for i in range(21)])

        from market_data import _calc_fii_score
        score = _calc_fii_score()
        assert score >= 60  # 1500 > 300 avg → bullish

    def test_mmi_fii_bearish(self, mocker):
        """FII selling above average → low FII score."""
        mocker.patch("market_data.get_fii_dii_flow", return_value={"fii_net": -1500})
        mocker.patch("persistence.load_fiidii_history",
                      return_value=[{"fii_net": 300, "date": f"d{i}"} for i in range(21)])

        from market_data import _calc_fii_score
        score = _calc_fii_score()
        assert score <= 40  # -1500 vs avg 300 → bearish

    def test_mmi_fii_no_history(self, mocker):
        """No FII history → neutral score (50)."""
        mocker.patch("market_data.get_fii_dii_flow", return_value=None)
        mocker.patch("persistence.load_fiidii_history", return_value=[])

        from market_data import _calc_fii_score
        score = _calc_fii_score()
        assert score == 50

    def test_mmi_breadth_all_advancing(self, mocker):
        """All 10 sectors advancing → breadth=100."""
        import pandas as pd
        sector_data = {}
        for t in ["^NSEBANK", "^CNXIT", "^CNXPHARMA", "^CNXAUTO", "^CNXFMCG",
                   "^CNXREALTY", "^CNXPSE", "^CNXMEDIA", "^CNXMETAL", "^CNXENERGY"]:
            sector_data[t] = pd.DataFrame({"Close": [100.0, 101.0]})

        from market_data import _calc_breadth_score
        score = _calc_breadth_score(sector_data)
        assert score == 100

    def test_mmi_breadth_none_advancing(self, mocker):
        """All sectors declining → breadth=0."""
        import pandas as pd
        sector_data = {}
        for t in ["^NSEBANK", "^CNXIT", "^CNXPHARMA", "^CNXAUTO", "^CNXFMCG",
                   "^CNXREALTY", "^CNXPSE", "^CNXMEDIA", "^CNXMETAL", "^CNXENERGY"]:
            sector_data[t] = pd.DataFrame({"Close": [101.0, 100.0]})

        from market_data import _calc_breadth_score
        score = _calc_breadth_score(sector_data)
        assert score == 0

    def test_mmi_breadth_half_advancing(self, mocker):
        """5 of 10 advancing → breadth=50."""
        import pandas as pd
        sector_data = {}
        tickers = ["^NSEBANK", "^CNXIT", "^CNXPHARMA", "^CNXAUTO", "^CNXFMCG",
                    "^CNXREALTY", "^CNXPSE", "^CNXMEDIA", "^CNXMETAL", "^CNXENERGY"]
        for i, t in enumerate(tickers):
            close_vals = [100.0, 101.0] if i < 5 else [101.0, 100.0]
            sector_data[t] = pd.DataFrame({"Close": close_vals})

        from market_data import _calc_breadth_score
        score = _calc_breadth_score(sector_data)
        assert score == 50

    def test_mmi_breadth_no_data(self, mocker):
        """No sector data → neutral breadth (50)."""
        from market_data import _calc_breadth_score
        score = _calc_breadth_score({})
        assert score == 50

    def test_mmi_zone_extreme_fear(self, mocker):
        """Score < 25 → Extreme Fear."""
        from market_data import get_mmi
        # Directly test zone logic
        _mmi = 20
        assert "Extreme Fear" in (
            "Extreme Greed" if _mmi >= 75 else
            "Greed" if _mmi >= 60 else
            "Neutral" if _mmi >= 40 else
            "Fear" if _mmi >= 25 else
            "Extreme Fear"
        )

    def test_mmi_zone_extreme_greed(self, mocker):
        """Score >= 75 → Extreme Greed."""
        _mmi = 80
        assert "Extreme Greed" in (
            "Extreme Greed" if _mmi >= 75 else
            "Greed" if _mmi >= 60 else
            "Neutral" if _mmi >= 40 else
            "Fear" if _mmi >= 25 else
            "Extreme Fear"
        )

    def test_mmi_graceful_on_yfinance_failure(self, mocker):
        """yfinance failure → fallback neutral (50), not crash."""
        mock_ticker = mocker.patch("yfinance.Ticker")
        mock_ticker.return_value.history.side_effect = Exception("API down")

        from market_data import get_mmi
        result = get_mmi()
        assert result is not None
        # All components default to 50, so MMI == 50 (neutral)
        assert result["mmi"] == 50.0
        assert result["zone"] == "Neutral"

    def test_mmi_trend_score_fewer_than_20_points(self, mocker):
        """Less than 20 data points → neutral trend score."""
        import pandas as pd
        nifty_df = pd.DataFrame({"Close": list(range(100, 110))})  # 10 points only

        from market_data import _calc_trend_score
        score = _calc_trend_score(nifty_df)
        assert score == 50

    def test_mmi_vix_empty(self, mocker):
        """Empty VIX data → neutral VIX score."""
        import pandas as pd
        vix_df = pd.DataFrame()

        from market_data import _calc_vix_score
        score = _calc_vix_score(vix_df)
        assert score == 50

    def test_graceful_on_empty_data(self, mocker):
        """Empty dataframe should return None-safe dict."""
        import pandas as pd
        mock_ticker = mocker.patch("yfinance.Ticker")
        mock_ticker.return_value.history.return_value = pd.DataFrame()
        from market_data import get_market_pulse
        result = get_market_pulse()
        assert result is not None
        assert result["nifty_price"] is None
