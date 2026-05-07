from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger("genorova.chat_store")

DEFAULT_SESSION_TITLE = "New Chat"
SQLITE_TIMEOUT_SECONDS = 5.0
SQLITE_BUSY_TIMEOUT_MS = int(SQLITE_TIMEOUT_SECONDS * 1000)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str | None:
    return json.dumps(value) if value is not None else None


def _json_loads(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _get_column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    if column_name in _get_column_names(conn, table_name):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init_db(db_path: Path) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                state_json TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                payload_json TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
            )
            """
        )
        _ensure_column(conn, "chat_sessions", "state_json", "TEXT")
        _ensure_column(conn, "chat_sessions", "metadata_json", "TEXT")
        _ensure_column(conn, "chat_messages", "payload_json", "TEXT")
        _ensure_column(conn, "chat_messages", "metadata_json", "TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions (user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages (session_id)")
        conn.commit()
    finally:
        conn.close()


def _session_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "state": _json_loads(row["state_json"]),
        "metadata": _json_loads(row["metadata_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if "message_count" in row.keys():
        payload["message_count"] = int(row["message_count"] or 0)
    if "last_message_preview" in row.keys():
        payload["last_message_preview"] = row["last_message_preview"]
    return payload


def _message_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "payload": _json_loads(row["payload_json"]),
        "metadata": _json_loads(row["metadata_json"]),
        "created_at": row["created_at"],
    }


def upsert_user(db_path: Path, *, user: dict[str, str]) -> None:
    init_db(db_path)
    now = utc_now_iso()
    created_at = str(user.get("created_at") or now)
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO users (id, email, name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                email = excluded.email,
                name = excluded.name,
                updated_at = excluded.updated_at
            """,
            (
                user["id"],
                user["email"],
                user["name"],
                created_at,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_session(
    db_path: Path,
    *,
    session_id: str,
    user_id: str | None = None,
) -> dict[str, Any] | None:
    init_db(db_path)
    conn = _connect(db_path)
    try:
        if user_id is None:
            row = conn.execute(
                """
                SELECT id, user_id, title, state_json, metadata_json, created_at, updated_at
                FROM chat_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id, user_id, title, state_json, metadata_json, created_at, updated_at
                FROM chat_sessions
                WHERE id = ? AND user_id = ?
                """,
                (session_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return _session_row_to_dict(row)
    finally:
        conn.close()


def ensure_session(
    db_path: Path,
    *,
    session_id: str,
    user: dict[str, str],
    title: str | None = None,
    state: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    upsert_user(db_path, user=user)
    now = utc_now_iso()
    final_title = (title or DEFAULT_SESSION_TITLE).strip() or DEFAULT_SESSION_TITLE
    existing = get_session(db_path, session_id=session_id)

    conn = _connect(db_path)
    try:
        if existing is None:
            conn.execute(
                """
                INSERT INTO chat_sessions (
                    id,
                    user_id,
                    title,
                    state_json,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user["id"],
                    final_title,
                    _json_dumps(state or {}),
                    _json_dumps(metadata or {}),
                    now,
                    now,
                ),
            )
            conn.commit()
        elif existing["user_id"] != user["id"]:
            raise ValueError("Chat session belongs to a different user.")
        else:
            next_title = existing["title"]
            if next_title == DEFAULT_SESSION_TITLE and final_title != DEFAULT_SESSION_TITLE:
                next_title = final_title
            next_state = dict(existing.get("state") or {})
            if state:
                next_state.update(state)
            next_metadata = dict(existing.get("metadata") or {})
            if metadata:
                next_metadata.update(metadata)
            conn.execute(
                """
                UPDATE chat_sessions
                SET title = ?, state_json = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_title,
                    _json_dumps(next_state),
                    _json_dumps(next_metadata),
                    now,
                    session_id,
                ),
            )
            conn.commit()
    finally:
        conn.close()

    return get_session(db_path, session_id=session_id, user_id=user["id"]) or {
        "id": session_id,
        "user_id": user["id"],
        "title": final_title,
        "state": state or {},
        "metadata": metadata or {},
        "created_at": now,
        "updated_at": now,
    }


def update_session_state(
    db_path: Path,
    *,
    session_id: str,
    user: dict[str, str],
    state: dict[str, Any],
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ensure_session(
        db_path,
        session_id=session_id,
        user=user,
        title=title,
        state=state,
        metadata=metadata,
    )


def add_message(
    db_path: Path,
    *,
    session_id: str,
    user: dict[str, str],
    role: str,
    content: str,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    session = ensure_session(
        db_path,
        session_id=session_id,
        user=user,
        title=title,
    )
    now = utc_now_iso()
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO chat_messages (
                session_id,
                role,
                content,
                payload_json,
                metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session["id"],
                role,
                content,
                _json_dumps(payload),
                _json_dumps(metadata),
                now,
            ),
        )
        conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
            (now, session["id"]),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT id, role, content, payload_json, metadata_json, created_at
            FROM chat_messages
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        return _message_row_to_dict(row)
    finally:
        conn.close()


def get_messages(
    db_path: Path,
    *,
    session_id: str,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    session = get_session(db_path, session_id=session_id, user_id=user_id)
    if session is None:
        return []

    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, role, content, payload_json, metadata_json, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
        return [_message_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def get_session_with_messages(
    db_path: Path,
    *,
    session_id: str,
    user_id: str | None = None,
) -> dict[str, Any] | None:
    session = get_session(db_path, session_id=session_id, user_id=user_id)
    if session is None:
        return None
    session["messages"] = get_messages(db_path, session_id=session_id, user_id=user_id)
    return session


def list_sessions(
    db_path: Path,
    *,
    user_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    init_db(db_path)
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT
                s.id,
                s.user_id,
                s.title,
                s.state_json,
                s.metadata_json,
                s.created_at,
                s.updated_at,
                (
                    SELECT COUNT(*)
                    FROM chat_messages m
                    WHERE m.session_id = s.id
                ) AS message_count,
                (
                    SELECT m.content
                    FROM chat_messages m
                    WHERE m.session_id = s.id
                    ORDER BY m.id DESC
                    LIMIT 1
                ) AS last_message_preview
            FROM chat_sessions s
            WHERE s.user_id = ?
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [_session_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def get_storage_status(db_path: Path) -> dict[str, Any]:
    status = {
        "available": False,
        "initialized": False,
        "mode": "sqlite",
        "durability": "persistent",
        "path": str(db_path),
        "user_count": 0,
        "session_count": 0,
        "message_count": 0,
        "size_bytes": 0,
        "last_error": None,
        "message": "Authenticated chat history is stored in SQLite.",
    }

    try:
        init_db(db_path)
        if db_path.exists():
            status["initialized"] = True
            status["size_bytes"] = db_path.stat().st_size

        conn = _connect(db_path)
        try:
            user_row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
            session_row = conn.execute("SELECT COUNT(*) AS cnt FROM chat_sessions").fetchone()
            message_row = conn.execute("SELECT COUNT(*) AS cnt FROM chat_messages").fetchone()
            status["user_count"] = int(user_row["cnt"] or 0) if user_row else 0
            status["session_count"] = int(session_row["cnt"] or 0) if session_row else 0
            status["message_count"] = int(message_row["cnt"] or 0) if message_row else 0
            status["available"] = True
        finally:
            conn.close()
    except Exception as exc:
        status["last_error"] = str(exc)
        LOGGER.warning("Unable to inspect chat storage at %s: %s", db_path, exc)

    return status
