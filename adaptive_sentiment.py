"""
Adaptive Sentiment Engine for NSE Sentiment Analyzer.

Two P0 innovations from recent arXiv research:

1. Adaptive TF-IDF Cluster Learner (arXiv:2606.03457 - Hybrid News Sentiment Engine)
   - Groups headlines into semantic neighborhoods via TF-IDF
   - Tracks realized average price reaction per cluster
   - Auto-adapts as market regimes shift (no retraining)
   - Calibrates ensemble weights against ground-truth price moves

2. News Dissemination Breadth Clustering (arXiv:2412.10823 - FinGPT)
   - Clusters related news articles by content similarity
   - Cluster size = dissemination breadth = market impact proxy
   - Large clusters = high-impact events

Both run on CPU, zero GPU, sub-second latency. Pure Python + scikit-learn.
"""

import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import DBSCAN

from persistence import DATA_DIR

logger = logging.getLogger(__name__)

# ─── Config ───
ADAPTIVE_CACHE_FILE = DATA_DIR / "adaptive_clusters.json"
CLUSTER_MIN_SAMPLES = 2  # DBSCAN min_samples
CLUSTER_EPS = 0.65  # TF-IDF cosine distance threshold
MAX_CLUSTERS = 50  # prevent unbounded growth
CALIBRATION_WINDOW_HOURS = 72  # recalibrate every 3 days
MIN_CLUSTER_SIZE_FOR_CALIBRATION = 3
DISSEMINATION_MIN_CLUSTER_SIZE = 2
DISSEMINATION_MAX_CLUSTERS = 20

# Thread safety
_adaptive_lock = threading.RLock()
_dissemination_lock = threading.RLock()


# ─── Helper: JSON-safe serialization ───
def _serialize_cluster(cluster: dict) -> dict:
    """Convert numpy types to JSON-serializable."""
    out = {}
    for k, v in cluster.items():
        if isinstance(v, (np.integer, np.floating)):
            out[k] = float(v)
        elif isinstance(v, np.ndarray):
            out[k] = v.tolist()
        elif isinstance(v, (list, dict, str, int, float, type(None))):
            out[k] = v
        else:
            out[k] = str(v)
    return out


def _deserialize_cluster(data: dict) -> dict:
    """Convert JSON back to working cluster dict."""
    return data  # Already JSON-serializable types


# ─── Adaptive TF-IDF Cluster Learner ───
class AdaptiveClusterLearner:
    """
    Learns sentiment from price reactions, not labels.

    Algorithm:
    1. On new headline + subsequent price move: vectorize headline, assign to cluster
    2. Each cluster tracks: centroid, headlines[], price_reactions[], count
    3. Prediction: find nearest cluster, return its average price reaction
    4. Calibration: every 72h, recompute cluster weights by correlation with actual moves
    """

    def __init__(self):
        self.clusters: dict[int, dict] = {}  # cluster_id -> {centroid, headlines, reactions, weight}
        self.vectorizer = TfidfVectorizer(
            max_features=500,
            ngram_range=(1, 2),
            stop_words="english",
            min_df=1,
            max_df=0.95,
        )
        self._fitted = False
        self._last_calibration = 0.0
        self._load()

    def _load(self):
        """Load clusters from disk."""
        try:
            if ADAPTIVE_CACHE_FILE.exists():
                with open(ADAPTIVE_CACHE_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                    self.clusters = {int(k): _deserialize_cluster(v) for k, v in data.get("clusters", {}).items()}
                    self._last_calibration = data.get("last_calibration", 0.0)
                    if self.clusters:
                        # Re-fit vectorizer on all stored headlines
                        all_headlines = []
                        for c in self.clusters.values():
                            all_headlines.extend(c.get("headlines", []))
                        if all_headlines:
                            self.vectorizer.fit(all_headlines)
                            self._fitted = True
                logger.info(f"Loaded {len(self.clusters)} adaptive clusters from disk")
        except Exception as e:
            logger.warning(f"Failed to load adaptive clusters: {e}")
            self.clusters = {}

    def _save(self):
        """Persist clusters to disk."""
        try:
            with _adaptive_lock:
                data = {
                    "clusters": {str(k): _serialize_cluster(v) for k, v in self.clusters.items()},
                    "last_calibration": self._last_calibration,
                    "saved_at": datetime.now().isoformat(),
                }
                with open(ADAPTIVE_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save adaptive clusters: {e}")

    def _get_next_cluster_id(self) -> int:
        return max(self.clusters.keys(), default=-1) + 1

    def _vectorize(self, text: str) -> np.ndarray:
        """Vectorize a single headline."""
        if not self._fitted:
            self.vectorizer.fit([text])
            self._fitted = True
        return self.vectorizer.transform([text]).toarray()[0]

    def _cosine_sim(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors."""
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def _find_or_create_cluster(self, headline: str, price_move_1h: float = 0.0, price_move_4h: float = 0.0) -> int:
        """Assign headline to nearest cluster or create new one."""
        vec = self._vectorize(headline)

        # Find nearest cluster
        best_id = None
        best_sim = 0.0
        for cid, cluster in self.clusters.items():
            if "centroid" in cluster:
                sim = self._cosine_sim(vec, np.array(cluster["centroid"]))
                if sim > best_sim and sim >= (1 - CLUSTER_EPS):
                    best_sim = sim
                    best_id = cid

        if best_id is not None:
            # Update existing cluster
            cluster = self.clusters[best_id]
            cluster["headlines"].append(headline)
            if price_move_1h != 0.0 or price_move_4h != 0.0:
                cluster["reactions_1h"].append(price_move_1h)
                cluster["reactions_4h"].append(price_move_4h)
            # Recompute centroid (incremental mean)
            n = len(cluster["headlines"])
            old_centroid = np.array(cluster["centroid"])
            cluster["centroid"] = ((n - 1) * old_centroid + vec) / n
            cluster["count"] = n
            return best_id
        else:
            # Create new cluster
            if len(self.clusters) >= MAX_CLUSTERS:
                # Evict least useful cluster (lowest weight * count)
                evict_id = min(self.clusters.keys(), key=lambda k: self.clusters[k].get("weight", 0.5) * self.clusters[k].get("count", 1))
                del self.clusters[evict_id]

            cid = self._get_next_cluster_id()
            self.clusters[cid] = {
                "centroid": vec.tolist(),
                "headlines": [headline],
                "reactions_1h": [price_move_1h] if price_move_1h != 0.0 else [],
                "reactions_4h": [price_move_4h] if price_move_4h != 0.0 else [],
                "count": 1,
                "weight": 0.5,  # neutral prior
            }
            return cid

    def update(self, headline: str, price_move_1h: float = 0.0, price_move_4h: float = 0.0):
        """Feed a headline + observed price reaction into the learner."""
        with _adaptive_lock:
            self._find_or_create_cluster(headline, price_move_1h, price_move_4h)
            self._save()

    def predict(self, headline: str) -> float:
        """Return expected price move (1h horizon) for a headline."""
        with _adaptive_lock:
            if not self.clusters or not self._fitted:
                return 0.0

            vec = self._vectorize(headline)
            best_weight = 0.0
            best_reaction = 0.0

            for cluster in self.clusters.values():
                if "centroid" not in cluster or not cluster["reactions_1h"]:
                    continue
                sim = self._cosine_sim(vec, np.array(cluster["centroid"]))
                weight = cluster.get("weight", 0.5) * sim
                if weight > best_weight:
                    best_weight = weight
                    best_reaction = float(np.mean(cluster["reactions_1h"]))

            return best_reaction

    def predict_4h(self, headline: str) -> float:
        """Return expected price move (4h horizon) for a headline."""
        with _adaptive_lock:
            if not self.clusters or not self._fitted:
                return 0.0

            vec = self._vectorize(headline)
            best_weight = 0.0
            best_reaction = 0.0

            for cluster in self.clusters.values():
                if "centroid" not in cluster or not cluster["reactions_4h"]:
                    continue
                sim = self._cosine_sim(vec, np.array(cluster["centroid"]))
                weight = cluster.get("weight", 0.5) * sim
                if weight > best_weight:
                    best_weight = weight
                    best_reaction = float(np.mean(cluster["reactions_4h"]))

            return best_reaction

    def calibrate(self, recent_headlines: list[str], recent_moves_1h: list[float], recent_moves_4h: list[float]):
        """
        Recalibrate cluster weights based on prediction accuracy.
        Called periodically (every 72h) with recent ground-truth data.
        """
        with _adaptive_lock:
            if not self.clusters or len(recent_headlines) < MIN_CLUSTER_SIZE_FOR_CALIBRATION:
                return

            now = time.time()
            if now - self._last_calibration < CALIBRATION_WINDOW_HOURS * 3600:
                return

            # For each cluster, compute correlation between its predictions and actual moves
            for cid, cluster in self.clusters.items():
                if "centroid" not in cluster or not cluster["reactions_1h"]:
                    continue

                predictions = []
                actuals = []
                centroid = np.array(cluster["centroid"])

                for hl, move_1h, move_4h in zip(recent_headlines, recent_moves_1h, recent_moves_4h):
                    vec = self._vectorize(hl)
                    sim = self._cosine_sim(vec, centroid)
                    if sim > 0.3:  # only count if cluster is relevant
                        predictions.append(sim * np.mean(cluster["reactions_1h"]))
                        actuals.append(move_1h)

                if len(predictions) >= 3:
                    corr = np.corrcoef(predictions, actuals)[0, 1]
                    if not np.isnan(corr):
                        # Weight = max(0, correlation)^2 — only positive predictive power counts
                        cluster["weight"] = float(max(0.0, corr) ** 2)

            self._last_calibration = now
            self._save()
            logger.info(f"Adaptive calibration complete: {len(self.clusters)} clusters weighted")


# ─── News Dissemination Breadth Clustering ───
class DisseminationClusterer:
    """
    Clusters related news articles to measure dissemination breadth.

    Based on FinGPT (arXiv:2412.10823):
    - Cluster articles by content similarity (TF-IDF + DBSCAN)
    - Cluster size = dissemination breadth = market impact proxy
    - Large clusters = high-impact events
    """

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=300,
            ngram_range=(1, 2),
            stop_words="english",
            min_df=1,
        )
        self._fitted = False

    def cluster_articles(self, articles: list[dict]) -> list[dict]:
        """
        Cluster articles by content similarity.

        Args:
            articles: list of {"title": str, "body": str, "source": str, "ticker": str}

        Returns:
            list of clusters, each with:
            - "articles": list of article indices
            - "size": int
            - "dissemination_score": float (0-1, normalized size)
            - "representative": str (centroid article title)
            - "sources": list of unique sources
            - "tickers": list of unique tickers mentioned
        """
        with _dissemination_lock:
            if not articles or len(articles) < DISSEMINATION_MIN_CLUSTER_SIZE:
                return []

            # Build combined text for each article
            texts = []
            for a in articles:
                text = f"{a.get('title', '')}. {a.get('body', '')}"
                texts.append(text)

            # Vectorize
            if not self._fitted:
                self.vectorizer.fit(texts)
                self._fitted = True
            X = self.vectorizer.transform(texts).toarray()

            # DBSCAN clustering
            clustering = DBSCAN(eps=0.7, min_samples=DISSEMINATION_MIN_CLUSTER_SIZE, metric="cosine")
            labels = clustering.fit_predict(X)

            # Build cluster summaries
            clusters = defaultdict(list)
            for idx, label in enumerate(labels):
                if label >= 0:  # -1 = noise
                    clusters[label].append(idx)

            results = []
            max_size = max((len(v) for v in clusters.values()), default=1)

            for label, indices in clusters.items():
                if len(indices) < DISSEMINATION_MIN_CLUSTER_SIZE:
                    continue

                # Representative = article closest to centroid
                cluster_vecs = X[indices]
                centroid = cluster_vecs.mean(axis=0)
                dists = np.linalg.norm(cluster_vecs - centroid, axis=1)
                rep_idx = indices[int(np.argmin(dists))]

                sources = list({articles[i].get("source", "Unknown") for i in indices})
                tickers = list({articles[i].get("ticker", "") for i in indices if articles[i].get("ticker")})

                results.append({
                    "articles": indices,
                    "size": len(indices),
                    "dissemination_score": min(len(indices) / max(10, max_size), 1.0),
                    "representative": articles[rep_idx].get("title", "")[:120],
                    "sources": sources,
                    "tickers": tickers,
                })

            # Sort by dissemination score (largest first)
            results.sort(key=lambda c: c["dissemination_score"], reverse=True)
            return results[:DISSEMINATION_MAX_CLUSTERS]


# ─── Singleton instances ───
_adaptive_learner: AdaptiveClusterLearner | None = None
_dissemination_clusterer: DisseminationClusterer | None = None


def get_adaptive_learner() -> AdaptiveClusterLearner:
    global _adaptive_learner
    if _adaptive_learner is None:
        _adaptive_learner = AdaptiveClusterLearner()
    return _adaptive_learner


def get_dissemination_clusterer() -> DisseminationClusterer:
    global _dissemination_clusterer
    if _dissemination_clusterer is None:
        _dissemination_clusterer = DisseminationClusterer()
    return _dissemination_clusterer


# ─── Public API ───
def learn_from_price_reaction(headline: str, price_move_1h: float, price_move_4h: float):
    """Feed a headline + observed price moves into the adaptive learner."""
    get_adaptive_learner().update(headline, price_move_1h, price_move_4h)


def predict_price_reaction(headline: str, horizon: str = "1h") -> float:
    """Predict expected price move for a headline."""
    learner = get_adaptive_learner()
    if horizon == "4h":
        return learner.predict_4h(headline)
    return learner.predict(headline)


def compute_dissemination_score(articles: list[dict]) -> float:
    """
    Compute overall dissemination breadth score for a set of articles.

    Returns 0-1 score where:
    - 0 = single isolated article
    - 1 = many articles from multiple sources covering same event
    """
    clusters = get_dissemination_clusterer().cluster_articles(articles)
    if not clusters:
        return 0.0

    # Weighted by cluster size and source diversity
    total_score = 0.0
    for c in clusters:
        source_diversity = min(len(c["sources"]) / 5.0, 1.0)  # max 5 sources
        total_score += c["dissemination_score"] * (0.7 + 0.3 * source_diversity)

    return min(total_score / len(clusters), 1.0)


def get_dissemination_clusters(articles: list[dict]) -> list[dict]:
    """Get detailed dissemination clusters for dashboard display."""
    return get_dissemination_clusterer().cluster_articles(articles)


def calibrate_adaptive_learner(recent_headlines: list[str], recent_moves_1h: list[float], recent_moves_4h: list[float]):
    """Trigger calibration of adaptive learner weights."""
    get_adaptive_learner().calibrate(recent_headlines, recent_moves_1h, recent_moves_4h)


# ─── Integration helpers for data_fetcher.py ───
def extract_price_moves_for_learning(ticker: str, headline_time: datetime, hist_1h: list, hist_4h: list) -> tuple[float, float]:
    """
    Given a headline timestamp and recent price history, compute the 1h and 4h
    forward returns for learning. Returns (move_1h, move_4h) as percentages.
    """
    if not hist_1h or not hist_4h:
        return 0.0, 0.0

    # Find price at headline time (approximate - use nearest)
    headline_ts = headline_time.timestamp() * 1000  # ms

    price_at_headline = None
    for bar in hist_1h:
        bar_ts = bar.get("time", 0)
        if isinstance(bar_ts, str):
            try:
                bar_ts = datetime.fromisoformat(bar_ts).timestamp() * 1000
            except Exception:
                continue
        if bar_ts <= headline_ts:
            price_at_headline = bar["close"]
        else:
            break

    if price_at_headline is None:
        price_at_headline = hist_1h[0]["close"]

    # 1h forward: find bar ~1h after
    move_1h = 0.0
    target_ts_1h = headline_ts + 3600 * 1000
    for bar in hist_1h:
        bar_ts = bar.get("time", 0)
        if isinstance(bar_ts, str):
            try:
                bar_ts = datetime.fromisoformat(bar_ts).timestamp() * 1000
            except Exception:
                continue
        if bar_ts >= target_ts_1h:
            move_1h = ((bar["close"] - price_at_headline) / price_at_headline) * 100
            break

    # 4h forward
    move_4h = 0.0
    target_ts_4h = headline_ts + 4 * 3600 * 1000
    for bar in hist_4h:
        bar_ts = bar.get("time", 0)
        if isinstance(bar_ts, str):
            try:
                bar_ts = datetime.fromisoformat(bar_ts).timestamp() * 1000
            except Exception:
                continue
        if bar_ts >= target_ts_4h:
            move_4h = ((bar["close"] - price_at_headline) / price_at_headline) * 100
            break

    return move_1h, move_4h