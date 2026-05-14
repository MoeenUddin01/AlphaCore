# Autonomous Crypto Quant

A production-grade, multi-agent AI system that predicts cryptocurrency prices using LSTM/TFT deep learning models and FinBERT NLP sentiment analysis, then autonomously manages a crypto portfolio through four specialized agents: **Manager**, **Risk**, **Execution**, and **Portfolio Monitor**.

> **Mode:** Paper trading (Binance Testnet) — safe for real-world deployment demo.  
> **Target assets:** BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, ADA/USDT

---

## Features

- **ML-Powered Predictions** — LSTM and Temporal Fusion Transformer models for price forecasting
- **Sentiment Analysis** — FinBERT-based NLP on crypto news headlines via CryptoPanic API
- **Multi-Agent System** — LangGraph orchestrated agents for strategy, risk, execution, and monitoring
- **Automated Trading Cycle** — Runs every 1 hour via APScheduler
- **Real-Time Dashboard** — Streamlit UI for portfolio overview, signals, trade log, and risk metrics
- **REST API** — FastAPI endpoints for portfolio, trade history, and ML signals
- **Persistent Storage** — SQLite (dev) / PostgreSQL (prod) via SQLAlchemy
- **Dockerized Deployment** — Docker Compose for one-command startup

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Deep learning | PyTorch 2.x |
| NLP model | FinBERT (ProsusAI/finbert via HuggingFace) |
| Price model | LSTM + optional Temporal Fusion Transformer |
| Agent framework | LangGraph 0.2+ |
| Crypto data | python-binance, ccxt |
| News/sentiment | CryptoPanic API (free) |
| On-chain data | CoinGecko API (free) |
| Feature engineering | pandas, numpy, ta-lib |
| Database | SQLite (dev) → PostgreSQL (prod) |
| API server | FastAPI |
| Dashboard | Streamlit |
| Task scheduler | APScheduler |
| Deployment | Docker + Docker Compose |
| Env management | python-dotenv |
| Testing | pytest |
| Logging | Python logging + rotating file handler |

---

## Getting Started

### Prerequisites

- Python 3.11+
- Binance Testnet account ([sign up here](https://testnet.binance.vision/))
- CryptoPanic API key ([free tier](https://cryptopanic.com/developers/api/))

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd autonomous-crypto-quant

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

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
COINGECKO_API_KEY=your_coingecko_key
DATABASE_URL=sqlite:///./crypto_quant.db
LOG_LEVEL=INFO
PORTFOLIO_INITIAL_CAPITAL=10000
MAX_POSITION_SIZE_PCT=0.05
STOP_LOSS_PCT=0.03
TRADING_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,ADA/USDT
```

---

## Usage

```bash
# Start the scheduler (runs trading cycle every hour)
python -m src.scheduler.job_runner

# Start the API server
uvicorn src.api.main:app --reload

# Start the dashboard
streamlit run src/dashboard/app.py
```

### Docker

```bash
docker-compose up --build
```

---

## Architecture

The system runs a closed-loop trading cycle every hour:

```
data_pipeline.py      → fetch latest candles + news
feature_engineer.py   → compute technical indicators
predictor.py          → LSTM price forecast + FinBERT sentiment
manager_agent.py      → combine signals, rank coins, set strategy
risk_agent.py         → screen each proposed trade
execution_agent.py    → fire approved orders to Binance Testnet
portfolio_monitor.py  → update P&L, check rebalance, log cycle
database/crud.py      → persist everything to DB
```

### Agent Roles

- **Manager Agent** — reads ML predictions + sentiment, ranks signals, decides strategy, delegates to Risk and Execution agents.
- **Risk Agent** — calculates VaR, checks max drawdown, enforces position size limits, approves or rejects each proposed trade.
- **Execution Agent** — takes approved orders, routes to Binance Testnet via python-binance, logs fills, handles slippage.
- **Portfolio Monitor** — tracks live P&L per position, triggers rebalancing when drift > 10%, sends alerts on drawdown breach, feeds summary back to Manager Agent each cycle.

---

## Project Structure

```
autonomous-crypto-quant/
├── CLAUDE.md                  # Master context file
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
│
├── src/
│   ├── data/                  # Data fetching & feature engineering
│   ├── models/                # LSTM, TFT, FinBERT, trainers
│   ├── agents/                # LangGraph agent system
│   ├── database/              # SQLAlchemy ORM & CRUD
│   ├── api/                   # FastAPI REST endpoints
│   ├── dashboard/             # Streamlit UI
│   ├── scheduler/             # APScheduler job definitions
│   └── utils/                 # Config, logging, helpers
│
├── models_saved/              # Trained model checkpoints
├── data_cache/                # Cached OHLCV data
├── logs/                      # Rotating log files
│
└── tests/
    ├── test_data/
    ├── test_models/
    ├── test_agents/
    └── test_api/
```

---

## Development Phases

| Phase | Description |
|---|---|
| Phase 1 | Project scaffold (config, logging, dependencies) |
| Phase 2 | Data pipeline (Binance, CoinGecko, CryptoPanic, features) |
| Phase 3 | ML models (LSTM, TFT, FinBERT, training loop) |
| Phase 4 | Agent system (LangGraph agents, state management) |
| Phase 5 | Database (SQLAlchemy models, CRUD, connection) |
| Phase 6 | API server (FastAPI routes, Pydantic schemas) |
| Phase 7 | Dashboard (Streamlit pages, Plotly charts) |
| Phase 8 | Scheduler (APScheduler job registry) |
| Phase 9 | Docker deployment (Dockerfile, Compose) |
| Phase 10 | Testing (pytest suite for all modules) |

---

## License

MIT
