"""
Genorova AI — FastAPI Web Service
===================================

REST API for the Genorova computational molecule analysis platform.
Exposes conservative ranked-molecule retrieval, scoring, and reporting over HTTP.
Canonical production entrypoint: `app/backend/main.py`.

ENDPOINTS:
    GET  /health           — service status
    POST /generate         — return ranked computational molecules for a disease
    POST /score            — score a single SMILES string
    GET  /best_molecules   — top 10 molecules discovered so far
    GET  /report           — HTML discovery report

USAGE:
    python -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8000 --reload

AUTHOR: Pushp Dwivedi | pushpdwivedi911@gmail.com
DATE:   April 2026
"""

import csv
import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

# Make src/ importable
sys.path.insert(0, str(Path(__file__).parent))

import auth_store
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from science_evidence import (
    ACTIVE_DISEASE,
    ACTIVE_PROGRAM_LABEL,
    ACTIVE_PROGRAM_SUMMARY,
    ACTIVE_REFERENCE_DRUG,
    ACTIVE_SCOPE_NOTE,
    ACTIVE_TARGET,
    build_comparison_presentation,
    build_faculty_explanation_stack,
    evaluate_candidate,
    evaluate_candidate_rows,
)

# ── Project paths ────────────────────────────────────────────────────────────

ROOT_DIR      = Path(__file__).parent.parent
OUTPUT_DIR    = ROOT_DIR / "outputs"
GENERATED_DIR = OUTPUT_DIR / "generated"
MODELS_DIR    = OUTPUT_DIR / "models"
DB_PATH       = OUTPUT_DIR / "genorova_memory.db"
REPORT_PATH   = OUTPUT_DIR / "genorova_report.html"
FRONTEND_DIST_DIR = ROOT_DIR.parent / "app" / "frontend" / "dist"
FRONTEND_INDEX_PATH = FRONTEND_DIST_DIR / "index.html"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"

CHAT_SESSION_MEMORY: dict[str, dict[str, Any]] = {}
# NOTE: BEST_MOLECULE is intentionally not a hardcoded constant.
# The "best" molecule is always determined at runtime by the canonical ranking
# path (validation.ranking) via _best_available_smiles() and api_stats().
# Never hardcode a molecule here — it would bypass all evidence evaluation.
PROTOTYPE_STATUS = "prototype_research_support"
AUTH_COOKIE_NAME = "genorova_session"
AUTH_COOKIE_MAX_AGE_SECONDS = auth_store.SESSION_TTL_DAYS * 24 * 60 * 60
LOGGER = logging.getLogger("genorova.api")
LOG_LEVEL_NAME = os.getenv("GENOROVA_LOG_LEVEL", "INFO").strip().upper()
APP_VERSION = os.getenv("GENOROVA_VERSION", "1.0.0").strip() or "1.0.0"
GENERATION_MODE_REAL = "real_generation"
GENERATION_MODE_CURATED = "curated_library_mode"
GENERATION_SAMPLE_MULTIPLIER = 6
GENERATION_SAMPLE_FLOOR = 40
GENERATION_SAMPLE_CAP = 120
GENERATION_PROBE_FLOOR = 20
GENERATION_PROBE_CAP = 24
STARTUP_STATE: dict[str, Any] = {
    "initialized": False,
    "started_at": None,
    "last_error": None,
    "warnings": [],
}

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL_NAME, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _default_auth_db_path() -> Path:
    override = os.getenv("GENOROVA_AUTH_DB_PATH", "").strip()
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        localappdata = os.getenv("LOCALAPPDATA", "").strip()
        if localappdata:
            return Path(localappdata) / "GenorovaAI" / "genorova_auth.db"

    return Path(tempfile.gettempdir()) / "GenorovaAI" / "genorova_auth.db"


AUTH_DB_PATH = _default_auth_db_path()


def _json_log(level: int, event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    LOGGER.log(level, json.dumps(payload, default=str, sort_keys=True))


def _public_url() -> str | None:
    configured = os.getenv("GENOROVA_PUBLIC_URL", "").strip().rstrip("/")
    if configured:
        return configured

    render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render_hostname:
        return f"https://{render_hostname}"

    return None


def _allowed_origins() -> list[str]:
    configured = os.getenv("GENOROVA_ALLOWED_ORIGINS", "").strip()
    if configured:
        origins = [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    else:
        origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
        public_url = _public_url()
        if public_url:
            origins.append(public_url)

    deduped: list[str] = []
    for origin in origins:
        if origin not in deduped:
            deduped.append(origin)
    return deduped


def _binding_truth_fields(raw_mode: str | None) -> dict[str, str]:
    """Map internal binding-path labels to the public truth surface."""
    mode = str(raw_mode or "unavailable")
    if mode == "real_docking":
        return {
            "binding_truth": "REAL_DOCKING",
            "binding_mode_public": "real_docking",
            "binding_claim": "real docking",
        }
    if mode in {"fallback_proxy", "scaffold_proxy"}:
        return {
            "binding_truth": "PREDICTED_OFFLINE",
            "binding_mode_public": "predicted_offline",
            "binding_claim": "predicted binding (Vina-validated offline)",
        }
    return {
        "binding_truth": "UNAVAILABLE",
        "binding_mode_public": "unavailable",
        "binding_claim": "binding unavailable",
    }


def _public_candidate_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    """Return the API-safe molecule payload with one public score field."""
    public = dict(candidate or {})
    clinical_score = public.get("clinical_score", public.get("rank_score"))
    public["clinical_score"] = _safe_float(clinical_score, default=0.0)

    raw_mode = public.get("binding_mode") or public.get("docking_mode")
    binding_truth = _binding_truth_fields(raw_mode)
    public["binding_path_mode_raw"] = raw_mode or "unavailable"
    public["binding_truth"] = binding_truth["binding_truth"]
    public["binding_claim"] = binding_truth["binding_claim"]
    public["binding_mode"] = binding_truth["binding_mode_public"]
    public["docking_mode"] = binding_truth["binding_mode_public"]

    if public["binding_truth"] == "PREDICTED_OFFLINE":
        existing_reason = str(public.get("binding_mode_reason") or "").strip()
        if not existing_reason.lower().startswith("predicted binding (vina-validated offline):"):
            public["binding_mode_reason"] = (
                f"Predicted binding (Vina-validated offline): live docking did not run for this request. {existing_reason}".strip()
            )

    binding_provenance = public.get("binding_provenance")
    if isinstance(binding_provenance, dict):
        normalized_provenance = dict(binding_provenance)
        normalized_provenance["binding_path_mode_raw"] = raw_mode or "unavailable"
        normalized_provenance["binding_truth"] = binding_truth["binding_truth"]
        normalized_provenance["binding_mode"] = binding_truth["binding_mode_public"]
        normalized_provenance["binding_claim"] = binding_truth["binding_claim"]
        public["binding_provenance"] = normalized_provenance

    validation = public.get("validation")
    if isinstance(validation, dict):
        normalized_validation = dict(validation)
        normalized_validation["clinical_score"] = public["clinical_score"]
        normalized_validation["binding_path_mode_raw"] = raw_mode or "unavailable"
        normalized_validation["binding_truth"] = binding_truth["binding_truth"]
        normalized_validation["binding_mode"] = binding_truth["binding_mode_public"]
        normalized_validation["docking_mode"] = binding_truth["binding_mode_public"]
        if isinstance(public.get("binding_provenance"), dict):
            normalized_validation["binding_provenance"] = public["binding_provenance"]
        public["validation"] = normalized_validation

    public.pop("rank_score", None)
    public.pop("model_score", None)
    public.pop("legacy_clinical_score", None)
    return public


def _public_generation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a user-facing generation payload with honest mode labeling."""
    public = dict(payload or {})
    generation_mode = public.get("generation_mode")
    public["generation_truth"] = (
        "REAL"
        if generation_mode == GENERATION_MODE_REAL
        else "LABELED_LIBRARY"
    )
    public["molecules"] = [
        _public_candidate_payload(candidate)
        for candidate in list(public.get("molecules") or [])
    ]
    trust = dict(public.get("trust") or {})
    if generation_mode:
        trust["generation_mode"] = generation_mode
    if public.get("generation_truth"):
        trust["generation_truth"] = public["generation_truth"]
    public["trust"] = trust
    return public


def _redact_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked = local[:1] + "*"
    else:
        masked = local[:2] + "*" * max(1, len(local) - 2)
    return f"{masked}@{domain}"


def _runtime_warnings(auth_status: dict[str, Any] | None = None) -> list[str]:
    warnings: list[str] = []
    if auth_status and not auth_status.get("available", False):
        warnings.append("auth_storage_unavailable")
    if not _cookie_secure():
        warnings.append("cookie_secure_disabled")
    if not FRONTEND_INDEX_PATH.exists():
        warnings.append("frontend_dist_missing")
    if not DB_PATH.exists() and not any(_load_csv(bucket) for bucket in ("diabetes", "infection")):
        warnings.append("molecule_catalog_unavailable")
    return warnings


def _auth_storage_status() -> dict[str, Any]:
    return auth_store.get_storage_status(AUTH_DB_PATH)


def _molecule_storage_status() -> dict[str, Any]:
    status: dict[str, Any] = {
        "available": False,
        "path": str(DB_PATH),
        "row_count": 0,
        "generated_csv_files": [],
        "report_available": REPORT_PATH.exists(),
        "last_error": None,
    }

    csv_files = sorted(str(path) for path in GENERATED_DIR.glob("*.csv"))
    status["generated_csv_files"] = csv_files

    if not DB_PATH.exists():
        return status

    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            row = conn.execute("SELECT COUNT(*) FROM molecules").fetchone()
            status["row_count"] = int(row[0] or 0) if row else 0
            status["available"] = True
        finally:
            conn.close()
    except Exception as exc:
        status["last_error"] = str(exc)

    return status


def _chat_session_status() -> dict[str, Any]:
    return {
        "mode": "process_memory",
        "durability": "ephemeral",
        "active_session_count": len(CHAT_SESSION_MEMORY),
        "message": (
            "Protected chat context in src.api is stored in process memory only and "
            "does not survive a restart."
        ),
    }


def _frontend_status() -> dict[str, Any]:
    return {
        "built": _frontend_is_built(),
        "index_path": str(FRONTEND_INDEX_PATH),
        "assets_path": str(FRONTEND_ASSETS_DIR),
        "assets_available": FRONTEND_ASSETS_DIR.exists(),
    }


def _chat_storage_status() -> dict[str, Any] | None:
    backend_chat_memory = sys.modules.get("chat_memory") or sys.modules.get("app.backend.chat_memory")
    if backend_chat_memory is None:
        try:
            from app.backend import chat_memory as backend_chat_memory
        except Exception:
            return None
    return backend_chat_memory.get_storage_status()


def _ops_status_payload() -> dict[str, Any]:
    auth_status = _auth_storage_status()
    molecule_status = _molecule_storage_status()
    frontend_status = _frontend_status()
    chat_status = _chat_session_status()
    warnings = _runtime_warnings(auth_status)
    health_state = "degraded" if warnings else "ok"

    return {
        "status": health_state,
        "prototype_status": PROTOTYPE_STATUS,
        "timestamp": datetime.now().isoformat(),
        "startup": {
            **STARTUP_STATE,
            "auth_db_path": str(AUTH_DB_PATH),
            "cookie_secure": _cookie_secure(),
        },
        "storage": {
            "auth": auth_status,
            "molecules": molecule_status,
            "chat_session": chat_status,
            "frontend": frontend_status,
            "report": {
                "available": REPORT_PATH.exists(),
                "path": str(REPORT_PATH),
            },
        },
        "degraded_states": warnings,
        "recommended_actions": [
            "Run scripts/smoke_check.py before deploys.",
            "Keep a recent backup of auth and molecule storage before demoing.",
            "Treat chat-session state in src.api as restart-ephemeral.",
        ],
    }

# ── FastAPI app ───────────────────────────────────────────────────────────────

def _initialize_runtime_state() -> None:
    STARTUP_STATE["started_at"] = datetime.now().isoformat()
    try:
        auth_store.init_db(AUTH_DB_PATH)
        auth_status = _auth_storage_status()
        STARTUP_STATE["initialized"] = bool(auth_status.get("available"))
        STARTUP_STATE["last_error"] = None
        STARTUP_STATE["warnings"] = _runtime_warnings(auth_status)
        _json_log(
            logging.INFO,
            "startup_complete",
            auth_db_path=str(AUTH_DB_PATH),
            auth_storage_available=auth_status.get("available"),
            frontend_built=_frontend_is_built(),
            molecule_db_exists=DB_PATH.exists(),
            warnings=STARTUP_STATE["warnings"],
        )
    except Exception:
        STARTUP_STATE["initialized"] = False
        STARTUP_STATE["last_error"] = "auth_storage_initialization_failed"
        STARTUP_STATE["warnings"] = ["auth_storage_initialization_failed"]
        LOGGER.exception("Auth storage initialization failed during startup.")


@asynccontextmanager
async def _app_lifespan(_: FastAPI):
    _initialize_runtime_state()
    yield


app = FastAPI(
    title       = "Genorova AI — Computational Molecule Analysis API",
    description = (
        "Prototype research-support API for computational molecule scoring, "
        "comparison, and conservative ranked-molecule retrieval. Outputs are "
        "not experimentally validated and should not be treated as treatment advice."
    ),
    version     = APP_VERSION,
    contact     = {
        "name":  "Pushp Dwivedi",
        "email": "pushpdwivedi911@gmail.com",
    },
    lifespan    = _app_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_ASSETS_DIR)), name="frontend-assets")

@app.middleware("http")
async def log_request_outcomes(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        _json_log(
            logging.ERROR,
            "request_exception",
            method=request.method,
            path=request.url.path,
            duration_ms=duration_ms,
            error=str(exc),
        )
        raise

    if response.status_code >= 400:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        level = logging.ERROR if response.status_code >= 500 else logging.WARNING
        _json_log(
            level,
            "request_result",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

    return response


# ── Request / Response models ────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    disease: str   # "diabetes" or "infection"
    count:   int   = 10


class ScoreRequest(BaseModel):
    smiles: str


class ChatRequest(BaseModel):
    message: str
    mode: str = "scientific"
    session_id: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)
    conversation_state: dict[str, Any] = Field(default_factory=dict)


class SignupRequest(BaseModel):
    name: str | None = None
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


def _cookie_secure() -> bool:
    explicit_value = os.getenv("GENOROVA_COOKIE_SECURE", "").strip().lower()
    if explicit_value in {"1", "true", "yes", "on"}:
        return True
    if explicit_value in {"0", "false", "no", "off"}:
        return False
    return os.getenv("RENDER", "").strip().lower() == "true"


def _set_auth_cookie(response: Response, session_token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        max_age=AUTH_COOKIE_MAX_AGE_SECONDS,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        path="/",
    )


def _current_user_from_request(request: Request) -> dict[str, str] | None:
    session_token = request.cookies.get(AUTH_COOKIE_NAME)
    if not session_token:
        return None
    return auth_store.get_user_for_session(AUTH_DB_PATH, session_id=session_token)


def get_current_user(request: Request) -> dict[str, str]:
    user = _current_user_from_request(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


# ── Helper: load scored CSV ──────────────────────────────────────────────────

def _load_csv(disease: str) -> list[dict]:
    """Load validated molecule CSV for a disease."""
    # Try pipeline output first, then CLI output
    for stem in [f"{disease}_candidates_validated", f"{disease}_cli_generated"]:
        path = GENERATED_DIR / f"{stem}.csv"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            return sorted(rows, key=lambda r: float(r.get("clinical_score", 0)),
                          reverse=True)
    return []


def _load_db_top(n: int = 10) -> list[dict]:
    """Load top N molecules from SQLite database."""
    if not DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM molecules ORDER BY clinical_score DESC LIMIT ?", (n,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _ranking_label(
    score: float | None = None,
    recommendation: str | None = None,
    candidate: dict | None = None,
) -> str:
    """
    Return the canonical human-readable label for a ranked candidate.

    Prefers the rank_label already computed by science_evidence.evaluate_candidate
    (which uses validation.ranking.best_candidate_label).  Falls back to a
    score-only approximation only when no full candidate dict is available.

    Callers should pass `candidate=` whenever they have the full evaluated dict
    so that evidence-quality gates are applied, not just a raw score threshold.
    """
    # Best path: use the pre-computed rank_label from the canonical ranking module
    if candidate is not None:
        precomputed = candidate.get("rank_label")
        if precomputed:
            return precomputed
        try:
            from validation.ranking import best_candidate_label as _bcl
            return _bcl(candidate)
        except Exception:
            pass

    # Fall back to score-bucket approximation (no evidence-quality gates)
    # These labels match the canonical ranking module labels.
    if score is not None:
        if score >= 0.65:
            return "provisional best candidate"
        if score >= 0.45:
            return "conditional computational lead"
        return "low-priority computational result"

    normalized = str(recommendation or "").lower()
    if "provisional" in normalized or "advance" in normalized:
        return "provisional best candidate"
    if "conditional" in normalized or "border" in normalized:
        return "conditional computational lead"
    return "low-priority computational result"


def _trust_block(
    *,
    validation_status: str,
    confidence_note: str,
    result_source: str,
    fallback_used: bool = False,
    limitations: list[str] | None = None,
    recommended_next_step: str | None = None,
) -> dict[str, Any]:
    """Return stable trust metadata for API and chat responses."""
    return {
        "prototype_status": PROTOTYPE_STATUS,
        "active_program": ACTIVE_PROGRAM_LABEL,
        "validation_status": validation_status,
        "confidence_note": confidence_note,
        "result_source": result_source,
        "fallback_used": fallback_used,
        "limitations": limitations or [
            "This is a computational research-support result.",
            "The system is not experimentally validated and should not be treated as a treatment recommendation.",
        ],
        "recommended_next_step": recommended_next_step or "Compare this output with known valid reference molecules before advancing it.",
    }


def _reference_smiles_for_disease(disease: str) -> list[str]:
    """Return a small safe fallback reference set when generated candidates are unavailable."""
    disease = disease.lower()
    try:
        from validation.reference_data import KNOWN_TARGETS, REFERENCE_DRUGS

        smiles: list[str] = []
        seen: set[str] = set()

        active_reference = REFERENCE_DRUGS.get(ACTIVE_REFERENCE_DRUG)
        if disease == ACTIVE_DISEASE and active_reference:
            seen.add(active_reference)
            smiles.append(active_reference)

        for info in KNOWN_TARGETS.values():
            if str(info.get("disease", "")).lower() != disease:
                continue
            reference_name = str(info.get("reference_drug") or "").strip().lower()
            reference_smiles = REFERENCE_DRUGS.get(reference_name)
            if not reference_smiles or reference_smiles in seen:
                continue
            seen.add(reference_smiles)
            smiles.append(reference_smiles)

        return smiles
    except Exception:
        return []


def _best_available_smiles() -> str | None:
    """
    Return the current best available active-program molecule SMILES.

    Returns None when no trustworthy candidate is available — callers must
    handle None explicitly rather than falling back to a hardcoded string.
    Previously this function returned a hardcoded SMILES constant; that was
    removed because hardcoded molecules bypass all evidence evaluation.
    """
    rows = _load_csv(ACTIVE_DISEASE)
    if rows:
        best = str(rows[0].get("smiles") or "").strip()
        if best:
            return best
    references = _reference_smiles_for_disease(ACTIVE_DISEASE)
    if references:
        return references[0]
    return None


def _fallback_reference_candidates(disease: str, count: int) -> list[dict[str, Any]]:
    """Score known reference molecules as an honest fallback when no candidate set is available."""
    fallback_rows = []
    seen: set[str] = set()
    for smiles in _reference_smiles_for_disease(disease):
        if smiles in seen:
            continue
        seen.add(smiles)
        try:
            payload = _score_smiles_payload(smiles)
        except HTTPException:
            continue
        fallback_rows.append(
            {
                "smiles": payload.get("smiles"),
                "molecular_weight": payload.get("molecular_weight"),
                "logp": payload.get("logp"),
                "qed_score": payload.get("qed_score"),
                "sa_score": payload.get("sa_score"),
                "clinical_score": payload.get("clinical_score"),
                "passes_lipinski": payload.get("passes_lipinski"),
                "recommendation": payload.get("recommendation"),
                "validation_status": "known_reference_scored",
                "confidence_note": "Reference molecule shown because no fresh valid model-generated candidate set was available.",
                "result_source": "known_reference_fallback",
                "fallback_used": True,
            }
        )
    fallback_rows.sort(key=lambda row: float(row.get("clinical_score") or 0), reverse=True)
    return fallback_rows[:count]


def _generation_sample_size(count: int) -> int:
    """Choose a bounded live-generation sample size."""
    return min(
        max(int(count) * GENERATION_SAMPLE_MULTIPLIER, GENERATION_SAMPLE_FLOOR),
        GENERATION_SAMPLE_CAP,
    )


def _generation_probe_size(count: int) -> int:
    """Choose a smaller probe size used to test backend viability."""
    return min(
        max(int(count) * 2, GENERATION_PROBE_FLOOR),
        GENERATION_PROBE_CAP,
    )


def _generation_backend_specs() -> list[dict[str, Any]]:
    """Return the ordered list of generation backends to probe."""
    return [
        {
            "name": "infection_vae",
            "label": "infection VAE checkpoint",
            "factory": "MoleculeGenerator",
            "checkpoint": MODELS_DIR / "infection" / "genorova_infection_best.pt",
            "batch_size": None,
        },
        {
            "name": "smilesvae_ar",
            "label": "autoregressive SMILESVAE checkpoint",
            "factory": "ARMoleculeGenerator",
            "checkpoint": MODELS_DIR / "ar" / "smilesvae_ar_best.pt",
            "batch_size": 20,
        },
    ]


@lru_cache(maxsize=4)
def _cached_generator(factory_name: str, checkpoint_path: str):
    """Load and cache a generation backend so repeated calls stay practical."""
    from generate import ARMoleculeGenerator, MoleculeGenerator

    checkpoint = Path(checkpoint_path)
    if factory_name == "ARMoleculeGenerator":
        return ARMoleculeGenerator(checkpoint_path=str(checkpoint), device="cpu")
    if factory_name == "MoleculeGenerator":
        return MoleculeGenerator(checkpoint_path=str(checkpoint), device="cpu")
    raise ValueError(f"Unsupported generator factory: {factory_name}")


def _reset_generator_state(generator: Any) -> None:
    """Clear mutable counters on cached generator instances before reuse."""
    for attr in ("valid_count", "invalid_count", "novel_count", "duplicate_count"):
        if hasattr(generator, attr):
            setattr(generator, attr, 0)
    if hasattr(generator, "last_debug_rows"):
        generator.last_debug_rows = []


def _run_generation_backend(spec: dict[str, Any], sample_size: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Execute one backend and return unique SMILES rows plus diagnostics."""
    checkpoint_path = Path(spec["checkpoint"])
    diagnostics = {
        "backend": spec["name"],
        "label": spec["label"],
        "checkpoint": str(checkpoint_path),
        "sample_size": sample_size,
        "status": "not_run",
        "valid_smiles": 0,
        "unique_valid_smiles": 0,
        "error": None,
    }

    if not checkpoint_path.exists():
        diagnostics["status"] = "missing_checkpoint"
        diagnostics["error"] = f"Checkpoint not found: {checkpoint_path}"
        return [], diagnostics

    try:
        generator = _cached_generator(spec["factory"], str(checkpoint_path))
        _reset_generator_state(generator)

        if spec["factory"] == "ARMoleculeGenerator":
            df = generator.generate_molecules(
                num_to_generate=sample_size,
                batch_size=min(spec.get("batch_size") or sample_size, sample_size),
            )
        else:
            df = generator.generate_molecules(num_to_generate=sample_size)
    except Exception as exc:
        diagnostics["status"] = "runtime_failed"
        diagnostics["error"] = str(exc)
        return [], diagnostics

    records = df.to_dict(orient="records") if hasattr(df, "to_dict") else []
    unique_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in records:
        smiles = str(row.get("smiles") or "").strip()
        if not smiles or smiles in seen:
            continue
        seen.add(smiles)
        unique_rows.append({"smiles": smiles})

    diagnostics["valid_smiles"] = len(records)
    diagnostics["unique_valid_smiles"] = len(unique_rows)
    diagnostics["status"] = "ready" if unique_rows else "no_valid_smiles"
    if not unique_rows:
        diagnostics["error"] = (
            f"{spec['label']} produced 0 valid SMILES in a live sample of {sample_size} molecules."
        )
    return unique_rows, diagnostics


def _attempt_runtime_generation(disease: str, count: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Try the live generation backends in order and return diagnostics either way."""
    sample_size = _generation_sample_size(count)
    probe_size = _generation_probe_size(count)
    attempts: list[dict[str, Any]] = []

    for index, spec in enumerate(_generation_backend_specs()):
        run_size = sample_size if index > 0 else probe_size
        rows, diagnostics = _run_generation_backend(spec, run_size)
        attempts.append(diagnostics)
        if not rows:
            continue

        if run_size < sample_size:
            rows, diagnostics = _run_generation_backend(spec, sample_size)
            attempts[-1] = diagnostics
            if not rows:
                continue

        return rows, {
            "attempted": True,
            "selected_backend": spec["name"],
            "selected_backend_label": spec["label"],
            "sample_size": sample_size,
            "attempts": attempts,
            "failure_reason": None,
            "disease": disease,
        }

    failure_reason = next(
        (
            attempt.get("error")
            for attempt in reversed(attempts)
            if attempt.get("error")
        ),
        "No live generation backend returned a valid SMILES string.",
    )
    return [], {
        "attempted": True,
        "selected_backend": None,
        "selected_backend_label": None,
        "sample_size": sample_size,
        "attempts": attempts,
        "failure_reason": failure_reason,
        "disease": disease,
    }


def _generate_candidates_for_disease(disease: str, count: int) -> dict:
    """Shared generation logic used by both REST and chat endpoints."""
    disease = disease.lower()
    if disease not in ("diabetes", "infection"):
        raise HTTPException(status_code=400, detail="disease must be 'diabetes' or 'infection'")

    count = min(count, 200)
    if disease != ACTIVE_DISEASE:
        return {
            "disease": disease,
            "count_returned": 0,
            "count_requested": count,
            "generated_at": datetime.now().isoformat(),
            "generation_status": "inactive_science_path",
            "generation_mode": "inactive_science_path",
            "message": (
                f"This live Genorova surface is currently standardized to the {ACTIVE_PROGRAM_LABEL}. "
                f"Requests for '{disease}' are outside the active science path in this workspace."
            ),
            "molecules": [],
            "trust": _trust_block(
                validation_status="inactive_science_path",
                confidence_note=ACTIVE_SCOPE_NOTE,
                result_source="inactive_program_scope",
                fallback_used=False,
                limitations=[
                    ACTIVE_SCOPE_NOTE,
                    "Use the active program when you want live generation or scoring from this workspace.",
                ],
                recommended_next_step="Score or compare molecules inside the active Genorova program path.",
            ),
        }

    live_rows, generation_diagnostics = _attempt_runtime_generation(disease, count)
    rows = live_rows
    source_type = "runtime_model_generation"
    generation_status = "runtime_model_generation"
    generation_mode = GENERATION_MODE_REAL
    fallback_used = False
    confidence_note = (
        "Fresh molecules were generated live from the autoregressive model and then revalidated under the active Genorova program."
    )
    limitations = [
        ACTIVE_SCOPE_NOTE,
        "These molecules are freshly generated computational candidates, not experimentally validated leads.",
        "Binding remains computational only unless a payload explicitly reports REAL_DOCKING.",
    ]
    recommended_next_step = (
        "Review the freshly generated molecules with scoring, comparison, and structure inspection before any chemistry decision."
    )

    if not rows:
        rows = _load_csv(disease)
        source_type = "precomputed_ranked_candidates"
        generation_status = GENERATION_MODE_CURATED
        generation_mode = GENERATION_MODE_CURATED
        fallback_used = True
        confidence_note = (
            "Live generation was attempted first, but no trustworthy runtime candidate set was available. "
            "Genorova is now labeling the response honestly as curated_library_mode."
        )
        limitations = [
            "Live generation was attempted but did not return a trustworthy candidate set for this request.",
            "These molecules come from a curated, previously scored library rather than a fresh generation pass.",
        ]
        recommended_next_step = (
            "Treat this as curated library mode and use scoring or comparison before making any synthesis decision."
        )

    if not rows:
        db_rows = _load_db_top(count)
        if db_rows:
            rows = db_rows
            source_type = "database_ranked_candidates"
            generation_status = GENERATION_MODE_CURATED
            generation_mode = GENERATION_MODE_CURATED
            confidence_note = (
                "Live generation did not return a trustworthy candidate set, so the API is surfacing stored scored molecules in curated_library_mode."
            )
            limitations = [
                "This response is sourced from stored scored molecules rather than a fresh generation run.",
                "Use the runtime generation diagnostics before claiming novel discovery from this endpoint.",
            ]
        else:
            rows = _fallback_reference_candidates(disease, count)
            source_type = "known_reference_fallback"
            generation_status = GENERATION_MODE_CURATED if rows else "no_valid_candidates_available"
            generation_mode = GENERATION_MODE_CURATED if rows else "no_valid_candidates_available"
            confidence_note = (
                "Live generation did not return a trustworthy candidate set, so the API is falling back to scored reference molecules in curated_library_mode."
                if rows else
                "Live generation produced no trustworthy valid candidate, and no safe curated library fallback was available."
            )
            limitations = [
                "Live generation produced no trustworthy valid candidates for this request.",
                "Known references are shown only as safe comparators and not as newly discovered molecules.",
            ] if rows else [
                "No trustworthy live-generated candidate set was available.",
                "No safe curated-library fallback was available for this disease bucket in the current workspace.",
            ]
            recommended_next_step = (
                "Score a known SMILES string or compare known molecules while live generation is being tuned."
            )

    if not rows:
        return {
            "disease": disease,
            "count_returned": 0,
            "count_requested": count,
            "generated_at": datetime.now().isoformat(),
            "generation_status": generation_status,
            "generation_mode": generation_mode,
            "generation_diagnostics": generation_diagnostics,
            "message": "No valid candidate was produced in this run. The API is returning an honest empty result instead of inventing a molecule.",
            "molecules": [],
            "trust": _trust_block(
                validation_status="no_valid_candidate_available",
                confidence_note=confidence_note,
                result_source=source_type,
                fallback_used=False,
                limitations=limitations,
                recommended_next_step=recommended_next_step,
            ),
        }

    results = evaluate_candidate_rows(
        rows,
        result_source=source_type,
        fallback_used=fallback_used,
        max_candidates=count,
        confidence_note=confidence_note,
        validation_status="canonical_selective_candidate_screen",
        limitations=[ACTIVE_SCOPE_NOTE, *limitations],
        recommended_next_step=recommended_next_step,
    )

    if not results or all(candidate.get("final_decision") == "reject" for candidate in results):
        return {
            "disease": disease,
            "count_returned": 0,
            "count_requested": count,
            "generated_at": datetime.now().isoformat(),
            "generation_status": (
                "runtime_generated_candidates_rejected_by_active_validation"
                if generation_mode == GENERATION_MODE_REAL
                else "curated_candidates_rejected_by_active_validation"
            ),
            "generation_mode": generation_mode,
            "generation_diagnostics": generation_diagnostics,
            "message": (
                "Candidate rows were available, but the active Genorova validation workflow did not find a trustworthy "
                "candidate to display after revalidation."
            ),
            "molecules": [],
            "trust": _trust_block(
                validation_status="all_candidates_rejected_by_active_validation",
                confidence_note="The stricter active validation path rejected the currently available candidates for display.",
                result_source=source_type,
                fallback_used=fallback_used,
                limitations=[
                    ACTIVE_SCOPE_NOTE,
                    "The active path now filters out low-trust candidates instead of showing them as leads.",
                ],
                recommended_next_step=recommended_next_step,
            ),
        }

    for index, candidate in enumerate(results, 1):
        candidate["rank"] = index
        _store_molecule(
            candidate.get("smiles"),
            candidate.get("qed_score"),
            candidate.get("sa_score"),
            candidate.get("molecular_weight"),
            candidate.get("logp"),
            candidate.get("clinical_score"),
            candidate.get("recommendation"),
        )

    return {
        "disease":          disease,
        "count_returned":   len(results),
        "count_requested":  count,
        "generated_at":     datetime.now().isoformat(),
        "generation_status": generation_status,
        "generation_mode":  generation_mode,
        "generation_diagnostics": generation_diagnostics,
        "message": (
            "Showing freshly generated and revalidated molecules from the live autoregressive Genorova path."
            if generation_mode == GENERATION_MODE_REAL else
            "Showing curated-library molecules because live generation did not return a trustworthy candidate set in this request."
        ),
        "trust": _trust_block(
            validation_status="canonical_selective_candidate_screen",
            confidence_note=confidence_note,
            result_source=source_type,
            fallback_used=fallback_used,
            limitations=[ACTIVE_SCOPE_NOTE, *limitations],
            recommended_next_step=recommended_next_step,
        ),
        "molecules":        results,
    }


def _score_smiles_payload(smiles: str) -> dict:
    """Shared scoring logic used by REST and chat endpoints."""
    try:
        payload = evaluate_candidate(
            smiles,
            result_source="direct_smiles_scoring",
            fallback_used=False,
            validation_status="canonical_direct_scoring",
            limitations=[
                ACTIVE_SCOPE_NOTE,
                f"This score comes from the active {ACTIVE_PROGRAM_LABEL} workflow and remains computational only.",
                "Proxy and heuristic fields should not be interpreted as experimental proof or clinical validation.",
            ],
            recommended_next_step=(
                f"Compare this molecule with {ACTIVE_REFERENCE_DRUG} or other program-relevant reference molecules before advancing it."
            ),
        )
        _store_molecule(
            payload["smiles"],
            payload["qed_score"],
            payload["sa_score"],
            payload["molecular_weight"],
            payload["logp"],
            payload["clinical_score"],
            payload["recommendation"],
        )
        payload["scored_at"] = datetime.now().isoformat()
        return payload

    except HTTPException:
        raise
    except ValueError as exc:
        _json_log(
            logging.WARNING,
            "score_validation_error",
            smiles=smiles,
            reason=str(exc),
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as e:
        _json_log(
            logging.ERROR,
            "score_unexpected_error",
            smiles=smiles,
            reason=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Scoring failed: {e}")


def _get_or_create_session_id(session_id: str | None) -> str:
    """Return a stable session identifier for the chat flow."""
    if session_id and session_id.strip():
        return session_id.strip()
    return f"session-{uuid.uuid4().hex}"


def _get_session_state(session_id: str, user_id: str) -> dict[str, Any]:
    """Read in-memory session state for the current deployment instance."""
    stored = CHAT_SESSION_MEMORY.get(session_id) or {}
    if stored.get("user_id") != user_id:
        return {}
    return dict(stored.get("state") or {})


def _save_session_state(session_id: str, user_id: str, state: dict[str, Any]) -> None:
    """Persist lightweight session context in memory for this process."""
    CHAT_SESSION_MEMORY[session_id] = {
        "user_id": user_id,
        "state": dict(state),
    }


def _merge_state_sources(
    frontend_state: dict[str, Any] | None,
    memory_state: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge frontend-provided context with backend in-memory session context."""
    merged: dict[str, Any] = {}
    if memory_state:
        merged.update(memory_state)
    if frontend_state:
        merged.update(frontend_state)
    return merged


def _molecule_svg(smiles: str | None, width: int = 360, height: int = 220) -> str | None:
    """Return an RDKit SVG rendering for a SMILES string when possible."""
    if not smiles:
        return None
    try:
        from rdkit import Chem
        from rdkit.Chem import rdDepictor
        from rdkit.Chem.Draw import rdMolDraw2D

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        rdDepictor.Compute2DCoords(mol)
        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        drawer.drawOptions().clearBackground = False
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        return drawer.GetDrawingText()
    except Exception:
        return None


# ── ENDPOINT: GET /health ─────────────────────────────────────────────────────

@app.post("/auth/signup", summary="Create a Genorova account")
def auth_signup(request: SignupRequest, response: Response):
    try:
        user = auth_store.create_user(
            AUTH_DB_PATH,
            email=request.email,
            password=request.password,
            name=request.name,
        )
    except auth_store.UserAlreadyExistsError as exc:
        _json_log(
            logging.WARNING,
            "auth_signup_conflict",
            email=_redact_email(request.email),
            reason=str(exc),
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except auth_store.AuthStoreError as exc:
        _json_log(
            logging.WARNING,
            "auth_signup_invalid",
            email=_redact_email(request.email),
            reason=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_token = auth_store.create_session(AUTH_DB_PATH, user_id=user["id"])
    _set_auth_cookie(response, session_token)
    _json_log(
        logging.INFO,
        "auth_signup_success",
        user_id=user["id"],
        email=_redact_email(user.get("email")),
    )
    return {"user": user}


@app.post("/auth/login", summary="Start an authenticated session")
def auth_login(request: LoginRequest, response: Response):
    try:
        user = auth_store.authenticate_user(
            AUTH_DB_PATH,
            email=request.email,
            password=request.password,
        )
    except auth_store.AuthStoreError as exc:
        _json_log(
            logging.WARNING,
            "auth_login_invalid_request",
            email=_redact_email(request.email),
            reason=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if user is None:
        _json_log(
            logging.WARNING,
            "auth_login_failed",
            email=_redact_email(request.email),
            reason="invalid_credentials",
        )
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    session_token = auth_store.create_session(AUTH_DB_PATH, user_id=user["id"])
    _set_auth_cookie(response, session_token)
    _json_log(
        logging.INFO,
        "auth_login_success",
        user_id=user["id"],
        email=_redact_email(user.get("email")),
    )
    return {"user": user}


@app.post("/auth/logout", summary="End the current authenticated session")
def auth_logout(request: Request, response: Response):
    session_token = request.cookies.get(AUTH_COOKIE_NAME)
    user = _current_user_from_request(request)
    if session_token:
        auth_store.delete_session(AUTH_DB_PATH, session_id=session_token)
    _clear_auth_cookie(response)
    _json_log(
        logging.INFO,
        "auth_logout",
        user_id=user.get("id") if user else None,
        had_session=bool(session_token),
    )
    return {"success": True}


@app.get("/auth/me", summary="Return the current authenticated user")
def auth_me(current_user: dict[str, str] = Depends(get_current_user)):
    return {"user": current_user}


def _readiness_payload() -> tuple[bool, dict[str, Any]]:
    ops_status = _ops_status_payload()
    checks = {
        "startup_initialized": bool(STARTUP_STATE.get("initialized")),
        "auth_storage_available": bool(ops_status["storage"]["auth"]["available"]),
        "frontend_built": bool(ops_status["storage"]["frontend"]["built"]),
        "cookie_secure": bool(_cookie_secure()),
    }
    ready = all(checks.values())
    return ready, {
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "timestamp": datetime.now().isoformat(),
        "version": APP_VERSION,
        "checks": checks,
        "degraded_states": ops_status["degraded_states"],
    }


@app.get("/health", summary="Service health check")
def health():
    """
    Returns running status and model availability.
    Use this to verify the server is up before sending requests.
    """
    ops_status = _ops_status_payload()
    diabetes_model  = (MODELS_DIR / "diabetes" / "genorova_diabetes_best.pt").exists()
    infection_model = (MODELS_DIR / "infection" / "genorova_infection_best.pt").exists()
    db_count = 0
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            db_count = conn.execute("SELECT COUNT(*) FROM molecules").fetchone()[0]
            conn.close()
        except Exception:
            pass

    stats = api_stats()
    payload = {
        "status":          "running",
        "model":           f"Genorova AI v{APP_VERSION}",
        "version":         APP_VERSION,
        "prototype_status": PROTOTYPE_STATUS,
        "timestamp":       datetime.now().isoformat(),
        "models_loaded": {
            "diabetes":  diabetes_model,
            "infection": infection_model,
        },
        "molecules_in_db": db_count,
        "best_molecule":   stats.get("best_molecule"),
        "best_clinical_score": stats.get("best_clinical_score", stats.get("best_score")),
        "best_score":      stats.get("best_score"),
        "health_status":   ops_status["status"],
        "degraded_states": ops_status["degraded_states"],
        "storage_summary": {
            "auth": {
                "available": ops_status["storage"]["auth"]["available"],
                "path": ops_status["storage"]["auth"]["path"],
            },
            "molecules": {
                "available": ops_status["storage"]["molecules"]["available"],
                "row_count": ops_status["storage"]["molecules"]["row_count"],
            },
            "chat_session": ops_status["storage"]["chat_session"],
            "frontend": {
                "built": ops_status["storage"]["frontend"]["built"],
            },
        },
        "trust_note":      "Operational status only. All molecule outputs are computational research-support results and not experimentally validated.",
    }
    chat_storage = _chat_storage_status()
    if chat_storage is not None:
        payload["chat_storage"] = chat_storage
    return payload


@app.get("/ready", summary="Readiness check for deployment and smoke tests")
def ready():
    ready_state, payload = _readiness_payload()
    status_code = 200 if ready_state else 503
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/version", summary="Release metadata for the running deployment")
def version():
    return {
        "name": "Genorova AI",
        "version": APP_VERSION,
        "public_url": _public_url(),
        "render_service": os.getenv("RENDER_SERVICE_NAME", "").strip() or None,
        "render_git_commit": os.getenv("RENDER_GIT_COMMIT", "").strip() or None,
        "render_instance_id": os.getenv("RENDER_INSTANCE_ID", "").strip() or None,
        "build_timestamp": STARTUP_STATE.get("started_at"),
    }


@app.get("/ops/status", summary="Detailed runtime and storage status")
def ops_status():
    return _ops_status_payload()


# ── ENDPOINT: POST /generate ──────────────────────────────────────────────────

@app.post("/generate", summary="Return ranked computational molecule results")
def generate(req: GenerateRequest):
    """
    Return ranked computational molecule results for a target disease.

    The active product flow favors honesty over forcing a fresh generation claim:
    it returns previously scored valid molecules, known reference fallbacks, or an
    explicit empty result when no trustworthy candidate set is available.

    - **disease**: "diabetes" or "infection"
    - **count**: number of molecules to return (max 200)
    """
    payload = _generate_candidates_for_disease(req.disease, req.count)
    trust = payload.get("trust", {})
    if trust.get("fallback_used") or payload.get("count_returned", 0) == 0:
        _json_log(
            logging.WARNING,
            "generate_degraded_result",
            disease=req.disease,
            count=req.count,
            generation_status=payload.get("generation_status"),
            result_source=trust.get("result_source"),
            returned=payload.get("count_returned", 0),
        )
    return _public_generation_payload(payload)


@app.post("/api/generate", summary="Return ranked computational molecules (SaaS API)")
def api_generate(req: GenerateRequest):
    """Alias route for the SaaS frontend deployed against src.api:app."""
    return generate(req)


# ── ENDPOINT: POST /score ─────────────────────────────────────────────────────

@app.post("/score", summary="Score a molecule with computational property estimates")
def score(req: ScoreRequest):
    """
    Compute Genorova's current computational score for any valid SMILES string.

    Returns a complete property profile including:
    - Drug-likeness (QED), synthetic accessibility (SA), Lipinski compliance
    - Genorova model score (0–1)
    - A model-ranked prioritization label suitable for exploratory research only
    """
    return _public_candidate_payload(_score_smiles_payload(req.smiles))


@app.post("/api/score", summary="Score a molecule (SaaS API)")
def api_score(req: ScoreRequest):
    """Alias route for the SaaS frontend deployed against src.api:app."""
    return score(req)


# ── ENDPOINT: GET /best_molecules ─────────────────────────────────────────────

@app.get("/best_molecules", summary="Top 10 molecules discovered")
def best_molecules(n: int = 10):
    """
    Return the top N computationally ranked molecules currently available to the platform.

    Queries the persistent molecule database that is updated every pipeline run.
    """
    n = min(n, 50)
    generated = _public_generation_payload(_generate_candidates_for_disease(ACTIVE_DISEASE, n))
    source = generated.get("trust", {}).get("result_source", "canonical_selective_candidate_screen")
    return {
        "source": source,
        "prototype_status": PROTOTYPE_STATUS,
        "active_program": ACTIVE_PROGRAM_LABEL,
        "count": generated.get("count_returned", 0),
        "molecules": generated.get("molecules", []),
    }


@app.get("/api/best", summary="Top 5 molecules for SaaS frontend")
def api_best():
    """Return the top 5 ranked molecules in a stable JSON payload."""
    return best_molecules(n=5)


@app.get("/api/stats", summary="Platform statistics for SaaS frontend")
def api_stats():
    """
    Return live platform statistics computed from the molecule database and
    CSV outputs.  Never returns hardcoded values — if no molecules have been
    generated yet the endpoint says so explicitly.
    """
    total = 0
    best_score = None
    best_molecule = None
    best_mw = None
    avg_qed = None
    avg_sa = None
    data_source = "none"

    # ── Primary: query SQLite database ───────────────────────────────────────
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row

            row = conn.execute("SELECT COUNT(*) AS cnt FROM molecules").fetchone()
            total = row["cnt"] if row else 0

            top = conn.execute(
                "SELECT smiles, clinical_score, molecular_weight, qed_score, sa_score "
                "FROM molecules ORDER BY clinical_score DESC LIMIT 1"
            ).fetchone()
            if top:
                best_molecule = top["smiles"]
                best_score    = round(float(top["clinical_score"] or 0), 4)
                best_mw       = _safe_float(top["molecular_weight"])

            avgs = conn.execute(
                "SELECT AVG(qed_score) AS aq, AVG(sa_score) AS as_ FROM molecules"
            ).fetchone()
            if avgs and avgs["aq"] is not None:
                avg_qed = round(float(avgs["aq"]), 4)
                avg_sa  = round(float(avgs["as_"]), 4)

            conn.close()
            if total > 0:
                data_source = "database"
        except Exception:
            pass

    # ── Fallback: scan pre-computed CSV files ─────────────────────────────────
    if total == 0:
        all_rows: list[dict] = []
        for disease in ("diabetes", "infection"):
            all_rows.extend(_load_csv(disease))
        total = len(all_rows)
        if all_rows:
            data_source = "csv"
            all_rows.sort(key=lambda r: float(r.get("clinical_score") or 0), reverse=True)
            top_row = all_rows[0]
            best_molecule = top_row.get("smiles")
            best_score    = _safe_float(top_row.get("clinical_score"))
            best_mw       = _safe_float(top_row.get("molecular_weight"))
            valid_qeds = [float(r["qed_score"]) for r in all_rows if r.get("qed_score")]
            valid_sas  = [float(r["sa_score"])  for r in all_rows if r.get("sa_score")]
            avg_qed = round(sum(valid_qeds) / len(valid_qeds), 4) if valid_qeds else None
            avg_sa  = round(sum(valid_sas)  / len(valid_sas),  4) if valid_sas  else None

    # ── Honest empty state ────────────────────────────────────────────────────
    if total == 0:
        return {
            "total_molecules":    0,
            "best_clinical_score": None,
            "best_score":         None,
            "best_molecule":      None,
            "best_molecular_weight": None,
            "avg_qed_score":      None,
            "avg_sa_score":       None,
            "data_source":        "none",
            "prototype_status":   PROTOTYPE_STATUS,
            "message": (
                "No molecules generated yet. "
                "Run: python src/run_pipeline.py to generate candidates."
            ),
        }

    return {
        "total_molecules":        total,
        "best_clinical_score":    best_score,
        "best_score":             best_score,
        "best_molecule":          best_molecule,
        "best_molecule_label":    _ranking_label(score=best_score),
        "best_molecule_note": (
            "The 'best molecule' shown here is ranked by the canonical evidence-weighted "
            "score from validation.ranking.  It is the top computational candidate only — "
            "not an experimentally validated result."
            if best_molecule else
            "No ranked molecule available yet."
        ),
        "best_molecular_weight":  best_mw,
        "avg_qed_score":          avg_qed,
        "avg_sa_score":           avg_sa,
        "data_source":            data_source,
        "prototype_status":       PROTOTYPE_STATUS,
        "active_program":         ACTIVE_PROGRAM_LABEL,
        "trust_note": (
            f"{ACTIVE_PROGRAM_SUMMARY} Metrics describe computationally ranked molecules "
            "and are not experimental validation."
        ),
    }


@app.post("/api/chat", summary="Natural-language Genorova chat endpoint")
def api_chat(
    req: ChatRequest,
    current_user: dict[str, str] = Depends(get_current_user),
):
    """Accept a natural-language request and route it through Genorova's core logic."""
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message cannot be empty.")

    session_id = _get_or_create_session_id(req.session_id)
    merged_state = _merge_state_sources(
        req.conversation_state,
        _get_session_state(session_id, current_user["id"]),
    )
    mode = _resolve_mode_from_message(message, _normalize_mode(req.mode), merged_state)
    intent = _parse_chat_intent(message)
    try:
        response = _build_chat_response(intent, mode, message, merged_state)
    except HTTPException as exc:
        _json_log(
            logging.WARNING if exc.status_code < 500 else logging.ERROR,
            "chat_request_failed",
            user_id=current_user["id"],
            intent=intent,
            mode=mode,
            status_code=exc.status_code,
            reason=str(exc.detail),
        )
        raise
    except Exception as exc:
        _json_log(
            logging.ERROR,
            "chat_request_failed",
            user_id=current_user["id"],
            intent=intent,
            mode=mode,
            status_code=500,
            reason=str(exc),
        )
        raise
    response["intent"] = intent
    response["mode"] = mode
    response["session_id"] = session_id
    response["history_window"] = req.history[-6:]
    response["generated_at"] = datetime.now().isoformat()
    _save_session_state(
        session_id,
        current_user["id"],
        response.get("conversation_state", merged_state),
    )
    return response


# ── ENDPOINT: GET /report ─────────────────────────────────────────────────────

@app.get("/report", response_class=HTMLResponse, summary="HTML discovery report")
def report():
    """
    Returns the full Genorova AI HTML discovery report.

    The report is self-contained (base64-embedded images) and can be saved
    directly as an HTML file.
    """
    if not REPORT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="Report not generated yet. Run: python src/genorova_cli.py report"
        )
    return HTMLResponse(content=REPORT_PATH.read_text(encoding="utf-8"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_float(val, default=0.0) -> float:
    try:
        return round(float(val), 4)
    except (TypeError, ValueError):
        return default


def _store_molecule(smiles, qed, sa, mw, logp, score, recommendation):
    """Persist a scored molecule to the SQLite database."""
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            """INSERT OR IGNORE INTO molecules
               (smiles, qed_score, sa_score, molecular_weight, logp,
                clinical_score, recommendation, is_candidate, generated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (smiles, qed, sa, mw, logp, score, recommendation,
             1 if score >= 0.85 else 0, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _normalize_mode(mode: str | None) -> str:
    """Normalize UI detail mode to a supported value."""
    normalized = str(mode or "scientific").strip().lower()
    if normalized not in {"simple", "scientific", "expert"}:
        return "scientific"
    return normalized


def _resolve_mode_from_message(message: str, fallback_mode: str, state: dict[str, Any]) -> str:
    """Allow follow-up requests to switch explanation depth conversationally."""
    lowered = message.lower()
    if "simple" in lowered or "simpler" in lowered or "simply" in lowered:
        return "simple"
    if "expert" in lowered or "deeper" in lowered:
        return "expert"
    if "scientific" in lowered or "technical" in lowered:
        return "scientific"
    return _normalize_mode(state.get("latest_mode", fallback_mode))


def _has_follow_up_reference(message: str) -> bool:
    """Detect whether the prompt is likely referring back to prior chat context."""
    lowered = message.lower()
    follow_up_phrases = (
        "it",
        "that",
        "this one",
        "the previous",
        "the last",
        "that one",
        "the candidate",
        "best one",
    )
    return any(phrase in lowered for phrase in follow_up_phrases)


def _extract_smiles_candidates(message: str) -> list[str]:
    """Extract likely SMILES strings from a free-text prompt."""
    pattern = re.compile(r"[A-Za-z0-9@+\-\[\]\(\)=#$\\/%.]{3,}")
    tokens = []
    for token in pattern.findall(message):
        looks_smiles_like = (
            any(char.isdigit() for char in token)
            or any(char in "[]=#()@+-/\\" for char in token)
            or (token.upper() == token and any(char.isalpha() for char in token))
        )
        if looks_smiles_like:
            tokens.append(token.strip(".,;:"))
    return list(dict.fromkeys(tokens))


def _extract_count(message: str, default: int = 5) -> int:
    """Read a requested molecule count from chat text."""
    match = re.search(r"\b(\d{1,3})\b", message)
    if not match:
        return default
    return max(1, min(int(match.group(1)), 20))


def _infer_disease_area(message: str) -> tuple[str, str]:
    """Map a user disease request to the current Genorova supported disease buckets."""
    lowered = message.lower()
    disease_map = {
        "diabetes": (ACTIVE_DISEASE, ACTIVE_PROGRAM_LABEL),
        "tb": ("infection", "archived infection lead story"),
        "tuberculosis": ("infection", "archived infection lead story"),
        "infection": ("infection", "archived infection lead story"),
        "infectious": ("infection", "archived infection lead story"),
        "bacterial": ("infection", "archived infection lead story"),
        "viral": ("infection", "archived infection lead story"),
        "sepsis": ("infection", "archived infection lead story"),
        "pneumonia": ("infection", "archived infection lead story"),
        "covid": ("infection", "archived infection lead story"),
    }
    for keyword, mapping in disease_map.items():
        if keyword in lowered:
            return mapping
    return (ACTIVE_DISEASE, ACTIVE_PROGRAM_LABEL)


def _parse_chat_intent(message: str) -> str:
    """Infer the high-level user intent from a natural-language request."""
    lowered = message.lower()
    if "why is this better" in lowered or "why is it better" in lowered:
        return "compare"
    if any(word in lowered for word in ("compare", "versus", "vs ", "difference between")):
        return "compare"
    if any(word in lowered for word in ("safer", "optimize", "optimise", "improve", "reduce toxicity", "less toxic", "toxic", "analog", "oral delivery")):
        return "optimize"
    if any(word in lowered for word in ("explain", "what is", "describe", "tell me about")):
        return "explain"
    if any(word in lowered for word in ("score", "profile", "analyze", "analyse", "evaluate")):
        return "score"
    if any(word in lowered for word in ("generate", "design", "find", "suggest", "candidate")):
        return "generate"
    return "generate"


def _resolve_reference_smiles(message: str, state: dict[str, Any]) -> list[str]:
    """Resolve explicit or contextual molecule references for follow-up prompts."""
    extracted = _extract_smiles_candidates(message)
    if extracted:
        return extracted

    latest_candidate = state.get("recent_candidate_smiles")
    best_smiles = state.get("recent_best_smiles") or _best_available_smiles()
    lowered = message.lower()

    if latest_candidate and _has_follow_up_reference(message):
        if "best" in lowered and "compare" in lowered and best_smiles:
            return [latest_candidate, best_smiles]
        return [latest_candidate]

    if ("best one" in lowered or "best molecule" in lowered) and best_smiles:
        return [best_smiles]

    return []


def _score_interpretation(score: float) -> str:
    """Convert a numeric score into a plain-language interpretation."""
    if score >= 0.85:
        return "high relative promise in Genorova's current ranking system"
    if score >= 0.60:
        return "moderate promise with meaningful optimization work still needed"
    return "low priority under the current computational ranking rules"


def _estimate_toxicity_risk(score_payload: dict) -> str:
    """Simple risk bucket derived from the current scoring payload."""
    risk_points = 0
    if score_payload.get("logp", 0) > 3:
        risk_points += 1
    if score_payload.get("molecular_weight", 0) > 450:
        risk_points += 1
    if score_payload.get("lipinski_violations", 0) > 0:
        risk_points += 1
    if score_payload.get("qed_score", 0) < 0.45:
        risk_points += 1
    if risk_points >= 3:
        return "high"
    if risk_points == 2:
        return "moderate"
    return "low"


def _novelty_overview(score_payload: dict, validation: dict | None = None) -> dict:
    """Return stable novelty evidence fields for API/chat payloads."""
    validation_block = dict(validation or score_payload.get("validation") or {})
    novelty_provenance = validation_block.get(
        "novelty_provenance",
        score_payload.get("novelty_provenance"),
    )
    return {
        "novelty_status": validation_block.get("novelty_status", score_payload.get("novelty_status")),
        "novelty_closest_reference": validation_block.get(
            "novelty_closest_reference",
            score_payload.get("novelty_closest_reference"),
        ),
        "novelty_tanimoto_score": validation_block.get(
            "novelty_tanimoto_score",
            score_payload.get("novelty_tanimoto_score"),
        ),
        "novelty_threshold": validation_block.get(
            "novelty_threshold",
            score_payload.get("novelty_threshold"),
        ),
        "novelty_reason": validation_block.get("novelty_reason", score_payload.get("novelty_reason")),
        "novelty_provenance": novelty_provenance,
        "novelty_provenance_explanation": validation_block.get(
            "novelty_provenance_explanation",
            score_payload.get("novelty_provenance_explanation")
            or (
                (novelty_provenance or {}).get("provenance_explanation")
                if isinstance(novelty_provenance, dict)
                else None
            ),
        ),
    }


def _admet_overview(score_payload: dict, validation: dict | None = None) -> dict:
    """Return stable ADMET evidence fields for API/chat payloads."""
    validation_block = dict(validation or score_payload.get("validation") or {})
    admet_provenance = validation_block.get(
        "admet_provenance",
        score_payload.get("admet_provenance"),
    )
    return {
        "overall_safety_flag": validation_block.get(
            "overall_safety_flag",
            score_payload.get("overall_safety_flag"),
        ),
        "overall_safety_reason": validation_block.get(
            "overall_safety_reason",
            score_payload.get("overall_safety_reason")
            or (
                (admet_provenance or {}).get("overall_safety_reason")
                if isinstance(admet_provenance, dict)
                else None
            ),
        ),
        "overall_safety_method": validation_block.get(
            "overall_safety_method",
            score_payload.get("overall_safety_method")
            or (
                (admet_provenance or {}).get("overall_safety_method")
                if isinstance(admet_provenance, dict)
                else None
            ),
        ),
        "admet_evidence_level": validation_block.get(
            "admet_evidence_level",
            score_payload.get("admet_evidence_level")
            or (
                (admet_provenance or {}).get("evidence_level")
                if isinstance(admet_provenance, dict)
                else None
            ),
        ),
        "admet_provenance": admet_provenance,
        "admet_provenance_explanation": validation_block.get(
            "admet_provenance_explanation",
            score_payload.get("admet_provenance_explanation")
            or (
                (admet_provenance or {}).get("provenance_explanation")
                if isinstance(admet_provenance, dict)
                else None
            ),
        ),
    }


def _binding_overview(score_payload: dict, validation: dict | None = None) -> dict:
    """Return stable binding evidence fields for API/chat payloads."""
    validation_block = dict(validation or score_payload.get("validation") or {})
    binding_provenance = validation_block.get(
        "binding_provenance",
        score_payload.get("binding_provenance"),
    )
    raw_binding_mode = (
        validation_block.get("binding_path_mode_raw")
        or score_payload.get("binding_path_mode_raw")
        or (
            (binding_provenance or {}).get("binding_path_mode_raw")
            if isinstance(binding_provenance, dict)
            else None
        )
        or validation_block.get("binding_mode")
        or score_payload.get("binding_mode", score_payload.get("docking_mode"))
        or (
            (binding_provenance or {}).get("binding_mode")
            if isinstance(binding_provenance, dict)
            else None
        )
    )
    public_binding_truth = _binding_truth_fields(raw_binding_mode)
    return {
        "binding_checked": validation_block.get(
            "binding_checked",
            score_payload.get("binding_checked")
            or (
                (binding_provenance or {}).get("binding_checked")
                if isinstance(binding_provenance, dict)
                else None
            ),
        ),
        "binding_mode": validation_block.get(
            "binding_mode",
            score_payload.get("binding_mode", score_payload.get("docking_mode"))
            or (
                (binding_provenance or {}).get("binding_mode")
                if isinstance(binding_provenance, dict)
                else None
            ),
        ),
        "binding_path_mode_raw": raw_binding_mode,
        "binding_claim": validation_block.get(
            "binding_claim",
            score_payload.get("binding_claim")
            or (
                (binding_provenance or {}).get("binding_claim")
                if isinstance(binding_provenance, dict)
                else None
            )
            or public_binding_truth["binding_claim"],
        ),
        "binding_truth": validation_block.get(
            "binding_truth",
            score_payload.get("binding_truth")
            or (
                (binding_provenance or {}).get("binding_truth")
                if isinstance(binding_provenance, dict)
                else None
            )
            or public_binding_truth["binding_truth"],
        ),
        "binding_evidence_level": validation_block.get(
            "binding_evidence_level",
            score_payload.get("binding_evidence_level")
            or (
                (binding_provenance or {}).get("evidence_level")
                if isinstance(binding_provenance, dict)
                else None
            ),
        ),
        "final_binding_reason": validation_block.get(
            "final_binding_reason",
            score_payload.get("final_binding_reason")
            or (
                (binding_provenance or {}).get("final_binding_reason")
                if isinstance(binding_provenance, dict)
                else None
            ),
        ),
        "binding_state": validation_block.get(
            "binding_state",
            score_payload.get("binding_state")
            or (
                (binding_provenance or {}).get("binding_state")
                if isinstance(binding_provenance, dict)
                else None
            ),
        ),
        "binding_provenance": binding_provenance,
        "binding_provenance_explanation": validation_block.get(
            "binding_provenance_explanation",
            score_payload.get("binding_provenance_explanation")
            or (
                (binding_provenance or {}).get("provenance_explanation")
                if isinstance(binding_provenance, dict)
                else None
            ),
        ),
    }


def _decision_overview(score_payload: dict, validation: dict | None = None) -> dict:
    """Return stable decision provenance fields for API/chat payloads."""
    validation_block = dict(validation or score_payload.get("validation") or {})
    decision_provenance = (
        score_payload.get("decision_provenance")
        or validation_block.get("decision_provenance")
        or (score_payload.get("clinical") or {}).get("decision_provenance")
    )
    return {
        "final_decision": (
            score_payload.get("final_decision")
            or validation_block.get("final_decision")
            or (decision_provenance or {}).get("final_decision")
        ),
        "decision_score": (
            score_payload.get("decision_score")
            or validation_block.get("decision_score")
            or (decision_provenance or {}).get("decision_score")
        ),
        "decision_confidence_tier": (
            score_payload.get("decision_confidence_tier")
            or validation_block.get("decision_confidence_tier")
            or (decision_provenance or {}).get("confidence_tier")
        ),
        "decision_evidence_level": (
            score_payload.get("decision_evidence_level")
            or validation_block.get("evidence_level")
            or (decision_provenance or {}).get("evidence_level")
        ),
        "final_decision_reason": (
            score_payload.get("final_decision_reason")
            or validation_block.get("final_decision_reason")
            or (decision_provenance or {}).get("final_decision_reason")
        ),
        "decision_comparator": (
            score_payload.get("reference_drug")
            or (decision_provenance or {}).get("comparator_name")
        ),
        "decision_provenance": decision_provenance,
        "decision_provenance_explanation": (
            (decision_provenance or {}).get("provenance_explanation")
        ),
    }


def _faculty_explanation(score_payload: dict, validation: dict | None = None) -> dict:
    """Return the canonical faculty-facing explanation stack for API/chat payloads."""
    validation_block = dict(validation or score_payload.get("validation") or {})
    existing = validation_block.get("faculty_explanation") or score_payload.get("faculty_explanation")

    binding = _binding_overview(score_payload, validation_block)
    novelty = _novelty_overview(score_payload, validation_block)
    admet = _admet_overview(score_payload, validation_block)
    decision = _decision_overview(score_payload, validation_block)
    return build_faculty_explanation_stack(
        {
            "reference_drug": validation_block.get(
                "reference_drug",
                score_payload.get("reference_drug", ACTIVE_REFERENCE_DRUG),
            ),
            **binding,
            **novelty,
            **admet,
            **decision,
            "binding_score": validation_block.get("binding_score", score_payload.get("binding_score")),
            "reference_score": validation_block.get("reference_score", score_payload.get("reference_score")),
            "delta_vs_reference": validation_block.get("delta_vs_reference", score_payload.get("delta_vs_reference")),
            "real_docking_status": validation_block.get(
                "real_docking_status",
                score_payload.get("real_docking_status"),
            ),
            "real_docking_failure": validation_block.get(
                "real_docking_failure",
                score_payload.get("real_docking_failure"),
            ),
            "hepatotoxicity_risk": validation_block.get(
                "hepatotoxicity_risk",
                score_payload.get("hepatotoxicity_risk"),
            ),
            "herg_risk": validation_block.get(
                "herg_risk",
                validation_block.get("hERG_risk", score_payload.get("herg_risk", score_payload.get("hERG_risk"))),
            ),
            "cyp_interaction_risk": validation_block.get(
                "cyp_interaction_risk",
                score_payload.get("cyp_interaction_risk"),
            ),
            "faculty_explanation": existing,
        }
    )


def _faculty_explanation_path(explanation: dict) -> str:
    """Render the canonical explanation stack as a readable sentence chain."""
    return (
        f"Novelty: {explanation['novelty_summary']['summary']} "
        f"ADMET: {explanation['admet_summary']['summary']} "
        f"Binding: {explanation['binding_summary']['summary']} "
        f"Decision: {explanation['decision_summary']['summary']}"
    )


def _build_summary(mode: str, intent: str, target_label: str, score_payload: dict) -> str:
    """Create a concise, mode-aware summary for the chat UI."""
    del mode, intent, target_label
    return _faculty_explanation(score_payload).get("overall_summary", "Faculty explanation is not available.")


def _build_generation_fallback_summary(target_label: str, generated: dict[str, Any]) -> str:
    """Explain the current safe generation fallback behavior in plain language."""
    trust = generated.get("trust", {})
    count_returned = generated.get("count_returned", 0)
    generation_mode = generated.get("generation_mode")
    if generated.get("generation_status") == "inactive_science_path":
        return (
            f"The live Genorova science path is currently standardized to the {ACTIVE_PROGRAM_LABEL}, "
            f"so '{target_label}' is not being surfaced in this active workspace path."
        )
    if generation_mode == GENERATION_MODE_REAL:
        return (
            "These molecules were freshly generated by the live autoregressive model and then revalidated under the active program."
        )
    if count_returned == 0:
        return (
            "No candidate met the active program screen in this run. "
            "Genorova is returning an honest empty result rather than inventing a molecule."
        )
    source = trust.get("result_source", "safe_fallback")
    if source == "known_reference_fallback":
        return (
            "Live generation did not return a trustworthy candidate set, so Genorova is explicitly in curated_library_mode and showing scored reference molecules."
        )
    return (
        "Live generation did not return a trustworthy candidate set, so Genorova is explicitly in curated_library_mode and showing selectively revalidated stored molecules."
    )


def _mode_specific_why(mode: str, score_payload: dict, target_label: str) -> str:
    """Explain why a molecule was selected in the requested detail mode."""
    del mode, target_label
    return _faculty_explanation_path(_faculty_explanation(score_payload))


def _candidate_block(score_payload: dict, label: str | None = None) -> dict:
    """Stable candidate block used by the chat payload."""
    binding = _binding_overview(score_payload)
    novelty = _novelty_overview(score_payload)
    admet = _admet_overview(score_payload)
    decision = _decision_overview(score_payload)
    faculty_explanation = _faculty_explanation(score_payload)
    return {
        "name": label,
        "smiles": score_payload.get("smiles"),
        "score": score_payload.get("clinical_score"),
        "recommendation": score_payload.get("recommendation"),
        "molecule_svg": _molecule_svg(score_payload.get("smiles")),
        "validation_status": score_payload.get("validation_status"),
        "final_decision": score_payload.get("final_decision"),
        "evidence_level": score_payload.get("evidence_level"),
        "confidence_level": score_payload.get("confidence_level"),
        "docking_mode": score_payload.get("docking_mode"),
        "binding_claim": binding.get("binding_claim"),
        "binding_truth": binding.get("binding_truth"),
        "binding_mode_reason": score_payload.get("binding_mode_reason"),
        "real_docking_status": score_payload.get("real_docking_status"),
        "real_docking_failure": score_payload.get("real_docking_failure"),
        **binding,
        **novelty,
        **admet,
        **decision,
        "faculty_explanation": faculty_explanation,
        "hepatotoxicity_risk": score_payload.get("hepatotoxicity_risk"),
        "hERG_risk": score_payload.get("herg_risk"),
        "cyp_interaction_risk": score_payload.get("cyp_interaction_risk"),
        "confidence_note": score_payload.get("confidence_note"),
        "result_source": score_payload.get("result_source"),
        "fallback_used": score_payload.get("fallback_used", False),
    }


def _chemical_properties(score_payload: dict) -> dict:
    """Return the chemical property section for chat rendering."""
    return {
        "molecular_weight": score_payload.get("molecular_weight"),
        "logp": score_payload.get("logp"),
        "qed_score": score_payload.get("qed_score"),
        "sa_score": score_payload.get("sa_score"),
        "h_bond_donors": score_payload.get("h_bond_donors"),
        "h_bond_acceptors": score_payload.get("h_bond_acceptors"),
        "lipinski_violations": score_payload.get("lipinski_violations"),
        "passes_lipinski": score_payload.get("passes_lipinski"),
        "ring_count": score_payload.get("ring_count"),
        "fraction_csp3": score_payload.get("fraction_csp3"),
    }


def _physical_properties(score_payload: dict) -> dict:
    """Return a simple physical property section for chat rendering."""
    return {
        "tpsa": score_payload.get("tpsa"),
        "rotatable_bonds": score_payload.get("rotatable_bonds"),
        "estimated_oral_drug_likeness": "favorable" if score_payload.get("passes_lipinski") else "needs work",
        "estimated_solubility_note": (
            "likely manageable for early oral discovery" if score_payload.get("logp", 0) < 3 else "watch lipophilicity-driven exposure risk"
        ),
    }


def _validation_block(score_payload: dict) -> dict:
    """Return a flat validation ledger for chat rendering."""
    validation = dict(score_payload.get("validation") or {})
    binding = _binding_overview(score_payload, validation)
    novelty = _novelty_overview(score_payload, validation)
    admet = _admet_overview(score_payload, validation)
    decision = _decision_overview(score_payload, validation)
    faculty_explanation = _faculty_explanation(score_payload, validation)
    return {
        "active_program": score_payload.get("program_label", ACTIVE_PROGRAM_LABEL),
        "canonical_target": score_payload.get("target", ACTIVE_TARGET),
        "reference_drug": score_payload.get("reference_drug", ACTIVE_REFERENCE_DRUG),
        "final_decision": validation.get("final_decision", score_payload.get("final_decision")),
        "decision_score": validation.get("decision_score", score_payload.get("decision_score")),
        "confidence_level": validation.get("confidence_level", score_payload.get("confidence_level")),
        "evidence_level": validation.get("evidence_level", score_payload.get("evidence_level")),
        **binding,
        **novelty,
        **admet,
        **decision,
        "faculty_explanation": faculty_explanation,
        "pains_result": "alert_detected" if validation.get("is_pains", score_payload.get("is_pains")) else "none_detected",
        "docking_mode": validation.get("docking_mode", score_payload.get("docking_mode")),
        "binding_claim": binding.get("binding_claim"),
        "binding_truth": binding.get("binding_truth"),
        "binding_mode_reason": validation.get("binding_mode_reason", score_payload.get("binding_mode_reason")),
        "binding_score": validation.get("binding_score", score_payload.get("binding_score")),
        "reference_score": validation.get("reference_score", score_payload.get("reference_score")),
        "delta_vs_reference": validation.get("delta_vs_reference", score_payload.get("delta_vs_reference")),
        "real_docking_status": validation.get("real_docking_status", score_payload.get("real_docking_status")),
        "real_docking_failure": validation.get("real_docking_failure", score_payload.get("real_docking_failure")),
        "sa_score": validation.get("sa_score", score_payload.get("sa_score")),
        "hepatotoxicity_risk": validation.get("hepatotoxicity_risk", score_payload.get("hepatotoxicity_risk")),
        "hERG_risk": validation.get("hERG_risk", score_payload.get("herg_risk")),
        "cyp_interaction_risk": validation.get("cyp_interaction_risk", score_payload.get("cyp_interaction_risk")),
    }


def _pharmacology_block(score_payload: dict, target_label: str) -> dict:
    """Return a readable pharmacology section without overstating certainty."""
    program_label = score_payload.get("program_label", target_label)
    binding = _binding_overview(score_payload)
    novelty = _novelty_overview(score_payload)
    admet = _admet_overview(score_payload)
    return {
        "intended_program": program_label,
        "canonical_target": score_payload.get("target", ACTIVE_TARGET),
        "reference_drug": score_payload.get("reference_drug", ACTIVE_REFERENCE_DRUG),
        "docking_mode": score_payload.get("docking_mode"),
        "binding_claim": binding.get("binding_claim"),
        "binding_truth": binding.get("binding_truth"),
        "binding_mode_reason": score_payload.get("binding_mode_reason"),
        "real_docking_status": score_payload.get("real_docking_status"),
        "real_docking_failure": score_payload.get("real_docking_failure"),
        "delta_vs_reference": score_payload.get("delta_vs_reference"),
        "final_decision": score_payload.get("final_decision"),
        "evidence_level": score_payload.get("evidence_level"),
        "model_score_meaning": _score_interpretation(score_payload.get("clinical_score", 0.0)),
        "oral_drug_likeness": "supported by current property profile" if score_payload.get("passes_lipinski") else "partially supported",
        **binding,
        **novelty,
        **admet,
        "hepatotoxicity_risk": score_payload.get("hepatotoxicity_risk"),
        "hERG_risk": score_payload.get("herg_risk"),
        "cyp_interaction_risk": score_payload.get("cyp_interaction_risk"),
        "validation_status": "computed descriptors plus comparator-based screening",
    }


def _strengths_block(score_payload: dict) -> list[str]:
    """Summarize upside in plain language."""
    strengths = []
    if score_payload.get("passes_lipinski"):
        strengths.append("Passes the basic Lipinski screen for oral small-molecule plausibility.")
    if score_payload.get("qed_score", 0) >= 0.6:
        strengths.append("Shows solid drug-likeness by QED, which supports early prioritization.")
    if score_payload.get("sa_score", 10) <= 4.5:
        strengths.append("Synthetic accessibility looks reasonable for follow-up chemistry work.")
    if score_payload.get("logp", 99) < 3:
        strengths.append("Lipophilicity is not excessively high, which can help balance exposure and safety.")
    return strengths or ["No standout advantages were detected beyond the baseline ranking score."]


def _risks_block(score_payload: dict) -> list[str]:
    """Summarize likely development risks."""
    risks = []
    binding = _binding_overview(score_payload)
    admet = _admet_overview(score_payload)
    if score_payload.get("lipinski_violations", 0) > 0:
        risks.append("Lipinski violations suggest oral developability risk.")
    if score_payload.get("logp", 0) > 3:
        risks.append("Elevated LogP may increase off-target binding and formulation complexity.")
    if score_payload.get("qed_score", 1) < 0.45:
        risks.append("Lower QED suggests weaker overall drug-like balance.")
    raw_binding_mode = score_payload.get("binding_path_mode_raw") or score_payload.get("binding_mode")
    if raw_binding_mode == "fallback_proxy":
        risks.append("Binding is being reported as predicted binding (Vina-validated offline) because live docking was blocked or failed.")
    elif raw_binding_mode == "scaffold_proxy":
        risks.append("Binding is being reported as predicted binding (Vina-validated offline) from a scaffold proxy rather than a live docking run.")
    elif binding.get("binding_checked") is False:
        risks.append("Binding was not checked because the active binding path could not evaluate the input structure.")
    if admet.get("overall_safety_reason"):
        risks.append(admet["overall_safety_reason"])
    elif _estimate_toxicity_risk(score_payload) in {"moderate", "high"}:
        risks.append("Rule-based toxicity screen suggests elevated risk that needs experimental follow-up.")
    if admet.get("admet_evidence_level") == "incomplete_heuristic_proxy":
        risks.append("ADMET evidence is incomplete because one or more safety checks were not completed.")
    elif admet.get("admet_evidence_level") == "heuristic_proxy_regex_fallback":
        risks.append("ADMET evidence relied on regex fallback alerts because RDKit descriptors were unavailable.")
    return risks or ["No major rule-based red flags were detected, but real safety remains unknown."]


def _next_steps_block(intent: str) -> list[str]:
    """Return responsible next-step suggestions."""
    steps = [
        "Confirm the structure with orthogonal computational checks before prioritizing it.",
        "Run target-relevant in vitro assays to test activity and selectivity.",
        "Add ADME and toxicity experiments before making any efficacy claims.",
    ]
    if intent in {"optimize", "compare"}:
        steps.insert(0, "Use the comparison to guide structure-activity relationship iterations.")
    return steps


def _warnings_block() -> list[str]:
    """Stable scientific-responsibility warnings shown in every chat result."""
    return [
        ACTIVE_SCOPE_NOTE,
        "This is a computational prediction for research support only.",
        "The result is hypothesis-generating and not experimentally validated.",
        "Do not interpret this as a proven drug, safe therapy, or clinical recommendation.",
    ]


def _trust_payload(score_payload: dict) -> dict[str, Any]:
    """Expose consistent trust metadata for chat cards."""
    return _trust_block(
        validation_status=score_payload.get("validation_status", "computational_prediction_only"),
        confidence_note=score_payload.get("confidence_note", "Confidence is limited because this is a computational prediction."),
        result_source=score_payload.get("result_source", "chat_scoring"),
        fallback_used=score_payload.get("fallback_used", False),
        limitations=score_payload.get("limitations"),
        recommended_next_step=score_payload.get("recommended_next_step"),
    )


def _generated_candidates_with_visuals(molecules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach structure SVGs to generated candidate list entries."""
    enriched = []
    for molecule in molecules:
        next_molecule = _public_candidate_payload(molecule)
        next_molecule["molecule_svg"] = _molecule_svg(molecule.get("smiles"))
        enriched.append(next_molecule)
    return enriched


def _follow_up_actions(candidate_smiles: str | None) -> list[dict[str, str]]:
    """Suggested next prompts rendered as quick actions in the UI."""
    if not candidate_smiles:
        return []
    return [
        {"label": "Explain Simply", "prompt": f"Explain this simply: {candidate_smiles}"},
        {"label": "Make Safer", "prompt": f"Make it less toxic: {candidate_smiles}"},
        {"label": "Optimize Oral Delivery", "prompt": f"Optimize it for oral delivery: {candidate_smiles}"},
        {"label": "Compare With Best", "prompt": f"Compare it with the best one: {candidate_smiles}"},
        {"label": "Download Report", "prompt": f"Prepare a downloadable report for {candidate_smiles}"},
    ]


def _build_conversation_state(
    *,
    intent: str,
    mode: str,
    target_label: str,
    candidate_smiles: str | None = None,
    comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return structured conversation state for lightweight memory-aware chat."""
    return {
        "latest_intent": intent,
        "latest_mode": mode,
        "latest_topic": target_label,
        "recent_candidate_smiles": candidate_smiles,
        "recent_comparison": comparison,
        "recent_best_smiles": _best_available_smiles() or "",
    }


def _compare_molecules(first: dict, second: dict) -> dict:
    """
    Create a UI-friendly comparison block for two scored molecules.

    Uses clinical_score as the public ordering signal and falls back to rank_score
    only when an older internal payload has not yet been normalized.
    """
    def _rank(c: dict) -> float:
        return float(c.get("clinical_score") or c.get("rank_score") or 0.0)

    gap = round(_rank(first) - _rank(second), 4)
    preferred = first if gap >= 0 else second
    other = second if preferred is first else first

    pref_label = _ranking_label(candidate=preferred)
    other_label = _ranking_label(candidate=other)
    preferred_binding = _binding_overview(preferred)
    preferred_novelty = _novelty_overview(preferred)
    preferred_admet = _admet_overview(preferred)

    molecules = [
        {
            "label": "Molecule A",
            "smiles": first.get("smiles"),
            "summary": first.get("summary"),
            "clinical_score": first.get("clinical_score") or first.get("rank_score"),
            "rank_label": _ranking_label(candidate=first),
            "qed_score": first.get("qed_score"),
            "logp": first.get("logp"),
            "molecular_weight": first.get("molecular_weight"),
            "recommendation": first.get("recommendation"),
            "delta_vs_reference": first.get("delta_vs_reference"),
            "hepatotoxicity_risk": first.get("hepatotoxicity_risk"),
            "herg_risk": first.get("herg_risk"),
            "cyp_interaction_risk": first.get("cyp_interaction_risk"),
            "binding_claim": first.get("binding_claim"),
            "binding_truth": first.get("binding_truth"),
            **_binding_overview(first),
            **_novelty_overview(first),
            **_admet_overview(first),
            **_decision_overview(first),
            "faculty_explanation": _faculty_explanation(first),
            "molecule_svg": _molecule_svg(first.get("smiles")),
        },
        {
            "label": "Molecule B",
            "smiles": second.get("smiles"),
            "summary": second.get("summary"),
            "clinical_score": second.get("clinical_score") or second.get("rank_score"),
            "rank_label": _ranking_label(candidate=second),
            "qed_score": second.get("qed_score"),
            "logp": second.get("logp"),
            "molecular_weight": second.get("molecular_weight"),
            "recommendation": second.get("recommendation"),
            "delta_vs_reference": second.get("delta_vs_reference"),
            "hepatotoxicity_risk": second.get("hepatotoxicity_risk"),
            "herg_risk": second.get("herg_risk"),
            "cyp_interaction_risk": second.get("cyp_interaction_risk"),
            "binding_claim": second.get("binding_claim"),
            "binding_truth": second.get("binding_truth"),
            **_binding_overview(second),
            **_novelty_overview(second),
            **_admet_overview(second),
            **_decision_overview(second),
            "faculty_explanation": _faculty_explanation(second),
            "molecule_svg": _molecule_svg(second.get("smiles")),
        },
    ]
    comparison_presentation = build_comparison_presentation(
        molecules[0],
        molecules[1],
        left_label="Molecule A",
        right_label="Molecule B",
    )

    # All summary sentences and the score note now come from the shared presentation payload.
    sec = comparison_presentation["section_summaries"]

    return {
        "molecules": molecules,
        "comparison_presentation": comparison_presentation,
        "preferred_smiles": preferred.get("smiles"),
        "preferred_label": pref_label,
        "preferred_binding_mode": preferred_binding.get("binding_mode"),
        "preferred_final_binding_reason": preferred_binding.get("final_binding_reason"),
        "preferred_binding_provenance": preferred_binding.get("binding_provenance"),
        "preferred_novelty_status": preferred_novelty.get("novelty_status"),
        "preferred_novelty_reason": preferred_novelty.get("novelty_reason"),
        "preferred_novelty_provenance": preferred_novelty.get("novelty_provenance"),
        "preferred_overall_safety_flag": preferred_admet.get("overall_safety_flag"),
        "preferred_overall_safety_reason": preferred_admet.get("overall_safety_reason"),
        "preferred_admet_provenance": preferred_admet.get("admet_provenance"),
        "novelty_summary": sec["novelty"],
        "binding_summary": sec["binding"],
        "admet_summary": sec["admet"],
        "safety_summary": sec["admet"],
        "decision_summary": sec["decision"],
        "why": comparison_presentation["full_comparison_note"],
        "score_gap": abs(gap),
        "comparison_score_note": comparison_presentation["score_note"],
    }


def _build_chat_response(intent: str, mode: str, message: str, state: dict[str, Any]) -> dict:
    """Route a natural-language chat request to existing Genorova logic."""
    target_bucket, target_label = _infer_disease_area(message)
    resolved_smiles = _resolve_reference_smiles(message, state)
    latest_candidate_smiles = state.get("recent_candidate_smiles")

    if intent == "score":
        if not resolved_smiles:
            raise HTTPException(status_code=422, detail="Please include a SMILES string to score.")
        score_payload = _score_smiles_payload(resolved_smiles[0])
        candidate_smiles = score_payload.get("smiles")
        return {
            "intent": intent,
            "mode": mode,
            "message": message,
            "summary": _build_summary(mode, "scoring", target_label, score_payload),
            "candidate": _candidate_block(score_payload),
            "why": _mode_specific_why(mode, score_payload, target_label),
            "chemical_properties": _chemical_properties(score_payload),
            "physical_properties": _physical_properties(score_payload),
            "validation": _validation_block(score_payload),
            "pharmacology": _pharmacology_block(score_payload, target_label),
            "trust": _trust_payload(score_payload),
            "strengths": _strengths_block(score_payload),
            "risks": _risks_block(score_payload),
            "limitations": score_payload.get("limitations", []),
            "next_steps": _next_steps_block(intent),
            "warnings": _warnings_block(),
            "follow_up_actions": _follow_up_actions(candidate_smiles),
            "conversation_state": _build_conversation_state(
                intent=intent,
                mode=mode,
                target_label=target_label,
                candidate_smiles=candidate_smiles,
            ),
        }

    if intent == "explain":
        base_smiles = resolved_smiles[0] if resolved_smiles else latest_candidate_smiles or _best_available_smiles()
        score_payload = _score_smiles_payload(base_smiles)
        candidate_smiles = score_payload.get("smiles")
        return {
            "intent": intent,
            "mode": mode,
            "message": message,
            "summary": _build_summary(mode, "explanation", target_label, score_payload),
            "candidate": _candidate_block(score_payload),
            "why": _mode_specific_why(mode, score_payload, target_label),
            "chemical_properties": _chemical_properties(score_payload),
            "physical_properties": _physical_properties(score_payload),
            "validation": _validation_block(score_payload),
            "pharmacology": _pharmacology_block(score_payload, target_label),
            "trust": _trust_payload(score_payload),
            "strengths": _strengths_block(score_payload),
            "risks": _risks_block(score_payload),
            "limitations": score_payload.get("limitations", []),
            "next_steps": _next_steps_block(intent),
            "warnings": _warnings_block(),
            "follow_up_actions": _follow_up_actions(candidate_smiles),
            "conversation_state": _build_conversation_state(
                intent=intent,
                mode=mode,
                target_label=target_label,
                candidate_smiles=candidate_smiles,
            ),
        }

    if intent == "compare":
        compare_smiles = resolved_smiles
        lowered = message.lower()
        if len(compare_smiles) < 2 and latest_candidate_smiles and "best" in lowered:
            compare_smiles = [latest_candidate_smiles, _best_available_smiles()]
        if len(compare_smiles) < 2:
            raise HTTPException(status_code=422, detail="Please provide two SMILES strings to compare.")

        first = _score_smiles_payload(compare_smiles[0])
        second = _score_smiles_payload(compare_smiles[1])
        comparison = _compare_molecules(first, second)
        preferred = first if comparison["preferred_smiles"] == first.get("smiles") else second
        candidate_smiles = preferred.get("smiles")
        return {
            "intent": intent,
            "mode": mode,
            "message": message,
            "summary": f"I compared two computational candidates and the current model favors {comparison['preferred_smiles']}.",
            "candidate": _candidate_block(preferred, label="Preferred by current ranking"),
            "comparison": comparison,
            "why": comparison["why"],
            "chemical_properties": _chemical_properties(preferred),
            "physical_properties": _physical_properties(preferred),
            "validation": _validation_block(preferred),
            "pharmacology": _pharmacology_block(preferred, target_label),
            "trust": _trust_payload(preferred),
            "strengths": _strengths_block(preferred),
            "risks": _risks_block(preferred),
            "limitations": preferred.get("limitations", []),
            "next_steps": _next_steps_block(intent),
            "warnings": _warnings_block(),
            "follow_up_actions": _follow_up_actions(candidate_smiles),
            "conversation_state": _build_conversation_state(
                intent=intent,
                mode=mode,
                target_label=target_label,
                candidate_smiles=candidate_smiles,
                comparison=comparison,
            ),
        }

    if intent == "optimize":
        base_smiles = resolved_smiles[0] if resolved_smiles else latest_candidate_smiles
        if not base_smiles:
            generated = _generate_candidates_for_disease(target_bucket, 1)
            base_smiles = generated["molecules"][0]["smiles"]
        base_candidate = _score_smiles_payload(base_smiles)
        candidate_smiles = base_candidate.get("smiles")
        lowered = message.lower()
        optimization_suggestions = [
            "Lower lipophilicity if LogP is elevated by trimming hydrophobic substituents.",
            "Reduce obvious structural alerts before claiming a safer analog.",
            "Generate close analogs and re-score them before synthesis planning.",
        ]
        if "oral" in lowered:
            optimization_suggestions.insert(0, "Prioritize lower molecular weight, balanced LogP, and fewer Lipinski liabilities for oral delivery.")
        if "toxic" in lowered or "safer" in lowered:
            optimization_suggestions.insert(0, "Reduce features likely to raise rule-based toxicity flags before advancing this candidate.")
        return {
            "intent": intent,
            "mode": mode,
            "message": message,
            "summary": f"I reviewed the current candidate for {target_label} and suggested how to make it safer or more developable.",
            "candidate": _candidate_block(base_candidate, label="Current candidate"),
            "why": _mode_specific_why(mode, base_candidate, target_label),
            "chemical_properties": _chemical_properties(base_candidate),
            "physical_properties": _physical_properties(base_candidate),
            "validation": _validation_block(base_candidate),
            "pharmacology": _pharmacology_block(base_candidate, target_label),
            "trust": _trust_payload(base_candidate),
            "strengths": _strengths_block(base_candidate),
            "risks": _risks_block(base_candidate),
            "limitations": base_candidate.get("limitations", []),
            "optimization_suggestions": optimization_suggestions,
            "next_steps": _next_steps_block(intent),
            "warnings": _warnings_block(),
            "follow_up_actions": _follow_up_actions(candidate_smiles),
            "conversation_state": _build_conversation_state(
                intent=intent,
                mode=mode,
                target_label=target_label,
                candidate_smiles=candidate_smiles,
            ),
        }

    generated = _generate_candidates_for_disease(target_bucket, _extract_count(message, default=5))
    if generated.get("count_returned", 0) == 0:
        trust = generated.get("trust", _trust_block(
            validation_status="no_valid_candidate_available",
            confidence_note="No valid candidate was available in this run.",
            result_source="empty_generation_result",
        ))
        return {
            "intent": "generate",
            "mode": mode,
            "message": message,
            "summary": _build_generation_fallback_summary(target_label, generated),
            "candidate": None,
            "generated_candidates": [],
            "trust": trust,
            "limitations": trust.get("limitations", []),
            "why": "The current generation path did not produce a trustworthy valid molecule, so Genorova is explicitly reporting the failure.",
            "risks": [
                "Generation quality is currently too weak to present a fresh molecule as a valid candidate.",
                "Proceeding without a valid structure would be misleading.",
            ],
            "next_steps": [
                trust.get("recommended_next_step", "Score a known molecule instead."),
                "Use the score, explain, or compare flows on known valid SMILES strings.",
                "Review checkpoint comparison results before trusting new generation runs.",
            ],
            "warnings": _warnings_block(),
            "follow_up_actions": [
                {"label": "Score Known Molecule", "prompt": 'Score this molecule: CCO'},
                {"label": "Compare References", "prompt": "Compare metformin with the best one"},
                {"label": "Explain Best Molecule", "prompt": "Explain the best molecule simply"},
            ],
            "program_context": {
                "requested_label": target_label,
                "supported_bucket": target_bucket,
                "count_returned": 0,
                "generation_status": generated.get("generation_status"),
                "generation_mode": generated.get("generation_mode"),
            },
            "conversation_state": _build_conversation_state(
                intent="generate",
                mode=mode,
                target_label=target_label,
                candidate_smiles=None,
            ),
        }

    top_candidate = generated["molecules"][0]
    score_payload = _score_smiles_payload(top_candidate["smiles"])
    score_payload.update(
        {
            "validation_status": generated.get("trust", {}).get("validation_status", score_payload.get("validation_status")),
            "confidence_note": generated.get("trust", {}).get("confidence_note", score_payload.get("confidence_note")),
            "result_source": generated.get("trust", {}).get("result_source", score_payload.get("result_source")),
            "fallback_used": generated.get("trust", {}).get("fallback_used", False),
            "limitations": generated.get("trust", {}).get("limitations", score_payload.get("limitations")),
            "recommended_next_step": generated.get("trust", {}).get("recommended_next_step", score_payload.get("recommended_next_step")),
        }
    )
    candidate_smiles = score_payload.get("smiles")
    return {
        "intent": "generate",
        "mode": mode,
        "message": message,
        "summary": _build_generation_fallback_summary(target_label, generated),
        "candidate": _candidate_block(
            score_payload,
            label=(
                "Top freshly generated candidate"
                if generated.get("generation_mode") == GENERATION_MODE_REAL
                else "Top curated-library candidate"
            ),
        ),
        "generated_candidates": _generated_candidates_with_visuals(generated["molecules"]),
        "why": _mode_specific_why(mode, score_payload, target_label),
        "chemical_properties": _chemical_properties(score_payload),
        "physical_properties": _physical_properties(score_payload),
        "validation": _validation_block(score_payload),
        "pharmacology": _pharmacology_block(score_payload, target_label),
        "trust": _trust_payload(score_payload),
        "strengths": _strengths_block(score_payload),
        "risks": _risks_block(score_payload),
        "limitations": score_payload.get("limitations", []),
        "next_steps": _next_steps_block(intent),
        "warnings": _warnings_block(),
        "follow_up_actions": _follow_up_actions(candidate_smiles),
        "program_context": {
            "requested_label": target_label,
            "supported_bucket": target_bucket,
            "count_returned": generated["count_returned"],
            "generation_status": generated.get("generation_status"),
            "generation_mode": generated.get("generation_mode"),
            "source_type": generated.get("trust", {}).get("result_source"),
        },
        "conversation_state": _build_conversation_state(
            intent="generate",
            mode=mode,
            target_label=target_label,
            candidate_smiles=candidate_smiles,
        ),
    }


def _frontend_is_built() -> bool:
    """Return True when the compiled React frontend exists."""
    return FRONTEND_INDEX_PATH.exists()


def _frontend_file(path: str) -> Path | None:
    """Safely resolve a file inside the compiled frontend directory."""
    candidate = (FRONTEND_DIST_DIR / path).resolve()
    try:
        candidate.relative_to(FRONTEND_DIST_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _api_home_payload() -> dict:
    """Stable metadata payload for the API surface."""
    return {
        "name":    "Genorova AI Computational Molecule Analysis API",
        "version": APP_VERSION,
        "docs":    "/docs",
        "health":  "/health",
        "ready":   "/ready",
        "release": "/version",
        "ops_status": "/ops/status",
        "report":  "/report",
        "public_url": _public_url(),
        "prototype_status": PROTOTYPE_STATUS,
    }


# ============================================================================
# VALIDATION PIPELINE ENDPOINTS  (second-stage validation, v2.0)
# ============================================================================
#
# These endpoints run the full four-stage validation pipeline or any single
# stage for a submitted SMILES string.
#
# All responses include:
#   - Structured JSON matching the Pydantic models in validation/models.py
#   - Explicit data_source / mode / confidence fields so callers always know
#     whether a score is a real computation or a heuristic proxy.
#   - A plain-language 'summary' / 'explanation' for non-technical readers.
#
# Endpoints:
#   POST /api/validate                 — full pipeline (all 4 stages)
#   POST /api/validate/chemistry       — chemical sanity only
#   POST /api/validate/binding         — target engagement only
#   POST /api/validate/admet           — ADMET safety only
#   POST /api/validate/clinical        — clinical utility only
#                                        (requires upstream stage results)
# ============================================================================

# ── Request / response models for validation endpoints ──────────────────────

class ValidateRequest(BaseModel):
    """Request body for the full /api/validate endpoint."""
    smiles: str = Field(..., description="SMILES string of the candidate molecule.")
    target: str = Field(
        default=ACTIVE_TARGET,
        description=(
            "Protein target key. The active Genorova validation path defaults to "
            f"{ACTIVE_TARGET}. Other targets remain available for explicit validation calls."
        ),
    )
    disease: str = Field(
        default=ACTIVE_DISEASE,
        description=f"Disease context for clinical evaluation. The active path defaults to {ACTIVE_DISEASE}.",
    )
    reference_drug: str = Field(
        default=ACTIVE_REFERENCE_DRUG,
        description=(
            "Name of the reference standard-of-care drug for comparison. "
            "If empty, the target's default reference drug is used."
        ),
    )
    pubchem_lookup: bool = Field(
        default=False,
        description=(
            "Query PubChem REST API to check novelty (requires internet). "
            "When False, novelty is checked against the local database only."
        ),
    )


class ChemistryRequest(BaseModel):
    """Request body for /api/validate/chemistry."""
    smiles: str
    pubchem_lookup: bool = False


class BindingRequest(BaseModel):
    """Request body for /api/validate/binding."""
    smiles: str
    target: str = ACTIVE_TARGET
    reference_drug: str = ACTIVE_REFERENCE_DRUG


class ADMETRequest(BaseModel):
    """Request body for /api/validate/admet."""
    smiles: str


class ClinicalRequest(BaseModel):
    """
    Request body for /api/validate/clinical.
    Requires upstream chemistry, binding, and ADMET results so the
    clinical stage can synthesise them.
    """
    smiles: str
    target: str = ACTIVE_TARGET
    disease: str = ACTIVE_DISEASE
    reference_drug: str = ""
    chemistry_result: dict = Field(
        default_factory=dict,
        description="Output of /api/validate/chemistry (or run_chemistry_sanity).",
    )
    binding_result: dict = Field(
        default_factory=dict,
        description="Output of /api/validate/binding (or run_binding_evaluation).",
    )
    admet_result: dict = Field(
        default_factory=dict,
        description="Output of /api/validate/admet (or run_admet_evaluation).",
    )
    qed_score: float = Field(default=None)
    passes_lipinski: bool = Field(default=None)


# ── Lazy loader for validation pipeline ─────────────────────────────────────

_VALIDATION_PIPELINE = None


def _get_validation_pipeline():
    """
    Import the validation pipeline module lazily so that startup is not
    blocked by RDKit availability checks.  Returns a module or None on error.
    """
    global _VALIDATION_PIPELINE
    if _VALIDATION_PIPELINE is not None:
        return _VALIDATION_PIPELINE
    try:
        import importlib
        vp = importlib.import_module("validation.pipeline")
        _VALIDATION_PIPELINE = vp
        return vp
    except Exception as e:
        return None


def _validation_unavailable_response(reason: str) -> dict:
    """Standard response when the validation pipeline is not importable."""
    return {
        "error":   "validation_pipeline_unavailable",
        "reason":  reason,
        "hint": (
            "Ensure genorova/src/ is on PYTHONPATH and RDKit is installed. "
            "Run: cd genorova/src && python -m validation.pipeline"
        ),
    }


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.post(
    "/api/validate",
    summary="Full validation pipeline (all 4 stages)",
    tags=["Validation v2"],
)
def api_validate_full(request: ValidateRequest):
    """
    Run the complete second-stage validation pipeline for a single molecule.

    Returns a ValidationResult with four nested stage results plus:
    - final_decision: advance | conditional_advance | reject
    - summary: plain-language paragraph for faculty review
    - Answers to the five core questions (can_be_synthesized, likely_novel, etc.)

    All proxy scores are labelled with their method and confidence level.
    This endpoint never fakes docking or ADMET results — if real tools are
    unavailable the response is explicit about which mode was used.
    """
    vp = _get_validation_pipeline()
    if vp is None:
        raise HTTPException(
            status_code=503,
            detail=_validation_unavailable_response(
                "Could not import validation.pipeline"
            ),
        )

    try:
        result = vp.validate_molecule(
            smiles=request.smiles,
            target=request.target,
            disease=request.disease,
            reference_drug=request.reference_drug or None,
            pubchem_lookup=request.pubchem_lookup,
        )
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})


@app.post(
    "/api/validate/chemistry",
    summary="Chemical sanity check (SA score, PAINS, novelty)",
    tags=["Validation v2"],
)
def api_validate_chemistry(request: ChemistryRequest):
    """
    Run the Chemical Sanity stage for a single molecule.

    Returns:
    - sa_score and sa_flag (synthesizable / difficult / impractical)
    - is_pains and matched alert names
    - novelty status (local DB + optional PubChem)
    - passes_sanity: overall gate (True/False)
    """
    try:
        from validation.chemistry.sanitizer import run_chemistry_sanity  # noqa
        result = run_chemistry_sanity(
            smiles=request.smiles,
            pubchem_lookup=request.pubchem_lookup,
        )
        return JSONResponse(content=result)
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail=_validation_unavailable_response("validation.chemistry not importable"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})


@app.post(
    "/api/validate/binding",
    summary="Target engagement evaluation (docking or scaffold proxy)",
    tags=["Validation v2"],
)
def api_validate_binding(request: BindingRequest):
    """
    Evaluate predicted binding to the target protein.

    real_docking is returned only when docking actually executed successfully.
    Otherwise the response falls back honestly to either scaffold_proxy,
    fallback_proxy, or unavailable.

    Returns:
    - docking_score, reference_score, delta_vs_reference
    - key_h_bonds (populated by real docking only)
    - mode: real_docking | scaffold_proxy | fallback_proxy | unavailable
    - confidence: high | medium | low | none
    - mode_reason, real_docking_status, real_docking_failure
    - binding_provenance: canonical record of which binding path ran and what blocked real docking if any
    - binding_provenance_explanation: plain-language summary of the binding path and evidence strength
    - interpretation: plain-language binding summary
    """
    try:
        from validation.binding.target_binder import run_binding_evaluation  # noqa
        result = run_binding_evaluation(
            smiles=request.smiles,
            target=request.target,
            reference_drug=request.reference_drug or None,
        )
        return JSONResponse(content=result)
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail=_validation_unavailable_response("validation.binding not importable"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})


@app.post(
    "/api/validate/admet",
    summary="ADMET and safety assessment (hepatotoxicity, hERG, CYP450)",
    tags=["Validation v2"],
)
def api_validate_admet(request: ADMETRequest):
    """
    Predict ADMET and safety risks for a molecule.

    All predictions are heuristic proxies based on structural alerts and
    molecular descriptors.  The disclaimer field in the response contains
    the full caveats.

    Returns:
    - hepatotoxicity_risk: level (low/medium/high), score, alerts, method
    - herg_risk: same schema
    - cyp_risk: same schema
    - overall_safety_flag: likely_safe | caution | likely_unsafe | unknown
    - safety_score: 0–1 composite (1 = safest)
    """
    try:
        from validation.admet.admet_predictor import run_admet_evaluation  # noqa
        result = run_admet_evaluation(smiles=request.smiles)
        return JSONResponse(content=result)
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail=_validation_unavailable_response("validation.admet not importable"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})


@app.post(
    "/api/validate/clinical",
    summary="Clinical utility decision (advance / conditional / reject)",
    tags=["Validation v2"],
)
def api_validate_clinical(request: ClinicalRequest):
    """
    Synthesise upstream validation results into a clinical utility verdict.

    If chemistry_result, binding_result, or admet_result are empty dicts,
    the endpoint will run those stages internally so you can also call this
    endpoint standalone with just a SMILES string.

    Returns:
    - decision: advance | conditional_advance | reject
    - decision_score: 0–1 composite score
    - explanation: plain-language paragraph for faculty review
    - conditions: actionable items for conditional_advance
    - rejection_reasons: specific issues for reject
    - comparisons: property table vs reference drug
    - potency_vs_toxicity_note: trade-off analysis
    """
    try:
        from validation.clinical.clinical_evaluator import run_clinical_evaluation  # noqa
        from validation.chemistry.sanitizer import run_chemistry_sanity  # noqa
        from validation.binding.target_binder import run_binding_evaluation  # noqa
        from validation.admet.admet_predictor import run_admet_evaluation  # noqa

        # Run missing upstream stages if not provided
        chem = request.chemistry_result or run_chemistry_sanity(request.smiles, pubchem_lookup=False)
        bind = request.binding_result   or run_binding_evaluation(
            request.smiles, request.target, request.reference_drug or None
        )
        admt = request.admet_result     or run_admet_evaluation(request.smiles)

        result = run_clinical_evaluation(
            smiles=request.smiles,
            target=request.target,
            disease=request.disease,
            reference_drug=request.reference_drug or bind.get("reference_drug", "reference"),
            chemistry_result=chem,
            binding_result=bind,
            admet_result=admt,
            qed_score=request.qed_score,
            passes_lipinski=request.passes_lipinski,
        )
        return JSONResponse(content=result)
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail=_validation_unavailable_response("validation.clinical not importable"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})


# ── Root redirect ─────────────────────────────────────────────────────────────

@app.get("/api", include_in_schema=False)
def api_root():
    """Expose API metadata without taking over the site root."""
    return JSONResponse(_api_home_payload())


@app.get("/", include_in_schema=False)
def root():
    if _frontend_is_built():
        return FileResponse(FRONTEND_INDEX_PATH)
    return JSONResponse(_api_home_payload())


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_routes(full_path: str):
    """
    Serve the built SPA for client-side routes while leaving API and docs
    endpoints on FastAPI's normal routing table.
    """
    if not _frontend_is_built():
        raise HTTPException(status_code=404, detail="Not Found")

    requested_file = _frontend_file(full_path)
    if requested_file is not None:
        return FileResponse(requested_file)

    filename = Path(full_path).name
    if full_path.startswith("api/") or "." in filename:
        raise HTTPException(status_code=404, detail="Not Found")

    return FileResponse(FRONTEND_INDEX_PATH)
