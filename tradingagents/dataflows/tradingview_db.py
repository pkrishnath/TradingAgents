"""SQLite storage layer for TradingView webhook OHLCV data."""

import os
import sqlite3
from datetime import datetime

import pandas as pd

from .config import get_config


def _get_db_path() -> str:
    """Resolve the SQLite database path from config or environment."""
    # Environment variable takes priority (for Docker)
    env_path = os.environ.get("TRADINGVIEW_DB_PATH")
    if env_path:
        return env_path
    config = get_config()
    db_path = config.get("tradingview_db_path")
    if db_path:
        return db_path
    return os.path.join(config["data_cache_dir"], "tradingview_market_data.db")


def _get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite database, creating the table if needed."""
    db_path = _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_data (
            timestamp TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            UNIQUE(ticker, timestamp)
        )
        """
    )
    conn.commit()
    return conn


def insert_bar(
    ticker: str,
    timestamp: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int,
) -> None:
    """Insert a single OHLCV bar. Idempotent — duplicates are silently ignored."""
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO market_data (ticker, timestamp, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticker, timestamp, open_, high, low, close, volume),
        )
        conn.commit()
    finally:
        conn.close()


def query_ohlcv(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Query OHLCV data and return a DataFrame matching yfinance conventions.

    Returns columns: Date, Open, High, Low, Close, Volume
    """
    conn = _get_connection()
    try:
        df = pd.read_sql_query(
            "SELECT timestamp, open, high, low, close, volume "
            "FROM market_data "
            "WHERE ticker = ? AND timestamp >= ? AND timestamp <= ? "
            "ORDER BY timestamp",
            conn,
            params=(ticker, start_date, end_date),
        )
    finally:
        conn.close()

    if df.empty:
        return df

    # Match yfinance column naming convention
    df.rename(
        columns={
            "timestamp": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        },
        inplace=True,
    )
    df["Date"] = pd.to_datetime(df["Date"])
    return df


def get_available_tickers() -> list[str]:
    """Return list of tickers that have data in the database."""
    conn = _get_connection()
    try:
        cursor = conn.execute("SELECT DISTINCT ticker FROM market_data ORDER BY ticker")
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def get_date_range(ticker: str) -> dict | None:
    """Return the earliest and latest timestamps for a ticker, or None if no data."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp), COUNT(*) "
            "FROM market_data WHERE ticker = ?",
            (ticker,),
        )
        row = cursor.fetchone()
        if row[0] is None:
            return None
        return {"min": row[0], "max": row[1], "count": row[2]}
    finally:
        conn.close()
