"""SQLAlchemy engine and session factory for the crypto quant system.

Provides a session factory, a context-managed ``get_db()`` helper,
table initialisation, and a liveness check for the database.
"""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.utils.config import settings
from src.utils.logger import get_logger

_logger = get_logger(__name__)

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


@contextmanager
def get_db() -> Iterator[Session]:
    """Yield a database session, rolling back and closing on exit.

    Guarantees the session is closed in all cases. If an exception
    occurs within the ``with`` block the transaction is rolled back
    before closing.

    Yields:
        A :class:`sqlalchemy.orm.Session` ready for queries.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        _logger.exception("Database session rolled back due to error")
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create all tables if they do not exist and log the count.

    Imports every model from ``src.database.models`` to register
    them with ``Base.metadata`` before calling ``create_all``.
    """
    from src.database.models import (  # noqa: F401 — register models
        CycleRun,
        PortfolioSnapshot,
        PortfolioState,
        Position,
        Signal,
        Trade,
    )

    _logger.info("Initialising database at %s", settings.DATABASE_URL)
    tables_before = len(Base.metadata.tables)
    Base.metadata.create_all(bind=engine)
    tables_after = len(Base.metadata.tables)

    _migrate_trades_table(engine)

    _logger.info(
        "Database ready — %d table(s) registered, %d created",
        tables_after,
        tables_after - tables_before,
    )


def _migrate_trades_table(db_engine: Engine) -> None:
    """Add missing columns to the ``trades`` table if they don't exist.

    Uses SQLAlchemy's ``inspect()`` for cross-database introspection.
    """
    inspector = inspect(db_engine)
    if not inspector.has_table("trades"):
        return

    existing = {col["name"] for col in inspector.get_columns("trades")}

    _MISSING_COLS: dict[str, str] = {
        "is_sentiment_driven": "BOOLEAN NOT NULL DEFAULT 1",
        "fee_paid": "NUMERIC(20, 8)",
    }

    with db_engine.connect() as conn:
        for col_name, col_def in _MISSING_COLS.items():
            if col_name not in existing:
                _logger.warning("Adding missing column '%s' to trades table", col_name)
                conn.execute(text(f"ALTER TABLE trades ADD COLUMN {col_name} {col_def}"))
        conn.commit()


def check_db_connection() -> bool:
    """Run a simple ``SELECT 1`` query to verify the database is reachable.

    Returns:
        ``True`` if the query succeeds, ``False`` otherwise.
    """
    try:
        with get_db() as db:
            db.execute(text("SELECT 1"))
        _logger.info("Database connection check passed")
        return True
    except Exception:
        _logger.exception("Database connection check failed")
        return False
