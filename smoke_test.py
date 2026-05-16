from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from http.client import HTTPConnection
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
STARTUP_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class Check:
    method: str
    path: str
    expected_statuses: set[int]
    body: dict[str, object] | None = None


CHECKS = [
    Check("GET", "/health", {200}),
    Check("GET", "/auth/me", {401}),
    Check("POST", "/api/chat", {401, 422}, {"message": "smoke test"}),
    Check("GET", "/metrics", {200}),
    Check("GET", "/api-docs", {200}),
]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def _request(port: int, check: Check) -> tuple[int, str]:
    payload = json.dumps(check.body).encode("utf-8") if check.body is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    conn = HTTPConnection(HOST, port, timeout=5)
    try:
        conn.request(check.method, check.path, body=payload, headers=headers)
        response = conn.getresponse()
        body = response.read().decode("utf-8", errors="replace")
        return response.status, body
    finally:
        conn.close()


def _wait_for_server(port: int) -> bool:
    deadline = time.time() + STARTUP_TIMEOUT_SECONDS
    while time.time() < deadline:
        try:
            status, _ = _request(port, Check("GET", "/health", {200}))
            if status < 500:
                return True
        except OSError:
            time.sleep(0.25)
    return False


def main() -> int:
    port = _free_port()
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.backend.main:app",
        "--host",
        HOST,
        "--port",
        str(port),
        "--app-dir",
        str(ROOT),
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        if not _wait_for_server(port):
            print("FAIL server startup")
            return 1

        failures = 0
        for check in CHECKS:
            try:
                status, body = _request(port, check)
            except OSError as exc:
                print(f"FAIL {check.method} {check.path} error={exc}")
                failures += 1
                continue

            if status in check.expected_statuses:
                print(f"PASS {check.method} {check.path} status={status}")
            else:
                snippet = body.replace("\n", " ")[:160]
                print(f"FAIL {check.method} {check.path} status={status} body={snippet}")
                failures += 1

        return 1 if failures else 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
