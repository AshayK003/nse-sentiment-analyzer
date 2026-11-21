"""
Tests for custom lexicon entries in sentiment.FINANCIAL_BOOSTERS.

Regression tests for the "profit booking" fix: in Indian market usage,
"profit booking" (and its variants) means investors selling holdings to
realise gains — selling pressure, a bearish signal — so these phrases must
score negative even though "profit" itself is a positive token.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sentiment import get_sia


class TestProfitBookingPhrases:
    @classmethod
    def setup_class(cls):
        cls.sia = get_sia()

    def compound(self, text: str) -> float:
        return self.sia.polarity_scores(text)["compound"]

    def test_profit_booking_is_negative(self):
        assert self.compound("profit booking") < 0

    def test_profit_booking_in_headline_is_negative(self):
        assert self.compound("Sensex falls amid profit booking in banking stocks") < 0

    def test_profit_taking_is_negative(self):
        assert self.compound("profit taking") < 0

    def test_booked_profits_is_negative(self):
        assert self.compound("booked profits") < 0

    def test_plain_profit_stays_positive(self):
        assert self.compound("Company reports strong quarterly profit growth") > 0
