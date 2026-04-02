"""
Database Models
===============
SQLAlchemy ORM models for persistent storage.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime, timezone
from app.db import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), unique=True, nullable=False, index=True)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PortfolioPosition(Base):
    __tablename__ = "portfolio"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), unique=True, nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    buy_price = Column(Float, nullable=False)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
