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
from datetime import datetime

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer, TfidfVectorizer

from persistence import DATA_DIR

logger = logging.getLogger(__name__)

# ─── Config ───
ADAPTIVE_CACHE_FILE = DATA_DIR / "adaptive_clusters.json"
CLUSTER_MIN_SAMPLES = 2  # DBSCAN min_samples
CLUSTER_EPS = 0.40  # TF-IDF cosine distance threshold - tighter for better discrimination (beats vs misses)
MAX_CLUSTERS = 50  # prevent unbounded growth
CALIBRATION_WINDOW_HOURS = 72  # recalibrate every 3 days
MIN_CLUSTER_SIZE_FOR_CALIBRATION = 3
DISSEMINATION_MIN_CLUSTER_SIZE = 2
DISSEMINATION_MAX_CLUSTERS = 20

# Indian market specific config
INDIAN_MARKET_HOURS = (9, 15, 30)  # 9:15 AM - 3:30 PM IST
PRE_MARKET_HOURS = (9, 0)  # Pre-market 9:00 AM
POST_MARKET_HOURS = (15, 30)  # Post-market 3:30 PM
MARKET_HOLIDAYS_2024 = [
    "2024-01-26", "2024-03-08", "2024-03-25", "2024-03-29", "2024-04-11",
    "2024-04-17", "2024-05-01", "2024-06-17", "2024-07-17", "2024-08-15",
    "2024-10-02", "2024-11-01", "2024-11-15", "2024-12-25"
]

# Indian market specific financial vocabulary
INDIAN_FINANCIAL_ENTITIES = {
    "sectors": ["banking", "bankingsector", "it", "informationtechnology", "pharma", "pharmaceuticals", "auto", "automobile", "fmcg", "consumergoods", "metals", "metal", "cement", "cementsector", "power", "energy", "realty", "realestate", "telecom", "telecommunications", "media", "entertainment", "capitalgoods", "construction", "infrastructure", "oil", "gas", "oilgas", "chemicals", "chemical", "textiles", "textile", "paper", "sugar", "fertilizers", "fertiliser", "pesticides", "agrochemicals", "specialtychemicals", "specialitychemicals"],
    "commodities": ["crude", "crudeoil", "brent", "wti", "gold", "silver", "copper", "aluminum", "aluminium", "zinc", "lead", "nickel", "naturalgas", "lng", "cng", "coal", "thermalcoal", "sugar", "cotton", "wheat", "rice", "soybean", "soy", "palmoil", "crudepalm", "rubber", "jute"],
    "currencies": ["rupee", "inr", "usd", "dollar", "usdinr", "eurinr", "gbpinr", "jpyinr", "rupeeweakens", "rupeestrengthens"],
    "indices": ["nifty", "nifty50", "banknifty", "sensex", "bse", "nse", "niftyit", "niftyauto", "niftypharma", "niftyfmcg", "niftybank", "niftymetal", "niftypsubank", "niftyprivatebank", "niftyrealty", "niftyenergy", "niftymedia", "niftycommodities", "niftyconsumption", "niftypse", "niftyinfra", "niftyserv"],
    "corporate_actions": ["dividend", "bonus", "split", "buyback", "buybackoffer", "rightsissue", "rights", "ipo", "fpo", "qip", "preferentialallotment", "esop", "stocksplit", "facevaluesplit", "demerger", "merger", "acquisition", "takeover", "openoffer", "delisting"],
    "regulatory": ["sebi", "rbi", "irdai", "pfda", "fda", "usfda", "dcgi", "cdsco", "sebiorder", "sebicircular", "rbicircular", "rbidirection", "rbiorder", "irdaiorder", "irdaicircular"],
    "regulators": ["sebi", "rbi", "irdai", "pfda", "fda", "usfda", "dcgi", "cdsco", "cbia", "nclt", "nclat", "sat", "satorder"],
    "ratings": ["upgrade", "downgrade", "upgrade", "downgrade", "outlook", "positive", "negative", "stable", "creditrating", "ratingupgrade", "ratingdowngrade", "outlookpositive", "outlooknegative", "outlookstable"],
    "financial_metrics": ["eps", "epsgrowth", "pe", "pb", "roe", "roce", "roic", "debt", "debttoequity", "currentratio", "quickratio", "interestcoverage", "operatingmargin", "netmargin", "revenuegrowth", "profitgrowth", "epsgrowth", "bookvalue", "dividendyield", "payout", "fcf", "freecashflow", "roa", "roic"],
    "corporate_keywords": ["beats", "misses", "beats", "misses", "beats", "misses", "surges", "plunges", "surges", "plunges", "rises", "falls", "surges", "plunges", "jumps", "drops", "rallies", "corrects", "surges", "plunges", "gains", "loses", "advances", "declines", "rallies", "corrects"],
}

# Indian market specific financial phrases
INDIAN_FINANCIAL_PHRASES = [
    "beats estimates", "misses estimates", "beats estimates", "misses estimates",
    "beats expectations", "misses expectations", "beats expectations", "misses expectations",
    "surpasses estimates", "misses estimates", "exceeds estimates", "falls short",
    "surpasses expectations", "falls short of expectations", "exceeds expectations", "falls short of estimates",
    "posts profit", "reports loss", "swings to profit", "swings to loss",
    "turns profitable", "turns loss-making", "returns to profit", "slips into red",
    "net profit rises", "net profit falls", "net profit jumps", "net profit drops",
    "revenue rises", "revenue falls", "revenue jumps", "revenue drops",
    "margin expands", "margin contracts", "margin improves", "margin contracts",
    "operating margin expands", "operating margin contracts",
    "net margin expands", "net margin contracts",
    "eps rises", "eps falls", "eps jumps", "eps drops",
    "eps beats estimates", "eps misses estimates",
    "revenue beats estimates", "revenue misses estimates",
    "profit beats estimates", "profit misses estimates",
    "ebitda beats estimates", "ebitda misses estimates",
    "margin beats estimates", "margin misses estimates",
    "dividend announced", "dividend declared", "dividend recommended",
    "bonus shares", "stock split", "face value split",
    "buyback announced", "buyback open", "buyback closes",
    "rights issue", "rights issue price", "rights issue ratio",
    "ipo opens", "ipo closes", "ipo subscribed", "ipo oversubscribed",
    "listing gains", "listing discount", "premium listing",
    "sebi approves", "rbi approves", "rbi rejects", "sebi rejects",
    "rbi policy", "repo rate", "reverse repo", "cash reserve ratio", "statutory liquidity ratio",
    "crr", "slr", "msf", "bank rate", "liquidity", "inflation", "cpi", "wpi",
    "gdp", "gdp growth", "iip", "industrial production", "core sector",
    "pmi", "manufacturing pmi", "services pmi", "composite pmi",
    "fii", "fpi", "dii", "mutual funds", "insurance companies", "banks", "fii buying", "fii selling", "dii buying", "dii selling",
    "fii net buyers", "fii net sellers", "dii net buyers", "dii net sellers",
    "block deal", "bulk deal", "bulk deals", "block deals",
    "insider trading", "insider buying", "insider selling",
    "pledge", "pledged shares", "unpledge", "unpledged shares",
    "promoter holding", "promoter stake", "promoter pledge", "promoter unpledge",
    "institutional holding", "institutional stake", "mutual fund holding", "insurance holding",
    "foreign holding", "foreign stake", "fpi holding", "fii holding",
    "retail holding", "retail stake", "hni holding", "hni stake",
]

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
    out = {}
    for k, v in data.items():
        if k == "centroid" and isinstance(v, list):
            out[k] = np.array(v)
        else:
            out[k] = v
    return out


# ─── Adaptive TF-IDF Cluster Learner ───
class AdaptiveClusterLearner:
    """
    Learns sentiment from price reactions, not labels.

    Algorithm:
    - Groups headlines into semantic neighborhoods via TF-IDF
    - Tracks realized average price reaction per cluster
    - Auto-adapts as market regimes shift (no retraining)
    - Calibrates ensemble weights against ground-truth price moves
    """

    def __init__(self):
            self.clusters: dict[int, dict] = {}  # cluster_id -> {centroid, headlines, reactions, weight}
            # Use TfidfVectorizer with custom tokenization for Indian financial text
            import re
        
            def custom_tokenizer(text: str) -> list:
                """Custom tokenizer optimized for Indian financial news."""
                text = text.lower()
                # Tokenize: words + financial symbols
                tokens = re.findall(r'\b[a-z]+\b|\d+(?:\.\d+)?%?|\$?\d+(?:\.\d+)?[kmbt]?', text)
            
                # Create unigrams
                unigrams = tokens
            
                # Create financial bigrams (adjacent words)
                bigrams = [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens)-1)]
            
                # Create financial trigrams
                trigrams = [f"{tokens[i]}_{tokens[i+1]}_{tokens[i+2]}" for i in range(len(tokens)-2)]
            
                # Financial n-grams with special handling for key phrases
                all_grams = unigrams + bigrams + trigrams
            
                # Add special financial phrase markers
                financial_markers = []
                for phrase in INDIAN_FINANCIAL_PHRASES:
                    if phrase in ' '.join(tokens):
                        financial_markers.append(f"__PHRASE__{phrase.replace(' ', '_')}")
            
                return all_grams + financial_markers
        
            self.vectorizer = TfidfVectorizer(
                max_features=8000,
                ngram_range=(1, 3),
                stop_words="english",
                min_df=1,
                max_df=0.95,
                sublinear_tf=True,
                tokenizer=custom_tokenizer,
            )
            self._fitted = False
            self._last_calibration = 0.0
            self._load()
            # Pre-fit on financial corpus to handle cold start
            self._prefit_vectorizer()
    def _load(self):
        """Load clusters from disk."""
        try:
            if ADAPTIVE_CACHE_FILE.exists():
                with open(ADAPTIVE_CACHE_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                    self.clusters = {int(k): _deserialize_cluster(v) for k, v in data.get("clusters", {}).items()}
                    self._last_calibration = data.get("last_calibration", 0.0)
                    # Re-fit vectorizer on stored headlines to match vocabulary
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

    def _prefit_vectorizer(self):
        """Pre-fit vectorizer on financial corpus to handle cold start."""
        financial_corpus = [
            "Reliance beats quarterly estimates profit growth",
            "TCS misses quarterly estimates profit decline",
            "INFY beats quarterly earnings revenue growth",
            "HDFC Bank beats profit estimates net interest income",
            "ICICI Bank misses profit estimates provisions rise",
            "Crude oil surges on supply fears OPEC cuts",
            "Brent crude rises on OPEC production cuts",
            "Gold prices steady on safe haven demand",
            "Rupee weakens against dollar RBI intervention",
            "RBI keeps rates unchanged repo rate unchanged",
            "Bank Nifty surges on rate cut hopes credit growth",
            "IT stocks rally on weak rupee dollar strength",
            "Pharma stocks rally on FDA approval clinical trials",
            "Auto stocks surge on festive demand rural recovery",
            "Metal stocks rally on China stimulus infrastructure",
            "Cement stocks surge on infrastructure spending budget",
            "Power stocks rally on demand growth capacity addition",
            "FMCG stocks steady on rural demand consumption",
            "Real estate stocks surge on housing demand low rates",
            "Telecom stocks rally on tariff hike subscriber growth",
            # Explicit negation examples for training
            "company beats estimates revenue profit beats",
            "company misses estimates revenue profit misses",
            "earnings beat revenue beat profit beat",
            "earnings miss revenue miss profit miss",
            "profit beats estimates beats estimates",
            "profit misses estimates misses estimates",
            "quarterly results beat expectations",
            "quarterly results miss expectations",
            "stock rises on beat results",
            "stock falls on miss results",
        ]
        self.vectorizer.fit(financial_corpus)
        self._fitted = True

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
        """Vectorize a single headline using HashingVectorizer (no fitting needed)."""
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

    def calibrate(self, recent_headlines: list[str], recent_moves_1h: list[float], recent_moves_4h: list[float], force: bool = False):
        """
        Recalibrate cluster weights based on prediction accuracy.
        Called periodically (every 72h) with recent ground-truth data.
        
        Args:
            recent_headlines: List of recent headlines
            recent_moves_1h: List of actual 1h price moves
            recent_moves_4h: List of actual 4h price moves
            force: If True, skip the 72-hour cooldown check
        """
        with _adaptive_lock:
            if not self.clusters or len(recent_headlines) < MIN_CLUSTER_SIZE_FOR_CALIBRATION:
                return

            now = time.time()
            if not force and now - self._last_calibration < CALIBRATION_WINDOW_HOURS * 3600:
                return

            # For each cluster, compute how well its average reaction predicts actual moves
            for cid, cluster in self.clusters.items():
                if "centroid" not in cluster or not cluster["reactions_1h"]:
                    continue

                # Collect actual moves for headlines that belong to this cluster
                cluster_actuals = []
                for hl, move_1h in zip(recent_headlines, recent_moves_1h):
                    vec = self._vectorize(hl)
                    sim = self._cosine_sim(vec, np.array(cluster["centroid"]))
                    if sim >= (1 - CLUSTER_EPS):  # headline belongs to this cluster
                        cluster_actuals.append(move_1h)

                if len(cluster_actuals) >= 3:
                    # Compare cluster's average reaction vs actual outcomes
                    cluster_mean = np.mean(cluster["reactions_1h"])
                    
                    # Direction agreement: how often does sign(cluster_mean) == sign(actual)?
                    correct_direction = sum(1 for a in cluster_actuals if 
                        (cluster_mean > 0 and a > 0) or (cluster_mean < 0 and a < 0) or (cluster_mean == 0 and a == 0))
                    direction_accuracy = correct_direction / len(cluster_actuals)
                    
                    # Magnitude accuracy: how close is magnitude?
                    magnitude_errors = [abs(cluster_mean - a) for a in cluster_actuals]
                    mean_magnitude_error = np.mean(magnitude_errors)
                    magnitude_accuracy = max(0, 1 - (mean_magnitude_error / (abs(cluster_mean) + 1)))
                    
                    # Combined weight: direction accuracy weighted more heavily
                    cluster["weight"] = float(0.7 * direction_accuracy + 0.3 * magnitude_accuracy)
                    
                    # Track calibration history
                    if "calibration_history" not in cluster:
                        cluster["calibration_history"] = []
                    cluster["calibration_history"].append({
                        "timestamp": now,
                        "direction_accuracy": direction_accuracy,
                        "magnitude_accuracy": magnitude_accuracy,
                        "weight": cluster["weight"],
                        "sample_size": len(cluster_actuals)
                    })
                    # Keep only last 10 calibrations
                    cluster["calibration_history"] = cluster["calibration_history"][-10:]

            self._last_calibration = now
            self._save()
            logger.info(f"Adaptive calibration complete: {len(self.clusters)} clusters weighted")


# ─── News Dissemination Breadth Clustering ───
class DisseminationClusterer:
    """
    Clusters related news articles to measure dissemination breadth.

    Based on FinGPT (arXiv:2412.10823):
    - Group articles by shared financial entities (tickers, commodities, sectors)
    - Cluster size = dissemination breadth = market impact proxy
    - Large multi-source clusters = high-impact events
    """

    def __init__(self):
            # Financial entity keywords for grouping
            self.commodity_keywords = {
                "crude": ["crude", "brent", "wti", "oil", "petroleum", "crudeoil"],
                "gold": ["gold", "bullion", "yellow metal", "goldprices", "goldprices"],
                "silver": ["silver", "silverprices"],
                "copper": ["copper", "copperprices"],
                "aluminum": ["aluminum", "aluminium", "aluminiumprices"],
                "natural_gas": ["natural gas", "lng", "cng", "naturalgas", "lngprices"],
                "coal": ["coal", "thermal coal", "coalprices"],
                "sugar": ["sugar", "sugarprices"],
                "steel": ["steel", "iron ore", "steelprices", "ironore"],
                "cotton": ["cotton", "cottonprices"],
                "wheat": ["wheat", "wheatprices"],
                "rice": [" rice ", "riceprices", "rice prices", "rice price"],
                "soybean": ["soybean", "soy", "soybeanprices"],
                "palm_oil": ["palm oil", "crude palm oil", "cpo", "palmoilprices"],
                "rubber": ["rubber", "natural rubber", "rubberprices"],
            }
            self.sector_keywords = {
                "banking": ["bank", "rbi", "rate", "interest", "lending", "deposit", "npa", "provisioning", "netinterestmargin", "nim", "casa", "casa ratio"],
                "it": ["it ", "software", "technology", "tech ", "services", "digital", "cloud", "saas", "erp", "consulting", "outsourcing", "bpo", "kpo", "ites"],
                "pharma": ["pharma", "drug", "medicine", "clinical", "fda", "usfda", "dcgi", "cdsco", "and", "anda", "bioequivalence", "generics", "api", "formulations", "cmo", "cdo", "r&d", "pipeline", "approval", "launch", "patent", "exclusivity"],
                "cement": ["cement", "construction", "infrastructure"],
                "metals": ["metal", "steel", "aluminum", "copper", "zinc"],
            }
            # Simple TF-IDF for fallback similarity
            self.vectorizer = HashingVectorizer(
                n_features=200,
                ngram_range=(1, 2),
                stop_words="english",
                alternate_sign=False,
                norm="l2",
            )
            self._fitted = True

    def _extract_entities(self, text: str) -> set:
        """Extract financial entities (commodities, sectors) from text."""
        text_lower = text.lower()
        entities = set()
        for entity, keywords in self.commodity_keywords.items():
            if any(kw in text_lower for kw in keywords):
                entities.add(f"commodity:{entity}")
        for entity, keywords in self.sector_keywords.items():
            if any(kw in text_lower for kw in keywords):
                entities.add(f"sector:{entity}")
        return entities

    def _get_article_signature(self, article: dict) -> frozenset:
        """Create a signature for grouping: entities only (tickers kept separate)."""
        text = f"{article.get('title', '')}. {article.get('body', '')}"
        entities = self._extract_entities(text)
        return frozenset(entities)

    def cluster_articles(self, articles: list[dict]) -> list[dict]:
        """
        Cluster articles by shared financial entities.

        Returns list of clusters with:
        - articles: list of article indices
        - size: int
        - dissemination_score: float (0-1, normalized size + source diversity)
        - representative: str (title of first article)
        - sources: list of unique sources
        - tickers: list of unique tickers
        """
        if not articles or len(articles) < DISSEMINATION_MIN_CLUSTER_SIZE:
            return []

        # Group by entity signature
        signature_groups = defaultdict(list)
        for idx, article in enumerate(articles):
            sig = self._get_article_signature(article)
            signature_groups[sig].append(idx)

        # Filter groups with at least 2 articles
        valid_groups = {sig: idxs for sig, idxs in signature_groups.items() if len(idxs) >= DISSEMINATION_MIN_CLUSTER_SIZE}

        if not valid_groups:
            return []

        # Build cluster summaries
        clusters = []
        max_size = max(len(idxs) for idxs in valid_groups.values())

        for sig, indices in valid_groups.items():
            sources = list({articles[i].get("source", "Unknown") for i in indices})
            tickers = list({t for i in indices for t in articles[i].get("ticker", "").upper().split() if t})
            entities = list(sig)

            # Dissemination score = normalized size * source diversity
            size_score = min(len(indices) / max(10, max_size), 1.0)
            source_diversity = min(len(sources) / 5.0, 1.0)  # max 5 sources
            dissemination_score = (0.7 * size_score) + (0.3 * source_diversity)

            clusters.append({
                "articles": indices,
                "size": len(indices),
                "dissemination_score": round(dissemination_score, 3),
                "representative": articles[indices[0]].get("title", "")[:120],
                "sources": sources,
                "tickers": tickers,
                "entities": entities,
            })

        # Sort by dissemination score (largest, most diverse first)
        clusters.sort(key=lambda c: c["dissemination_score"], reverse=True)
        return clusters[:DISSEMINATION_MAX_CLUSTERS]

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
def learn_from_price_reaction(headline: str, price_move_1h: float, price_move_4h: float) -> bool:
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


def calibrate_adaptive_learner(recent_headlines: list[str], recent_moves_1h: list[float], recent_moves_4h: list[float]) -> dict | None:
    """Trigger calibration of adaptive learner weights."""
    get_adaptive_learner().calibrate(recent_headlines, recent_moves_1h, recent_moves_4h, force=True)


# ─── Integration helpers for data_fetcher.py ───
def extract_price_moves_for_learning(ticker: str, headline_time: datetime, hist_1h: list, hist_4h: list) -> tuple[float, float]:
    """
    Given a headline timestamp and recent price history, compute the 1h and 4h
    forward returns for learning. Returns (move_1h, move_4h) as percentages.
    """
    if not hist_1h or not hist_4h:
        return 0.0, 0.0

    # Find price at headline time (approximate - use nearest)

    price_at_headline = None
    for bar in hist_1h:
        bar_ts = bar.get("time", 0)
        if isinstance(bar_ts, str):
            try:
                bar_ts = datetime.fromisoformat(bar_ts).timestamp() * 1000
            except (ValueError, TypeError):
                continue  # malformed timestamp: skip bar
            price_at_headline = bar["close"]
        else:
            break

    if price_at_headline is None:
        price_at_headline = hist_1h[0]["close"]

    # 1h forward: find bar ~1h after
    move_1h = 0.0
    for bar in hist_1h:
        bar_ts = bar.get("time", 0)
        if isinstance(bar_ts, str):
            try:
                bar_ts = datetime.fromisoformat(bar_ts).timestamp() * 1000
            except (ValueError, TypeError):
                continue  # malformed timestamp: skip bar
            move_1h = ((bar["close"] - price_at_headline) / price_at_headline) * 100
            break

    # 4h forward
    move_4h = 0.0
    for bar in hist_4h:
        bar_ts = bar.get("time", 0)
        if isinstance(bar_ts, str):
            try:
                bar_ts = datetime.fromisoformat(bar_ts).timestamp() * 1000
            except (ValueError, TypeError):
                continue  # malformed timestamp: skip bar
            move_4h = ((bar["close"] - price_at_headline) / price_at_headline) * 100
            break

    return move_1h, move_4h