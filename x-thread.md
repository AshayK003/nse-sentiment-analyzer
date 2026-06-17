📊 I'm building 52 AI tools in 52 weeks.

Tool #1 is done: NSE Stock Sentiment Analyzer.

Enter any NSE ticker → live price + news sentiment → BUY/HOLD/CAUTION signal.

Here's how it works 🧵

1/8
The problem: Retail traders like me check prices on one tab, news on another, and manually connect the dots. That's slow and emotional.

The fix: One dashboard that does all three. Ticker in → price + headlines + sentiment out.

2/8
Built with:
• Streamlit (UI)
• yfinance (NSE price data)
• DuckDuckGo News (free, zero API fees)
• VADER + custom financial lexicon (sentiment)

Zero API keys needed. Runs on any laptop.

3/8
For RELIANCE this morning:
📍 ₹1,328.80 (+₹21.80)
🟢 Positive sentiment across news
📰 5 articles found (Jio IPO speculation, AGM triggers)

All in ~3 seconds.

4/8
The sentiment analysis isn't just "good" or "bad." Every headline gets scored:

🟢 Positive → "Reliance Power gains for third straight session"
🔴 Negative → "Stock downgraded by analysts"
⚪ Neutral → "Stock market live today"

Then aggregated into a clear signal.

5/8
Why I built this instead of using a paid tool:
• No subscription (₹199 one-time)
• No API keys to manage
• Works for all 5,000+ NSE stocks + ETFs
• Customisable → add your own tickers, modify the lexicon

6/8
Where to get it:

→ Gumroad (link below): ₹199 one-time
→ GitHub (open-source, instructions in repo)

The GitHub version lets you run it yourself. The Gumroad version is the same + supports the 52-tool challenge.

7/8
Next week's tool: LinkedIn Post Hook Generator for Indian founders.

The week after: Resume vs JD Matcher for placement season.

Following: NSE Portfolio Risk Scanner.

52 weeks. 52 tools. All public.

8/8

→ Gumroad: [link]
→ GitHub: github.com/AshayK003/nse-sentiment-analyzer

Built by @sentinelcipher. Follow along for the next 51. 📡
