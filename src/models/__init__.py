"""
Shared data models — inter-layer contracts for NSE Sentiment Analyzer.
These are the ONLY types that cross layer boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import math


class EventType(Enum):
    """Classified event categories from news headlines."""
    EARNINGS = "earnings"
    MERGER_ACQUISITION = "merger_acquisition"
    REGULATORY = "regulatory"
    PRODUCT_LAUNCH = "product_launch"
    MANAGEMENT_CHANGE = "management_change"
    DIVIDEND = "dividend"
    SPLIT = "split"
    BUYBACK = "buyback"
    GUIDANCE = "guidance"
    INSIDER = "insider"
    CONTRACT = "contract"
    LEGAL = "legal"
    MACRO = "macro"
    UNKNOWN = "unknown"


class Signal(Enum):
    """Trading signal output."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class TrendDirection(Enum):
    """Price trend direction."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class OHLCV:
    """Single candlestick."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def __post_init__(self):
        if any(math.isnan(v) for v in (self.open, self.high, self.low, self.close)):
            raise ValueError("OHLCV contains NaN")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("Invalid OHLC relationship")


@dataclass(frozen=True)
class Headline:
    """News headline with metadata."""
    title: str
    summary: str
    url: str
    source: str
    published: datetime
    ticker: str = ""

    @property
    def text(self) -> str:
        return f"{self.title}. {self.summary}"


@dataclass(frozen=True)
class SentimentScore:
    """Sentiment analysis result."""
    compound: float          # -1 to 1 (VADER compound)
    positive: float          # 0 to 1
    negative: float          # 0 to 1
    neutral: float           # 0 to 1
    confidence: float        # 0 to 1 (based on source weight + text length)
    event_type: EventType = EventType.UNKNOWN
    event_confidence: float = 0.0


@dataclass(frozen=True)
class Indicators:
    """Technical indicators computed from OHLCV."""
    rsi_14: float
    macd: float
    macd_signal: float
    macd_hist: float
    sma_20: float
    sma_50: float
    sma_200: float
    volume_ratio: float      # current / 20-day avg
    atr_14: float
    trend: TrendDirection
    trend_strength: float    # 0 to 1 (ADX-based)

    def is_bullish(self) -> bool:
        return self.trend == TrendDirection.BULLISH and self.rsi_14 < 70

    def is_bearish(self) -> bool:
        return self.trend == TrendDirection.BEARISH and self.rsi_14 > 30


@dataclass(frozen=True)
class CascadeEvent:
    """Detected sentiment cascade."""
    direction: TrendDirection
    sentiment_score: float
    confirming_events: list[EventType]
    confidence: float
    start_date: datetime
    duration_days: int


@dataclass(frozen=True)
class InstitutionalFlow:
    """FII/DII data point."""
    date: datetime
    fii_net: float      # Cr
    dii_net: float      # Cr
    fii_buy: float
    fii_sell: float
    dii_buy: float
    dii_sell: float


@dataclass(frozen=True)
class PriceData:
    """Complete price + institutional context."""
    ohlcv: list[OHLCV]
    indicators: Indicators
    institutional: list[InstitutionalFlow] = field(default_factory=list)
    current_price: float = 0.0
    change_pct: float = 0.0
    high_52w: float = 0.0
    low_52w: float = 0.0


@dataclass(frozen=True)
class Verdict:
    """Final trading verdict."""
    ticker: str
    signal: Signal
    confidence: int           # 0-100
    sentiment: SentimentScore
    indicators: Indicators
    cascade: Optional[CascadeEvent] = None
    rationale: str = ""
    price_data: Optional[PriceData] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "signal": self.signal.value,
            "confidence": self.confidence,
            "sentiment": {
                "compound": self.sentiment.compound,
                "event": self.sentiment.event_type.value,
            },
            "indicators": {
                "rsi": self.indicators.rsi_14,
                "trend": self.indicators.trend.value,
            },
            "cascade": self.cascade.direction.value if self.cascade else None,
            "rationale": self.rationale,
            "price": self.price_data.current_price if self.price_data else None,
        }


@dataclass(frozen=True)
class AnalysisRequest:
    """Input to the orchestrator."""
    ticker: str
    period: str = "1y"        # yfinance period string
    include_news: bool = True
    include_institutional: bool = True
    force_refresh: bool = False


@dataclass(frozen=True)
class AnalysisResult:
    """Output from orchestrator."""
    verdict: Verdict
    raw_headlines: list[Headline] = field(default_factory=list)
    cached: bool = False
    fetch_duration_ms: int = 0