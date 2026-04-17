from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar


LOGGER = logging.getLogger("genorova.chat_memory")

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONVERSATION_TITLE = "New Chat"
CHAT_MEMORY_DB_ENV = "CHAT_MEMORY_DB_PATH"
SQLITE_TIMEOUT_SECONDS = 5.0
SQLITE_BUSY_TIMEOUT_MS = int(SQLITE_TIMEOUT_SECONDS * 1000)
MEMORY_DB_URI = f"file:genorova_chat_memory_{uuid.uuid4().hex}?mode=memory&cache=shared"

T = TypeVar("T")


@dataclass(frozen=True)
class StorageCandidate:
    label: str
    mode: str
    database: str
    path: str | None = None
    uri: bool = False

    @property
    def key(self) -> str:
        return f"{self.mode}:{self.database}"

    @property
    def display_path(self) -> str:
        return self.path or self.database


@dataclass
class StorageStatus:
    available: bool = False
    initialized: bool = False
    mode: str = "uninitialized"
    durability: str = "unknown"
    label: str | None = None
    path: str | None = None
    degraded: bool = False
    fallback_active: bool = False
    last_error: str | None = None
    message: str | None = None


_STATE_LOCK = threading.RLock()
_ACTIVE_CANDIDATE: StorageCandidate | None = None
_MEMORY_ANCHOR: sqlite3.Connection | None = None
_STORAGE_STATUS = StorageStatus()


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


def _runtime_db_path() -> Path:
    return Path.cwd() / "runtime" / "chat_memory.db"


def _temp_db_path() -> Path:
    return Path(tempfile.gettempdir()) / "GenorovaAI" / "chat_memory.db"


def _localappdata_db_path() -> Path | None:
    localappdata = os.getenv("LOCALAPPDATA", "").strip()
    if os.name != "nt" or not localappdata:
        return None
    return Path(localappdata) / "GenorovaAI" / "chat_memory.db"


def _env_override_db_path() -> Path | None:
    override = os.getenv(CHAT_MEMORY_DB_ENV, "").strip()
    if not override:
        return None
    return Path(override).expanduser()


def _append_file_candidate(
    candidates: list[StorageCandidate],
    seen: set[str],
    *,
    label: str,
    path: Path | None,
) -> None:
    if path is None:
        return
    normalized = str(path.expanduser())
    if normalized in seen:
        return
    seen.add(normalized)
    candidates.append(
        StorageCandidate(
            label=label,
            mode="file",
            database=normalized,
            path=normalized,
        )
    )


def _build_storage_candidates() -> list[StorageCandidate]:
    candidates: list[StorageCandidate] = []
    seen: set[str] = set()

    _append_file_candidate(
        candidates,
        seen,
        label="env_override",
        path=_env_override_db_path(),
    )
    _append_file_candidate(
        candidates,
        seen,
        label="localappdata",
        path=_localappdata_db_path(),
    )
    _append_file_candidate(
        candidates,
        seen,
        label="runtime",
        path=_runtime_db_path(),
    )
    _append_file_candidate(
        candidates,
        seen,
        label="tempdir",
        path=_temp_db_path(),
    )
    candidates.append(
        StorageCandidate(
            label="memory",
            mode="memory",
            database=MEMORY_DB_URI,
            uri=True,
        )
    )
    return candidates


def _open_connection(candidate: StorageCandidate) -> sqlite3.Connection:
    if candidate.mode == "file":
        db_path = Path(candidate.path or candidate.database)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            candidate.database,
            timeout=SQLITE_TIMEOUT_SECONDS,
        )
    else:
        conn = sqlite3.connect(
            candidate.database,
            timeout=SQLITE_TIMEOUT_SECONDS,
            uri=True,
            check_same_thread=False,
        )

    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _close_memory_anchor() -> None:
    global _MEMORY_ANCHOR

    if _MEMORY_ANCHOR is None:
        return

    try:
        _MEMORY_ANCHOR.close()
    except sqlite3.Error:
        LOGGER.debug("Ignoring close error while releasing in-memory chat DB anchor.", exc_info=True)
    finally:
        _MEMORY_ANCHOR = None


def _set_storage_status(
    *,
    candidate: StorageCandidate | None,
    initialized: bool,
    fallback_active: bool,
    last_error: str | None,
) -> None:
    global _STORAGE_STATUS

    if candidate is None:
        _STORAGE_STATUS = StorageStatus(
            available=False,
            initialized=False,
            mode="unavailable",
            durability="unavailable",
            degraded=True,
            fallback_active=fallback_active,
            last_error=last_error,
            message="Chat storage is unavailable.",
        )
        return

    degraded = candidate.mode == "memory"
    message = None
    if degraded:
        message = (
            "Chat storage is running in degraded in-memory mode. "
            "Conversation history will be lost when the process restarts."
        )
    elif fallback_active:
        message = f"Chat storage fell back to {candidate.label}."

    _STORAGE_STATUS = StorageStatus(
        available=True,
        initialized=initialized,
        mode=candidate.mode,
        durability="persistent" if candidate.mode == "file" else "ephemeral",
        label=candidate.label,
        path=candidate.path,
        degraded=degraded,
        fallback_active=fallback_active,
        last_error=last_error,
        message=message,
    )


def get_storage_status() -> dict[str, Any]:
    with _STATE_LOCK:
        return asdict(_STORAGE_STATUS)


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


def _initialize_schema(conn: sqlite3.Connection) -> None:
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


def _bootstrap_storage(*, force: bool = False, skip_key: str | None = None) -> StorageCandidate:
    global _ACTIVE_CANDIDATE, _MEMORY_ANCHOR

    with _STATE_LOCK:
        if _ACTIVE_CANDIDATE is not None and _STORAGE_STATUS.initialized and not force:
            return _ACTIVE_CANDIDATE

        if force:
            _ACTIVE_CANDIDATE = None
            _close_memory_anchor()

        candidates = _build_storage_candidates()
        primary_key = candidates[0].key if candidates else None
        last_error: str | None = None

        for candidate in candidates:
            if skip_key is not None and candidate.key == skip_key:
                continue

            try:
                if candidate.mode == "memory":
                    _close_memory_anchor()
                    anchor = _open_connection(candidate)
                    _initialize_schema(anchor)
                    _MEMORY_ANCHOR = anchor
                else:
                    conn = _open_connection(candidate)
                    try:
                        _initialize_schema(conn)
                    finally:
                        conn.close()

                _ACTIVE_CANDIDATE = candidate
                fallback_active = skip_key is not None or candidate.key != primary_key
                _set_storage_status(
                    candidate=candidate,
                    initialized=True,
                    fallback_active=fallback_active,
                    last_error=last_error,
                )
                LOGGER.info("Chat storage selected: %s", candidate.display_path)
                if fallback_active:
                    LOGGER.warning(
                        "Chat storage fallback activated; using %s (%s).",
                        candidate.display_path,
                        candidate.mode,
                    )
                if candidate.mode == "memory":
                    LOGGER.warning(
                        "Chat storage is running in degraded in-memory mode; "
                        "conversation history will not survive restart."
                    )
                return candidate
            except (OSError, sqlite3.Error) as exc:
                last_error = f"{candidate.label}: {exc}"
                LOGGER.warning(
                    "Failed to initialize chat storage candidate %s (%s): %s",
                    candidate.label,
                    candidate.display_path,
                    exc,
                )

        _ACTIVE_CANDIDATE = None
        _close_memory_anchor()
        _set_storage_status(
            candidate=None,
            initialized=False,
            fallback_active=True,
            last_error=last_error,
        )
        raise RuntimeError(last_error or "Chat storage is unavailable.")


def init_db() -> dict[str, Any]:
    _bootstrap_storage()
    return get_storage_status()


def get_db_path() -> Path | None:
    candidate = _bootstrap_storage()
    if candidate.mode != "file" or not candidate.path:
        return None
    return Path(candidate.path)


def get_connection() -> sqlite3.Connection:
    candidate = _bootstrap_storage()
    return _open_connection(candidate)


def _run_with_connection(operation: Callable[[sqlite3.Connection], T]) -> T:
    candidate = _bootstrap_storage()
    last_error: Exception | None = None

    for attempt in range(2):
        try:
            conn = _open_connection(candidate)
            try:
                return operation(conn)
            finally:
                conn.close()
        except (OSError, sqlite3.Error) as exc:
            last_error = exc
            LOGGER.warning(
                "Chat storage operation failed on %s: %s",
                candidate.display_path,
                exc,
            )
            if attempt == 1:
                break
            candidate = _bootstrap_storage(force=True, skip_key=candidate.key)

    raise RuntimeError(f"Chat storage is unavailable: {last_error}") from last_error


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

    def _create(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT INTO conversations (id, title, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, final_title, _json_dumps(metadata), now, now),
        )
        conn.commit()

    _run_with_connection(_create)
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

    update_fields: dict[str, str] = {}
    if title and (not conversation["title"] or conversation["title"] == DEFAULT_CONVERSATION_TITLE):
        cleaned = title.strip()
        if cleaned:
            update_fields["title"] = cleaned
    if metadata:
        merged_metadata = conversation.get("metadata") or {}
        merged_metadata.update(metadata)
        update_fields["metadata_json"] = _json_dumps(merged_metadata)

    if update_fields:
        update_fields["updated_at"] = utc_now_iso()
        assignments = ", ".join(f"{key} = ?" for key in update_fields.keys())
        params = list(update_fields.values()) + [conversation_id]

        def _update(conn: sqlite3.Connection) -> None:
            conn.execute(
                f"UPDATE conversations SET {assignments} WHERE id = ?",
                params,
            )
            conn.commit()

        _run_with_connection(_update)

    return get_conversation(conversation_id)


def update_conversation_title(conversation_id: str, title: str) -> None:
    cleaned = (title or "").strip()
    if not cleaned:
        return

    def _update(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            UPDATE conversations
            SET title = ?, updated_at = ?
            WHERE id = ? AND (title IS NULL OR title = ?)
            """,
            (cleaned, utc_now_iso(), conversation_id, DEFAULT_CONVERSATION_TITLE),
        )
        conn.commit()

    _run_with_connection(_update)


def list_conversations(limit: int = 50) -> list[dict[str, Any]]:
    def _list(conn: sqlite3.Connection) -> list[dict[str, Any]]:
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

    return _run_with_connection(_list)


def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    def _get(conn: sqlite3.Connection) -> dict[str, Any] | None:
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

    return _run_with_connection(_get)


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

    def _add(conn: sqlite3.Connection) -> dict[str, Any]:
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

    return _run_with_connection(_add)


def get_messages(conversation_id: str) -> list[dict[str, Any]]:
    def _get(conn: sqlite3.Connection) -> list[dict[str, Any]]:
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

    return _run_with_connection(_get)


def get_conversation_with_messages(conversation_id: str) -> dict[str, Any] | None:
    conversation = get_conversation(conversation_id)
    if conversation is None:
        return None

    conversation["messages"] = get_messages(conversation_id)
    return conversation
