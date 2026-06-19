# AlphaCore — Autonomous Crypto Quant

A production-grade, multi-agent AI system that predicts cryptocurrency prices using LSTM deep learning models and FinBERT NLP sentiment analysis, then autonomously manages a crypto portfolio through four specialized agents: **Manager**, **Risk**, **Execution**, and **Portfolio Monitor**.

> **Mode:** Paper trading (Binance Testnet) — safe for real-world deployment demo.  
> **Target assets:** BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, ADA/USDT

---

## Features

- **Data Pipeline** — fetches OHLCV candles (Binance), market data (CoinGecko), news (CryptoPanic), Fear & Greed Index, **funding rate**, **open interest**
- **Technical Indicators** — RSI, MACD, Bollinger Bands, ATR, EMAs, returns, volatility via `pandas-ta`
- **Two ML Models Per Symbol** — `LSTMModel` for price direction (2-class, ~50% acc) and `LSTMClassifier` for volatility regime (sigmoid, ~83% acc)
- **Volatility Regime Prediction** — binary target from 4-candle price range vs 24-candle median; BCE loss, saves `_classifier_best.pt` checkpoints
- **Confidence Scoring** — combined score: `direction_conf × 0.4 + vol_prob × 0.3 + |sentiment| × 0.3`
- **Sentiment Analysis** — FinBERT (ProsusAI/finbert) with **time-decay weighting** — fresher headlines contribute more via linear decay over 24h (10% floor); `avg_headline_age_hours` logged per headline batch
- **Multi-Agent Pipeline** — LangGraph StateGraph: Manager → Risk → Execution → Portfolio Monitor
- **Manager Agent (Option A)** — sentiment-primary trading; side determined solely by `abs(sentiment_score)` thresholds (`>0.30 BUY`, `<-0.30 SELL`); LSTM direction logged for research only; position halved in high-volatility regime; **paused mode** check skips new entry proposals when `data_cache/.trading_paused` flag exists
- **Risk Management** — position sizing, concentration limits (≤20% per coin), total exposure caps (≤80%), drawdown circuit breaker (>15%), duplicate prevention, **correlation risk** (≥3 same-direction positions halves quantity, ≥4 rejects)
- **Auto-Exit Monitoring** — `PortfolioMonitor.check_exit_conditions()` checks every open position against SL/TP from DB each cycle; generates `ProposedTrade` with `is_auto_exit=True` that bypasses all risk checks
- **Real Trading Fees** — `TRADING_FEE_PCT=0.001` (0.1%) deducted from realised P&L on both entry and exit legs; `fee_paid` persisted on `ExecutedTrade` and `Trade` DB table
- **Idempotency Lock** — file-based `FileLock` on `data_cache/.trading_cycle.lock` (5s timeout) prevents double execution when scheduler fires overlapping cycles
- **Kill Switch** — `POST /portfolio/pause-trading` writes a flag file; `POST /portfolio/resume-trading` deletes it; Streamlit sidebar buttons; Manager Agent reads flag each cycle and skips new entry trades while allowing SL/TP exits
- **Paper Trading** — Binance Testnet integration with slippage modelling
- **REST API** — FastAPI with 15+ endpoints for portfolio, trades, signals, health, **sentiment validation**, **pause/resume**
- **Streamlit Dashboard** — overview, ML signals, trade history, risk metrics, **sentiment validation** pages with Plotly charts
- **Persistent Storage** — SQLite via SQLAlchemy ORM (5 tables) with `is_sentiment_driven`, `signal_confidence`, `fee_paid` columns on `Trade`
- **Sentiment Validation Dashboard** — win-rate color-coded metric, sample-size progress bar, win/loss sentiment comparison chart, statistical readiness gate (requires ≥30 trades)
- **Automated Scheduling** — 4-mode CLI entry point: `trade` (full stack), `api` (server only), `train` (LSTM training), `dashboard` (Streamlit)
- **Scheduler** — APScheduler with 3 recurring jobs (trading cycle, cache refresh, health check) + one-shot model training on startup
- **Training Data** — 2 years of 1h OHLCV via Yahoo Finance (free, no API key); Binance Futures for funding rate / open interest
- **Dockerized** — Docker Compose for one-command startup

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Deep learning | PyTorch 2.x (CUDA 12.6) |
| NLP model | FinBERT (ProsusAI/finbert via HuggingFace) |
| Price model | LSTM (direction) + LSTMClassifier (volatility regime) |
| Agent framework | LangGraph 0.2+ |
| Crypto data | python-binance (Testnet), CoinGecko API |
| News/sentiment | CryptoPanic API (free tier) |
| Feature engineering | pandas, numpy, pandas-ta |
| Database | SQLAlchemy ORM, SQLite (dev) |
| API server | FastAPI + Uvicorn |
| Dashboard | Streamlit + Plotly |
| Task scheduler | APScheduler |
| Package manager | uv |
| Deployment | Docker + Docker Compose |
| Logging | Python logging + rotating file handler |

---

## Getting Started

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Binance Testnet account ([sign up here](https://testnet.binance.vision/))
- CryptoPanic API key ([free tier](https://cryptopanic.com/developers/api/))

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
CRYPTOPANIC_API_KEY=your_cryptopanic_key
COINGECKO_API_KEY=
DATABASE_URL=sqlite:///./alphacore.db
LOG_LEVEL=INFO
PORTFOLIO_INITIAL_CAPITAL=10000
MAX_POSITION_SIZE_PCT=0.05
STOP_LOSS_PCT=0.03
TRADING_FEE_PCT=0.001
TRADING_PAUSED=False
TRADING_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,ADA/USDT
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

### Run a single trading cycle (one-off)

```bash
python -c "
from src.data.data_pipeline import DataPipeline
from src.agents import run_cycle
from src.database.crud import save_cycle

pipeline = DataPipeline()
data = pipeline.run()
state = run_cycle(data, {'cash': 10000, 'total_value': 10000})
save_cycle(state)
print('Cycle complete:', state['cycle_id'])
"
```

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

## Dashboard Pages

| Page | Description |
|---|---|---|
| **Overview** | Portfolio value chart, asset allocation donut, agent status bar, Fear & Greed gauge, signal confidence chart |
| **ML Signals** | Bullish/bearish/neutral counts, signal table with direction emojis, sentiment gauges per symbol, confidence over time |
| **Trade History** | Stats cards, filterable trade table with coloured side column, P&L bar chart, best/worst trade |
| **Risk Dashboard** | Drawdown, peak value, win rate, avg P&L; drawdown chart, cycle performance table, risk alert thresholds |
| **Validation** | Sentiment-driven trade win rate with colour-coded metric, sample size progress bar, win/loss sentiment bar chart, statistical readiness gate (≥30 trades) |

---

## Architecture

The system runs a closed-loop trading cycle every hour:

```
DataPipeline         → fetch candles + news + market data + funding rate + open interest
FeatureEngineer      → compute indicators + volatility regime target (target_vol_regime)
Predictor            → LSTM direction (2-class) + LSTMClassifier vol regime (sigmoid) + FinBERT sentiment (time-decay weighted)
Manager Agent        → sentiment-primary (Option A): rank by |sentiment|, side from sentiment thresholds, skip if paused flag exists
Risk Agent           → screen each proposed trade (6 checks + auto-exit bypass)
Execution Agent      → fire approved orders to Binance Testnet, calculate + record fee_paid
Portfolio Monitor    → check SL/TP auto-exit conditions, update P&L (fee-aware), check rebalance, log cycle
CRUD / Database      → persist everything to SQLite including fee_paid, is_sentiment_driven, signal_confidence
```

### Agent Roles

- **Manager Agent (Option A)** — sentiment-primary trading: ranks signals by `|sentiment_score|`, side determined by thresholds (`>0.30 → BUY`, `<-0.30 → SELL`), halves position in high-volatility regime, appends `vol_tag` to reasoning; checks `data_cache/.trading_paused` flag at start of `run()` — skips all new entry proposals when paused, allowing only auto-exit trades through; LSTM direction model outputs logged for research only
- **Risk Agent** — 6 independent checks: position size limit (≤5% of portfolio), concentration (≤20% per coin), total exposure (≤80%), drawdown circuit breaker (>15% halts all trading), duplicate position prevention, **correlation risk** (>2 same-direction open positions halves quantity, >3 rejects entirely); trades with `is_auto_exit=True` bypass all 6 checks
- **Execution Agent** — takes approved orders from state, fetches live price, models random slippage (0–0.15%), calculates `fee_paid = executed_quantity × executed_price × TRADING_FEE_PCT`, routes market orders to Binance Testnet, records all fill details including order ID
- **Portfolio Monitor** — calls `check_exit_conditions(state)` each cycle: iterates open positions, queries DB for SL/TP prices, generates `ProposedTrade` with `is_auto_exit=True` when triggered; tracks **fee-aware realised P&L**: `(exit_price - entry_price) × qty - proportional_entry_fee - exit_fee`; accumulates `total_entry_fees` per position on BUY, deducts proportionally on SELL; computes total portfolio value + drawdown from peak; triggers rebalance alerts when any position drifts >10% from equal-weight target

---

## Database Schema

Five SQLAlchemy ORM tables:

| Table | Key Columns |
|---|---|---|
| `cycle_runs` | `cycle_id` (UUID), signals/proposed/approved/executed counts, portfolio value, P&L, drawdown, `cycle_log` (JSON) |
| `signals` | FK → `cycle_runs.cycle_id`, symbol, predicted return, direction, confidence, sentiment score/label, Fear & Greed |
| `trades` | FK → `cycle_runs.cycle_id`, symbol, side, proposed/executed quantity + price, stop-loss, take-profit, status, PnL, `is_sentiment_driven` (Boolean), `signal_confidence` (Numeric), `fee_paid` (Numeric) |
| `positions` | `symbol` (unique), quantity, avg entry price, current price, unrealised PnL |
| `portfolio_snapshots` | FK → `cycle_runs.cycle_id`, total value, cash, positions value, P&L, peak value, drawdown |

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
├── src/
│   ├── data/                  # Data fetching & feature engineering
│   │   ├── binance_client.py
│   │   ├── coingecko_client.py
│   │   ├── cryptopanic_client.py
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
│   │       └── risk.py
│   │       ├── validation.py
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
|---|---|---|
| Phase 1 | Project scaffold (config, logging, dependencies) | ✅ Complete |
| Phase 2 | Data pipeline (Binance, CoinGecko, CryptoPanic, features) | ✅ Complete |
| Phase 3 | ML models (LSTM, TFT, FinBERT, training loop) | ✅ Complete |
| Phase 4 | Agent system (LangGraph agents, state management) | ✅ Complete |
| Phase 5 | Database (SQLAlchemy models, CRUD, connection) | ✅ Complete |
| Phase 6 | API server (FastAPI routes, Pydantic schemas) | ✅ Complete |
| Phase 7 | Dashboard (Streamlit pages, Plotly charts) | ✅ Complete |
| Phase 8 | Scheduler + dual-model training (direction + vol regime, Yahoo Finance data, manager filters) | ✅ Complete |
| Phase 9 | Docker deployment (Dockerfile, Compose) | ⏳ Pending |
| Phase 10 | Testing (pytest suite for all modules) | ⏳ Pending |

---

## License

MIT
