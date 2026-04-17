from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8
PASSWORD_ITERATIONS = 600_000
SESSION_TTL_DAYS = 30
SQLITE_TIMEOUT_SECONDS = 5.0
SQLITE_BUSY_TIMEOUT_MS = int(SQLITE_TIMEOUT_SECONDS * 1000)
LOGGER = logging.getLogger("genorova.auth_store")


class AuthStoreError(ValueError):
    """Base error for auth store validation or persistence problems."""


class UserAlreadyExistsError(AuthStoreError):
    """Raised when the requested email address already belongs to a user."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def _session_expiry_iso() -> str:
    return (utc_now() + timedelta(days=SESSION_TTL_DAYS)).isoformat()


def normalize_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not EMAIL_REGEX.match(normalized):
        raise AuthStoreError("Please enter a valid email address.")
    return normalized


def normalize_name(name: str | None, email: str) -> str:
    candidate = (name or "").strip()
    if not candidate:
        candidate = email.split("@", 1)[0]
    return candidate[:80]


def validate_password(password: str) -> str:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AuthStoreError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    return password


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    resolved_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        resolved_salt,
        PASSWORD_ITERATIONS,
    )
    return (
        base64.b64encode(resolved_salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, password_salt: str, password_hash: str) -> bool:
    try:
        salt = base64.b64decode(password_salt.encode("ascii"))
    except (ValueError, TypeError):
        return False

    _, candidate_hash = _hash_password(password, salt=salt)
    return hmac.compare_digest(candidate_hash, password_hash)


def _public_user(row: sqlite3.Row) -> dict[str, str]:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "created_at": row["created_at"],
    }


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions (user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions (expires_at)"
        )
        conn.commit()
    finally:
        conn.close()


def create_user(db_path: Path, *, email: str, password: str, name: str | None = None) -> dict[str, str]:
    init_db(db_path)
    normalized_email = normalize_email(email)
    validate_password(password)
    resolved_name = normalize_name(name, normalized_email)
    password_salt, password_hash = _hash_password(password)
    now = utc_now_iso()

    conn = _connect(db_path)
    try:
        user_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO users (id, email, name, password_hash, password_salt, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, normalized_email, resolved_name, password_hash, password_salt, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, email, name, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return _public_user(row)
    except sqlite3.IntegrityError as exc:
        raise UserAlreadyExistsError("An account with that email already exists.") from exc
    finally:
        conn.close()


def authenticate_user(db_path: Path, *, email: str, password: str) -> dict[str, str] | None:
    init_db(db_path)
    normalized_email = normalize_email(email)

    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT id, email, name, password_hash, password_salt, created_at
            FROM users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()
        if row is None:
            return None
        if not verify_password(password, row["password_salt"], row["password_hash"]):
            return None
        return _public_user(row)
    finally:
        conn.close()


def create_session(db_path: Path, *, user_id: str) -> str:
    init_db(db_path)
    session_id = secrets.token_urlsafe(32)
    now = utc_now_iso()
    expires_at = _session_expiry_iso()

    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO auth_sessions (id, user_id, created_at, updated_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, user_id, now, now, expires_at),
        )
        conn.commit()
        return session_id
    finally:
        conn.close()


def delete_session(db_path: Path, *, session_id: str) -> None:
    init_db(db_path)
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM auth_sessions WHERE id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def delete_expired_sessions(db_path: Path) -> None:
    init_db(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            "DELETE FROM auth_sessions WHERE expires_at <= ?",
            (utc_now_iso(),),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_for_session(db_path: Path, *, session_id: str) -> dict[str, str] | None:
    if not session_id:
        return None

    init_db(db_path)
    delete_expired_sessions(db_path)
    now = utc_now_iso()

    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT users.id, users.email, users.name, users.created_at
            FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.id = ? AND auth_sessions.expires_at > ?
            """,
            (session_id, now),
        ).fetchone()
        if row is None:
            return None

        conn.execute(
            "UPDATE auth_sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        conn.commit()
        return _public_user(row)
    finally:
        conn.close()


def get_storage_status(db_path: Path) -> dict[str, Any]:
    status = {
        "available": False,
        "initialized": False,
        "path": str(db_path),
        "durability": "persistent",
        "users_count": 0,
        "session_count": 0,
        "size_bytes": 0,
        "last_error": None,
    }

    try:
        init_db(db_path)
        if db_path.exists():
            status["initialized"] = True
            status["size_bytes"] = db_path.stat().st_size

        conn = _connect(db_path)
        try:
            user_row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
            session_row = conn.execute("SELECT COUNT(*) AS cnt FROM auth_sessions").fetchone()
            status["users_count"] = int(user_row["cnt"] or 0) if user_row else 0
            status["session_count"] = int(session_row["cnt"] or 0) if session_row else 0
            status["available"] = True
        finally:
            conn.close()
    except Exception as exc:
        status["last_error"] = str(exc)
        LOGGER.warning("Unable to inspect auth storage at %s: %s", db_path, exc)

    return status
