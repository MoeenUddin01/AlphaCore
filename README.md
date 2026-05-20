# AlphaCore — Autonomous Crypto Quant

A production-grade, multi-agent AI system that predicts cryptocurrency prices using LSTM deep learning models and FinBERT NLP sentiment analysis, then autonomously manages a crypto portfolio through four specialized agents: **Manager**, **Risk**, **Execution**, and **Portfolio Monitor**.

> **Mode:** Paper trading (Binance Testnet) — safe for real-world deployment demo.  
> **Target assets:** BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, ADA/USDT

---

## Features

- **Data Pipeline** — fetches OHLCV candles (Binance), market data (CoinGecko), news (CryptoPanic), Fear & Greed Index
- **Technical Indicators** — RSI, MACD, Bollinger Bands, ATR, EMAs, returns, volatility via `pandas-ta`
- **ML Price Prediction** — LSTM (PyTorch) with configurable sequence length and training loop (early stopping, checkpointing)
- **Sentiment Analysis** — FinBERT (ProsusAI/finbert) on crypto news headlines
- **Multi-Agent Pipeline** — LangGraph StateGraph: Manager → Risk → Execution → Portfolio Monitor
- **Risk Management** — position sizing, concentration limits, exposure caps, drawdown circuit breaker, duplicate detection
- **Paper Trading** — Binance Testnet integration with slippage modelling
- **REST API** — FastAPI with 10+ endpoints for portfolio, trades, signals, health
- **Streamlit Dashboard** — overview, ML signals, trade history, risk metrics pages with Plotly charts
- **Persistent Storage** — SQLite via SQLAlchemy ORM (5 tables)
- **Automated Scheduling** — APScheduler for hourly trading cycles
- **Dockerized** — Docker Compose for one-command startup

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Deep learning | PyTorch 2.x (CUDA 12.6) |
| NLP model | FinBERT (ProsusAI/finbert via HuggingFace) |
| Price model | LSTM + simplified Temporal Fusion Transformer |
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
TRADING_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,ADA/USDT
```

---

## Usage

### Start the API server

```bash
uvicorn src.api.main:app --reload
```

Open **http://localhost:8000/docs** for interactive API documentation (Swagger UI).

### Start the Dashboard

```bash
streamlit run src/dashboard/app.py
```

Open **http://localhost:8501** for the Streamlit dashboard.

> **Note:** The dashboard uses `.streamlit/config.toml` for headless mode and auto-refresh every 60 seconds. No manual configuration needed.

### Run a single trading cycle

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

### Start the automated scheduler

```bash
python -m src.scheduler.job_runner
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
| `GET` | `/trades/history` | Trade history (optional `?symbol=` filter) |
| `GET` | `/trades/stats` | Trade statistics (counts, volume) |
| `GET` | `/trades/{trade_id}` | Single trade by UUID |
| `GET` | `/signals/latest` | Signals from most recent cycle |
| `GET` | `/signals/history` | Historical signals |
| `GET` | `/signals/summary` | Daily signal summary |

---

## Dashboard Pages

| Page | Description |
|---|---|
| **Overview** | Portfolio value chart, asset allocation donut, agent status bar, Fear & Greed gauge, signal confidence chart |
| **ML Signals** | Bullish/bearish/neutral counts, signal table with direction emojis, sentiment gauges per symbol, confidence over time |
| **Trade History** | Stats cards, filterable trade table with coloured side column, P&L bar chart, best/worst trade |
| **Risk Dashboard** | Drawdown, peak value, win rate, avg P&L; drawdown chart, cycle performance table, risk alert thresholds |

---

## Architecture

The system runs a closed-loop trading cycle every hour:

```
DataPipeline         → fetch candles + news + market data
FeatureEngineer      → compute RSI, MACD, Bollinger, ATR, EMAs
Predictor            → LSTM price forecast + FinBERT sentiment
Manager Agent        → combine signals, rank coins, set strategy
Risk Agent           → screen each proposed trade (5 checks)
Execution Agent      → fire approved orders to Binance Testnet
Portfolio Monitor    → update P&L, check rebalance, log cycle
CRUD / Database      → persist everything to SQLite
```

### Agent Roles

- **Manager Agent** — reads ML predictions + sentiment, ranks signals by composite score (`confidence × 0.6 + |sentiment| × 0.4`), detects conflicts (price vs. sentiment mismatch), generates proposed trades with stop-loss and take-profit
- **Risk Agent** — 5 independent checks: position size limit, concentration (≤20% per coin), total exposure (≤80%), drawdown circuit breaker (>15% halts trading), duplicate position prevention
- **Execution Agent** — takes approved orders, fetches live price, models slippage (0–0.15%), routes market orders to Binance Testnet, records fill details
- **Portfolio Monitor** — tracks live P&L per position, computes total value + drawdown from peak, triggers rebalance alerts when allocation drift > 10%

---

## Database Schema

Five SQLAlchemy ORM tables:

| Table | Key Columns |
|---|---|
| `cycle_runs` | `cycle_id` (UUID), signals/proposed/approved/executed counts, portfolio value, P&L, drawdown, `cycle_log` (JSON) |
| `signals` | FK → `cycle_runs.cycle_id`, symbol, predicted return, direction, confidence, sentiment score/label, Fear & Greed |
| `trades` | FK → `cycle_runs.cycle_id`, symbol, side, proposed/executed quantity + price, stop-loss, take-profit, status, PnL |
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
│   ├── scheduler/             # APScheduler job definitions
│   └── utils/                 # Config, logging, helpers
│       ├── config.py
│       ├── logger.py
│       └── helpers.py
│
├── models_saved/              # Trained model checkpoints (.pt)
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
| Phase 8 | Scheduler (APScheduler job registry) | ⏳ Pending |
| Phase 9 | Docker deployment (Dockerfile, Compose) | ⏳ Pending |
| Phase 10 | Testing (pytest suite for all modules) | ⏳ Pending |

---

## License

MIT
