"""
Tests for event classifier — pattern matching and VADER adjustment.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from event_classifier import adjust_with_event, classify_headline


class TestClassifyHeadline:
    """Tests for headline event classification."""

    def test_order_win_wins_contract(self):
        event, base = classify_headline("TCS wins $2B contract from US client", "")
        assert event == "ORDER_WIN"
        assert base > 0

    def test_order_win_bags(self):
        event, base = classify_headline("L&T bags Rs 500Cr order from railways", "")
        assert event == "ORDER_WIN"
        assert base > 0

    def test_order_win_secured(self):
        event, base = classify_headline("Company secures multi-year deal with Govt", "")
        assert event == "ORDER_WIN"
        assert base > 0

    def test_dividend_declared(self):
        event, base = classify_headline("Company declares 200% dividend", "")
        assert event == "BUYBACK_DIVIDEND"
        assert base > 0

    def test_dividend_announced(self):
        event, base = classify_headline("HDFCBANK announces interim dividend", "")
        assert event == "BUYBACK_DIVIDEND"
        assert base > 0

    def test_buyback_announced(self):
        event, base = classify_headline("Board approves Rs 1000Cr buyback", "")
        assert event == "BUYBACK_DIVIDEND"
        assert base > 0

    def test_bonus_issue(self):
        event, base = classify_headline("Company announces 1:1 bonus issue", "")
        assert event == "BUYBACK_DIVIDEND"
        assert base > 0

    def test_earnings_beat_profit_jumps(self):
        event, base = classify_headline("HDFCBANK profit jumps 20% in Q1", "")
        assert event == "EARNINGS_BEAT"
        assert base > 0

    def test_earnings_miss_profit_falls(self):
        event, base = classify_headline("TCS profit falls 5% amid slowdown", "")
        assert event == "EARNINGS_MISS"
        assert base < 0

    def test_litigation_sebi_penalty(self):
        event, base = classify_headline("SEBI imposes Rs 5Cr penalty on company", "")
        assert event == "LITIGATION"
        assert base < 0

    def test_litigation_cbi_raid(self):
        event, base = classify_headline("CBI raids premises of company officials", "")
        assert event == "LITIGATION"
        assert base < 0

    def test_regulatory_rbi_action(self):
        event, base = classify_headline("RBI restricts lending activities of bank", "")
        assert event == "REGULATORY"
        assert base < 0

    def test_guidance_raised(self):
        """Even with 'strong quarter' in the text, 'raises guidance' should match first."""
        event, base = classify_headline(
            "Company raises FY26 guidance after strong quarter", ""
        )
        assert event == "GUIDANCE_POSITIVE"
        assert base > 0

    def test_guidance_cut_with_intervening_words(self):
        event, base = classify_headline(
            "Company cuts revenue outlook amid headwinds", ""
        )
        assert event == "GUIDANCE_NEGATIVE"
        assert base < 0

    def test_downgrade_credit_rating(self):
        """'downgrades credit rating' should match DEBT_STRESS not GUIDANCE_NEGATIVE."""
        event, base = classify_headline(
            "Moody's downgrades credit rating of company", ""
        )
        assert event == "DEBT_STRESS"
        assert base < 0

    def test_resignation(self):
        event, base = classify_headline("CFO resigns citing personal reasons", "")
        assert event == "MGMT_CHANGE_NEGATIVE"
        assert base < 0

    def test_neutral_headline_no_event(self):
        event, base = classify_headline("Company to hold board meeting on March 15", "")
        assert event is None
        assert base == 0.0

    def test_empty_headline(self):
        event, base = classify_headline("", "")
        assert event is None
        assert base == 0.0

    def test_product_launch(self):
        event, base = classify_headline(
            "Company launches new electric vehicle platform", ""
        )
        assert event == "PRODUCT_LAUNCH"
        assert base > 0

    def test_expansion_new_plant(self):
        event, base = classify_headline(
            "Company invests Rs 200Cr in new plant at Gujarat", ""
        )
        assert event == "EXPANSION"
        assert base > 0

    def test_debt_stress_npa(self):
        event, base = classify_headline("Bank reports rise in NPAs during Q3", "")
        assert event == "DEBT_STRESS"
        assert base < 0

    def test_management_appointment(self):
        event, base = classify_headline(
            "Company appoints new CEO to lead expansion", ""
        )
        assert event == "MANAGEMENT_POSITIVE"
        assert base > 0

    def test_earnings_beat_record_profit(self):
        event, base = classify_headline("Company reports record quarterly profit", "")
        assert event == "EARNINGS_BEAT"
        assert base > 0

    def test_mgmt_change_ousted(self):
        event, base = classify_headline("Board ousts chairman after governance issues", "")
        assert event == "MGMT_CHANGE_NEGATIVE"
        assert base < 0

    def test_sue_litigation(self):
        """'sued' with word boundary should not match inside 'issue'."""
        event_sued, base_sued = classify_headline(
            "Company sued over patent infringement", ""
        )
        assert event_sued == "LITIGATION"

        event_issue, base_issue = classify_headline(
            "Company announces bonus issue", ""
        )
        assert event_issue == "BUYBACK_DIVIDEND"  # Not LITIGATION


class TestAdjustWithEvent:
    """Tests for VADER + event blending."""

    def test_no_event_no_change(self):
        assert adjust_with_event(0.5, 0.0) == 0.5
        assert adjust_with_event(-0.3, 0.0) == -0.3

    def test_confident_vader_mostly_kept(self):
        """VADER confident (0.8) with positive event → 0.8*0.8 + 0.2*0.35 = 0.71"""
        result = adjust_with_event(0.8, 0.35)
        assert 0.65 < result < 0.8  # Mostly VADER, slight event boost

    def test_uncertain_vader_event_dominates(self):
        """VADER uncertain (0.0) with strong negative event → mostly event"""
        result = adjust_with_event(0.0, -0.35)
        assert -0.3 < result < -0.15  # Mostly event-driven

    def test_uncertain_neutral_event_unchanged(self):
        """No event → no change even when VADER is uncertain"""
        assert adjust_with_event(0.0, 0.0) == 0.0

    def test_clamped_to_range(self):
        """Result stays within [-1, 1]."""
        result = adjust_with_event(0.9, 0.4)
        assert -1.0 <= result <= 1.0

    def test_negative_event_reverses_uncertain_vader(self):
        """VADER slightly positive but uncertain, event strongly negative."""
        result = adjust_with_event(0.15, -0.4)
        # 0.3 * 0.15 + 0.7 * (-0.4) = 0.045 - 0.28 = -0.235
        assert result < 0
