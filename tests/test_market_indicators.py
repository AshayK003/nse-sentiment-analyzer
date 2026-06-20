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
