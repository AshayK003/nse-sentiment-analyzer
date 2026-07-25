"""
Verdict builder — composes all signals into final trading verdict.
Pure strategy layer: no I/O, deterministic.
"""

from __future__ import annotations

from ..contracts import (
    Verdict, Signal, SentimentScore, Indicators,
    TrendDirection, CascadeEvent, PriceData, AnalysisRequest
)


def build_verdict(
    ticker: str,
    price_data: PriceData,
    sentiment: SentimentScore,
    cascade: CascadeEvent | None,
    request: AnalysisRequest,
) -> Verdict:
    """
    Build final trading verdict from all signals.

    Signal Logic:
    - Start with sentiment signal (BUY/SELL/HOLD)
    - Adjust based on technical indicators (trend, RSI, MACD)
    - Adjust based on cascade (amplifies or contradicts)
    - Confidence = weighted average of all factors

    Args:
        ticker: Stock symbol
        price_data: OHLCV + indicators + current price
        sentiment: Aggregated sentiment score
        cascade: Optional cascade event
        request: Original analysis request

    Returns:
        Verdict with signal, confidence, rationale
    """
    # Base signal from sentiment
    signal = _sentiment_to_signal(sentiment)
    base_confidence = int(sentiment.confidence * 100)

    # Technical adjustment
    tech_signal, tech_conf = _technical_signal(price_data.indicators)
    if tech_signal != "HOLD":
        # Blend sentiment + technical (60/40)
        if signal == tech_signal:
            # Agreement = higher confidence
            base_confidence = min(base_confidence + 15, 95)
        else:
            # Disagreement = lower confidence, favor technical for swing
            signal = tech_signal
            base_confidence = int(tech_conf * 100)

    # Cascade adjustment
    if cascade:
        if cascade.direction == TrendDirection.BULLISH and signal == "BUY":
            base_confidence = min(base_confidence + 10, 95)
        elif cascade.direction == TrendDirection.BEARISH and signal == "SELL":
            base_confidence = min(base_confidence + 10, 95)
        elif (cascade.direction == TrendDirection.BULLISH and signal == "SELL") or \
             (cascade.direction == TrendDirection.BEARISH and signal == "BUY"):
            # Cascade contradicts signal — reduce confidence
            base_confidence = max(base_confidence - 20, 20)

    # RSI extreme check
    rsi = price_data.indicators.rsi_14
    if rsi > 75 and signal == "BUY":
        signal = "HOLD"
        base_confidence = max(base_confidence - 15, 30)
    elif rsi < 25 and signal == "SELL":
        signal = "HOLD"
        base_confidence = max(base_confidence - 15, 30)

    # Price vs 200 SMA
    sma_200 = price_data.indicators.sma_200
    current = price_data.current_price
    if sma_200 > 0:
        if current < sma_200 * 0.95 and signal == "BUY":
            # Price well below 200 SMA — caution
            base_confidence = max(base_confidence - 10, 30)
        elif current > sma_200 * 1.05 and signal == "SELL":
            base_confidence = max(base_confidence - 10, 30)

    # Build rationale
    rationale_parts = []
    rationale_parts.append(f"Sentiment: {sentiment.compound:.2f} ({sentiment.event_type.value})")
    rationale_parts.append(f"Tech: RSI={rsi:.0f}, Trend={price_data.indicators.trend.value}")
    if cascade:
        rationale_parts.append(f"Cascade: {cascade.direction.value} ({cascade.confidence:.0%})")
    rationale = " | ".join(rationale_parts)

    return Verdict(
        ticker=ticker,
        signal=Signal(signal.lower()),
        confidence=min(base_confidence, 95),
        sentiment=sentiment,
        indicators=price_data.indicators,
        cascade=cascade,
        rationale=rationale,
        price_data=price_data,
    )


def _sentiment_to_signal(sentiment: SentimentScore) -> str:
    """Convert sentiment to base signal."""
    if sentiment.compound > 0.15 and sentiment.confidence > 0.4:
        return "BUY"
    elif sentiment.compound < -0.15 and sentiment.confidence > 0.4:
        return "SELL"
    else:
        return "HOLD"


def _technical_signal(indicators: Indicators) -> tuple[str, float]:
    """
    Generate signal from technical indicators.

    Returns:
        (signal, confidence_0_1)
    """
    # Trend-based
    if indicators.trend == TrendDirection.BULLISH:
        if indicators.rsi_14 < 70:
            return "BUY", indicators.trend_strength
        else:
            return "HOLD", 0.5  # Overbought
    elif indicators.trend == TrendDirection.BEARISH:
        if indicators.rsi_14 > 30:
            return "SELL", indicators.trend_strength
        else:
            return "HOLD", 0.5  # Oversold

    # MACD confirmation
    if indicators.macd > indicators.macd_signal and indicators.macd_hist > 0:
        return "BUY", 0.6
    elif indicators.macd < indicators.macd_signal and indicators.macd_hist < 0:
        return "SELL", 0.6

    return "HOLD", 0.4


def get_verdict_summary(verdict: Verdict) -> dict:
    """Convert verdict to summary dict for UI/API."""
    return {
        "ticker": verdict.ticker,
        "signal": verdict.signal.value,
        "confidence": verdict.confidence,
        "price": verdict.price_data.current_price if verdict.price_data else None,
        "change_pct": verdict.price_data.change_pct if verdict.price_data else None,
        "sentiment": verdict.sentiment.compound,
        "event": verdict.sentiment.event_type.value,
        "rsi": verdict.indicators.rsi_14,
        "trend": verdict.indicators.trend.value,
        "cascade": verdict.cascade.direction.value if verdict.cascade else None,
        "rationale": verdict.rationale,
    }