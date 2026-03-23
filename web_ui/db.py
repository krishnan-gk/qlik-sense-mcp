"""SQLite persistence — users, chat messages, token usage, and cost tracking."""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

# Stored next to the running app; excluded from git via .gitignore
DB_PATH = Path(__file__).parent.parent / "chat_history.db"

# Claude Sonnet 4.6 pricing (per 1 000 tokens)
COST_PER_1K_INPUT  = 0.003   # $3 per 1M input tokens
COST_PER_1K_OUTPUT = 0.015   # $15 per 1M output tokens


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist yet."""
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                email      TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    TEXT    NOT NULL,
                user_email    TEXT    NOT NULL,
                user_name     TEXT    NOT NULL,
                qlik_app_id   TEXT    DEFAULT '',
                qlik_app_name TEXT    DEFAULT '',
                question      TEXT    NOT NULL,
                answer        TEXT    NOT NULL,
                input_tokens  INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cost_usd      REAL    DEFAULT 0.0,
                timestamp     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)


def upsert_user(name: str, email: str) -> None:
    """Insert a new user or update last_seen for a returning user."""
    with _connect() as conn:
        conn.execute("""
            INSERT INTO users (email, name, first_seen, last_seen)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(email) DO UPDATE SET
                name      = excluded.name,
                last_seen = CURRENT_TIMESTAMP
        """, (email.strip().lower(), name.strip()))


def new_session_id() -> str:
    """Generate a unique session ID."""
    return str(uuid.uuid4())


def compute_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate API cost in USD for a single exchange."""
    return (input_tokens / 1000 * COST_PER_1K_INPUT) + \
           (output_tokens / 1000 * COST_PER_1K_OUTPUT)


def log_message(
    *,
    session_id: str,
    user_email: str,
    user_name: str,
    question: str,
    answer: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    qlik_app_id: str = "",
    qlik_app_name: str = "",
) -> float:
    """Persist a Q&A exchange and return the cost in USD."""
    cost = compute_cost(input_tokens, output_tokens)
    with _connect() as conn:
        conn.execute("""
            INSERT INTO messages
                (session_id, user_email, user_name, qlik_app_id, qlik_app_name,
                 question, answer, input_tokens, output_tokens, cost_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            user_email.strip().lower(),
            user_name.strip(),
            qlik_app_id,
            qlik_app_name,
            question,
            answer,
            input_tokens,
            output_tokens,
            cost,
        ))
    return cost


def session_totals(session_id: str) -> dict:
    """Return cumulative token + cost totals for the current session."""
    with _connect() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*)          AS exchanges,
                SUM(input_tokens) AS input_tokens,
                SUM(output_tokens)AS output_tokens,
                SUM(cost_usd)     AS cost_usd
            FROM messages
            WHERE session_id = ?
        """, (session_id,)).fetchone()
    return {
        "exchanges":     row["exchanges"]     or 0,
        "input_tokens":  row["input_tokens"]  or 0,
        "output_tokens": row["output_tokens"] or 0,
        "cost_usd":      row["cost_usd"]      or 0.0,
    }
