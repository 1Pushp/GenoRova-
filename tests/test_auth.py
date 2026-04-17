from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def auth_db_path():
    root = Path(tempfile.gettempdir()) / "genorova_auth_pytests"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{uuid.uuid4().hex}.db"


@pytest.fixture
def auth_client(api_module, monkeypatch, auth_db_path):
    monkeypatch.setattr(api_module, "AUTH_DB_PATH", auth_db_path)
    api_module.CHAT_SESSION_MEMORY.clear()

    with TestClient(api_module.app) as client:
        yield client


def test_auth_signup_me_logout_flow(auth_client):
    signup_response = auth_client.post(
        "/auth/signup",
        json={
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "password": "password123",
        },
    )

    assert signup_response.status_code == 200
    signup_payload = signup_response.json()

    assert signup_payload["user"]["email"] == "ada@example.com"
    assert signup_payload["user"]["name"] == "Ada Lovelace"
    assert "password_hash" not in signup_payload["user"]
    assert "password_salt" not in signup_payload["user"]

    me_response = auth_client.get("/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["user"]["email"] == "ada@example.com"

    logout_response = auth_client.post("/auth/logout")
    assert logout_response.status_code == 200
    assert logout_response.json()["success"] is True

    me_after_logout = auth_client.get("/auth/me")
    assert me_after_logout.status_code == 401


def test_auth_login_and_cookie_session_persist_across_refresh(api_module, monkeypatch, auth_db_path):
    monkeypatch.setattr(api_module, "AUTH_DB_PATH", auth_db_path)
    api_module.CHAT_SESSION_MEMORY.clear()

    with TestClient(api_module.app) as client:
        signup_response = client.post(
            "/auth/signup",
            json={
                "name": "Grace Hopper",
                "email": "grace@example.com",
                "password": "password123",
            },
        )
        assert signup_response.status_code == 200

        logout_response = client.post("/auth/logout")
        assert logout_response.status_code == 200

        login_response = client.post(
            "/auth/login",
            json={
                "email": "grace@example.com",
                "password": "password123",
            },
        )
        assert login_response.status_code == 200

        refreshed_cookies = client.cookies

    with TestClient(api_module.app) as refreshed_client:
        refreshed_client.cookies.update(refreshed_cookies)
        me_response = refreshed_client.get("/auth/me")

    assert me_response.status_code == 200
    assert me_response.json()["user"]["email"] == "grace@example.com"


def test_api_chat_requires_authentication(auth_client):
    response = auth_client.post(
        "/api/chat",
        json={
            "message": 'score "CCO"',
            "mode": "scientific",
            "history": [],
            "conversation_state": {},
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required."
