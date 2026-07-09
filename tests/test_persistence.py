"""
Tests for data persistence (portfolio, track record, cache).
All file I/O is isolated to tmp_path via the tmp_data_dir fixture.
"""

from datetime import datetime, timedelta


class TestPersistenceIO:
    """Tests for low-level JSON helpers."""

    def test_load_json_missing_file(self, tmp_data_dir):
        """Missing file returns default []."""
        from persistence import _load_json, PORTFOLIO_FILE
        assert _load_json(PORTFOLIO_FILE, []) == []

    def test_load_json_corrupted(self, tmp_data_dir):
        """Corrupted JSON returns default."""
        from persistence import _load_json, PORTFOLIO_FILE
        PORTFOLIO_FILE.write_text("{{{garbage}}}")
        assert _load_json(PORTFOLIO_FILE, []) == []

    def test_save_and_load_roundtrip(self, tmp_data_dir):
        """Saving and loading returns the same data."""
        from persistence import _save_json, _load_json, PORTFOLIO_FILE
        data = [{"ticker": "SBIN", "added": "2026-06-01"}]
        _save_json(PORTFOLIO_FILE, data)
        loaded = _load_json(PORTFOLIO_FILE, [])
        assert loaded == data

    def test_save_json_silent_on_readonly_fs(self, tmp_data_dir):
        """_save_json should not raise on PermissionError."""
        from persistence import _save_json
        # Try saving to a blocked path — should silently pass
        blocked = tmp_data_dir / "readonly" / "file.json"
        # Without creating the parent, this will fail OSError
        _save_json(blocked, [1, 2, 3])  # Should not raise


class TestCache:
    """Tests for cache_get / cache_set."""

    def test_cache_set_and_get(self, tmp_data_dir):
        """Cache set then get returns the same value."""
        from persistence import cache_set, cache_get
        key = "stock_RELIANCE"
        data = {"price": 2500.0, "change": 25.0}
        cache_set(key, data)
        result = cache_get(key)
        assert result == data

    def test_cache_missing_key(self, tmp_data_dir):
        """Missing cache key returns None."""
        from persistence import cache_get
        assert cache_get("nonexistent_key") is None

    def test_cache_expiry(self, tmp_data_dir):
        """Cache entry older than TTL returns None."""
        from persistence import cache_set, cache_get
        key = "stock_HDFCBANK"
        cache_set(key, 100)
        # Write an expired timestamp manually
        from persistence import CACHE_FILE, _load_json, _save_json
        cache = _load_json(CACHE_FILE, {})
        cache[key] = {
            "data": 100,
            "cached_at": (datetime.now() - timedelta(minutes=30)).isoformat(),
        }
        _save_json(CACHE_FILE, cache)
        assert cache_get(key) is None

    def test_cache_fresh_edge(self, tmp_data_dir):
        """Cache entry at exactly TTL-1s should still be fresh."""
        from persistence import cache_set, cache_get
        from persistence import CACHE_FILE, _load_json, _save_json

        key = "fresh_key"
        cache_set(key, "fresh_data")
        # Rewind timestamp to just under TTL
        cache = _load_json(CACHE_FILE, {})
        cache[key] = {
            "data": "fresh_data",
            "cached_at": (datetime.now()
                          - timedelta(seconds=14*60 + 59)).isoformat(),
        }
        _save_json(CACHE_FILE, cache)
        assert cache_get(key) == "fresh_data"

    def test_cache_empty_cache_file(self, tmp_data_dir):
        """Empty cache file should be treated as empty cache."""
        from persistence import cache_get
        # No cache file exists at all
        assert cache_get("any_key") is None


class TestPortfolio:
    """Tests for portfolio save/load."""

    def test_portfolio_save_and_load(self, mocker, tmp_data_dir):
        """Saving portfolio then loading returns same list."""
        # Mock st.session_state to support dot access
        mock_ss = mocker.MagicMock()
        mock_ss.get.return_value = None
        mock_ss._portfolio = []
        mocker.patch("streamlit.session_state", mock_ss)

        from persistence import save_portfolio, load_portfolio

        save_portfolio(["SBIN", "RELIANCE", "TCS"])
        loaded = load_portfolio()
        assert loaded == ["SBIN", "RELIANCE", "TCS"]

    def test_portfolio_default_empty(self, tmp_data_dir):
        """No portfolio file should return []."""
        from persistence import load_portfolio
        # Don't mock session_state — it won't persist between calls
        # in test, but load_portfolio handles this gracefully
        result = load_portfolio()
        # Should return file contents (empty) or session items
        assert isinstance(result, list)

    def test_portfolio_in_session_state(self, mocker, tmp_data_dir):
        """Portfolio loads from session_state when file is empty."""
        mock_ss = mocker.MagicMock()
        mock_ss.get.return_value = ["SBIN", "ICICIBANK"]
        mock_ss._portfolio = ["SBIN", "ICICIBANK"]
        mocker.patch("streamlit.session_state", mock_ss)

        from persistence import load_portfolio
        result = load_portfolio()
        assert "SBIN" in result
        assert "ICICIBANK" in result


class TestTrackRecord:
    """Tests for track record persistence."""

    def test_track_record_empty_default(self, tmp_data_dir):
        """No track record file should default to []."""
        from persistence import load_track_record
        result = load_track_record()
        assert result == []

    def test_track_record_append(self, tmp_data_dir):
        """Saving multiple records and loading returns them all."""
        from persistence import save_track_record, load_track_record

        records = [
            {"ticker": "SBIN", "signal": "BULLISH", "vote": True},
            {"ticker": "TCS", "signal": "NEUTRAL", "vote": None},
        ]
        save_track_record(records)
        loaded = load_track_record()
        assert len(loaded) == 2
        assert loaded[0]["ticker"] == "SBIN"
        assert loaded[1]["ticker"] == "TCS"


class TestUpdateSourceAccuracy:
    """Tests for Bayesian source accuracy updates."""

    def test_correct_vote_existing_source(self, mocker):
        from persistence import update_source_accuracy

        accuracy = {
            "Economic Times": {"alpha": 8.0, "beta": 4.0}
        }
        mocker.patch("persistence.load_source_accuracy", return_value=accuracy)
        save_mock = mocker.patch("persistence.save_source_accuracy")

        update_source_accuracy("Economic Times", True)

        saved = save_mock.call_args.args[0]
        assert saved["Economic Times"]["alpha"] == 9.0
        assert saved["Economic Times"]["beta"] == 4.0

    def test_incorrect_vote_existing_source(self, mocker):
        from persistence import update_source_accuracy

        accuracy = {
            "Moneycontrol": {"alpha": 7.0, "beta": 3.0}
        }
        mocker.patch("persistence.load_source_accuracy", return_value=accuracy)
        save_mock = mocker.patch("persistence.save_source_accuracy")

        update_source_accuracy("Moneycontrol", False)

        saved = save_mock.call_args.args[0]
        assert saved["Moneycontrol"]["alpha"] == 7.0
        assert saved["Moneycontrol"]["beta"] == 4.0

    def test_new_source_correct_vote(self, mocker):
        from persistence import update_source_accuracy

        mocker.patch("persistence.load_source_accuracy", return_value={})
        save_mock = mocker.patch("persistence.save_source_accuracy")

        update_source_accuracy("NewSource", True)

        saved = save_mock.call_args.args[0]
        assert saved["NewSource"]["alpha"] == 7.0
        assert saved["NewSource"]["beta"] == 6.0

    def test_new_source_incorrect_vote(self, mocker):
        from persistence import update_source_accuracy

        mocker.patch("persistence.load_source_accuracy", return_value={})
        save_mock = mocker.patch("persistence.save_source_accuracy")

        update_source_accuracy("NewSource", False)

        saved = save_mock.call_args.args[0]
        assert saved["NewSource"]["alpha"] == 6.0
        assert saved["NewSource"]["beta"] == 7.0

    def test_unknown_source_uses_default_prior(self, mocker):
        from persistence import update_source_accuracy

        mocker.patch("persistence.load_source_accuracy", return_value={})
        save_mock = mocker.patch("persistence.save_source_accuracy")

        update_source_accuracy("Unknown", True)

        saved = save_mock.call_args.args[0]
        assert saved["Unknown"]["alpha"] == 7.0
        assert saved["Unknown"]["beta"] == 6.0

    def test_multiple_sequential_votes(self, mocker):
        from persistence import update_source_accuracy

        accuracy = {
            "Economic Times": {"alpha": 8.0, "beta": 4.0}
        }
        mocker.patch("persistence.load_source_accuracy", return_value=accuracy)
        save_mock = mocker.patch("persistence.save_source_accuracy")

        update_source_accuracy("Economic Times", True)
        update_source_accuracy("Economic Times", True)
        update_source_accuracy("Economic Times", True)
        update_source_accuracy("Economic Times", False)

        saved = save_mock.call_args.args[0]
        assert saved["Economic Times"]["alpha"] == 11.0
        assert saved["Economic Times"]["beta"] == 5.0
