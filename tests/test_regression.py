"""Regression sentinel tests (Issue #27).

Each test guards a specific, previously-fixed bug. If one of these fails,
a known bug has reappeared — do not delete the test, fix the regression.

Bug history:
  1. NaN price propagation — ETF crash v2.6.0 (₹nan displayed)
  2. Duplicate VADER lexicon keys ("growth", "sell") — v2.5.0
  3. Missing _render_pivot_html NameError crash — v2.5.0
"""
import math

from render import _is_valid_num, _render_pivot_html
from sentiment import get_sia


class TestRegressionNaNPrice:
    """Regression 1: `float('nan')` is truthy, so `info.get(x) or fallback`
    passed NaN through and the dashboard rendered ₹nan / nan% for ETFs
    (NIFTYBEES, GOLDBEES). Fixed in v2.6.0 via _is_valid_num()."""

    def test_is_valid_num_rejects_nan(self):
        assert _is_valid_num(float("nan")) is False

    def test_is_valid_num_rejects_none(self):
        assert _is_valid_num(None) is False

    def test_is_valid_num_accepts_positive_number(self):
        assert _is_valid_num(100.0) is True

    def test_is_valid_num_accepts_zero(self):
        assert _is_valid_num(0) is True

    def test_is_valid_num_rejects_string_nan(self):
        assert _is_valid_num("nan") is False


class TestRegressionVaderLexicon:
    """Regression 2: the custom financial lexicon defined "growth" twice
    (1.0 then 0.5); Python keeps the last, so "growth" scored 0.5.
    Same overwrite hit "sell". Fixed in v2.5.x."""

    def test_growth_scores_strongly_positive(self):
        sia = get_sia()
        assert sia.lexicon.get("growth", 0) == 1.0

    def test_sell_is_negative(self):
        sia = get_sia()
        assert sia.lexicon.get("sell", 0) < 0

    def test_growth_compound_positive_in_context(self):
        sia = get_sia()
        score = sia.polarity_scores("Company reports strong growth")
        assert score["compound"] > 0


class TestRegressionPivotRender:
    """Regression 3: rendering crashed with NameError because
    _render_pivot_html() was referenced but missing. Fixed in v2.5.x."""

    def test_pivot_renderer_exists_and_callable(self):
        assert callable(_render_pivot_html)

    def test_pivot_renderer_handles_wellformed_data(self):
        # Keys match the actual contract: pivot / resistance / support
        data = {
            "pivot": 100.0,
            "resistance": 105.0,
            "support": 95.0,
        }
        html = _render_pivot_html(data)
        assert isinstance(html, str)
        assert len(html) > 0
        assert "100.00" in html or "100" in html

    def test_pivot_renderer_survives_empty_data(self):
        # Must not raise on empty/missing pivot data (defensive path).
        html = _render_pivot_html({})
        assert isinstance(html, str)
