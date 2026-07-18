# AlphaCore — Autonomous Crypto Quant

A production-grade, multi-agent AI system that predicts cryptocurrency prices using LSTM deep learning models and FinBERT NLP sentiment analysis, then autonomously manages a crypto portfolio through four specialized agents: **Manager**, **Risk**, **Execution**, and **Portfolio Monitor**.

> **Mode:** Paper trading (Binance Testnet) — safe for real-world deployment demo.  
> **Target assets:** BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, ADA/USDT  
> **Status:** Production live — 24/7 automated trading via local scheduler + Neon Postgres + Vercel dashboard  
> **News sources:** CoinDesk RSS (active), CoinMarketCap Fear & Greed (active), Currents API (active), CryptoPanic (dormant — 403), CryptoCompare (dormant — needs key), cryptocurrency.cv (dormant — 402)

---

## Features

- **Data Pipeline** — fetches OHLCV candles (Binance), market data (CoinGecko), news (6 sources: CoinDesk RSS, CoinMarketCap, Currents API, CryptoPanic, CryptoCompare, cryptocurrency.cv), Fear & Greed Index
- **Multi-Source News** — `MultiSourceNewsClient` aggregates 3 active sources (CoinDesk RSS, CoinMarketCap, Currents API) with relevance filtering, dedup via SequenceMatcher ≥0.75, and per-source logging; 3 dormant sources documented for future activation
- **Technical Indicators** — RSI, MACD, Bollinger Bands, ATR, EMAs, returns, volatility via `pandas-ta`
- **Two ML Models Per Symbol** — `LSTMModel` for price direction (2-class, ~50% acc — random) and `LSTMClassifier` for volatility regime (sigmoid, 76–89% test acc)
- **Volatility Regime Prediction** — binary target from 4-candle price range vs 24-candle median; BCE loss, saves `_classifier_best.pt` checkpoints
- **Sentiment Analysis** — FinBERT (ProsusAI/finbert) with **exponential time-decay weighting** — `weight = 0.5^(age_hours / half_life_hours)` with `HALF_LIFE_HOURS=12.0`; headlines at 12h→50%, 24h→25%, 48h→6.25%; `avg_headline_age_hours` logged per headline batch
- **Multi-Agent Pipeline** — 5-node LangGraph StateGraph: monitor_exits → Manager → Risk → Execution → monitor_update (auto-exits detected and executed in the same cycle)
- **Manager Agent** — sentiment-primary trading; side determined by `abs(sentiment_score)` thresholds (`>0.30 BUY`, `<-0.30 SELL`); position halved in high-volatility regime; **holdings-aware filtering** skips BUY if symbol already held and SELL if no position exists; **paused mode** check skips new entry proposals when flag file exists (auto-exits still processed); pre-execution headline refresh via MultiSourceNewsClient
- **Dual Position Caps** — percentage-based (5% of portfolio) AND absolute dollar cap ($500 USD) — `min()` protects against portfolio-value bugs
- **Risk Management** — position sizing, concentration limits (≤20% per coin), total exposure caps (≤80%), drawdown circuit breaker (>15%), duplicate prevention, **correlation risk**, **SELL-without-holding guard** (spot-only safety)
- **Auto-Exit Monitoring** — `PortfolioMonitor.check_exit_conditions()` checks every open position against SL/TP each cycle; generates `ProposedTrade` with `is_auto_exit=True` that bypasses all risk checks
- **Trade Origin Tracking** — `trade_origin` column (`bot_sentiment`, `bot_auto_exit`, `manual`, `pre_tracking`) enables bot-only vs all-trades metric splitting in reporting
- **Alert Webhook** — Discord/Telegram alerts on: drawdown >10%, ≥2 failed trades in a cycle, scheduler job exceptions, scheduler crashes
- **Real Trading Fees** — `TRADING_FEE_PCT=0.001` (0.1%) deducted from realised P&L on both entry and exit legs; `fee_paid` persisted on `ExecutedTrade` and `Trade` DB table
- **Idempotency Lock** — file-based `FileLock` on `data_cache/.trading_cycle.lock` (5s timeout) prevents double execution when scheduler fires overlapping cycles
- **Kill Switch** — `POST /portfolio/pause-trading` writes a flag file; `POST /portfolio/resume-trading` deletes it; Manager Agent reads flag each cycle and skips new entry trades while allowing SL/TP exits
- **Mainnet Safety Guard** — two-env-var confirmation required for real-money trading: `BINANCE_TESTNET=false` AND `I_UNDERSTAND_THIS_IS_REAL_MONEY=true` must both be set, or a `RuntimeError` is raised
- **Paper Trading** — Binance Testnet integration with slippage modelling
- **REST API** — FastAPI with 15+ endpoints for portfolio, trades, signals, health, sentiment validation, pause/resume
- **Next.js Frontend** — dark-terminal themed dashboard with 6 pages: overview, wallet, signals, trades, risk, validation; live data via React Query polling (30s stale / 60s refetch); animated charts (Recharts, Framer Motion)
- **Persistent Storage** — PostgreSQL (Neon.tech) via SQLAlchemy ORM (10 tables: 6 paper-test + 4 real) with `is_sentiment_driven`, `signal_confidence`, `fee_paid`, `trade_origin` columns on `Trade`
- **Sentiment Validation** — win-rate color-coded metric, sample-size progress bar, win/loss sentiment comparison chart, statistical readiness gate (requires ≥30 trades)
- **Decoupled Processes** — `--mode trade` runs scheduler only, `--mode api` runs API server only — separate OS processes sharing the same database; deploy on different machines or hosting platforms
- **Scheduler** — APScheduler with 3 recurring jobs (trading cycle, cache refresh, health check) + one-shot model training on startup
- **Training Data** — 2 years of 1h OHLCV via Binance Mainnet (read-only, no API key needed)
- **CryptoPanic 403 Fast-Fail** — `RuntimeError` → `ValueError` on 403 response eliminates 9× retry waste per pair (3 retries × 3 nesting levels)
- **Real-Money Infrastructure (read-only)** — `main_real.py` runs as a completely separate process with isolated `real_*` database tables, its own Binance API credentials (read-only key), and zero impact on the paper-test system. Account-sync job pulls live balances/positions from the real Binance account every hour. **No order placement in this phase.**
- **Real-Money Safety Controls** — kill-switch API (`/real/safety/toggle` + `/real/safety/status`) with daily loss limit, max position cap, and trades-per-day limit enforced via `real_safety_check()`; dedicated `real_kill_switch` DB table with confirm-word toggle
- **Real-Money Dashboard Pages** — three Next.js pages under `/real` (Safety Controls, Positions, Portfolio/Wallet) accessible from the sidebar's REAL section alongside the existing DEMO section
- **Dockerized** — Docker Compose for one-command startup

---

## Tech Stack

| Layer | Technology |
|---|---|---|
| Language | Python 3.12 + TypeScript |
| Deep learning | PyTorch 2.x (CUDA 12.6) |
| NLP model | FinBERT (ProsusAI/finbert via HuggingFace) |
| Price model | LSTM (direction) + LSTMClassifier (volatility regime) |
| Agent framework | LangGraph 0.2+ |
| Crypto data | python-binance (Testnet + Mainnet read-only), CoinGecko API |
| News/sentiment | CoinDesk RSS, CoinMarketCap (Fear & Greed), Currents API, CryptoPanic, CryptoCompare, cryptocurrency.cv |
| Feature engineering | pandas, numpy, pandas-ta |
| Database | SQLAlchemy ORM, PostgreSQL (Neon.tech) |
| API server | FastAPI + Uvicorn |
| Dashboard | Next.js 16, TypeScript, Tailwind v4, shadcn/ui, Recharts, Framer Motion |
| Task scheduler | APScheduler |
| Package manager | uv (Python) / npm (frontend) |
| Deployment | Docker + Docker Compose |
| Logging | Python logging + rotating file handler |
| Timestamp handling | `src/utils/timestamps.py` — normalises datetime, unix, ISO 8601, plain strings |

---

## Getting Started

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Node.js 20+ (for frontend)
- Binance Testnet account ([sign up here](https://testnet.binance.vision/))

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd AlphaCore

# Create virtual environment and install dependencies with uv
uv venv
source .venv/bin/activate
uv sync

# Copy environment file and fill in your keys
cp .env.example .env
```

### Configuration

Edit `.env` with your API keys and preferences:

```env
BINANCE_API_KEY=your_testnet_api_key
BINANCE_API_SECRET=your_testnet_api_secret
BINANCE_TESTNET=true
COINGECKO_API_KEY=
COINMARKETCAP_API_KEY=
CURRENTS_API_KEY=
CRYPTOPANIC_API_KEY=
CRYPTOCOMPARE_API_KEY=
DATABASE_URL=postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
LOG_LEVEL=INFO
PORTFOLIO_INITIAL_CAPITAL=10000
MAX_POSITION_SIZE_PCT=0.05
MAX_POSITION_SIZE_USD=500
STOP_LOSS_PCT=0.03
TRADING_FEE_PCT=0.001
TRADING_PAUSED=False
TRADING_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,ADA/USDT
ALERT_WEBHOOK_URL=
```

---

## Usage

## System Modes

### Paper-Testing Entry Point

AlphaCore's paper-test entry point provides four modes:

```bash
# Scheduler only — runs trading cycles (no API server, no uvicorn)
python main.py --mode trade

# API server only (no scheduler)
python main.py --mode api

# Train LSTM models for all trading pairs, then exit
python main.py --mode train

# Launch the Streamlit dashboard
python main.py --mode dashboard
```

The default mode is `trade` — just `python main.py` starts the full system.

### Real-Money Infrastructure (Isolated)

A completely separate entry point with its own database tables and credentials:

```bash
# Run one read-only account-sync cycle (pull balances, write to real_* tables)
python main_real.py --mode sync

# Start the recurring account-sync daemon (every 1h)
python main_real.py --mode daemon
```

> **Read-only guarantee:** No order placement is implemented. The Binance API key should be created with read-only permissions only.

### Explore the API

When running in `trade` or `api` mode, visit **http://localhost:8000/docs** for Swagger UI.

### Frontend Dashboard

Start the Next.js frontend (requires Node.js 20+):

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** for the dark-terminal dashboard.

### Run all tests

```bash
pytest tests/
```

### Docker

```bash
docker-compose up --build
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|---|
| `GET` | `/` | Welcome message |
| `GET` | `/health` | Health check with DB status |
| `GET` | `/portfolio/history` | Portfolio snapshot history |
| `GET` | `/portfolio/metrics` | Aggregate performance metrics |
| `GET` | `/portfolio/wallet` | Wallet view: cash, live holdings with unrealized PnL, closed positions with realized PnL |
| `GET` | `/portfolio/cycles` | Recent agent cycle runs |
| `GET` | `/portfolio/positions` | Current open positions |
| `GET` | `/portfolio/sentiment-validation` | Validate sentiment trading edge (≥30 trades) |
| `POST` | `/portfolio/pause-trading` | Pause all new entry trades via flag file |
| `POST` | `/portfolio/resume-trading` | Delete pause flag, resume normal trading |
| `GET` | `/trades/history` | Trade history (optional `?symbol=` filter) |
| `GET` | `/trades/stats` | Trade statistics (counts, volume) |
| `GET` | `/trades/{trade_id}` | Single trade by UUID |
| `GET` | `/signals/latest` | Signals from most recent cycle |
| `GET` | `/signals/history` | Historical signals |
| `GET` | `/signals/summary` | Daily signal summary |
| `GET` | `/real/safety/status` | Real-account kill-switch status + limits |
| `POST` | `/real/safety/toggle` | Toggle real-account trading (requires `CONFIRM` word) |
| `GET` | `/real/portfolio/latest` | Real-account latest portfolio snapshot |
| `GET` | `/real/portfolio/positions` | Real-account open positions |
| `GET` | `/real/portfolio/history` | Real-account portfolio snapshot history |
| `GET` | `/real/trades/history` | Real-account trade history |

---

## Frontend Pages (Next.js)

| Page | Route | Description |
|---|---|---|
| **Overview** | `/` | KPI row (cash, positions, total value, active trades), pipeline stage strip, portfolio area chart, allocation donut, Fear & Greed gauge + countdown timer |
| **Wallet** | `/wallet` | Cash KPI (CountUp), live holdings grid (7 columns), closed positions table with artifact badge |
| **Signals** | `/signals` | Bullish/bearish/neutral KPI cards, signals table with sentiment bars and volatility badges, market sentiment indicator |
| **Trades** | `/trades` | Symbol + status filterable table, KPI row (total trades, win rate, P&L), KPI badges per status badge |
| **Risk** | `/risk` | VaR progress, concentration, exposure, drawdown cards with tiered colors; drawdown area chart, risk alerts |
| **Validation** | `/validation` | Win rate metric with color threshold bar, avg win/loss, sample progress bar, sentiment conviction bar chart |
| **Real: Controls** | `/real` | Kill-switch toggle (CONFIRM word), max position / daily loss / trades-per-day limits |
| **Real: Positions** | `/real/positions` | Real-account open positions table with current prices |
| **Real: Wallet** | `/real/wallet` | Real-account portfolio snapshot, cash balance, holdings |

---

## Architecture

The system runs a closed-loop trading cycle every hour:

```
DataPipeline         → fetch candles + news (MultiSourceNewsClient: CoinDesk RSS + CoinMarketCap + Currents) + market data
FeatureEngineer      → compute indicators + volatility regime target
Predictor            → LSTM direction (2-class) + LSTMClassifier vol regime (sigmoid) + FinBERT sentiment (exponential time-decay weighted, half-life=12h)
Monitor (check exits)→ detect SL/TP breaches on open positions, propose auto-exit trades
Manager Agent        → sentiment-primary: rank by |sentiment|, side from sentiment thresholds, holdings-aware filter (skip BUY if held / SELL if not held), apply USD + % position caps, skip if paused
Risk Agent           → screen each proposed trade (7 checks: size, concentration, exposure, drawdown, duplicate, correlation, SELL-without-holding; auto-exit bypasses all)
Execution Agent      → validate LOT_SIZE + MIN_NOTIONAL, round qty down to step size, fire orders to Binance Testnet, record fee_paid, set trade_origin
Monitor (update)     → update P&L, persist positions to DB, compute portfolio state
CRUD / Database      → persist everything to PostgreSQL (Neon.tech)
```

### Agent Roles

- **Manager Agent** — sentiment-primary trading; ranks signals by `|sentiment_score|`, side from thresholds (`>0.30 BUY`, `<-0.30 SELL`); applies dual position caps: `min(portfolio_pct_qty, usd_cap_qty)`; **holdings-aware filtering** skips BUY if symbol already held and SELL if no position exists (spot cannot short); preserves auto-exit trades from monitor_exits; checks pause flag at start of `run()` — skips new entries when paused, allows auto-exits through; pre-execution headline refresh via `MultiSourceNewsClient`
- **Risk Agent** — 7 independent checks: position size (≤5%), concentration (≤20% per coin), exposure (≤80%), drawdown (>15% halts), duplicate prevention, correlation risk (≥3 same-direction halves, ≥4 rejects), **SELL-without-holding guard** (rejects sell when no position held); trades with `is_auto_exit=True` bypass all checks
- **Execution Agent** — fetches live price, fetches symbol filters (LOT_SIZE stepSize, MIN_NOTIONAL), rounds quantity **down** to step size (never up, never exceeds), validates notional ≥ MIN_NOTIONAL, returns `REJECTED_LOT_SIZE` status for invalid orders; models random slippage (0–0.15%), calculates `fee_paid = qty × price × TRADING_FEE_PCT`, routes market orders to Binance Testnet
- **Portfolio Monitor** — two-stage: `check_exit_conditions()` (first) iterates open positions, queries SL/TP from DB, proposes auto-exits; `run()` (last) updates **fee-aware realised P&L** per filled trade, persists positions to DB (`query-then-update-or-insert`), computes total portfolio value and drawdown from peak; `trade_origin` set to `bot_auto_exit` on auto-exits, `bot_sentiment` on sentiment entries

---

## Performance

Live paper-trading since June 23, 2026 on Binance Testnet:

| Metric | Value |
|--------|-------|
| Initial capital | $10,000 |
| Current portfolio | ~$12,761 |
| Gross return | +27.6% |
| Peak value | $12,762 |
| Current drawdown | 0.00% from peak |
| Sentiment-driven trades | 17 tracked (57.1% win rate, +$11.57 PnL) |
| Bot-only trades | 10 SELLs (50.0% win rate, +$3.34 PnL) |
| All trades closed | 14 (7W/7L, avg win +$6.70, avg loss -$4.92, R:R 1.36:1) |
| Direction accuracy | ~50% (random — LSTM adds no alpha) |
| Volatility accuracy | 76–89% (useful for regime awareness) |

> **Honest assessment:** The return tracks the bullish market, not predictive skill. The direction LSTM performs at coin-flip level. The system's real value is its safety net — proper position sizing, stop-loss enforcement, LOT_SIZE validation, auto-exit detection, drawdown circuit breaker, and position reconciliation prevent catastrophic losses while the models improve.

---

## Database Schema

Ten SQLAlchemy ORM tables on PostgreSQL (Neon.tech) — 6 paper-test + 4 real:

| Table | Domain | Key Columns |
|---|---|---|
| `cycle_runs` | Test | `cycle_id` (UUID), signals/proposed/approved/executed counts, portfolio value, P&L, drawdown |
| `signals` | Test | FK → `cycle_runs.cycle_id`, symbol, predicted return, direction, confidence, sentiment score/label, Fear & Greed |
| `trades` | Test | FK → `cycle_runs.cycle_id`, symbol, side, proposed/executed qty + price, SL/TP, status, PnL, `trade_origin` |
| `positions` | Test | `symbol` (unique), quantity, avg entry price, current price, unrealised PnL |
| `portfolio_snapshots` | Test | FK → `cycle_runs.cycle_id`, total value, cash, positions value, P&L, peak value, drawdown |
| `portfolio_state` | Test | Singleton row, peak value, validation start date |
| `real_trades` | **Real** | `sync_id`, symbol, side, executed qty/price, order_id, status, PnL, fee |
| `real_positions` | **Real** | `symbol` (unique), quantity, avg entry price, current price, unrealised PnL |
| `real_portfolio_snapshots` | **Real** | `sync_id`, total value, cash, positions value, P&L, peak value, drawdown |
| `real_portfolio_state` | **Real** | Singleton row, peak value |

> Real tables are structurally separate — queries against test tables can never touch real data.

---

## Project Structure

```
AlphaCore/
├── CLAUDE.md                  # Master context file
├── README.md
├── .env.example
├── .gitignore
├── pyproject.toml             # Dependencies (uv/pip)
├── main.py                    # Paper-test entry point (4 modes)
├── main_real.py               # Real-money infrastructure (isolated, read-only)
├── docker-compose.yml
├── Dockerfile
├── frontend/                  # Next.js 16 dashboard
│   ├── app/                   # App router pages + layout
│   ├── components/            # shadcn/ui + custom components
│   ├── hooks/                 # React Query hooks
│   └── lib/                   # API client + types + utils
├── src/
│   ├── data/                  # Data fetching & feature engineering
│   │   ├── binance_client.py
│   │   ├── binance_real_client.py # Read-only real-account client (no trade capability)
│   │   ├── coingecko_client.py
│   │   ├── rss_news_client.py     # CoinDesk RSS (free, no API key)
│   │   ├── coinmarketcap_client.py # Fear & Greed + Global Metrics
│   │   ├── currents_client.py     # Currents API news (active)
│   │   ├── cryptopanic_client.py  # CryptoPanic news (dormant — 403)
│   │   ├── cryptocompare_client.py# CryptoCompare news (dormant — needs key)
│   │   ├── cryptocurrency_cv_client.py # cryptocurrency.cv (dormant — 402)
│   │   ├── gnews_client.py        # GNews API (dormant — 12h delay)
│   │   ├── multi_source_news.py   # Aggregator: 3 active, 3 dormant
│   │   ├── reddit_client.py
│   │   ├── yahoo_client.py
│   │   ├── feature_engineer.py
│   │   └── data_pipeline.py
│   ├── models/                # ML models
│   │   ├── lstm_model.py
│   │   ├── tft_model.py
│   │   ├── sentiment_model.py
│   │   ├── trainer.py
│   │   └── predictor.py
│   ├── agents/                # LangGraph agent system
│   │   ├── agent_state.py
│   │   ├── manager_agent.py
│   │   ├── risk_agent.py
│   │   ├── execution_agent.py
│   │   ├── portfolio_monitor.py
│   │   └── __init__.py
│   ├── database/              # SQLAlchemy ORM & CRUD
│   │   ├── connection.py
│   │   ├── models.py
│   │   ├── crud.py
│   │   ├── real_crud.py       # Real-trading CRUD (isolated from test data)
│   │   └── real_safety.py     # Kill-switch + safety limits for real-money
│   ├── api/                   # FastAPI REST endpoints
│   │   ├── main.py
│   │   ├── schemas.py
│   │   └── routes/
│   │       ├── portfolio.py
│   │       ├── trades.py
│   │       ├── signals.py
│   │       ├── real_portfolio.py
│   │       ├── real_trades.py
│   │       └── real_safety.py
│   ├── dashboard/             # Streamlit UI
│   │   ├── app.py
│   │   ├── components/
│   │   │   ├── metrics.py
│   │   │   └── charts.py
│   │   └── pages/
│   │       ├── overview.py
│   │       ├── signals.py
│   │       ├── trades.py
│   │       ├── risk.py
│   │       └── validation.py
│   ├── scheduler/             # APScheduler job definitions
│   │   ├── __init__.py
│   │   ├── job_runner.py      # SchedulerRunner class (lifecycle, signal handling)
│   │   └── jobs.py            # 4 job functions (trading cycle, cache, health, training)
│   └── utils/                 # Config, logging, helpers
│       ├── config.py
│       ├── logger.py
│       ├── helpers.py
│       └── timestamps.py      # datetime/unix/ISO 8601 normalisation
│
├── models_saved/              # Trained model checkpoints ({sym}_lstm_best.pt, {sym}_classifier_best.pt)
├── artifacts/                 # Scaler params + training config + per-symbol metrics JSON
├── data_cache/                # Cached OHLCV CSVs
├── logs/                      # Rotating log files
├── .streamlit/
│   └── config.toml            # Streamlit config (headless mode)
│
└── tests/
    ├── test_data/
    ├── test_models/
    ├── test_agents/
    └── test_api/
```

---

## Development Phases

| Phase | Description | Status |
|---|---|---|---|
| Phase 1 | Project scaffold (config, logging, dependencies) | ✅ Complete |
| Phase 2 | Data pipeline (Binance, CoinGecko, RSS, features) | ✅ Complete |
| Phase 3 | ML models (LSTM, TFT, FinBERT, training loop) | ✅ Complete |
| Phase 4 | Agent system (LangGraph agents, state management) | ✅ Complete |
| Phase 5 | Database (SQLAlchemy models, CRUD, connection) | ✅ Complete |
| Phase 6 | API server (FastAPI routes, Pydantic schemas) | ✅ Complete |
| Phase 7 | Dashboard (Streamlit pages, Plotly charts) | ✅ Complete |
| Phase 8 | Scheduler + dual-model training (direction + vol regime, manager filters) | ✅ Complete |
| Phase 9 | Docker deployment (Dockerfile, Compose) | ⏳ Pending |
| Phase 10 | Testing (pytest suite for all modules) | ⏳ Pending |
| Phase 11 | Next.js frontend (TypeScript, shadcn/ui, Recharts, React Query) | ✅ Complete |
| Phase 12 | Mainnet safety guard, USD cap, alert webhook, LOT_SIZE validation | ✅ Complete |
| Phase 13 | PnL recording fix (avg_entry lookup at execution time, pre-fix artifact labeling) | ✅ Complete |
| Phase 14 | Position decrement on SELL fix, wallet endpoint + frontend wallet page | ✅ Complete |
| Phase 15 | Cycle integrity validation, position reconciliation, auto-pause on drawdown | ✅ Complete |
| Phase 16 | Cash-from-trades fix (W01/W02), dynamic portfolio value | ✅ Complete |
| Phase 17 | Multi-source news client (Currents, GNews, CryptoPanic, CryptoCompare, CoinMarketCap, cryptocurrency.cv) | ✅ Complete |
| Phase 18 | Exponential decay sentiment weighting (half-life 12h) + shared timestamp normalisation | ✅ Complete |
| Phase 19 | Trade origin tracking (`bot_sentiment`, `bot_auto_exit`, `manual`, `pre_tracking`) | ✅ Complete |
| Phase 20 | Holdings-aware signal filtering (skip BUY if held, skip SELL if not held) | ✅ Complete |
| Phase 21 | CryptoPanic 403 fast-fail (ValueError → 0 retries instead of RuntimeError → 9 retries) | ✅ Complete |
| Phase 22 | Real-money infrastructure: isolated `real_*` tables, read-only Binance client, separate `main_real.py` entry point, `--mode sync`/`daemon` | ✅ Complete |
| Phase 23 | Real-money API endpoints (`/real/portfolio`, `/real/trades`, `/real/safety`) with kill-switch controls | ✅ Complete |
| Phase 24 | Next.js real-account pages (`/real` controls, `/real/positions`, `/real/wallet`) in DEMO/REAL sidebar | ✅ Complete |

---

## License

MIT
