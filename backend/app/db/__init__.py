"""
Database Connection Module
==========================
SQLAlchemy async engine with SQLite (aiosqlite driver).

Change DATABASE_URL to PostgreSQL for production:
    postgresql+asyncpg://user:pass@localhost:5432/fincontext
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import os

# ---------------------------------------------------------------------------
# Database URL — SQLite for dev, swap to PostgreSQL for prod
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "fincontext.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{DB_PATH}")

engine = create_async_engine(DATABASE_URL, echo=False)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Base model for all ORM classes
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Dependency: get a DB session for FastAPI routes
# ---------------------------------------------------------------------------
async def get_db():
    """Yield a database session for use in FastAPI dependencies."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Create all tables on startup
# ---------------------------------------------------------------------------
async def init_db():
    """Create the tables this app actually owns.

    On Postgres that is ONLY `llm_cache`.

    The User / WatchlistItem / PortfolioPosition models in db/models.py are
    legacy SQLAlchemy definitions — in production those tables are owned by
    supabase/migrations/*.sql and carry RLS policies, and they're read through
    the supabase client, not this engine. An unscoped `create_all` is dangerous
    there for one specific reason: Supabase keeps auth in `auth.users`, so
    `public.users` does NOT exist, and `checkfirst` would happily CREATE it —
    a new table in the PostgREST-exposed `public` schema with no RLS enabled.
    That is exactly the exposure migration 001 was written to close, so we
    never hand `create_all` the full metadata against Postgres.

    On SQLite (local dev — the default when DATABASE_URL is unset) there's no
    Supabase behind the engine, so creating everything is safe and convenient.
    """
    from app.db import models  # noqa: F401 — import so models register with Base

    async with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            await conn.run_sync(Base.metadata.create_all)
        else:
            await conn.run_sync(
                Base.metadata.create_all,
                tables=[models.LLMCache.__table__],
            )
