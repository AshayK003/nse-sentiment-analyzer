# Changelog

## [2.2.2] — 2026-06-20

### Changed
- **SmartScore trend accuracy improved** — The SmartScore now accounts for event-adjusted headline signals (earnings, deals, regulatory actions) when measuring market breadth. This makes the composite trend number and component bars more reliable when event-heavy news is in play.
- **Sidebar portfolio UX redesigned** — Clearer section labels, current price shown inline with every holding, and a heatmap legend (green/red/grey color key) so you know what each colour means at a glance.

### Fixed
- **Sidebar ticker names no longer show stray asterisks** — Bold ticker names in the portfolio list were rendering as `**RELIANCE**` instead of **RELIANCE**. Now rendering correctly.

## [2.2.1] — 2026-06-20

### Changed
- **App loads faster** — Removed unused code paths and consolidated duplicate configuration. Smaller codebase = less to maintain.
- **Reddit: no more local CLI setup** — Removed the `rdt-cli` fallback. Reddit now works exclusively through OAuth (the cloud-friendly path). If you have OAuth env vars set, Reddit posts show up; if not, they're skipped — no extra tools needed.
- **Volume spike detection wired to dashboard** — `detect_volume_spike()` was already tested and ready, now it powers the volume spike badges you see on each holding. No change in behaviour, just cleaner under the hood.

### Fixed
- **Sentiment history CSV had a mislabeled column** — The `neg_count` field in exported CSVs was actually storing neutral headline count instead of negatives. Exports now correctly label negative headline counts.

## [2.2.0] — 2026-06-20

### Added
- **Portfolio P&L Tracking** — Set entry price when adding a stock. Sidebar shows live P&L (₹ and %) per holding, green for profit, red for loss.
- **Market Heatmap** — Compact 3-column grid in sidebar, every holding color-coded by daily % change.
- **Portfolio News Badges** — 📌 In portfolio badge on headlines that mention your holdings.
- **Volume Spike Detection** — `detect_volume_spike()` flags abnormal trading volume (N× 20-day average).
- **Stagnation Warnings** — `detect_stagnation()` flags stocks stuck in a tight range for 10+ days.

### Changed
- New entry price column in add-ticker row (sidebar)
- Metrics grid on landing page expanded from 4 to 6 columns

### Fixed
- **Trend sparkline blank on first analysis** — `render_sparkline()` now draws a dashed flat line + dot for single data points instead of returning empty SVG. Users see their SmartScore level immediately on first use.

## [2.1.3] — 2026-06-20

### Added
- **Shareable Snapshot Links** — Every ticker now has a public URL (`?ticker=RELIANCE`) showing SmartScore, signal, and price. Share on Telegram/WhatsApp/X. Full analysis unlocks behind the paywall.
- **Public changelog** — This file. Users can see what's new.
- **Feature request channel** — Feedback form linked in sidebar.

### Fixed
- **ETF 52W proximity crash** — `None` price (ETFs) caused `TypeError` in the proximity badge calculation. Guarded with `_is_valid_num()`.

## [2.1.2] — 2026-06-20

### Fixed
- **ETF NaN prices** — ETFs (NIFTYBEES, GOLDBEES, MIDCAPETF) showed `₹nan` and `nan%` because `float('nan')` is truthy in Python. Added `_nf()` NaN-safe extractor and `_is_valid_num()` guards throughout.

## [2.1.1] — 2026-06-20

### Changed
- Removed duplicate emoji-to-SVG mapping, consolidated to `get_signal_icon()`
- Collapsed 15-line if/elif sentiment chain to 7-line dict lookup
- Moved lazy imports to module level
- Removed 6 redundant `str()` wrappers

### Fixed
- Dashboard iframe height: formula-based (`2200 + n_news*120`)
- Mobile-responsive CSS breakpoints

## [2.1.0] — 2026-06-20

### Added
- 504 ticker aliases (was 72)
- 18 event types (was 13): `RATING_UPGRADE`, `JV_MOU`, `FUNDRAISE`, `CONTRACT_LOSS`, `DIVESTMENT`
- Bayesian calibration visible in dashboard
- 270 NSE tickers (was 85)

## [2.0.0] — 2026-06

### Added
- Bayesian source calibration (learns from 👍/👎 votes)
- Optional FinBERT transformer (`USE_FINBERT=true`)
- Lucide SVG icons throughout (replaced Unicode emojis)
- Yahoo Finance retries with jitter + suffix fallback

## [1.0.0] — 2026-05

### Added
- Initial release
- Live NSE stock data via yfinance
- Multi-source RSS news sentiment
- SmartScore composite (0-100)
- Technical indicators (RSI, SMA, MACD)
- Portfolio tracking
- Dark-themed HTML dashboard
