from __future__ import annotations

import tempfile
import uuid
from pathlib import Path


def test_health_and_ops_status_include_runtime_visibility(api_client, api_module, monkeypatch):
    temp_root = Path(tempfile.gettempdir()) / "genorova_ops_tests"
    temp_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(api_module, "AUTH_DB_PATH", temp_root / f"auth_{uuid.uuid4().hex}.db")
    monkeypatch.setattr(api_module, "DB_PATH", temp_root / f"molecules_{uuid.uuid4().hex}.db")
    api_module.CHAT_SESSION_MEMORY.clear()

    health_response = api_client.get("/health")
    assert health_response.status_code == 200
    health_payload = health_response.json()

    assert "health_status" in health_payload
    assert "degraded_states" in health_payload
    assert "storage_summary" in health_payload
    assert "auth" in health_payload["storage_summary"]
    assert "chat_session" in health_payload["storage_summary"]

    ops_response = api_client.get("/ops/status")
    assert ops_response.status_code == 200
    ops_payload = ops_response.json()

    assert "startup" in ops_payload
    assert "storage" in ops_payload
    assert "auth" in ops_payload["storage"]
    assert "molecules" in ops_payload["storage"]
    assert "chat_session" in ops_payload["storage"]
    assert "frontend" in ops_payload["storage"]

    ready_response = api_client.get("/ready")
    assert ready_response.status_code in {200, 503}
    ready_payload = ready_response.json()
    assert "ready" in ready_payload
    assert "checks" in ready_payload
    assert "version" in ready_payload

    version_response = api_client.get("/version")
    assert version_response.status_code == 200
    version_payload = version_response.json()
    assert version_payload["name"] == "Genorova AI"
    assert "version" in version_payload
