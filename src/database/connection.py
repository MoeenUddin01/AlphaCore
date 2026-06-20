"""SQLAlchemy engine and session factory for the crypto quant system.

Provides a session factory, a context-managed ``get_db()`` helper,
table initialisation, and a liveness check for the database.
"""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
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
        Position,
        Signal,
        Trade,
    )

    _logger.info("Initialising database at %s", settings.DATABASE_URL)
    tables_before = len(Base.metadata.tables)
    Base.metadata.create_all(bind=engine)
    tables_after = len(Base.metadata.tables)

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
        )
        trades_exists = result.scalar() is not None
        if trades_exists:
            col_result = conn.execute(
                text("PRAGMA table_info(trades)")
            )
            cols = {row[1] for row in col_result.fetchall()}
            if "is_sentiment_driven" not in cols:
                _logger.warning(
                    "The 'trades' table is missing column 'is_sentiment_driven'. "
                    "Delete the old .db file and let it recreate fresh — "
                    "this is pre-production paper trading, safe to do so."
                )

    _logger.info(
        "Database ready — %d table(s) registered, %d created",
        tables_after,
        tables_after - tables_before,
    )


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
