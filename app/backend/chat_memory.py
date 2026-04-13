import json
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PRIMARY_DB_PATH = DATA_DIR / "chat_memory.db"
FALLBACK_DB_PATH = Path(tempfile.gettempdir()) / "genorova_chat_memory.db"
DEFAULT_CONVERSATION_TITLE = "New Chat"
_ACTIVE_DB_PATH: Path | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: dict[str, Any] | None) -> str | None:
    return json.dumps(value) if value is not None else None


def _json_loads(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def get_db_path() -> Path:
    global _ACTIVE_DB_PATH

    if _ACTIVE_DB_PATH is not None:
        return _ACTIVE_DB_PATH

    for candidate in (PRIMARY_DB_PATH, FALLBACK_DB_PATH):
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(candidate)
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.close()
            _ACTIVE_DB_PATH = candidate
            return candidate
        except sqlite3.Error:
            continue

    _ACTIVE_DB_PATH = PRIMARY_DB_PATH
    return _ACTIVE_DB_PATH


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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
    columns = _get_column_names(conn, table_name)
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                message_type TEXT NOT NULL DEFAULT 'text',
                tool_used TEXT,
                data_json TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations (id)
            )
            """
        )

        _ensure_column(conn, "conversations", "title", f"TEXT NOT NULL DEFAULT '{DEFAULT_CONVERSATION_TITLE}'")
        _ensure_column(conn, "conversations", "metadata_json", "TEXT")
        _ensure_column(conn, "messages", "message_type", "TEXT NOT NULL DEFAULT 'text'")
        _ensure_column(conn, "messages", "tool_used", "TEXT")
        _ensure_column(conn, "messages", "metadata_json", "TEXT")
        conn.commit()


def _conversation_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "metadata": _json_loads(row["metadata_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _message_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "type": row["message_type"],
        "tool_used": row["tool_used"],
        "data": _json_loads(row["data_json"]),
        "metadata": _json_loads(row["metadata_json"]),
        "created_at": row["created_at"],
    }


def create_conversation(
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conversation_id = str(uuid.uuid4())
    now = utc_now_iso()
    final_title = (title or DEFAULT_CONVERSATION_TITLE).strip() or DEFAULT_CONVERSATION_TITLE

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO conversations (id, title, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, final_title, _json_dumps(metadata), now, now),
        )
        conn.commit()

    return get_conversation(conversation_id)


def ensure_conversation(
    conversation_id: str | None = None,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not conversation_id:
        return create_conversation(title=title, metadata=metadata)

    conversation = get_conversation(conversation_id)
    if conversation is None:
        return create_conversation(title=title, metadata=metadata)

    update_fields = {}
    if title and (not conversation["title"] or conversation["title"] == DEFAULT_CONVERSATION_TITLE):
        update_fields["title"] = title.strip()
    if metadata:
        merged_metadata = conversation.get("metadata") or {}
        merged_metadata.update(metadata)
        update_fields["metadata_json"] = _json_dumps(merged_metadata)

    if update_fields:
        update_fields["updated_at"] = utc_now_iso()
        assignments = ", ".join(f"{key} = ?" for key in update_fields.keys())
        params = list(update_fields.values()) + [conversation_id]
        with get_connection() as conn:
            conn.execute(
                f"UPDATE conversations SET {assignments} WHERE id = ?",
                params,
            )
            conn.commit()

    return get_conversation(conversation_id)


def update_conversation_title(conversation_id: str, title: str) -> None:
    cleaned = (title or "").strip()
    if not cleaned:
        return

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE conversations
            SET title = ?, updated_at = ?
            WHERE id = ? AND (title IS NULL OR title = ?)
            """,
            (cleaned, utc_now_iso(), conversation_id, DEFAULT_CONVERSATION_TITLE),
        )
        conn.commit()


def list_conversations(limit: int = 50) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, metadata_json, created_at, updated_at
            FROM conversations
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [_conversation_row_to_dict(row) for row in rows]


def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, title, metadata_json, created_at, updated_at
            FROM conversations
            WHERE id = ?
            """,
            (conversation_id,),
        ).fetchone()

    if row is None:
        return None
    return _conversation_row_to_dict(row)


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    message_type: str = "text",
    tool_used: str | None = None,
    data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_conversation(conversation_id)
    now = utc_now_iso()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO messages (
                conversation_id,
                role,
                content,
                message_type,
                tool_used,
                data_json,
                metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                role,
                content,
                message_type,
                tool_used,
                _json_dumps(data),
                _json_dumps(metadata),
                now,
            ),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT id, role, content, message_type, tool_used, data_json, metadata_json, created_at
            FROM messages
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

    return _message_row_to_dict(row)


def get_messages(conversation_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, message_type, tool_used, data_json, metadata_json, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()

    return [_message_row_to_dict(row) for row in rows]


def get_conversation_with_messages(conversation_id: str) -> dict[str, Any] | None:
    conversation = get_conversation(conversation_id)
    if conversation is None:
        return None

    conversation["messages"] = get_messages(conversation_id)
    return conversation
