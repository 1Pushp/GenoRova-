from __future__ import annotations

import importlib
import sqlite3
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _reload_chat_memory():
    import chat_memory

    return importlib.reload(chat_memory)


def _reload_backend_main():
    import main as backend_main

    return importlib.reload(backend_main)


@pytest.fixture
def chat_temp_dir() -> Path:
    root = Path(tempfile.gettempdir()) / "genorova_chat_memory_tests"
    root.mkdir(parents=True, exist_ok=True)
    temp_dir = root / f"case_{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def test_chat_memory_creates_missing_directory(monkeypatch, chat_temp_dir):
    db_path = chat_temp_dir / "nested" / "chat" / "state" / "chat_memory.db"
    monkeypatch.chdir(chat_temp_dir)
    monkeypatch.setenv("CHAT_MEMORY_DB_PATH", str(db_path))
    monkeypatch.setenv("LOCALAPPDATA", str(chat_temp_dir / "LocalAppData"))

    chat_memory = _reload_chat_memory()
    status = chat_memory.init_db()

    assert status["initialized"] is True
    assert status["mode"] == "file"
    assert status["path"] == str(db_path)
    assert db_path.exists()


def test_chat_memory_falls_back_from_broken_override_path(monkeypatch, chat_temp_dir):
    broken_parent = chat_temp_dir / "not_a_directory"
    broken_parent.write_text("this file blocks directory creation", encoding="utf-8")
    override_path = broken_parent / "child" / "chat_memory.db"

    monkeypatch.chdir(chat_temp_dir)
    monkeypatch.setenv("CHAT_MEMORY_DB_PATH", str(override_path))
    monkeypatch.setenv("LOCALAPPDATA", str(chat_temp_dir / "LocalAppData"))

    chat_memory = _reload_chat_memory()
    status = chat_memory.init_db()

    assert status["initialized"] is True
    assert status["fallback_active"] is True
    assert status["mode"] == "file"
    assert status["path"] != str(override_path)
    assert Path(status["path"]).exists()
    assert status["last_error"] is not None


def test_chat_memory_persists_conversation_and_messages(monkeypatch, chat_temp_dir):
    db_path = chat_temp_dir / "persistent" / "chat_memory.db"
    monkeypatch.chdir(chat_temp_dir)
    monkeypatch.setenv("CHAT_MEMORY_DB_PATH", str(db_path))
    monkeypatch.setenv("LOCALAPPDATA", str(chat_temp_dir / "LocalAppData"))

    chat_memory = _reload_chat_memory()
    chat_memory.init_db()

    conversation = chat_memory.create_conversation(
        title="Reliability Test",
        metadata={"source": "pytest"},
    )
    stored_message = chat_memory.add_message(
        conversation_id=conversation["id"],
        role="user",
        content="hello world",
        metadata={"kind": "smoke"},
    )

    loaded_conversation = chat_memory.get_conversation_with_messages(conversation["id"])
    all_conversations = chat_memory.list_conversations()

    assert stored_message["content"] == "hello world"
    assert loaded_conversation is not None
    assert loaded_conversation["title"] == "Reliability Test"
    assert len(loaded_conversation["messages"]) == 1
    assert loaded_conversation["messages"][0]["metadata"]["kind"] == "smoke"
    assert all_conversations[0]["id"] == conversation["id"]


def test_chat_memory_uses_in_memory_fallback_when_file_storage_fails(monkeypatch, chat_temp_dir):
    monkeypatch.chdir(chat_temp_dir)
    monkeypatch.delenv("CHAT_MEMORY_DB_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(chat_temp_dir / "LocalAppData"))

    chat_memory = _reload_chat_memory()
    original_open_connection = chat_memory._open_connection

    def fail_file_connections(candidate):
        if candidate.mode == "file":
            raise sqlite3.OperationalError("simulated file storage failure")
        return original_open_connection(candidate)

    monkeypatch.setattr(chat_memory, "_open_connection", fail_file_connections)

    status = chat_memory.init_db()
    conversation = chat_memory.create_conversation(title="Memory fallback")

    assert status["initialized"] is True
    assert status["mode"] == "memory"
    assert status["degraded"] is True
    assert status["fallback_active"] is True
    assert "in-memory" in (status["message"] or "")
    assert chat_memory.get_conversation(conversation["id"]) is not None


def test_backend_startup_and_chat_routes_survive_db_failure(monkeypatch, chat_temp_dir):
    monkeypatch.chdir(chat_temp_dir)
    monkeypatch.delenv("CHAT_MEMORY_DB_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(chat_temp_dir / "LocalAppData"))

    chat_memory = _reload_chat_memory()
    original_open_connection = chat_memory._open_connection

    def fail_file_connections(candidate):
        if candidate.mode == "file":
            raise sqlite3.OperationalError("simulated startup failure")
        return original_open_connection(candidate)

    monkeypatch.setattr(chat_memory, "_open_connection", fail_file_connections)

    backend_main = _reload_backend_main()

    with TestClient(backend_main.app) as client:
        storage_response = client.get("/chat/storage")
        conversations_response = client.get("/conversations")
        chat_response = client.post("/chat", json={"message": "hello there"})
        health_response = client.get("/health")

    assert storage_response.status_code == 200
    assert storage_response.json()["chat_storage"]["mode"] == "memory"

    assert conversations_response.status_code == 200
    assert conversations_response.json() == {"conversations": []}

    assert chat_response.status_code == 200
    chat_payload = chat_response.json()
    assert chat_payload["conversation_id"]
    assert chat_payload["message"]["role"] == "assistant"

    assert health_response.status_code == 200
    assert health_response.json()["chat_storage"]["degraded"] is True
