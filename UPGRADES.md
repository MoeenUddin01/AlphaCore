# UPGRADES.md — AlphaCore Post-30-Trade Upgrade Plan

> Created: 2026-07-07
> Trigger: After 30 sentiment-tracked trades reached (currently 12/30)
> Status: PLANNED — not yet started

---

## Table of Contents
1. [Critical — Core Alpha](#1-critical--core-alpha)
2. [High Priority — Risk & Safety](#2-high-priority--risk--safety)
3. [High Priority — Data Pipeline](#3-high-priority--data-pipeline)
4. [Medium Priority — Frontend](#4-medium-priority--frontend)
5. [Medium Priority — Backend](#5-medium-priority--backend)
6. [Low Priority — Infrastructure](#6-low-priority--infrastructure)
7. [Low Priority — Code Quality](#7-low-priority--code-quality)
8. [Daily Report](#8-daily-report)

---

## 1. Critical — Core Alpha

These directly impact whether the system makes money.

### U01 — Fix Direction LSTM (Core Bottleneck)
- **File:** `src/models/lstm_model.py`
- **Issue:** Direction LSTM outputs ~50% confidence for all pairs — random coin flip. val_loss stuck at ~0.693 (log loss of random guess). The model learns nothing.
- **Fix needed:**
  - Increase training data (currently only 2951 rows from Mainnet)
  - Add more features: funding rate, open interest, volume profile
  - Try different architectures: Transformer, TCN, or ensemble
  - Add walk-forward validation instead of simple train/val split
  - Consider removing direction model entirely if it can't beat random

### U02 — Add Profit-Taking Strategy
- **File:** `src/agents/manager_agent.py`
- **Issue:** Only exit triggers are SL (-3%) and TP (+6%). No graduated profit-taking.
- **Fix needed:**
  - Scale out at intervals: sell 25% at +3%, 25% at +6%, 25% at +9%, trail last 25%
  - Or: move stop loss to breakeven after +3% gain
  - Or: trailing stop loss (e.g., trail at 2% below highest price since entry)

### U03 — Position Cooldown
- **File:** `src/agents/manager_agent.py`
- **Issue:** System can re-buy the same coin immediately after selling. No cooldown period.
- **Fix needed:**
  - Track last sell timestamp per symbol in PortfolioState
  - Block new BUY for same symbol within N hours of last SELL
  - Configurable cooldown period (e.g., `POSITION_COOLDOWN_HOURS=4`)

### U04 — Sentiment Model Improvement
- **File:** `src/models/sentiment_model.py`
- **Issue:** FinBERT gives mostly neutral (0.0) scores. CoinDesk RSS returns 0-2 articles per cycle. 33% win rate on validation trades.
- **Fix needed:**
  - Add more news sources: The Block, Decrypt, CoinTelegraph (RSS or API)
  - Add Reddit/Twitter sentiment (optional, paid APIs)
  - Fine-tune FinBERT on crypto-specific headlines
  - Weight recent articles more heavily (time decay)
  - Combine with Fear & Greed index as secondary signal

---

## 2. High Priority — Risk & Safety

### U05 — Real VaR Model
- **File:** `src/agents/risk_agent.py`
- **Issue:** Portfolio VaR on frontend is hardcoded `totalValue * 0.02` — not a real Value-at-Risk calculation.
- **Fix needed:**
  - Implement Historical VaR using rolling returns window
  - Implement Parametric VaR (assumes normal distribution)
  - Add Conditional VaR (Expected Shortfall)
  - Show VaR per position and portfolio-wide
  - Configurable confidence level (95%, 99%)

### U06 — API Authentication
- **File:** `src/api/main.py`, `src/api/routes/`
- **Issue:** All API endpoints are wide open — anyone with the URL can view portfolio, trigger sells, pause trading.
- **Fix needed:**
  - Add API key authentication (simple bearer token)
  - Add rate limiting per endpoint
  - Add CORS properly (currently allows all origins)
  - Consider: JWT tokens for dashboard sessions

### U07 — Max Daily Loss Limit
- **File:** `src/agents/risk_agent.py`
- **Issue:** Only circuit breaker is drawdown > 15% from peak. No daily loss limit.
- **Fix needed:**
  - Track daily P&L in PortfolioState
  - Block new trades if daily loss exceeds threshold (e.g., -$200)
  - Reset daily counter at midnight UTC
  - Configurable: `MAX_DAILY_LOSS_USD=200`

### U08 — Position Correlation Guard
- **File:** `src/agents/risk_agent.py`
- **Issue:** Correlation check exists but is basic. Doesn't prevent correlated drawdowns.
- **Fix needed:**
  - Compute rolling correlation matrix between held assets
  - Reduce position size when correlation > 0.8
  - Alert when portfolio becomes too correlated
  - Consider: maximum portfolio entropy (diversification score)

---

## 3. High Priority — Data Pipeline

### U09 — Expand News Sources
- **File:** `src/data/rss_news_client.py`
- **Issue:** Only CoinDesk RSS (25 articles). Returns 0-2 articles per cycle for most coins. SOL has 0 coverage. Most sentiment scores are 0.0 (neutral).
- **Verified free RSS feeds (no API key):**
  - CoinDesk (current): `https://www.coindesk.com/arc/outboundfeeds/rss/` — 25 articles
  - **U.Today:** `https://u.today/rss` — 93 articles (BTC:34, ETH:14, SOL:4, BNB:3, ADA:4)
  - **Crypto.News:** `https://crypto.news/feed/` — 50 articles (BTC:11, ETH:8, SOL:5, BNB:1, ADA:1)
  - **Decrypt:** `https://decrypt.co/feed` — 35 articles (BTC:6, ETH:3, SOL:2, BNB:2)
  - **CoinTelegraph:** `https://cointelegraph.com/rss` — 30 articles (BTC:11, ETH:4, SOL:1)
  - ~~The Block: `https://www.theblock.co/rss.xml` — 0 articles (feed broken)~~
  - ~~Bitcoin Magazine: `https://bitcoinmagazine.com/feed` — BTC only, no alts~~
- **Impact:** Adding 4 feeds = 233 total articles vs 25 now (9x increase)
  - BTC: 8 → 72 matches, ETH: 1 → 27, SOL: 0 → 12, BNB: 2 → 8, ADA: 1 → 6
- **Fix needed:**
  - Add all 4 working RSS feeds to `RSS_FEEDS` dict in `rss_news_client.py`
  - Deduplicate across sources (same article appears on multiple sites)
  - Increase per-symbol keyword matching (currently exact match)

### U10 — Fix CoinDesk RSS Keyword Matching
- **File:** `src/data/rss_news_client.py`
- **Issue:** Keyword matching is too strict. "Bitcoin" matches but "BTC" doesn't always match.
- **Fix needed:**
  - Add fuzzy matching (Levenshtein distance)
  - Match on both full name and ticker (Bitcoin/BTC, Ethereum/ETH)
  - Add category/tag matching from RSS feed
  - Score relevance based on keyword position in title vs body

### U11 — On-Chain Data Integration
- **File:** `src/data/coingecko_client.py`
- **Issue:** CoinGecko data fetched but barely used in model features.
- **Fix needed:**
  - Add active addresses, transaction count, exchange inflow/outflow
  - Add NVT ratio (Network Value to Transactions)
  - Add MVRV ratio (Market Value to Realized Value)
  - Feed into model as additional features

### U12 — Order Book Depth
- **File:** `src/data/binance_client.py`
- **Issue:** No order book analysis. System trades blindly without liquidity info.
- **Fix needed:**
  - Fetch order book depth (top 20 levels)
  - Calculate bid/ask spread
  - Calculate order book imbalance (bid volume / ask volume)
  - Add as feature to model
  - Use for execution: avoid large orders when book is thin

---

## 4. Medium Priority — Frontend

### U13 — Dashboard KPI Polish (W05)
- **Files:** `frontend/components/dashboard/*.tsx`
- **Issue:** KPI cards are plain. No visual hierarchy.
- **Fix needed:**
  - Gradient backgrounds for KPI cards
  - Glow effect on positive/negative values
  - Thicker chart lines (currently 1px)
  - Hover states with tooltips
  - Animate value changes (count-up animation)

### U14 — Real-Time Price Ticker
- **File:** `frontend/components/dashboard/`
- **Issue:** Prices update every 30s via polling. No WebSocket.
- **Fix needed:**
  - Add WebSocket connection to Binance Testnet
  - Stream real-time prices to frontend
  - Update charts in real-time
  - Show price flash on change (green/red)

### U15 — Trade History Filters
- **File:** `frontend/app/trades/page.tsx`
- **Issue:** Trade history has no filters. Hard to find specific trades.
- **Fix needed:**
  - Filter by symbol (dropdown)
  - Filter by side (BUY/SELL)
  - Filter by date range
  - Filter by P&L (winners/losers)
  - Sort by any column
  - Export to CSV

### U16 — Risk Dashboard Improvements
- **File:** `frontend/app/risk/page.tsx`
- **Issue:** Risk page is minimal. No visual risk metrics.
- **Fix needed:**
  - Portfolio heatmap (correlation matrix)
  - Drawdown chart over time
  - VaR chart with confidence intervals
  - Position exposure bar chart
  - Risk score gauge (0-100)

### U17 — Mobile Responsiveness
- **Files:** `frontend/app/**/*.tsx`
- **Issue:** Pages not optimized for mobile. Tables overflow.
- **Fix needed:**
  - Responsive grid layouts
  - Collapsible sidebar
  - Touch-friendly buttons
  - Mobile-optimized tables (card layout on small screens)

---

## 5. Medium Priority — Backend

### U18 — Replace Deprecated datetime.utcnow()
- **Files:** `src/database/crud.py`, `src/database/models.py`, `src/agents/*.py`
- **Issue:** `datetime.utcnow()` is deprecated in Python 3.12+. 17 occurrences across codebase.
- **Fix needed:**
  - Replace all `datetime.utcnow()` with `datetime.now(timezone.utc)`
  - Import `timezone` from `datetime`
  - Files affected:
    - `src/database/crud.py` (lines 56, 160, 371, 384, 740)
    - `src/database/models.py` (lines 60, 90, 108, 122, 144)
    - `src/agents/portfolio_monitor.py` (lines 45, 166, 255)
    - `src/agents/execution_agent.py` (line 73)
    - `src/agents/risk_agent.py` (line 235)
    - `src/agents/manager_agent.py` (line 151)
    - `src/agents/__init__.py` (line 82)

### U19 — Remove Dead Code
- **Files:** `src/data/cryptocompare_client.py`, `src/data/cryptopanic_client.py`, `src/dashboard/`
- **Issue:** CryptoCompare and CryptoPanic clients exist but are never imported/used. Streamlit dashboard exists but Next.js replaced it.
- **Fix needed:**
  - Delete `src/data/cryptocompare_client.py` (147 lines)
  - Delete `src/data/cryptopanic_client.py` (116 lines)
  - Delete `src/dashboard/` directory (entire Streamlit dashboard)
  - Remove any references in `requirements.txt`
  - Clean up `.env.example` (remove `CRYPTOPANIC_API_KEY`, `CRYPTOCOMPARE_API_KEY`)

### U20 — API Pagination
- **File:** `src/api/routes/trades.py`, `src/api/routes/portfolio.py`
- **Issue:** Endpoints return all records. No pagination. Will slow down as data grows.
- **Fix needed:**
  - Add `page` and `per_page` query parameters
  - Default: 50 records per page
  - Add `total_count` and `has_more` to response
  - Add cursor-based pagination for large datasets

### U21 — Database Indexes
- **File:** `src/database/models.py`
- **Issue:** No explicit indexes on frequently queried columns.
- **Fix needed:**
  - Add index on `Trade.created_at`
  - Add index on `Trade.symbol`
  - Add index on `Trade.status`
  - Add composite index on `(Trade.symbol, Trade.status)`
  - Add index on `PortfolioSnapshot.created_at`
  - Add index on `CycleRun.created_at`

### U22 — Graceful Shutdown
- **File:** `main.py`, `src/scheduler/jobs.py`
- **Issue:** Scheduler killed with SIGTERM leaves incomplete cycles. No graceful shutdown.
- **Fix needed:**
  - Register signal handlers (SIGTERM, SIGINT)
  - Wait for current cycle to complete before exiting
  - Save state to DB on shutdown
  - Log shutdown reason

---

## 6. Low Priority — Infrastructure

### U23 — Docker Setup
- **Files:** `Dockerfile`, `docker-compose.yml`
- **Issue:** Both files are empty (0 bytes). No containerization.
- **Fix needed:**
  - Write `Dockerfile` for Python backend (multi-stage build)
  - Write `docker-compose.yml` with:
    - `scheduler` service (mode=trade)
    - `api` service (mode=api)
    - `postgres` service (for local dev)
    - `frontend` service (Node.js)
  - Add health checks
  - Add volume mounts for logs and model checkpoints
  - Add environment variable configuration

### U24 — Auto-Start on Boot
- **Issue:** Scheduler and API must be manually started after machine reboot.
- **Fix needed:**
  - Create systemd service files for Linux
  - Or: crontab `@reboot` entries
  - Or: Docker Compose with `restart: always`
  - Files:
    - `/etc/systemd/system/alpha-scheduler.service`
    - `/etc/systemd/system/alpha-api.service`

### U25 — Log Rotation
- **File:** `src/utils/logger.py`
- **Issue:** Logs rotate by size but no maximum retention period.
- **Fix needed:**
  - Add max log age (e.g., 30 days)
  - Compress old logs (gzip)
  - Add log upload to cloud storage (optional)

### U26 — Monitoring & Alerting
- **Issue:** Only Discord/Telegram webhook for critical events. No monitoring dashboard.
- **Fix needed:**
  - Add Prometheus metrics endpoint
  - Add Grafana dashboard (optional)
  - Add uptime monitoring (UptimeRobot, BetterStack)
  - Add error tracking (Sentry)

---

## 7. Low Priority — Code Quality

### U27 — Type Hints Enforcement
- **Issue:** Type hints exist but not enforced. No mypy in CI.
- **Fix needed:**
  - Add `mypy` to `requirements.txt`
  - Add `mypy.ini` config
  - Add mypy step to `.github/workflows/tests.yml`
  - Fix any type errors

### U28 — Docstring Coverage
- **Issue:** Most functions have docstrings, but some are incomplete.
- **Fix needed:**
  - Add `interrogate` to check docstring coverage
  - Target: 100% function docstrings
  - Add return type documentation
  - Add example usage in docstrings

### U29 — Unit Test Coverage
- **Files:** `tests/test_data/`, `tests/test_models/`, `tests/test_api/`
- **Issue:** Test directories exist but are empty (only `__init__.py`). No tests for data layer, models, or API.
- **Fix needed:**
  - `tests/test_data/test_binance_client.py` — mock Binance API calls
  - `tests/test_data/test_rss_news_client.py` — mock RSS feed
  - `tests/test_data/test_feature_engineer.py` — test indicator calculations
  - `tests/test_models/test_sentiment_model.py` — test FinBERT scoring
  - `tests/test_models/test_lstm_model.py` — test model inference
  - `tests/test_api/test_portfolio.py` — test all portfolio endpoints
  - `tests/test_api/test_signals.py` — test signal endpoints
  - `tests/test_api/test_trades.py` — test trade endpoints
  - Target: 80% code coverage

### U30 — Ruff Linting
- **Issue:** No linter configured. Code style inconsistent.
- **Fix needed:**
  - Add `ruff` to `requirements.txt`
  - Add `ruff.toml` config
  - Add ruff check to `.github/workflows/tests.yml`
  - Fix all linting errors

### U31 — Security Audit
- **Issue:** No security scanning in CI.
- **Fix needed:**
  - Add `bandit` for Python security scanning
  - Add `safety` for dependency vulnerability checking
  - Add to CI pipeline
  - Fix any findings

---

## Summary — Priority Matrix

| Priority | ID | Description | Effort | Impact | Evidence |
|----------|----|-------------|--------|--------|----------|
| CRITICAL | U01 | Fix Direction LSTM | High | Core alpha | 50% confidence = random |
| CRITICAL | F01 | Sentiment not predictive | Medium | Signal quality | Winners/losers same score |
| CRITICAL | F02 | Stop loss too tight | Low | Risk mgmt | Selling at the bottom |
| CRITICAL | U02 | Profit-taking strategy | Medium | Returns | 1:1 risk/reward |
| CRITICAL | U03 | Position cooldown | Low | Risk mgmt | Quick trades lose |
| HIGH | F03 | Quick trades lose | Low | Strategy | <2h trades all lose |
| HIGH | F04 | Risk/reward 1:1 | Medium | Returns | Thin profits |
| HIGH | U04 | Sentiment improvement | Medium | Signal quality | 23.5% validation win rate |
| HIGH | U05 | Real VaR model | Medium | Risk mgmt | Hardcoded 2% |
| HIGH | U06 | API authentication | Low | Security | Wide open |
| HIGH | U07 | Daily loss limit | Low | Risk mgmt | No daily cap |
| HIGH | U08 | Correlation guard | Medium | Diversification | Basic check |
| HIGH | U09 | Expand news sources | Low | Data quality | 25 → 233 articles |
| HIGH | U10 | Fix keyword matching | Low | Data quality | False positives |
| HIGH | U11 | On-chain data | Medium | Features | CoinGecko barely used |
| HIGH | U12 | Order book depth | Medium | Execution | No liquidity info |
| MEDIUM | F05 | Long holds better | Low | Strategy | >48h = 62.5% win rate |
| MEDIUM | U13 | KPI polish | Low | UX | Plain cards |
| MEDIUM | U14 | WebSocket prices | Medium | Real-time | 30s polling |
| MEDIUM | U15 | Trade filters | Low | UX | No filters |
| MEDIUM | U16 | Risk dashboard | Medium | UX | Minimal |
| MEDIUM | U17 | Mobile responsive | Medium | UX | Desktop only |
| MEDIUM | U18 | Fix utcnow() | Low | Code quality | 17 occurrences |
| MEDIUM | U19 | Remove dead code | Low | Cleanup | 3 dead files |
| MEDIUM | U20 | API pagination | Low | Performance | No pagination |
| MEDIUM | U21 | Database indexes | Low | Performance | No indexes |
| MEDIUM | U22 | Graceful shutdown | Low | Reliability | Hard kill |
| LOW | U23 | Docker setup | Medium | Deployment | Empty files |
| LOW | U24 | Auto-start | Low | Ops | Done (crontab) |
| LOW | U25 | Log rotation | Low | Ops | No retention |
| LOW | U26 | Monitoring | Medium | Observability | Only webhook |
| LOW | U27 | Type hints | Low | Code quality | Not enforced |
| LOW | U28 | Docstrings | Low | Documentation | Incomplete |
| LOW | U29 | Unit tests | High | Quality | 4 empty dirs |
| LOW | U30 | Ruff linting | Low | Code quality | Not configured |
| LOW | U31 | Security audit | Low | Security | No scanning |

---

## 8. Testing Phase Observations (17 Trades)

> Added: 2026-07-11 after analyzing 17 completed trades

### Critical Findings

#### F01 — Sentiment Score Is NOT Predictive
- **Evidence:** Winners avg sentiment = +0.49, Losers avg sentiment = +0.51
- **Impact:** Sentiment-based BUY/SELL decisions are essentially random
- **Root cause:** FinBERT only sees 25 CoinDesk articles, most neutral
- **Fix:** U09 (expand news sources) + U04 (sentiment improvement)

#### F02 — Stop Loss Too Tight (-3%)
- **Evidence:** SOL stop loss triggered 2 times, BTC once — system sells at the bottom
- **Impact:** -3% SL causes $-10.49 loss on SOL (biggest single loss)
- **Fix:** U02 (profit-taking strategy) — consider wider SL (-5%) or trailing stop

#### F03 — Quick Trades Lose Money
- **Evidence:** Trades held <2 hours: 0 wins, 1 loss
- **Impact:** System enters and exits too fast — no time for price to move
- **Fix:** U03 (position cooldown) — minimum hold time before selling

#### F04 — Risk/Reward Ratio Is 1:1
- **Evidence:** Average win = +$5.36, Average loss = -$5.26
- **Impact:** Even with 53.8% win rate, profits are thin
- **Fix:** U02 (profit-taking) — let winners run, cut losers faster

#### F05 — Long Holds Perform Better
- **Evidence:** Trades held >48h: 5W/3L (62.5% win rate)
- **Impact:** System should hold positions longer
- **Fix:** U02 (trailing stop loss) + U03 (minimum hold time)

### Priority Updates Based on Findings

| Priority | ID | Description | Evidence |
|----------|----|-------------|----------|
| CRITICAL | F01 | Sentiment not predictive | Winners/losers same score |
| CRITICAL | F02 | Stop loss too tight | Selling at the bottom |
| HIGH | F03 | Quick trades lose | <2h trades all lose |
| HIGH | F04 | Risk/reward 1:1 | Thin profits |
| MEDIUM | F05 | Long holds better | >48h = 62.5% win rate |

### Recommended Action Order (Post-30 Trades)

1. **U09** — Expand news sources (fixes F01)
2. **U02** — Profit-taking strategy (fixes F02, F04, F05)
3. **U03** — Position cooldown (fixes F03)
4. **U04** — Sentiment improvement (fixes F01)
5. **U07** — Daily loss limit (safety net)

---

## 9. Daily Report

> Append daily status updates below this line after each trading day.

### 2026-07-07

**System Status:** Healthy
**Scheduler:** Running (PID 8728), last cycle 13:02 UTC
**API:** Running (PID 27660), ngrok active
**Frontend:** Vercel deployed, live at `https://frontend-taupe-iota-69.vercel.app`

**Portfolio:**
| Coin | Qty | Entry | Current | PnL% |
|------|-----|-------|---------|------|
| BTC | 0.00397 | $63,008 | $62,574 | -0.69% |
| ETH | 0.1415 | $1,768 | $1,751 | -0.95% |
| BNB | ~$250 | $577 | $568 | -1.60% |
| SOL | 3.105 | $80.51 | $78.35 | -2.68% |

**Cash:** $11,773
**Holdings:** ~$750
**Total Value:** ~$12,526
**Realised PnL:** +$38.22
**Unrealised PnL:** -$10.40 (all positions slightly down today)

**Sentiment Validation:**
- Trades tracked: 12/30 (40% complete)
- Win rate: 33.33% (all-time), 70% (recent 10)
- Strategy decay: No signal

**Risk Status:**
- Drawdown: 0% (below 10% threshold)
- SOL closest to stop loss: 0.3% away
- No positions near take profit

**Key Observations:**
1. SOL down 2.68% — approaching stop loss at $78.09 (0.3% away)
2. BNB down 1.60% — stop loss at $560 (1.4% away)
3. BTC and ETH also slightly red today
4. All positions within safe range but watch SOL closely
5. CoinDesk RSS returning very few articles — sentiment mostly neutral

**Actions Taken Today:**
- Added Exit Levels table to Wallet page (SL/TP visualization)
- Updated Status column to show both SL and TP distances
- Frontend deployed to Vercel

**Planned for Tomorrow:**
- Monitor SOL — if it hits $78.09, auto-sell triggers
- Continue collecting sentiment trades toward 30-trade threshold
- Review if news sources need expansion

---

*Last updated: 2026-07-07*
