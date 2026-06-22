"""Centralised configuration loader for the Autonomous Crypto Quant system.

Loads all environment variables from a .env file via pydantic-settings
and validates them at import time. This is the single source of truth
for all configuration — never import os.environ directly elsewhere.
"""

import json
from decimal import Decimal
from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, Json
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_trading_pairs(v: Any) -> Any:
    """Accept comma-separated string or JSON array for TRADING_PAIRS."""
    if isinstance(v, str):
        v = v.strip()
        if v.startswith("["):
            return v
        parts = [p.strip() for p in v.split(",") if p.strip()]
        return json.dumps(parts)
    return v


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    BINANCE_API_KEY: str
    BINANCE_API_SECRET: str
    BINANCE_TESTNET: bool = True

    CRYPTOPANIC_API_KEY: str
    COINGECKO_API_KEY: str = ""
    CRYPTOCOMPARE_API_KEY: str = ""

    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "AlphaCore/1.0"

    DATABASE_URL: str = "sqlite:///./alphacore.db"
    LOG_LEVEL: str = "INFO"

    PORTFOLIO_INITIAL_CAPITAL: Decimal = Decimal("10000")
    MAX_POSITION_SIZE_PCT: float = 0.05
    MAX_POSITION_SIZE_USD: Decimal = Decimal("500")
    STOP_LOSS_PCT: float = 0.03
    TRADING_FEE_PCT: float = 0.001
    TRADING_PAUSED: bool = False

    TRADING_PAIRS: Annotated[Json[list[str]], BeforeValidator(_parse_trading_pairs)] = [
        "BTC/USDT",
        "ETH/USDT",
        "SOL/USDT",
        "BNB/USDT",
        "ADA/USDT",
    ]

    MODEL_CHECKPOINT_DIR: str = "./models_saved"
    DATA_CACHE_DIR: str = "./data_cache"

    ALERT_WEBHOOK_URL: str = ""


settings = Settings()
