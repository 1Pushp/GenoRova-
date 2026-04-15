from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
GENOROVA_SRC = ROOT / "genorova" / "src"
APP_BACKEND = ROOT / "app" / "backend"

for candidate in (ROOT, GENOROVA_SRC, APP_BACKEND):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)


@pytest.fixture
def api_module():
    import genorova.src.api as api

    return api


@pytest.fixture
def api_client(api_module):
    with TestClient(api_module.app) as client:
        yield client


@pytest.fixture
def null_logger() -> logging.Logger:
    logger = logging.getLogger("genorova.tests")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


@pytest.fixture
def project_temp_dir() -> Path:
    temp_root = ROOT / "genorova" / "outputs" / "test_artifacts"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = temp_root / f"case_{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir
