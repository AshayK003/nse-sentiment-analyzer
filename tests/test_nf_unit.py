"""Unit tests for _nf() — NaN-safe float extractor (Issue #20).

_nf() is used across the rendering pipeline to convert yfinance values
to floats while safely handling None and NaN. Regression 1 of the v2.6.0
ETF crash (₹nan display) traced back to NaN slipping through this path.
"""
import math

import pytest

from data_fetcher import _nf


class TestNf:
    def test_none_returns_none(self):
        assert _nf(None) is None

    def test_nan_returns_none(self):
        assert _nf(float("nan")) is None

    def test_nan_float_from_string_returns_none(self):
        assert _nf("nan") is None

    def test_positive_number_passes_through(self):
        assert _nf(100.0) == 100.0

    def test_zero_is_preserved(self):
        # 0 is falsy — callers must not use `or` on _nf output.
        assert _nf(0) == 0

    def test_negative_number_preserved(self):
        assert _nf(-12.5) == -12.5

    def test_int_coerced_to_float(self):
        result = _nf(7)
        assert isinstance(result, float)
        assert result == 7.0

    def test_numeric_string_coerced(self):
        assert _nf("42.5") == 42.5

    def test_infinity_is_not_nan_so_passthrough(self):
        # inf is a valid float, only NaN is filtered
        assert _nf(float("inf")) == float("inf")

    def test_bool_rejected_by_float_semantics(self):
        # bools are ints in Python; float(True) == 1.0. Document behavior.
        assert _nf(True) == 1.0

    @pytest.mark.parametrize(
        "bad", ["abc", "", [], {}, object()]
    )
    def test_unconvertible_raises_typeerror_or_valueerror(self, bad):
        with pytest.raises((TypeError, ValueError)):
            _nf(bad)

    def test_very_small_value_precision_kept(self):
        assert _nf(1e-9) == 1e-9
