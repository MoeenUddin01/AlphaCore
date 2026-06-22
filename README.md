# AlphaCore — Autonomous Crypto Quant

A production-grade, multi-agent AI system that predicts cryptocurrency prices using LSTM deep learning models and FinBERT NLP sentiment analysis, then autonomously manages a crypto portfolio through four specialized agents: **Manager**, **Risk**, **Execution**, and **Portfolio Monitor**.

> **Mode:** Paper trading (Binance Testnet) — safe for real-world deployment demo.  
> **Target assets:** BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, ADA/USDT

---

## Features

- **Data Pipeline** — fetches OHLCV candles (Binance), market data (CoinGecko), news (CoinDesk RSS), Fear & Greed Index
- **Technical Indicators** — RSI, MACD, Bollinger Bands, ATR, EMAs, returns, volatility via `pandas-ta`
- **Two ML Models Per Symbol** — `LSTMModel` for price direction (2-class, ~50% acc) and `LSTMClassifier` for volatility regime (sigmoid, ~83% acc)
- **Volatility Regime Prediction** — binary target from 4-candle price range vs 24-candle median; BCE loss, saves `_classifier_best.pt` checkpoints
- **Sentiment Analysis** — FinBERT (ProsusAI/finbert) with **time-decay weighting** — fresher headlines contribute more via linear decay over 24h (10% floor); `avg_headline_age_hours` logged per headline batch
- **Multi-Agent Pipeline** — 5-node LangGraph StateGraph: monitor_exits → Manager → Risk → Execution → monitor_update
- **Manager Agent (Option A)** — sentiment-primary trading; side determined solely by `abs(sentiment_score)` thresholds (`>0.30 BUY`, `<-0.30 SELL`); position halved in high-volatility regime; **paused mode** check skips new entry proposals when flag file exists (auto-exits still processed)
- **Dual Position Caps** — percentage-based (5% of portfolio) AND absolute dollar cap ($500 USD) — `min()` protects against portfolio-value bugs
- **Risk Management** — position sizing, concentration limits (≤20% per coin), total exposure caps (≤80%), drawdown circuit breaker (>15%), duplicate prevention, **correlation risk**, **SELL-without-holding guard** (spot-only safety)
- **Auto-Exit Monitoring** — `PortfolioMonitor.check_exit_conditions()` checks every open position against SL/TP each cycle; generates `ProposedTrade` with `is_auto_exit=True` that bypasses all risk checks
- **Alert Webhook** — Discord/Telegram alerts on: drawdown >10%, ≥2 failed trades in a cycle, scheduler job exceptions, scheduler crashes
- **Real Trading Fees** — `TRADING_FEE_PCT=0.001` (0.1%) deducted from realised P&L on both entry and exit legs; `fee_paid` persisted on `ExecutedTrade` and `Trade` DB table
- **Idempotency Lock** — file-based `FileLock` on `data_cache/.trading_cycle.lock` (5s timeout) prevents double execution when scheduler fires overlapping cycles
- **Kill Switch** — `POST /portfolio/pause-trading` writes a flag file; `POST /portfolio/resume-trading` deletes it; Manager Agent reads flag each cycle and skips new entry trades while allowing SL/TP exits
- **Mainnet Safety Guard** — two-env-var confirmation required for real-money trading: `BINANCE_TESTNET=false` AND `I_UNDERSTAND_THIS_IS_REAL_MONEY=true` must both be set, or a `RuntimeError` is raised
- **Paper Trading** — Binance Testnet integration with slippage modelling
- **REST API** — FastAPI with 15+ endpoints for portfolio, trades, signals, health, sentiment validation, pause/resume
- **Next.js Frontend** — dark-terminal themed dashboard with 5 pages: overview, signals, trades, risk, validation; live data via React Query polling; animated charts (Recharts, Framer Motion)
- **Persistent Storage** — SQLite via SQLAlchemy ORM (6 tables) with `is_sentiment_driven`, `signal_confidence`, `fee_paid` columns on `Trade`
- **Sentiment Validation** — win-rate color-coded metric, sample-size progress bar, win/loss sentiment comparison chart, statistical readiness gate (requires ≥30 trades)
- **Automated Scheduling** — 4-mode CLI entry point: `trade` (full stack), `api` (server only), `train` (LSTM training), `dashboard` (Streamlit); frontend started separately via `npm run dev`
- **Scheduler** — APScheduler with 3 recurring jobs (trading cycle, cache refresh, health check) + one-shot model training on startup
- **Training Data** — 2 years of 1h OHLCV via Binance Mainnet (read-only, no API key needed)
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
| News/sentiment | CoinDesk RSS (free, no API key) |
| Feature engineering | pandas, numpy, pandas-ta |
| Database | SQLAlchemy ORM, SQLite (dev) |
| API server | FastAPI + Uvicorn |
| Dashboard | Next.js 16, TypeScript, Tailwind v4, shadcn/ui, Recharts, Framer Motion |
| Task scheduler | APScheduler |
| Package manager | uv (Python) / npm (frontend) |
| Deployment | Docker + Docker Compose |
| Logging | Python logging + rotating file handler |

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
DATABASE_URL=sqlite:///./alphacore.db
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

AlphaCore provides a single entry point with four modes:

```bash
# Full trading system — API server (background) + scheduler (foreground)
python main.py --mode trade

# API server only (no scheduler)
python main.py --mode api

# Train LSTM models for all trading pairs, then exit
python main.py --mode train

# Launch the Streamlit dashboard
python main.py --mode dashboard
```

The default mode is `trade` — just `python main.py` starts the full system.

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
|---|---|---|
| `GET` | `/` | Welcome message |
| `GET` | `/health` | Health check with DB status |
| `GET` | `/portfolio/history` | Portfolio snapshot history |
| `GET` | `/portfolio/metrics` | Aggregate performance metrics |
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

---

## Frontend Pages (Next.js)

| Page | Route | Description |
|---|---|---|
| **Overview** | `/` | KPI row (cash, positions, total value, active trades), pipeline stage strip, portfolio area chart, allocation donut, Fear & Greed gauge + countdown timer |
| **Signals** | `/signals` | Bullish/bearish/neutral KPI cards, signals table with sentiment bars and volatility badges, market sentiment indicator |
| **Trades** | `/trades` | Symbol + status filterable table, KPI row (total trades, win rate, P&L), KPI badges per status badge |
| **Risk** | `/risk` | VaR progress, concentration, exposure, drawdown cards with tiered colors; drawdown area chart, risk alerts |
| **Validation** | `/validation` | Win rate metric with color threshold bar, avg win/loss, sample progress bar, sentiment conviction bar chart |

---

## Architecture

The system runs a closed-loop trading cycle every hour:

```
DataPipeline         → fetch candles + news + market data
FeatureEngineer      → compute indicators + volatility regime target
Predictor            → LSTM direction (2-class) + LSTMClassifier vol regime (sigmoid) + FinBERT sentiment (time-decay weighted)
Monitor (check exits)→ detect SL/TP breaches on open positions, propose auto-exit trades
Manager Agent        → sentiment-primary: rank by |sentiment|, side from sentiment thresholds, apply USD + % position caps, skip if paused
Risk Agent           → screen each proposed trade (7 checks: size, concentration, exposure, drawdown, duplicate, correlation, SELL-without-holding; auto-exit bypasses all)
Execution Agent      → validate LOT_SIZE + MIN_NOTIONAL, round qty down to step size, fire orders to Binance Testnet, record fee_paid
Monitor (update)     → update P&L, persist positions to DB, compute portfolio state
CRUD / Database      → persist everything to SQLite
```

### Agent Roles

- **Manager Agent** — sentiment-primary trading; ranks signals by `|sentiment_score|`, side from thresholds (`>0.30 BUY`, `<-0.30 SELL`); applies dual position caps: `min(portfolio_pct_qty, usd_cap_qty)`; preserves auto-exit trades from monitor_exits; checks pause flag at start of `run()` — skips new entries when paused, allows auto-exits through
- **Risk Agent** — 7 independent checks: position size (≤5%), concentration (≤20% per coin), exposure (≤80%), drawdown (>15% halts), duplicate prevention, correlation risk (≥3 same-direction halves, ≥4 rejects), **SELL-without-holding guard** (rejects sell when no position held); trades with `is_auto_exit=True` bypass all checks
- **Execution Agent** — fetches live price, fetches symbol filters (LOT_SIZE stepSize, MIN_NOTIONAL), rounds quantity **down** to step size (never up, never exceeds), validates notional ≥ MIN_NOTIONAL, returns `REJECTED_LOT_SIZE` status for invalid orders; models random slippage (0–0.15%), calculates `fee_paid = qty × price × TRADING_FEE_PCT`, routes market orders to Binance Testnet
- **Portfolio Monitor** — two-stage: `check_exit_conditions()` (first) iterates open positions, queries SL/TP from DB, proposes auto-exits; `run()` (last) updates **fee-aware realised P&L** per filled trade, persists positions to DB (`query-then-update-or-insert`), computes total portfolio value and drawdown from peak

---

## Database Schema

Six SQLAlchemy ORM tables:

| Table | Key Columns |
|---|---|---|
| `cycle_runs` | `cycle_id` (UUID), signals/proposed/approved/executed counts, portfolio value, P&L, drawdown, `cycle_log` (JSON) |
| `signals` | FK → `cycle_runs.cycle_id`, symbol, predicted return, direction, confidence, sentiment score/label, Fear & Greed |
| `trades` | FK → `cycle_runs.cycle_id`, symbol, side, proposed/executed quantity + price, stop-loss, take-profit, status, PnL, `is_sentiment_driven` (Boolean), `signal_confidence` (Numeric), `fee_paid` (Numeric) |
| `positions` | `symbol` (unique), quantity, avg entry price, current price, unrealised PnL |
| `portfolio_snapshots` | FK → `cycle_runs.cycle_id`, total value, cash, positions value, P&L, peak value, drawdown |
| `portfolio_state` | Singleton row, holdings JSON, last updated timestamp |

---

## Project Structure

```
AlphaCore/
├── CLAUDE.md                  # Master context file
├── README.md
├── .env.example
├── .gitignore
├── pyproject.toml             # Dependencies (uv/pip)
├── main.py                    # Single entry point (4 modes)
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
│   │   ├── coingecko_client.py
│   │   ├── rss_news_client.py # CoinDesk RSS (free, no API key)
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
│   │   └── crud.py
│   ├── api/                   # FastAPI REST endpoints
│   │   ├── main.py
│   │   ├── schemas.py
│   │   └── routes/
│   │       ├── portfolio.py
│   │       ├── trades.py
│   │       └── signals.py
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
│       └── helpers.py
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

---

## License

MIT
