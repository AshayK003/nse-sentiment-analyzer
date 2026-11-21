"""
Regression tests for the 2026-11-20 audit remediation (v2.15.2).

Covers: phrase-level sentiment overrides (#34), atomic persistence with
corrupt-file quarantine, real network timeouts (RSS + DuckDuckGo), early
return on invalid tickers, zero-division guards, and import weight (no
sklearn at module load).

All external I/O is mocked or isolated to tmp_path. Subprocess tests run
with a clean PYTHONPATH to avoid environment contamination.
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = Path(__file__).resolve().parent.parent


class TestTickerResolution:
    def test_malformed_symbol_does_not_trigger_online_lookup(self, mocker):
        from data_fetcher import resolve_ticker

        online = mocker.patch("data_fetcher._search_ticker_online")
        assert resolve_ticker("ZZZZ-INVALID") == (None, None)
        online.assert_not_called()


# ─── F1: phrase-level sentiment (issue #34) ───


class TestPhraseSentiment:
    """'profit booking' is bearish in Indian markets despite the bullish
    'profit' token. VADER ignores multi-word lexicon keys, so the fix must
    be a phrase-level override at the scoring chokepoint."""

    @classmethod
    def setup_class(cls):
        from sentiment import get_sia

        cls.sia = get_sia()

    def _score(self, title):
        from sentiment import analyze_headline_sentiment

        return analyze_headline_sentiment(title, "", self.sia)

    def test_profit_booking_is_bearish(self):
        assert self._score("Profit booking hits IT stocks")["compound"] < 0

    def test_profit_taking_phrases_score_bearish(self):
        for phrase in ("profit booking", "profit taking", "booked profits"):
            assert self._score(phrase)["compound"] < 0, phrase

    def test_plain_profit_headline_remains_bullish(self):
        assert self._score("Company reports strong quarterly profit growth")["compound"] > 0

    def test_strong_profit_booking_is_bearish(self):
        assert self._score("Strong profit booking seen in midcaps")["compound"] < 0

    def test_uppercase_profit_booking_is_bearish(self):
        assert self._score("PROFIT BOOKING DRAGS MARKET")["compound"] < 0

    def test_hyphenated_profit_booking_is_bearish(self):
        assert self._score("Profit-booking drags IT stocks")["compound"] < 0

    def test_profit_taking_phrases_are_bearish(self):
        for phrase in (
            "profit taking",
            "profit-taking",
            "booked profits",
            "booked profit",
        ):
            assert self._score(phrase)["compound"] < 0, phrase

    def test_negated_profit_taking_phrases_keep_raw_vader(self):
        for phrase in (
            "no profit taking",
            "not profit-taking",
            "without booked profits",
        ):
            raw = self.sia.polarity_scores(phrase)["compound"]
            assert self._score(phrase)["compound"] == raw, phrase

    def test_negated_phrase_does_not_mask_an_affirmative_phrase(self):
        headline = "No profit booking today, but profit taking weighed on shares"
        assert self._score(headline)["compound"] < 0

    def test_order_booking_not_penalized(self):
        """'booking' alone must not turn bullish order-win news negative."""
        assert self._score("Company wins order booking")["compound"] > 0

    def test_profit_warning_still_bearish(self):
        assert self._score("Profit warning issued by auto ancillary maker")["compound"] < 0

    def test_negated_phrase_keeps_raw_vader(self):
        """'No profit booking' must not be flipped bearish by the override."""
        text = "No profit booking seen, stock rallies"
        raw = self.sia.polarity_scores(text)["compound"]
        assert self._score(text)["compound"] == raw

    def test_raw_vader_subdict_preserved(self):
        """Provenance: the unadjusted VADER components stay available."""
        text = "Profit booking hits IT stocks"
        result = self._score(text)
        assert result["vader"] == self.sia.polarity_scores(text)


def test_sentiment_analyzer_resource_is_initialized_once(mocker):
    import sentiment

    sentiment.get_sia.clear()
    factory = mocker.patch.object(sentiment, "SentimentIntensityAnalyzer")
    try:
        first = sentiment.get_sia()
        second = sentiment.get_sia()
        assert first is second
        factory.assert_called_once_with()
    finally:
        sentiment.get_sia.clear()


# ─── F5/F9: atomic persistence + quarantine + history pruning ───


def _bad_dump(data, f, **kwargs):
    """Simulate a crash mid-serialization: partial write then failure."""
    f.write('{"broken":')
    raise OSError("disk full")


class TestAtomicPersistence:
    def test_json_crash_midwrite_preserves_original(self, tmp_data_dir, mocker):
        from persistence import PORTFOLIO_FILE, _load_json, _save_json

        good = [{"ticker": "SBIN", "added": "2026-06-01"}]
        _save_json(PORTFOLIO_FILE, good)
        mocker.patch("persistence.json.dump", side_effect=_bad_dump)
        _save_json(PORTFOLIO_FILE, [{"ticker": "TCS"}])  # must not raise
        assert _load_json(PORTFOLIO_FILE, []) == good
        assert not list(tmp_data_dir.glob("*.tmp")), "tmp residue after failed save"

    def test_corrupt_json_quarantined(self, tmp_data_dir):
        from persistence import PORTFOLIO_FILE, _load_json

        PORTFOLIO_FILE.write_text("{{{garbage}}}")
        assert _load_json(PORTFOLIO_FILE, []) == []
        assert not PORTFOLIO_FILE.exists(), "corrupt file must be renamed away"
        quarantined = tmp_data_dir / "portfolio.json.corrupt"
        assert quarantined.exists()
        assert quarantined.read_text() == "{{{garbage}}}"

    def test_corrupt_json_honors_dict_default(self, tmp_data_dir):
        from persistence import TRACK_FILE, _load_json

        TRACK_FILE.write_text("not json")
        assert _load_json(TRACK_FILE, {"fallback": True}) == {"fallback": True}

    def test_successful_save_leaves_no_tmp(self, tmp_data_dir):
        from persistence import PORTFOLIO_FILE, _save_json

        _save_json(PORTFOLIO_FILE, [{"ticker": "SBIN"}])
        assert not list(tmp_data_dir.glob("*.tmp"))

    def test_csv_crash_midwrite_preserves_original(self, tmp_data_dir, mocker):
        import csv

        from persistence import HISTORY_FILE, save_sentiment_history

        with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["date", "ticker", "smartscore"])
            w.writeheader()
            w.writerow({"date": "2026-11-19", "ticker": "SBIN", "smartscore": "60"})
        original = HISTORY_FILE.read_text()
        mocker.patch("persistence.csv.DictWriter", side_effect=OSError("boom"))
        save_sentiment_history("TCS", {"smartscore": 70.0})  # must not raise
        assert HISTORY_FILE.read_text() == original
        assert not list(tmp_data_dir.glob("*.tmp"))

    def test_csv_prunes_rows_older_than_365_days(self, tmp_data_dir):
        import csv
        from datetime import datetime

        from persistence import HISTORY_FILE, save_sentiment_history

        with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["date", "ticker", "smartscore"])
            w.writeheader()
            w.writerow({"date": "2020-01-01", "ticker": "SBIN", "smartscore": "10"})
            w.writerow({"date": "2020-01-02", "ticker": "TCS", "smartscore": "20"})
        save_sentiment_history("INFY", {"smartscore": 55.0})
        with open(HISTORY_FILE, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        dates = {r["date"] for r in rows}
        assert "2020-01-01" not in dates and "2020-01-02" not in dates
        assert datetime.now().strftime("%Y-%m-%d") in dates

    def test_csv_caps_total_rows(self, tmp_data_dir):
        import csv
        from datetime import datetime

        from persistence import HISTORY_FILE, save_sentiment_history

        today = datetime.now().strftime("%Y-%m-%d")
        with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["date", "ticker", "smartscore"])
            w.writeheader()
            for i in range(6000):
                w.writerow({"date": today, "ticker": f"T{i}", "smartscore": "50"})
        save_sentiment_history("NEW", {"smartscore": 55.0})
        with open(HISTORY_FILE, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) <= 5000

    def test_adaptive_cache_crash_preserves_original(self, tmp_path, monkeypatch, mocker):
        import adaptive_sentiment as adaptive

        cache = tmp_path / "adaptive_clusters.json"
        monkeypatch.setattr(adaptive, "ADAPTIVE_CACHE_FILE", cache)
        good = '{"clusters": {}, "last_calibration": 0.0}'
        cache.write_text(good)
        learner = adaptive.AdaptiveClusterLearner()
        mocker.patch("adaptive_sentiment.json.dump", side_effect=_bad_dump)
        learner._save()  # must not raise
        assert cache.read_text() == good
        assert not list(tmp_path.glob("*.tmp"))


# ─── F3/F4: real network timeouts ───


class TestRssTimeout:
    def test_rss_fetch_uses_requests_with_timeout(self, mocker):
        from data_fetcher import _parse_rss_feed

        mock_resp = mocker.MagicMock()
        mock_resp.content = b"<rss></rss>"
        mock_get = mocker.patch("data_fetcher.requests.get", return_value=mock_resp)
        mock_feed = mocker.MagicMock()
        mock_feed.entries = []
        mock_parse = mocker.patch("feedparser.parse", return_value=mock_feed)

        _parse_rss_feed("economic times markets", "https://example.com/rss", "TCS", "Tata Consultancy")

        assert mock_get.called, "RSS must be fetched via requests (feedparser has no timeout support)"
        assert mock_get.call_args.kwargs.get("timeout") == 10
        mock_parse.assert_called_once_with(b"<rss></rss>")

    def test_rss_http_error_degrades_gracefully(self, mocker):
        import requests as req

        from data_fetcher import _parse_rss_feed

        mocker.patch("data_fetcher.requests.get", side_effect=req.Timeout("stalled"))
        relevant, all_items, label = _parse_rss_feed(
            "economic times markets", "https://example.com/rss", "TCS", "Tata Consultancy"
        )
        assert relevant == [] and all_items == []


class TestDdgsTimeout:
    """A hung DuckDuckGo worker must be abandoned at the timeout budget,
    not waited out by the executor's blocking shutdown."""

    def _isolate(self, mocker, timeout=0.3):
        mocker.patch("data_fetcher.cache_get", return_value=None)
        mocker.patch("data_fetcher.cache_set")
        mocker.patch("data_fetcher.TICKER_RSS_FEEDS", [])
        mocker.patch("data_fetcher.INDIA_RSS_FEEDS", {})
        mocker.patch("data_fetcher._DDGS_RATE_LIMITED_UNTIL", 0.0)
        import data_fetcher
        if hasattr(data_fetcher, "_DDGS_TIMEOUT"):
            mocker.patch("data_fetcher._DDGS_TIMEOUT", timeout)

    def test_search_news_abandons_hung_ddgs(self, mocker):
        from data_fetcher import search_news

        self._isolate(mocker)

        def hang(*a, **k):
            threading.Event().wait(4)

        mocker.patch("data_fetcher._ddgs_search", side_effect=hang)
        t0 = time.time()
        articles, _, _, _, _ = search_news("TEST", "Test Co", max_results=5)
        elapsed = time.time() - t0
        assert elapsed < 2.0, f"search_news waited {elapsed:.1f}s for hung DDGS worker"
        assert articles == []

    def test_market_headlines_abandons_hung_ddgs(self, mocker):
        from data_fetcher import fetch_market_headlines

        self._isolate(mocker)
        mocker.patch("data_fetcher.COMMODITY_RSS_FEEDS", {})

        def hang(*a, **k):
            threading.Event().wait(4)

        mocker.patch("data_fetcher._ddgs_commodity_search", side_effect=hang)
        t0 = time.time()
        items = fetch_market_headlines()
        elapsed = time.time() - t0
        assert elapsed < 2.0, f"fetch_market_headlines waited {elapsed:.1f}s for hung DDGS worker"
        assert items == []

    def test_ddgs_success_results_merged(self, mocker):
        from data_fetcher import search_news

        self._isolate(mocker, timeout=5)

        def fake(ticker, company, seen, results, stats, max_results):
            results.append({
                "title": "DDG item", "body": "", "date": "2026-11-20",
                "url": "https://ddg.example/1", "source": "DuckDuckGo",
            })
            stats["DuckDuckGo"] = 1

        mocker.patch("data_fetcher._ddgs_search", side_effect=fake)
        articles, _, stats, _, _ = search_news("TEST", "Test Co", max_results=5)
        assert len(articles) == 1
        assert articles[0]["title"] == "DDG item"
        assert stats.get("DuckDuckGo") == 1

    def test_ddgs_timeout_marks_rate_limited(self, mocker):
        from data_fetcher import search_news

        self._isolate(mocker)
        mark = mocker.patch("data_fetcher._mark_ddgs_rate_limited")

        def hang(*a, **k):
            threading.Event().wait(4)

        mocker.patch("data_fetcher._ddgs_search", side_effect=hang)
        search_news("TEST", "Test Co", max_results=5)
        assert mark.called


# ─── F14: zero-division guard ───


class TestMarketPulseGuard:
    def setup_method(self):
        from market_data import _fetch_ticker, get_market_pulse

        getattr(get_market_pulse, "clear")()
        getattr(_fetch_ticker, "clear")()

    def test_zero_prev_close_does_not_raise(self, mocker):
        import pandas as pd

        from market_data import get_market_pulse

        hist = pd.DataFrame({"Close": [0.0, 100.0]})
        mock_ticker = mocker.MagicMock()
        mock_ticker.history.return_value = hist
        mocker.patch("yfinance.Ticker", return_value=mock_ticker)
        result = get_market_pulse()
        assert result["nifty_price"] == 100.0
        assert result["nifty_change_pct"] is None


# ─── Import weight: no sklearn at module load ───


def _run_clean_python(script):
    env = dict(os.environ, PYTHONPATH="")
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120,
    )


class TestImportWeight:
    """sklearn costs ~3.1s at import and is only used by the (currently
    unwired) adaptive learner. Module import must stay light so a deployed
    app never pays for — or loads — ML machinery during normal use."""

    def test_adaptive_import_does_not_load_sklearn(self):
        proc = _run_clean_python(
            "import adaptive_sentiment, sys; "
            "bad = [m for m in sys.modules if m == 'sklearn' or m.startswith('sklearn.')]; "
            "sys.exit(1 if bad else 0)"
        )
        assert proc.returncode == 0, f"sklearn loaded at import: {proc.stderr[-400:]}"

    def test_data_fetcher_import_does_not_load_sklearn(self):
        proc = _run_clean_python(
            "import data_fetcher, sys; "
            "bad = [m for m in sys.modules if m == 'sklearn' or m.startswith('sklearn.')]; "
            "sys.exit(1 if bad else 0)"
        )
        assert proc.returncode == 0, f"sklearn loaded at import: {proc.stderr[-400:]}"

    def test_dissemination_clustering_works_without_sklearn(self):
        proc = _run_clean_python(
            "import sys, adaptive_sentiment as a; "
            "c = a.DisseminationClusterer(); "
            "arts = ["
            "{'title': 'crude oil prices rise', 'body': 'brent crude up', 'source': 'ET', 'ticker': 'ONGC'}, "
            "{'title': 'crude oil rally continues', 'body': 'brent crude gains', 'source': 'MC', 'ticker': 'ONGC'}]; "
            "cl = c.cluster_articles(arts); "
            "bad = [m for m in sys.modules if m.startswith('sklearn')]; "
            "sys.exit(0 if cl and not bad else 1)"
        )
        assert proc.returncode == 0, f"dissemination needs sklearn or failed: {proc.stderr[-400:]}"

    def test_learner_lazy_loads_sklearn_on_instantiation(self):
        proc = _run_clean_python(
            "import sys, adaptive_sentiment as a; "
            "pre = [m for m in sys.modules if m.startswith('sklearn')]; "
            "learner = a.AdaptiveClusterLearner(); "
            "post = [m for m in sys.modules if m.startswith('sklearn')]; "
            "sys.exit(0 if not pre and post else 1)"
        )
        assert proc.returncode == 0, f"lazy sklearn import broken: {proc.stderr[-400:]}"
