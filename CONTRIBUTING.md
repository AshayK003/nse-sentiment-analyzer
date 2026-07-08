# Contributing to NSE Sentiment Analyzer

Thanks for considering a contribution. This project is open-source under AGPL v3, and every improvement — whether it's a bug fix, a new news source, or an additional financial term for the lexicon — makes the tool better for everyone.

**Before opening a PR, please open an issue first.** This prevents wasted effort if the change doesn't fit the project's scope or direction.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [What We Need](#what-we-need)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Development Setup](#development-setup)
- [Testing](#testing)
- [PR Workflow](#pr-workflow)
- [Style Guide](#style-guide)
- [Commit Conventions](#commit-conventions)
- [License](#license)

---

## Code of Conduct

Be respectful. This project welcomes contributors of all experience levels. No dismissive comments, no personal attacks, no harassment. Focus on the code, not the person.

---

## What We Need

| Area | Examples |
|------|----------|
| **Financial lexicon expansion** | Indian-market-specific terms for VADER (Hinglish, banking metrics, fund-flow terms, corporate actions) |
| **News source integration** | Additional Indian financial RSS feeds — Moneycontrol, ET, LiveMint, NDTV Profit, Business Standard |
| **NSE ticker updates** | New listings, delistings, symbol changes, corporate actions (splits, rebrands, demergers) |
| **UI improvements** | Accessibility (WCAG), mobile responsiveness, streamlined layout |
| **Bug fixes** | Open an issue first with reproduction steps |
| **Test coverage** | Edge cases for empty results, partial data, rate limits, network failures |

---

## Reporting Bugs

1. **Search existing issues** — your bug may already be reported or fixed.
2. **Open an issue** with:
   - A clear title
   - Steps to reproduce (ticker searched, what you expected, what happened)
   - Screenshot if applicable
   - Environment (Streamlit Cloud URL or local setup)

**Bug reports that include reproduction steps and expected/actual behavior get fixed faster.**

---

## Suggesting Features

1. **Open an issue** describing what you want and why.
2. Include a **concrete use case** — "Add volume profile indicators" is vague; "Show volume-at-price on the chart to identify support/resistance levels for swing trades" is actionable.
3. Mention if you're willing to implement it yourself.

Features requiring paid APIs, API keys, or new runtime dependencies are unlikely to be accepted.

---

## Development Setup

### Prerequisites

- Python 3.11+
- `pip` or `uv` (recommended for speed)

### Install

```bash
git clone https://github.com/AshayK003/nse-sentiment-analyzer.git
cd nse-sentiment-analyzer

# Install dependencies
pip install -r requirements.txt
# or
uv pip install -r requirements.txt

# Run the app
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

### Optional: FinBERT

```bash
pip install torch transformers
USE_FINBERT=true streamlit run app.py
```

### Optional: FII/DII Data

```bash
pip install nsepython
```

---

## Testing

This project takes testing seriously. Every new feature and bug fix must include tests.

### Running Tests

```bash
# Full suite (205 tests, mocked APIs, no network)
python -m pytest tests/ -v -q

# With coverage
python -m pytest tests/ --cov

# Specific file
python -m pytest tests/test_data_fetcher.py -v

# Specific test
python -m pytest tests/test_indicators.py::TestIndicators::test_rsi -v
```

### Test Design Principles

- **All external APIs must be mocked** — `yfinance`, `feedparser`, `duckduckgo_search`, `requests`. Never hit production services in tests.
- **Use `pytest-mock`** for patching. Fixtures in `conftest.py` provide `tmp_data_dir` for isolated file I/O and `sample_hist` DataFrame for indicators.
- **Tests should be deterministic** — no reliance on current date, network state, or random seeds. If you need dates, generate them dynamically relative to now.
- **Markers** — use `@pytest.mark.slow` for tests that hit real APIs (opt-in, not run by default), `@pytest.mark.regression` for tests covering previously-fixed bugs.

---

## PR Workflow

1. **Open an issue** describing the change (bug → reproduction; feature → use case).
2. **Fork the repo** and create a branch from `master`.
3. **Write tests first** for any new logic (TDD).
4. **Make your changes** — keep diffs small, one logical change per PR.
5. **Run the full suite** — `python -m pytest tests/ -q` must pass.
6. **Push and open a PR** against `master`. Reference the issue in the description.

### Before Submitting

- [ ] Tests pass locally (`python -m pytest tests/ -q`)
- [ ] No new warnings introduced
- [ ] No new dependencies added (unless absolutely necessary and discussed in the issue)
- [ ] Code is sync-first (no async/await)
- [ ] CHANGELOG.md updated with your change under the correct version heading
- [ ] Commit messages follow the convention below

---

## Style Guide

### Python

- **Sync-first** — no async. Parallelism via `concurrent.futures.ThreadPoolExecutor`.
- **Mock all external APIs** in tests.
- **Use `cache_get`/`cache_set`** from `persistence.py` for API response caching.
- **Prefer deletion over abstraction** — YAGNI. When in doubt, leave it out.
- **Lucide SVGs** for all UI icons — no emojis where an SVG serves the same purpose.
- **AGPL v3 header** — new files should include the license header comment.

### What to Avoid

| Don't | Why |
|-------|-----|
| New dependencies without strong reason | Every dep is a maintenance burden and a supply-chain risk |
| Async patterns | This project is sync-first; parallelism uses `ThreadPoolExecutor` |
| Patching symptoms instead of root causes | Fix the source, not the surface |
| Features requiring paid APIs | Keeps the project free for everyone |
| Large monolithic PRs | One logical change per PR makes reviews faster |

---

## Commit Conventions

Use conventional commit prefixes. This keeps the changelog auto-readable and helps reviewers understand the scope at a glance.

| Prefix | When to use |
|--------|-------------|
| `feat:` | New feature or enhancement |
| `fix:` | Bug fix |
| `test:` | Adding or updating tests |
| `docs:` | Documentation, README, CHANGELOG |
| `refactor:` | Code restructuring with no behavior change |
| `perf:` | Performance improvement |
| `style:` | Formatting, linting, whitespace |
| `chore:` | Build config, CI, tooling |

**Examples:**

```
feat: add L2 disk cache for price history
fix: handle NaN avg_vol in ETF volume spike detection
test: add regression test for RSI division by zero
docs: update README with 3-tier cache overview
```

---

## Review Process

1. Maintainer reviews within a few days.
2. You may be asked to make changes. This is normal — don't take it personally.
3. Once approved, the maintainer merges (squash). The commit message in the changelog is the PR title.

---

## License

By contributing, you agree that your contributions will be licensed under the **GNU AGPL v3** — same as the project. See [LICENSE](LICENSE).
