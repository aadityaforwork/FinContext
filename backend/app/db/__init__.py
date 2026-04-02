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
    """Create all tables if they don't exist."""
    from app.db import models  # noqa: F401 — import so models register with Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
