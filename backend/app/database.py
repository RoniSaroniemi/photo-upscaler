import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings

DB_PATH = Path(settings.TEMP_DIR) / "upscaler.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                balance_cents INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT FALSE
            );

            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                stripe_session_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)


# --- User operations ---

def get_or_create_user(email: str) -> dict:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            return dict(row)
        user_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, email, balance_cents) VALUES (?, ?, 0)",
            (user_id, email),
        )
        return {"id": user_id, "email": email, "balance_cents": 0}


def get_user_by_id(user_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


# --- Auth token operations ---

def create_auth_token(email: str) -> str:
    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO auth_tokens (token, email, expires_at, used) VALUES (?, ?, ?, FALSE)",
            (token, email, expires_at.isoformat()),
        )
    return token


def verify_auth_token(token: str) -> str | None:
    """Verify and consume a token. Returns email if valid, None otherwise."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM auth_tokens WHERE token = ? AND used = FALSE",
            (token,),
        ).fetchone()
        if not row:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            return None
        conn.execute("UPDATE auth_tokens SET used = TRUE WHERE token = ?", (token,))
        return row["email"]


# --- Session operations ---

def create_session(user_id: str) -> str:
    session_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, user_id, expires_at) VALUES (?, ?, ?)",
            (session_id, user_id, expires_at.isoformat()),
        )
    return session_id


def get_session_user(session_id: str) -> dict | None:
    """Get user from session ID. Returns None if session is expired or invalid."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT u.* FROM sessions s
               JOIN users u ON s.user_id = u.id
               WHERE s.session_id = ? """,
            (session_id,),
        ).fetchone()
        if not row:
            return None
        session = conn.execute(
            "SELECT expires_at FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        expires_at = datetime.fromisoformat(session["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            return None
        return dict(row)


def delete_session(session_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


# --- Balance operations ---

def get_balance(user_id: str) -> int:
    """Returns balance in cents."""
    with get_db() as conn:
        row = conn.execute("SELECT balance_cents FROM users WHERE id = ?", (user_id,)).fetchone()
        return row["balance_cents"] if row else 0


def add_balance(user_id: str, amount_cents: int, description: str, stripe_session_id: str | None = None) -> int:
    """Add to user balance. Returns new balance in cents."""
    tx_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET balance_cents = balance_cents + ? WHERE id = ?",
            (amount_cents, user_id),
        )
        conn.execute(
            "INSERT INTO transactions (id, user_id, amount_cents, type, description, stripe_session_id) VALUES (?, ?, ?, 'topup', ?, ?)",
            (tx_id, user_id, amount_cents, description, stripe_session_id),
        )
        row = conn.execute("SELECT balance_cents FROM users WHERE id = ?", (user_id,)).fetchone()
        return row["balance_cents"]


def deduct_balance(user_id: str, amount_cents: int, description: str) -> int | None:
    """Deduct from user balance. Returns new balance or None if insufficient."""
    with get_db() as conn:
        row = conn.execute("SELECT balance_cents FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row or row["balance_cents"] < amount_cents:
            return None
        tx_id = str(uuid.uuid4())
        conn.execute(
            "UPDATE users SET balance_cents = balance_cents - ? WHERE id = ?",
            (amount_cents, user_id),
        )
        conn.execute(
            "INSERT INTO transactions (id, user_id, amount_cents, type, description) VALUES (?, ?, ?, 'charge', ?)",
            (tx_id, user_id, -amount_cents, description),
        )
        row = conn.execute("SELECT balance_cents FROM users WHERE id = ?", (user_id,)).fetchone()
        return row["balance_cents"]


# --- Transaction operations ---

def get_transactions(user_id: str, limit: int = 50) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
