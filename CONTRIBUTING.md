# Contributing to NSE Stock Sentiment Analyzer

Thank you for your interest in contributing! This project follows a sync-first, sync-only architecture with mocked external APIs in tests.

## Development Setup

```bash
# Clone and enter
git clone https://github.com/AshayK003/nse-sentiment-analyzer.git
cd nse-sentiment-analyzer

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dev dependencies
pip install -r requirements.txt
pip install pytest pytest-mock pytest-cov

# Run tests to verify setup
python -m pytest tests/ -q
```

## Code Style

- **Sync-first** — no `async`/`await`. Parallelism via `concurrent.futures.ThreadPoolExecutor`
- **Mock all external APIs** in tests — `yfinance`, `feedparser`, `duckduckgo_search`, `requests`
- **Use `cache_get`/`cache_set`** from `persistence.py` for API response caching
- **Prefer deletion over abstraction** — YAGNI. When in doubt, leave it out.
- **Lucide SVGs** for all UI icons — no emojis where an SVG serves the same purpose
- **Type hints** for new functions (existing code gradually migrating)

## Commit Messages

Prefix by type:
- `fix:` — bug fix
- `feat:` — new feature
- `test:` — test additions/changes
- `docs:` — documentation
- `refactor:` — code restructuring without behavior change
- `chore:` — maintenance, deps, CI

Examples:
```
fix: handle NaN in ETF price display
feat: add Adaptive TF-IDF Cluster Learner
test: add dissemination clustering tests
docs: sync README test count to 180
```

## PR Workflow

1. **Open an issue** first — describe the bug (with reproduction) or feature (with use case)
2. **Fork and branch** from `master`
3. **Write tests first** for any new logic (TDD)
4. **Run full suite** — `python -m pytest tests/ -q` must pass
5. **Keep diffs small** — one logical change per PR
6. **Submit PR** with clear description linking the issue

## Testing Requirements

- All external APIs mocked in tests
- Fixtures in `tests/conftest.py` provide isolated `tmp_data_dir` and sample DataFrames
- Integration tests verify module boundaries (stock data → sentiment → event classification → SmartScore)
- Markers in `pyproject.toml`:
  - `slow` — tests hitting real APIs (opt-in)
  - `regression` — tests for previously-fixed bugs

## What We Need

- **Financial lexicon expansion** — Indian-market-specific terms for VADER
- **News source integration** — additional Indian financial RSS feeds
- **NSE ticker updates** — new listings, delistings, symbol changes
- **UI improvements** — accessibility, mobile responsiveness, i18n
- **Bug fixes** — open an issue first with reproduction steps
- **Test coverage** — edge cases for empty results, partial data, rate limits

## What We Avoid

- Adding new dependencies without strong justification
- Introducing `async` patterns (project is sync-first)
- Patching symptoms instead of root causes
- Features requiring paid APIs or API keys

## License

By contributing, you agree that your contributions will be licensed under the **GNU AGPL v3** (same as the project).