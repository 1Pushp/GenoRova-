from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
SESSION_TTL_DAYS = 7
SUPPORT_EMAIL = "pushpdwivedi911@gmail.com"
SQLITE_TIMEOUT_SECONDS = 5.0
SQLITE_BUSY_TIMEOUT_MS = int(SQLITE_TIMEOUT_SECONDS * 1000)
LOGGER = logging.getLogger("genorova.auth_store")

# Plan names and their daily generation limits.
# "enterprise" uses a very high cap; billing deferral means all users
# default to "free" unless manually overridden via plan_overrides.
PLAN_LIMITS: dict[str, int] = {
    "free": 10,
    "research": 500,
    "enterprise": 100_000,
}
DEFAULT_PLAN = "free"


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_requests (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                resolved_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS support_queue (
                id TEXT PRIMARY KEY,
                request_type TEXT NOT NULL,
                target_email TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                key_prefix TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                last_used_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys (user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys (key_hash)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_user_day ON usage_events (user_id, created_at)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_overrides (
                user_id TEXT PRIMARY KEY,
                plan TEXT NOT NULL,
                set_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
            """
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


def create_password_reset_request(db_path: Path, *, email: str) -> dict[str, str]:
    init_db(db_path)
    normalized = normalize_email(email)
    request_id = str(uuid.uuid4())
    support_queue_id = str(uuid.uuid4())
    now = utc_now_iso()
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO password_reset_requests (id, email, requested_at, status)
            VALUES (?, ?, ?, 'pending')
            """,
            (request_id, normalized, now),
        )
        conn.execute(
            """
            INSERT INTO support_queue (
                id,
                request_type,
                target_email,
                payload_json,
                status,
                created_at
            )
            VALUES (?, 'password_reset', ?, ?, 'pending', ?)
            """,
            (
                support_queue_id,
                SUPPORT_EMAIL,
                json.dumps({"request_id": request_id, "email": normalized}),
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "id": request_id,
        "email": normalized,
        "requested_at": now,
        "status": "pending",
        "support_queue_id": support_queue_id,
        "support_target_email": SUPPORT_EMAIL,
    }


def _hash_api_key(raw_key: str) -> str:
    """Return a SHA-256 hex digest of the raw API key (never stored in plaintext)."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def create_api_key(db_path: Path, *, user_id: str, name: str) -> dict[str, str]:
    """
    Generate a new API key for a user.

    Returns a dict with the raw key (shown ONCE, never again) plus safe metadata.
    The raw key is not stored — only its SHA-256 hash is persisted.
    """
    init_db(db_path)
    raw_key = "gnrv_" + secrets.token_urlsafe(32)
    key_hash = _hash_api_key(raw_key)
    key_prefix = raw_key[:12]
    key_id = str(uuid.uuid4())
    now = utc_now_iso()
    resolved_name = (name or "").strip()[:80] or "API Key"

    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO api_keys (id, user_id, key_hash, key_prefix, name, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (key_id, user_id, key_hash, key_prefix, resolved_name, now),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "id": key_id,
        "key": raw_key,
        "key_prefix": key_prefix,
        "name": resolved_name,
        "created_at": now,
        "revoked_at": None,
        "last_used_at": None,
    }


def list_api_keys(db_path: Path, *, user_id: str) -> list[dict[str, Any]]:
    """Return all non-revoked API keys for a user (safe metadata only, no raw key)."""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, key_prefix, name, created_at, revoked_at, last_used_at
            FROM api_keys
            WHERE user_id = ? AND revoked_at IS NULL
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "key_prefix": row["key_prefix"],
                "name": row["name"],
                "created_at": row["created_at"],
                "revoked_at": row["revoked_at"],
                "last_used_at": row["last_used_at"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def revoke_api_key(db_path: Path, *, key_id: str, user_id: str) -> bool:
    """
    Revoke an API key by ID for a user.

    Returns True if the key was found and revoked, False if not found or not owned.
    """
    init_db(db_path)
    now = utc_now_iso()
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            """
            UPDATE api_keys SET revoked_at = ?
            WHERE id = ? AND user_id = ? AND revoked_at IS NULL
            """,
            (now, key_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_user_for_api_key(db_path: Path, *, raw_key: str) -> dict[str, str] | None:
    """
    Validate an API key and return the owning user if valid.

    Returns None if the key is unknown or revoked.
    Also updates last_used_at on a successful hit.
    """
    if not raw_key:
        return None
    init_db(db_path)
    key_hash = _hash_api_key(raw_key)
    now = utc_now_iso()
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT users.id, users.email, users.name, users.created_at,
                   api_keys.id AS key_id
            FROM api_keys
            JOIN users ON users.id = api_keys.user_id
            WHERE api_keys.key_hash = ? AND api_keys.revoked_at IS NULL
            """,
            (key_hash,),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
            (now, row["key_id"]),
        )
        conn.commit()
        return _public_user(row)
    finally:
        conn.close()


def record_usage_event(db_path: Path, *, user_id: str, endpoint: str) -> None:
    """Record a single usage event (e.g. a generation call) for rate-limit accounting."""
    init_db(db_path)
    event_id = str(uuid.uuid4())
    now = utc_now_iso()
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO usage_events (id, user_id, endpoint, created_at) VALUES (?, ?, ?, ?)",
            (event_id, user_id, endpoint, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_daily_usage_count(db_path: Path, *, user_id: str, endpoint: str) -> int:
    """Return the number of usage events for a user on today (UTC calendar day)."""
    init_db(db_path)
    today_prefix = utc_now().strftime("%Y-%m-%d")
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM usage_events
            WHERE user_id = ? AND endpoint = ? AND created_at LIKE ?
            """,
            (user_id, endpoint, f"{today_prefix}%"),
        ).fetchone()
        return int(row["cnt"] or 0) if row else 0
    finally:
        conn.close()


def get_plan_for_user(db_path: Path, *, user_id: str) -> str:
    """
    Return the plan name for a user.

    Looks up plan_overrides (manually set by admin); defaults to DEFAULT_PLAN
    when no override exists (billing is deferred).
    """
    init_db(db_path)
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT plan FROM plan_overrides WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row and row["plan"] in PLAN_LIMITS:
            return row["plan"]
        return DEFAULT_PLAN
    finally:
        conn.close()


def set_plan_for_user(db_path: Path, *, user_id: str, plan: str) -> None:
    """Manually assign a plan to a user (admin use only)."""
    if plan not in PLAN_LIMITS:
        raise AuthStoreError(f"Unknown plan '{plan}'. Valid plans: {list(PLAN_LIMITS)}")
    init_db(db_path)
    now = utc_now_iso()
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO plan_overrides (user_id, plan, set_at)
            VALUES (?, ?, ?)
            ON CONFLICT (user_id) DO UPDATE SET plan = excluded.plan, set_at = excluded.set_at
            """,
            (user_id, plan, now),
        )
        conn.commit()
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
        "support_queue_count": 0,
        "api_keys_count": 0,
        "usage_events_count": 0,
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
            support_row = conn.execute("SELECT COUNT(*) AS cnt FROM support_queue").fetchone()
            keys_row = conn.execute("SELECT COUNT(*) AS cnt FROM api_keys WHERE revoked_at IS NULL").fetchone()
            usage_row = conn.execute("SELECT COUNT(*) AS cnt FROM usage_events").fetchone()
            status["users_count"] = int(user_row["cnt"] or 0) if user_row else 0
            status["session_count"] = int(session_row["cnt"] or 0) if session_row else 0
            status["support_queue_count"] = int(support_row["cnt"] or 0) if support_row else 0
            status["api_keys_count"] = int(keys_row["cnt"] or 0) if keys_row else 0
            status["usage_events_count"] = int(usage_row["cnt"] or 0) if usage_row else 0
            status["available"] = True
        finally:
            conn.close()
    except Exception as exc:
        status["last_error"] = str(exc)
        LOGGER.warning("Unable to inspect auth storage at %s: %s", db_path, exc)

    return status
