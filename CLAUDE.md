# CLAUDE.md — Autonomous Crypto Quant System
> Master context file. Read this entire file before touching any code.

## Project Identity
- **Name:** Autonomous Crypto Quant
- **Purpose:** A production-grade, multi-agent AI system that predicts cryptocurrency prices using LSTM/TFT deep learning models and FinBERT NLP sentiment analysis, then autonomously manages a crypto portfolio through four specialized agents: Manager, Risk, Execution, and Portfolio Monitor.
- **Mode:** Paper trading (Binance Testnet) — safe for real-world deployment demo.
- **Target assets:** BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, ADA/USDT

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

## Project Structure
autonomous-crypto-quant/
├── CLAUDE.md                  ← you are here
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
│
├── src/
│   ├── __init__.py
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   ├── binance_client.py       ← fetch OHLCV candles
│   │   ├── coingecko_client.py     ← on-chain + market data
│   │   ├── cryptopanic_client.py   ← news headlines
│   │   ├── feature_engineer.py     ← RSI, MACD, Bollinger, returns
│   │   └── data_pipeline.py        ← orchestrates all data fetching
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── lstm_model.py           ← LSTM price predictor (PyTorch)
│   │   ├── tft_model.py            ← Temporal Fusion Transformer
│   │   ├── sentiment_model.py      ← FinBERT sentiment scorer
│   │   ├── trainer.py              ← training loop, checkpointing
│   │   └── predictor.py            ← unified inference interface
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── manager_agent.py        ← strategy + delegation (LangGraph)
│   │   ├── risk_agent.py           ← VaR, drawdown, position sizing
│   │   ├── execution_agent.py      ← order routing (Binance Testnet)
│   │   ├── portfolio_monitor.py    ← live P&L, rebalancing, alerts
│   │   └── agent_state.py          ← shared LangGraph state schema
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py               ← SQLAlchemy ORM models
│   │   ├── crud.py                 ← create/read/update/delete ops
│   │   └── connection.py           ← DB engine + session factory
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py                 ← FastAPI app entry point
│   │   ├── routes/
│   │   │   ├── portfolio.py        ← portfolio endpoints
│   │   │   ├── trades.py           ← trade history endpoints
│   │   │   └── signals.py          ← ML signal endpoints
│   │   └── schemas.py              ← Pydantic request/response models
│   │
│   ├── dashboard/
│   │   ├── app.py                  ← Streamlit main app
│   │   ├── pages/
│   │   │   ├── overview.py         ← portfolio overview page
│   │   │   ├── signals.py          ← ML predictions page
│   │   │   ├── trades.py           ← trade log page
│   │   │   └── risk.py             ← risk metrics page
│   │   └── components/
│   │       ├── charts.py           ← reusable Plotly chart components
│   │       └── metrics.py          ← reusable metric card components
│   │
│   ├── scheduler/
│   │   ├── __init__.py
│   │   ├── job_runner.py           ← APScheduler setup + job registry
│   │   └── jobs.py                 ← scheduled job definitions
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logger.py               ← centralised logging config
│       ├── config.py               ← env var loading + validation
│       └── helpers.py              ← shared utility functions
│
├── models_saved/               ← trained model checkpoints (.pt files)
├── data_cache/                 ← cached OHLCV CSVs for offline use
├── logs/                       ← rotating log files
│
└── tests/
    ├── test_data/
    ├── test_models/
    ├── test_agents/
    └── test_api/

---

## Development Phases

| Phase | Name | Files involved |
|---|---|---|
| Phase 1 | Project scaffold | `.env.example`, `.gitignore`, `requirements.txt`, `utils/config.py`, `utils/logger.py` |
| Phase 2 | Data pipeline | `binance_client.py`, `coingecko_client.py`, `cryptopanic_client.py`, `feature_engineer.py`, `data_pipeline.py` |
| Phase 3 | ML models | `lstm_model.py`, `sentiment_model.py`, `trainer.py`, `predictor.py` |
| Phase 4 | Agent system | `agent_state.py`, `manager_agent.py`, `risk_agent.py`, `execution_agent.py`, `portfolio_monitor.py` |
| Phase 5 | Database | `database/models.py`, `database/crud.py`, `database/connection.py` |
| Phase 6 | API server | `api/main.py`, all routes, `schemas.py` |
| Phase 7 | Dashboard | All Streamlit files |
| Phase 8 | Scheduler | `job_runner.py`, `jobs.py` |
| Phase 9 | Docker deploy | `Dockerfile`, `docker-compose.yml` |
| Phase 10 | Testing | All test files |

---

## Coding Rules (enforce strictly)
1. Every file must have a module-level docstring explaining what it does.
2. Every function must have a type-annotated signature and a docstring.
3. Never hardcode API keys, secrets, or URLs — always load from `.env` via `utils/config.py`.
4. All errors must be caught, logged with `utils/logger.py`, and re-raised with context — never silently swallowed.
5. Every external API call must have retry logic with exponential backoff (max 3 retries).
6. Data returned from any function must be validated — use Pydantic models or explicit type checks.
7. All monetary values (prices, portfolio value, P&L) must use Python `Decimal` type, never `float`.
8. Database writes must use transactions — never raw uncommitted writes.
9. Agent state must be immutable between steps — never mutate shared state directly.
10. Every new file created must be importable without side effects on import.

---

## Environment Variables Required
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TESTNET=true
CRYPTOPANIC_API_KEY=
COINGECKO_API_KEY=
DATABASE_URL=sqlite:///./crypto_quant.db
LOG_LEVEL=INFO
PORTFOLIO_INITIAL_CAPITAL=10000
MAX_POSITION_SIZE_PCT=0.05
STOP_LOSS_PCT=0.03
TRADING_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,ADA/USDT
MODEL_CHECKPOINT_DIR=./models_saved
DATA_CACHE_DIR=./data_cache

---

## Agent Roles — Quick Reference
- **Manager Agent** — reads ML predictions + sentiment, ranks signals, decides strategy, delegates to Risk and Execution agents.
- **Risk Agent** — calculates VaR, checks max drawdown, enforces position size limits, approves or rejects each proposed trade.
- **Execution Agent** — takes approved orders, routes to Binance Testnet via python-binance, logs fills, handles slippage.
- **Portfolio Monitor** — tracks live P&L per position, triggers rebalancing when drift > 10%, sends alerts on drawdown breach, feeds summary back to Manager Agent each cycle.

---

## Cycle Flow (runs every 1 hour via APScheduler)

data_pipeline.py      → fetch latest candles + news
feature_engineer.py   → compute indicators
predictor.py          → LSTM price forecast + FinBERT sentiment
manager_agent.py      → combine signals, rank coins, set strategy
risk_agent.py         → screen each proposed trade
execution_agent.py    → fire approved orders to Binance Testnet
portfolio_monitor.py  → update P&L, check rebalance, log cycle
database/crud.py      → persist everything to DB


---

## Important Notes for the Coding Agent
- Always read `CLAUDE.md` fully before starting any task.
- When building any file, check which phase it belongs to and ensure all Phase N-1 dependencies exist first.
- Use `src/utils/config.py` for all config — never import `os.environ` directly anywhere else.
- Use `src/utils/logger.py` for all logging — never use `print()` in production code.
- The system must be fully runnable with `docker-compose up` after Phase 9.
- Paper trading only — never connect to Binance live account, always use Testnet.
- **Code change = process restart required.** Both `--mode api` and `--mode trade` are long-lived Python processes that import all modules at startup and never reload. Any change to `*.py` files (especially `crud.py`, `agents/`, `api/`, `models/`) requires explicitly killing and restarting the affected process. There is no hot-reload. This rule applies identically to both processes — if you edit query logic, restart the API. If you edit pipeline/agent logic, restart the scheduler. When in doubt, restart both with `kill <PID> && nohup ... &`.
