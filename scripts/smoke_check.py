from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import os
import sys
import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
GENOROVA_SRC = ROOT / "genorova" / "src"


def _ensure_import_paths() -> None:
    for candidate in (ROOT, GENOROVA_SRC):
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)


def _load_api_module(auth_db_path: Path, molecule_db_path: Path):
    os.environ["GENOROVA_AUTH_DB_PATH"] = str(auth_db_path)
    _ensure_import_paths()

    module_name = "genorova.src.api"
    if module_name in sys.modules:
        api_module = importlib.reload(sys.modules[module_name])
    else:
        api_module = importlib.import_module(module_name)

    api_module.AUTH_DB_PATH = auth_db_path
    api_module.DB_PATH = molecule_db_path
    api_module.CHAT_SESSION_MEMORY.clear()
    return api_module


def _check(condition: bool, label: str, detail: str = "") -> None:
    if not condition:
        message = f"[FAIL] {label}"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message)
    suffix = f" - {detail}" if detail else ""
    print(f"[PASS] {label}{suffix}")


def _frontend_dist_status() -> tuple[bool, str]:
    dist_index = ROOT / "app" / "frontend" / "dist" / "index.html"
    return dist_index.exists(), str(dist_index)


def _quiet_request(callable_):
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
        return callable_()


def run_smoke(check_frontend_dist: bool = True) -> int:
    temp_root = Path(tempfile.gettempdir()) / "genorova_smoke"
    temp_root.mkdir(parents=True, exist_ok=True)
    auth_db_path = temp_root / f"auth_{uuid.uuid4().hex}.db"
    molecule_db_path = temp_root / f"molecules_{uuid.uuid4().hex}.db"
    email = f"smoke-{uuid.uuid4().hex[:10]}@example.com"

    api_module = _load_api_module(auth_db_path, molecule_db_path)

    with TestClient(api_module.app) as client:
        health = client.get("/health")
        _check(health.status_code == 200, "health", f"status_code={health.status_code}")
        health_payload = health.json()
        _check(health_payload.get("status") == "running", "health status", health_payload.get("status", "missing"))

        ops = client.get("/ops/status")
        _check(ops.status_code == 200, "ops status", f"status_code={ops.status_code}")
        ops_payload = ops.json()
        _check("storage" in ops_payload and "auth" in ops_payload["storage"], "ops storage payload", "auth storage visible")

        signup = client.post(
            "/auth/signup",
            json={
                "name": "Smoke Tester",
                "email": email,
                "password": "password123",
            },
        )
        _check(signup.status_code == 200, "signup", f"status_code={signup.status_code}")

        me = client.get("/auth/me")
        _check(me.status_code == 200, "auth/me", f"status_code={me.status_code}")
        _check(me.json()["user"]["email"] == email, "auth identity", me.json()["user"]["email"])

        score = _quiet_request(lambda: client.post("/score", json={"smiles": "CCO"}))
        _check(score.status_code == 200, "score", f"status_code={score.status_code}")
        _check(score.json().get("smiles") == "CCO", "score payload", "returned scored molecule")

        validate = _quiet_request(
            lambda: client.post(
                "/api/validate/chemistry",
                json={"smiles": "CCO"},
            )
        )
        _check(validate.status_code == 200, "validate chemistry", f"status_code={validate.status_code}")

        generate = _quiet_request(
            lambda: client.post(
                "/generate",
                json={"disease": "diabetes", "count": 2},
            )
        )
        _check(generate.status_code == 200, "generate", f"status_code={generate.status_code}")
        generate_payload = generate.json()
        _check("trust" in generate_payload, "generate trust payload", generate_payload.get("generation_status", "missing"))

        ranked = _quiet_request(lambda: client.get("/api/best"))
        _check(ranked.status_code == 200, "ranked candidate response", f"status_code={ranked.status_code}")
        ranked_payload = ranked.json()
        _check("molecules" in ranked_payload, "ranked candidate payload", ranked_payload.get("source", "missing"))

        chat = _quiet_request(
            lambda: client.post(
                "/api/chat",
                json={
                    "message": "Show the top computational candidates in the active diabetes workflow",
                    "mode": "scientific",
                    "history": [],
                    "conversation_state": {},
                },
            )
        )
        _check(chat.status_code == 200, "chat", f"status_code={chat.status_code}")
        _check(bool(chat.json().get("summary")), "chat summary", "summary returned")

        logout = client.post("/auth/logout")
        _check(logout.status_code == 200, "logout", f"status_code={logout.status_code}")

        me_after_logout = client.get("/auth/me")
        _check(me_after_logout.status_code == 401, "auth/me after logout", f"status_code={me_after_logout.status_code}")

    if check_frontend_dist:
        dist_ok, dist_path = _frontend_dist_status()
        _check(dist_ok, "frontend dist", dist_path)

    print("[PASS] smoke suite complete")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fast Genorova pre-deploy smoke checks.")
    parser.add_argument(
        "--skip-frontend-dist",
        action="store_true",
        help="Skip checking that app/frontend/dist/index.html exists.",
    )
    args = parser.parse_args()
    return run_smoke(check_frontend_dist=not args.skip_frontend_dist)


if __name__ == "__main__":
    raise SystemExit(main())
