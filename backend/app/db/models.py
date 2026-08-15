"""
Database Models
===============
SQLAlchemy ORM models for persistent storage.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint, Boolean, Index, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db import Base


def _utcnow_naive() -> datetime:
    """Current UTC time as a NAIVE datetime, for plain `DateTime` columns.

    Mirrors services/llm_cache._utcnow_naive() — see that docstring for the full
    rationale. The short version: these are `DateTime` columns without
    `timezone=True`, so an AWARE default is not just cosmetically inconsistent,
    it is rejected outright by asyncpg ("invalid input for query argument ...
    can't subtract offset-naive and offset-aware datetimes") and the whole
    INSERT fails.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    # Nullable for OAuth-only users (no password set)
    password_hash = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)
    # Google OAuth
    google_id = Column(String(255), unique=True, nullable=True, index=True)
    avatar_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    watchlist_items = relationship(
        "WatchlistItem", back_populates="user", cascade="all, delete-orphan"
    )
    portfolio_positions = relationship(
        "PortfolioPosition", back_populates="user", cascade="all, delete-orphan"
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    __table_args__ = (
        UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker = Column(String(20), nullable=False, index=True)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="watchlist_items")


class PortfolioPosition(Base):
    __tablename__ = "portfolio"
    __table_args__ = (
        UniqueConstraint("user_id", "ticker", name="uq_portfolio_user_ticker"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker = Column(String(20), nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    buy_price = Column(Float, nullable=False)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="portfolio_positions")


class LLMCache(Base):
    """
    Persistent cache for LLM / agent crew outputs.

    Saves tokens (and Supabase storage) by reusing analytical results across
    requests. Keyed by a deterministic string the caller chooses (e.g.
    "deep_dive:RELIANCE:2025-05-01"). Payload is the entire response dict.

    Eviction: opportunistic — services/llm_cache.set() periodically deletes
    rows where expires_at < now(). No pg_cron / triggers needed (works on
    both SQLite dev and Postgres prod).
    """
    __tablename__ = "llm_cache"

    cache_key = Column(String(255), primary_key=True)
    payload = Column(JSON, nullable=False)
    scope = Column(String(64), nullable=False, default="global")  # 'global' or 'user:<id>'
    # NAIVE UTC, not aware — see _utcnow_naive() above. services/llm_cache.py
    # standardised `expires_at` on naive UTC (2026-08-11) but this default was
    # missed, so every set() built an INSERT mixing a naive expires_at with an
    # aware created_at. asyncpg rejected the whole statement, llm_cache.set()
    # swallowed it as a warning, and the persistent cross-worker tier silently
    # never wrote a single row from then until 2026-08-15 — meaning every cold
    # worker re-ran the full news+LLM fan-out it was supposed to skip.
    created_at = Column(DateTime, default=_utcnow_naive, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index("ix_llm_cache_scope_expires", "scope", "expires_at"),
    )
