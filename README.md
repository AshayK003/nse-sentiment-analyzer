# 📊 NSE Stock Sentiment Analyzer

**AI Tool #1 of 52** — Enter any NSE ticker & get live price + news sentiment analysis in one dashboard.

![Streamlit](https://img.shields.io/badge/Built%20with-Streamlit-FF4B4B)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What it does

Paste an NSE ticker (RELIANCE, HDFCBANK, TCS…) → get a **live dashboard** with:

- ✅ Current price + day change
- ✅ Day range & volume
- ✅ P/E ratio & 52-week range
- ✅ News sentiment score (🟢 Positive / 🔴 Negative / ⚪ Neutral)
- ✅ Headline-by-headline breakdown
- ✅ Overall BUY / HOLD / CAUTION signal

## How it works

```
You type "RELIANCE"
        ↓
 yfinance → Live price, PE, volume, 52W range
        ↓
 DuckDuckGo → Last 7 days of news articles
        ↓
 VADER + Financial Lexicon → Per-headline sentiment scores
        ↓
 Dashboard → Overall signal + sentiment distribution
```

## Quick start

```bash
git clone https://github.com/AshayK003/nse-sentiment-analyzer
cd nse-sentiment-analyzer
pip install -r requirements.txt
streamlit run app.py
```

Then open `http://localhost:8501` in your browser.

## Tech stack

- **Streamlit** — UI framework
- **yfinance** — Yahoo Finance data (NSE stocks via `.NS` suffix)
- **DuckDuckGo Search** — News aggregation (free, no API key)
- **NLTK VADER** — Sentiment analysis with custom financial lexicon
- **Zero external API costs** — runs entirely on your laptop

## Pricing

**₹199 one-time** on Gumroad. No subscription. No API keys needed.

## Roadmap (future tools)

Weeks 2–52 will cover:
- LinkedIn Post Hook Generator for Indian Founders
- Resume vs JD Matcher for College Placements
- NSE Portfolio Risk Scanner
- Instagram Caption Generator (Hinglish)
- AI-Powered CAT Exam Prep Assistant
- And 47 more…

---

Built by [@sentinelcipher](https://x.com/sentinelcipher) · Part of the **52 AI Tools in 52 Weeks** challenge.
