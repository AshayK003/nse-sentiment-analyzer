"""Tests for entry price persistence and portfolio news matching."""

import pytest


class TestEntryPrices:
    """Tests for save_entry_price() and load_entry_prices()."""

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        from persistence import save_entry_price, load_entry_prices
        from pathlib import Path

        # Redirect data dir to tmp_path
        monkeypatch.setattr("persistence.DATA_DIR", tmp_path)
        monkeypatch.setattr("persistence.ENTRY_PRICES_FILE", tmp_path / "entry_prices.json")

        save_entry_price("RELIANCE", 2850.50)
        prices = load_entry_prices()

        assert prices["RELIANCE"] == 2850.50

    def test_load_empty_returns_empty_dict(self, tmp_path, monkeypatch):
        from persistence import load_entry_prices
        from pathlib import Path

        monkeypatch.setattr("persistence.DATA_DIR", tmp_path)
        monkeypatch.setattr("persistence.ENTRY_PRICES_FILE", tmp_path / "entry_prices.json")

        prices = load_entry_prices()

        assert prices == {}

    def test_update_existing_entry(self, tmp_path, monkeypatch):
        from persistence import save_entry_price, load_entry_prices
        from pathlib import Path

        monkeypatch.setattr("persistence.DATA_DIR", tmp_path)
        monkeypatch.setattr("persistence.ENTRY_PRICES_FILE", tmp_path / "entry_prices.json")

        save_entry_price("RELIANCE", 2850.50)
        save_entry_price("RELIANCE", 2900.00)
        prices = load_entry_prices()

        assert prices["RELIANCE"] == 2900.00

    def test_calc_portfolio_pnl(self):
        from persistence import calc_portfolio_pnl

        result = calc_portfolio_pnl(2850.50, 3277.00, 12)

        assert result["pnl_abs"] == pytest.approx(5118.0, rel=0.1)
        assert "pnl_pct" in result

    def test_calc_portfolio_pnl_negative(self):
        from persistence import calc_portfolio_pnl

        result = calc_portfolio_pnl(512.0, 454.0, 14)

        assert result["pnl_abs"] < 0
        assert result["pnl_pct"] < 0

    def test_calc_portfolio_pnl_none_price(self):
        from persistence import calc_portfolio_pnl

        result = calc_portfolio_pnl(100.0, None, 10)

        assert result["pnl_pct"] == 0.0
        assert result["pnl_abs"] == 0.0
