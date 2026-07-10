"""
Database layer for tempest-air.
Handles local SQLite buffer on the Pi.
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "air.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                pm1_0       REAL NOT NULL,
                pm2_5       REAL NOT NULL,
                pm10        REAL NOT NULL,
                p03um       INTEGER NOT NULL,
                p05um       INTEGER NOT NULL,
                p10um       INTEGER NOT NULL,
                p25um       INTEGER NOT NULL,
                p50um       INTEGER NOT NULL,
                p100um      INTEGER NOT NULL,
                sent        INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_readings_sent
            ON readings (sent, timestamp)
        """)
        conn.commit()
    logger.info("Database initialised at %s", DB_PATH)


def insert_reading(reading: dict) -> int:
    """Insert a reading and return its row id."""
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO readings (
                timestamp,
                pm1_0, pm2_5, pm10,
                pm1_0_atmos, pm2_5_atmos, pm10_atmos,
                p03um, p05um, p10um, p25um, p50um, p100um
            ) VALUES (
                :timestamp,
                :pm1_0, :pm2_5, :pm10,
                :pm1_0_atmos, :pm2_5_atmos, :pm10_atmos,
                :p03um, :p05um, :p10um, :p25um, :p50um, :p100um
            )
        """, reading)
        conn.commit()
        return cursor.lastrowid


def get_unsent(limit: int = 100) -> list[dict]:
    """Return unsent readings oldest-first, up to limit."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM readings
            WHERE sent = 0
            ORDER BY timestamp ASC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(row) for row in rows]


def mark_sent(ids: list[int]) -> None:
    """Mark a list of reading ids as successfully sent."""
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    with get_connection() as conn:
        conn.execute(
            f"UPDATE readings SET sent = 1 WHERE id IN ({placeholders})",
            ids
        )
        conn.commit()


def purge_old(max_days: int = 7) -> int:
    """Delete sent readings older than max_days. Returns count deleted."""
    with get_connection() as conn:
        cursor = conn.execute("""
            DELETE FROM readings
            WHERE sent = 1
              AND timestamp < datetime('now', ? || ' days')
        """, (f"-{max_days}",))
        conn.commit()
        return cursor.rowcount


def count_unsent() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM readings WHERE sent = 0"
        ).fetchone()
        return row[0]
