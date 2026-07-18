"""FastAPI application entry point for the AlphaCore system.

Creates and configures the API server with CORS, routers, startup
initialisation, health check, and a root welcome endpoint.
"""

from datetime import datetime, timezone

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from src.api.routes.portfolio import router as portfolio_router
from src.api.routes.real_portfolio import router as real_portfolio_router
from src.api.routes.real_safety import router as real_safety_router
from src.api.routes.real_trades import router as real_trades_router
from src.api.routes.signals import router as signals_router
from src.api.routes.trades import router as trades_router
from src.api.schemas import HealthResponse
from src.database.connection import check_db_connection, init_db
from src.utils.logger import get_logger

_logger = get_logger(__name__)

app = FastAPI(
    title="AlphaCore Autonomous Crypto Quant",
    description="Multi-agent AI system for autonomous crypto portfolio management",
    version="1.0.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio_router)
app.include_router(real_portfolio_router)
app.include_router(real_safety_router)
app.include_router(real_trades_router)
app.include_router(trades_router)
app.include_router(signals_router)


@app.on_event("startup")
async def on_startup() -> None:
    """Initialise the database and log all registered routes."""
    init_db()
    _logger.info("Server startup complete — %d route(s) registered", len(app.routes))
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            _logger.debug("  %s %s", sorted(route.methods), route.path)


@app.get("/", summary="Root welcome")
def root() -> dict[str, str]:
    return {
        "name": "AlphaCore Autonomous Crypto Quant",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns the API status, database connectivity, current timestamp, and version.",
)
def health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        database=check_db_connection(),
        timestamp=datetime.now(timezone.utc),
        version="1.0.0",
    )
