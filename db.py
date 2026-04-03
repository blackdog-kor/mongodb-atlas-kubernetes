"""db.py — SQLite 영속 저장소"""
import sqlite3, json, os
from datetime import datetime, date
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "/data/eve.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS stats (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT DEFAULT (datetime('now')),
            event_type TEXT NOT NULL,
            payload    TEXT
        );
        CREATE TABLE IF NOT EXISTS daily_stats (
            day          TEXT PRIMARY KEY,
            messages     INTEGER DEFAULT 0,
            images       INTEGER DEFAULT 0,
            searches     INTEGER DEFAULT 0,
            errors       INTEGER DEFAULT 0,
            clicks       INTEGER DEFAULT 0,
            conversions  INTEGER DEFAULT 0,
            revenue      REAL    DEFAULT 0.0
        );
        CREATE TABLE IF NOT EXISTS pipelines (
            name       TEXT PRIMARY KEY,
            last_run   TEXT,
            last_status TEXT,
            run_count  INTEGER DEFAULT 0
        );
        """)

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

# ── 글로벌 통계 ──────────────────────────────────────
def inc_stat(key: str, delta: int = 1):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO stats(key, value, updated_at) VALUES(?,?,datetime('now'))
            ON CONFLICT(key) DO UPDATE
            SET value = CAST(CAST(value AS INTEGER) + ? AS TEXT),
                updated_at = datetime('now')
        """, (key, str(delta), delta))

def set_stat(key: str, value):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO stats(key,value,updated_at) VALUES(?,?,datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value=?, updated_at=datetime('now')
        """, (key, str(value), str(value)))

def get_stat(key: str, default=0):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM stats WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

def get_all_stats() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM stats").fetchall()
        return {r["key"]: r["value"] for r in rows}

# ── 일별 통계 ────────────────────────────────────────
def inc_daily(field: str, delta=1, revenue=0.0):
    today = date.today().isoformat()
    with get_conn() as conn:
        conn.execute(f"""
            INSERT INTO daily_stats(day, {field}) VALUES(?, ?)
            ON CONFLICT(day) DO UPDATE SET {field} = {field} + ?
        """, (today, delta, delta))
        if revenue:
            conn.execute("""
                INSERT INTO daily_stats(day, revenue) VALUES(?,?)
                ON CONFLICT(day) DO UPDATE SET revenue = revenue + ?
            """, (today, revenue, revenue))

def get_daily_history(days: int = 14) -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM daily_stats ORDER BY day DESC LIMIT ?
        """, (days,)).fetchall()
        return [dict(r) for r in reversed(rows)]

# ── 이벤트 로그 ──────────────────────────────────────
def log_event(event_type: str, payload: dict = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO events(event_type, payload) VALUES(?,?)",
            (event_type, json.dumps(payload or {}, ensure_ascii=False))
        )

def get_recent_events(limit: int = 50) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

# ── 파이프라인 추적 ───────────────────────────────────
def update_pipeline_status(name: str, status: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO pipelines(name, last_run, last_status, run_count)
            VALUES(?, datetime('now'), ?, 1)
            ON CONFLICT(name) DO UPDATE
            SET last_run=datetime('now'), last_status=?, run_count=run_count+1
        """, (name, status, status))

def get_pipeline_statuses() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM pipelines ORDER BY name").fetchall()
        return [dict(r) for r in rows]
