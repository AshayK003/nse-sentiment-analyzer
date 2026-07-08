# SmartScore Algorithm

## Overview

SmartScore is a composite sentiment score that summarizes the overall market sentiment on a scale from **0 to 100**.

Instead of relying on a single metric, it combines four different signals:

- Recent sentiment (EWMA)
- Event-adjusted sentiment
- Headline breadth
- News volume

Each component contributes to the final score using predefined weights.

| Component | Weight |
|-----------|-------:|
| Recency | 45% |
| Event-adjusted sentiment | 25% |
| Headline breadth | 20% |
| News volume | 10% |

The final score is calculated as:

```text
SmartScore = 100 × (
    0.45 × S_recency +
    0.25 × S_events +
    0.20 × S_breadth +
    0.10 × S_volume
)
```

The result is always limited to the range **0–100**.

---

## Components

### 1. Recency

Recent sentiment should have a larger influence than older sentiment.

To achieve this, SmartScore uses an Exponentially Weighted Moving Average (EWMA) with a **36-hour half-life**.

Each historical value receives a weight calculated as:

```text
weight = exp(-ln(2) × hours_ago / 36)
```

This means that a value from 36 hours ago contributes roughly half as much as today's value.

Only historical sentiment from the last **30 days** is considered.

---

### 2. Event-adjusted Sentiment

This component is simply the average of all event-adjusted headline sentiment scores.

It represents the overall market sentiment after event classification has been applied.

---

### 3. Headline Breadth

Headline breadth measures whether positive news outweighs negative news.

A headline is considered:

- Positive if its score is **≥ 0.3**
- Negative if its score is **≤ -0.3**

The breadth score is calculated as:

```text
(Positive Headlines − Negative Headlines) / Total Headlines
```

The result is then normalized to a value between **0** and **1**.

---

### 4. News Volume

More headlines generally provide a stronger signal, but very large numbers of articles should not dominate the score.

For that reason, news volume is normalized using:

```text
log(1 + headline_count) / log(1 + MAX_HEADLINES)
```

where `MAX_HEADLINES = 20`.

---

## Signal Interpretation

After the SmartScore is calculated, it is converted into a market signal.

| SmartScore | Signal |
|------------|--------|
| 65–100 | 🟢 BULLISH |
| 40–64.9 | ⚪ NEUTRAL |
| 0–39.9 | 🔴 BEARISH |

---

## Example

Assume the following normalized values:

| Component | Value |
|-----------|------:|
| Recency | 0.80 |
| Event-adjusted sentiment | 0.60 |
| Headline breadth | 0.75 |
| News volume | 0.90 |

The SmartScore would be:

```text
100 × (
0.45 × 0.80 +
0.25 × 0.60 +
0.20 × 0.75 +
0.10 × 0.90
)

= 75
```

The resulting signal would be **BULLISH**.

---

## Edge Cases

- No headlines return an empty SmartScore result.
- Historical entries older than 30 days are ignored.
- Invalid historical records are skipped.
- The final score is always clamped to the range **0–100**.

---

## Limitations

SmartScore is designed to summarize recent news sentiment. It should be used as an indicator rather than a prediction of future market performance.