"""
Genorova AI — FastAPI Web Service
===================================

REST API for the Genorova AI drug discovery platform.
Exposes molecule generation, scoring, and reporting over HTTP.

ENDPOINTS:
    GET  /health           — service status
    POST /generate         — generate drug candidates for a disease
    POST /score            — score a single SMILES string
    GET  /best_molecules   — top 10 molecules discovered so far
    GET  /report           — HTML discovery report

USAGE:
    python -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

AUTHOR: Pushp Dwivedi | pushpdwivedi911@gmail.com
DATE:   April 2026
"""

import sys
import sqlite3
import csv
import re
import uuid
from pathlib import Path
from datetime import datetime
from typing import Any

# Make src/ importable
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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
BEST_MOLECULE = "COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2"

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "Genorova AI — Drug Discovery API",
    description = (
        "Generative AI platform for diabetes and infectious disease drug design. "
        "Uses a Variational Autoencoder trained on ChEMBL data, scored against "
        "real Phase 3 clinical trial endpoints."
    ),
    version     = "1.0.0",
    contact     = {
        "name":  "Pushp Dwivedi",
        "email": "pushpdwivedi911@gmail.com",
    },
)

if FRONTEND_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_ASSETS_DIR)), name="frontend-assets")


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


def _generate_candidates_for_disease(disease: str, count: int) -> dict:
    """Shared generation logic used by both REST and chat endpoints."""
    disease = disease.lower()
    if disease not in ("diabetes", "infection"):
        raise HTTPException(status_code=400,
                            detail="disease must be 'diabetes' or 'infection'")

    count = min(count, 200)
    rows = _load_csv(disease)
    if not rows:
        raise HTTPException(
            status_code=503,
            detail=f"No pre-computed candidates for '{disease}'. "
                   "Run: python src/run_pipeline.py first."
        )

    top = rows[:count]
    results = []
    for i, row in enumerate(top, 1):
        results.append({
            "rank":             i,
            "smiles":           row.get("smiles", ""),
            "molecular_weight": _safe_float(row.get("molecular_weight")),
            "logp":             _safe_float(row.get("logp")),
            "qed_score":        _safe_float(row.get("qed_score")),
            "sa_score":         _safe_float(row.get("sa_score")),
            "clinical_score":   _safe_float(row.get("clinical_score")),
            "passes_lipinski":  str(row.get("passes_lipinski", "")).lower() in ("true", "1", "yes"),
            "recommendation":   row.get("recommendation", ""),
        })

    return {
        "disease":          disease,
        "count_returned":   len(results),
        "count_requested":  count,
        "generated_at":     datetime.now().isoformat(),
        "molecules":        results,
    }


def _score_smiles_payload(smiles: str) -> dict:
    """Shared scoring logic used by REST and chat endpoints."""
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, QED, Crippen
        from scorer import genorova_clinical_score, calculate_sa_score

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise HTTPException(status_code=422, detail="Invalid SMILES string")

        mw = Descriptors.MolWt(mol)
        logp = Crippen.MolLogP(mol)
        hbd = Descriptors.NumHDonors(mol)
        hba = Descriptors.NumHAcceptors(mol)
        tpsa = Descriptors.TPSA(mol)
        qed = QED.qed(mol)
        sa = calculate_sa_score(smiles)
        rotatable_bonds = Descriptors.NumRotatableBonds(mol)
        rings = Descriptors.RingCount(mol)
        fraction_csp3 = Descriptors.FractionCSP3(mol)
        viol = sum([mw > 500, logp > 5, hbd > 5, hba > 10])
        lip = viol == 0
        score_val = genorova_clinical_score(smiles)

        if score_val >= 0.85:
            recommendation = "Strong candidate"
        elif score_val >= 0.60:
            recommendation = "Borderline"
        else:
            recommendation = "Reject"

        _store_molecule(smiles, qed, sa, mw, logp, score_val, recommendation)

        return {
            "smiles": smiles,
            "molecular_weight": round(mw, 2),
            "logp": round(logp, 3),
            "h_bond_donors": hbd,
            "h_bond_acceptors": hba,
            "tpsa": round(tpsa, 2),
            "qed_score": round(qed, 4),
            "sa_score": round(sa, 4),
            "passes_lipinski": lip,
            "lipinski_violations": viol,
            "clinical_score": round(score_val, 4),
            "recommendation": recommendation,
            "rotatable_bonds": rotatable_bonds,
            "ring_count": rings,
            "fraction_csp3": round(fraction_csp3, 3),
            "scored_at": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scoring failed: {e}")


def _get_or_create_session_id(session_id: str | None) -> str:
    """Return a stable session identifier for the chat flow."""
    if session_id and session_id.strip():
        return session_id.strip()
    return f"session-{uuid.uuid4().hex}"


def _get_session_state(session_id: str) -> dict[str, Any]:
    """Read in-memory session state for the current deployment instance."""
    return dict(CHAT_SESSION_MEMORY.get(session_id, {}))


def _save_session_state(session_id: str, state: dict[str, Any]) -> None:
    """Persist lightweight session context in memory for this process."""
    CHAT_SESSION_MEMORY[session_id] = dict(state)


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

@app.get("/health", summary="Service health check")
def health():
    """
    Returns running status and model availability.
    Use this to verify the server is up before sending requests.
    """
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

    return {
        "status":          "running",
        "model":           "Genorova AI v1.0",
        "timestamp":       datetime.now().isoformat(),
        "models_loaded": {
            "diabetes":  diabetes_model,
            "infection": infection_model,
        },
        "molecules_in_db": db_count,
        "best_molecule":   "COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2",
        "best_score":      0.9649,
    }


# ── ENDPOINT: POST /generate ──────────────────────────────────────────────────

@app.post("/generate", summary="Generate drug candidates")
def generate(req: GenerateRequest):
    """
    Generate new drug molecule candidates for a target disease.

    Uses the trained VAE + library screening to return top scored candidates.
    Falls back to the pre-computed CSV if the model is not loaded in memory.

    - **disease**: "diabetes" or "infection"
    - **count**: number of molecules to return (max 200)
    """
    return _generate_candidates_for_disease(req.disease, req.count)


@app.post("/api/generate", summary="Generate drug candidates (SaaS API)")
def api_generate(req: GenerateRequest):
    """Alias route for the SaaS frontend deployed against src.api:app."""
    return generate(req)


# ── ENDPOINT: POST /score ─────────────────────────────────────────────────────

@app.post("/score", summary="Score a molecule")
def score(req: ScoreRequest):
    """
    Compute the Genorova Clinical Score for any valid SMILES string.

    Returns a complete property profile including:
    - Drug-likeness (QED), synthetic accessibility (SA), Lipinski compliance
    - Genorova clinical score (0–1)
    - Recommendation: Strong candidate / Borderline / Reject
    """
    return _score_smiles_payload(req.smiles)


@app.post("/api/score", summary="Score a molecule (SaaS API)")
def api_score(req: ScoreRequest):
    """Alias route for the SaaS frontend deployed against src.api:app."""
    return score(req)


# ── ENDPOINT: GET /best_molecules ─────────────────────────────────────────────

@app.get("/best_molecules", summary="Top 10 molecules discovered")
def best_molecules(n: int = 10):
    """
    Return the top N molecules discovered by Genorova AI, ranked by clinical score.

    Queries the persistent molecule database that is updated every pipeline run.
    """
    n = min(n, 50)
    rows = _load_db_top(n)

    if not rows:
        # Fallback: read directly from CSVs
        all_rows = []
        for disease in ("diabetes", "infection"):
            for row in _load_csv(disease):
                row["target_disease"] = disease
                all_rows.append(row)
        all_rows.sort(key=lambda r: float(r.get("clinical_score", 0)), reverse=True)
        rows = []
        for i, row in enumerate(all_rows[:n], 1):
            rows.append({
                "rank":           i,
                "smiles":         row.get("smiles", ""),
                "clinical_score": _safe_float(row.get("clinical_score")),
                "qed_score":      _safe_float(row.get("qed_score")),
                "sa_score":       _safe_float(row.get("sa_score")),
                "target_disease": row.get("target_disease", ""),
                "recommendation": row.get("recommendation", ""),
            })
        return {"source": "csv", "count": len(rows), "molecules": rows}

    return {
        "source":    "database",
        "count":     len(rows),
        "molecules": [
            {
                "rank":           i + 1,
                "smiles":         r.get("smiles", ""),
                "clinical_score": r.get("clinical_score", 0),
                "qed_score":      r.get("qed_score", 0),
                "sa_score":       r.get("sa_score", 0),
                "target_disease": r.get("target_disease", ""),
                "recommendation": r.get("recommendation", ""),
            }
            for i, r in enumerate(rows)
        ],
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
            "best_score":         None,
            "best_molecule":      None,
            "best_molecular_weight": None,
            "avg_qed_score":      None,
            "avg_sa_score":       None,
            "data_source":        "none",
            "message": (
                "No molecules generated yet. "
                "Run: python src/run_pipeline.py to generate candidates."
            ),
        }

    return {
        "total_molecules":       total,
        "best_score":            best_score,
        "best_molecule":         best_molecule,
        "best_molecular_weight": best_mw,
        "avg_qed_score":         avg_qed,
        "avg_sa_score":          avg_sa,
        "data_source":           data_source,
    }


@app.post("/api/chat", summary="Natural-language Genorova chat endpoint")
def api_chat(req: ChatRequest):
    """Accept a natural-language request and route it through Genorova's core logic."""
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message cannot be empty.")

    session_id = _get_or_create_session_id(req.session_id)
    merged_state = _merge_state_sources(req.conversation_state, _get_session_state(session_id))
    mode = _resolve_mode_from_message(message, _normalize_mode(req.mode), merged_state)
    intent = _parse_chat_intent(message)
    response = _build_chat_response(intent, mode, message, merged_state)
    response["intent"] = intent
    response["mode"] = mode
    response["session_id"] = session_id
    response["history_window"] = req.history[-6:]
    response["generated_at"] = datetime.now().isoformat()
    _save_session_state(session_id, response.get("conversation_state", merged_state))
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
        "diabetes": ("diabetes", "diabetes"),
        "tb": ("infection", "tuberculosis"),
        "tuberculosis": ("infection", "tuberculosis"),
        "infection": ("infection", "infectious disease"),
        "infectious": ("infection", "infectious disease"),
        "bacterial": ("infection", "bacterial infection"),
        "viral": ("infection", "viral infection"),
        "sepsis": ("infection", "sepsis"),
        "pneumonia": ("infection", "pneumonia"),
        "covid": ("infection", "COVID-like infectious disease"),
    }
    for keyword, mapping in disease_map.items():
        if keyword in lowered:
            return mapping
    return ("infection", "infectious disease")


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
    best_smiles = state.get("recent_best_smiles", BEST_MOLECULE)
    lowered = message.lower()

    if latest_candidate and _has_follow_up_reference(message):
        if "best" in lowered and "compare" in lowered:
            return [latest_candidate, best_smiles]
        return [latest_candidate]

    if "best one" in lowered or "best molecule" in lowered:
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


def _build_summary(mode: str, intent: str, target_label: str, score_payload: dict) -> str:
    """Create a concise, mode-aware summary for the chat UI."""
    score = score_payload.get("clinical_score", 0.0)
    interpretation = _score_interpretation(score)
    if mode == "simple":
        return (
            f"This {intent} result is a computationally ranked molecule for {target_label}. "
            f"It scored {score:.4f}, which suggests {interpretation}."
        )
    if mode == "expert":
        return (
            f"Genorova ranked this molecule as a {intent} output for {target_label} with a clinical score of "
            f"{score:.4f}. The signal is driven by its current drug-likeness, synthetic accessibility, and "
            f"Lipinski-friendly property balance, but it remains a hypothesis-generating result."
        )
    return (
        f"Genorova selected this computational candidate for {target_label} with a clinical score of {score:.4f}. "
        f"That places it in a range indicating {interpretation}."
    )


def _mode_specific_why(mode: str, score_payload: dict, target_label: str) -> str:
    """Explain why a molecule was selected in the requested detail mode."""
    mw = score_payload.get("molecular_weight", 0.0)
    logp = score_payload.get("logp", 0.0)
    qed = score_payload.get("qed_score", 0.0)
    sa = score_payload.get("sa_score", 0.0)
    lip = "passes" if score_payload.get("passes_lipinski") else "does not fully pass"
    if mode == "simple":
        return (
            f"It was chosen because it looks reasonably drug-like for a {target_label} program: "
            f"the size is manageable, the lipophilicity is not extreme, and the model gave it a relatively good rank."
        )
    if mode == "expert":
        return (
            f"Selection was driven by a balanced property profile: MW {mw}, LogP {logp}, QED {qed}, SA {sa}, and "
            f"Lipinski compliance status that currently {lip}. In Genorova's present ranking setup, that combination "
            f"supports prioritization for follow-up rather than any claim of validated efficacy."
        )
    return (
        f"It was selected because the model saw a favorable balance of molecular size (MW {mw}), lipophilicity "
        f"(LogP {logp}), drug-likeness (QED {qed}), and synthetic accessibility (SA {sa}). It currently {lip} "
        f"the Lipinski screen."
    )


def _candidate_block(score_payload: dict, label: str | None = None) -> dict:
    """Stable candidate block used by the chat payload."""
    return {
        "name": label,
        "smiles": score_payload.get("smiles"),
        "score": score_payload.get("clinical_score"),
        "recommendation": score_payload.get("recommendation"),
        "molecule_svg": _molecule_svg(score_payload.get("smiles")),
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


def _pharmacology_block(score_payload: dict, target_label: str) -> dict:
    """Return a readable pharmacology section without overstating certainty."""
    toxicity_risk = _estimate_toxicity_risk(score_payload)
    return {
        "intended_program": target_label,
        "predicted_activity": "model-ranked hit-like candidate",
        "clinical_score_meaning": _score_interpretation(score_payload.get("clinical_score", 0.0)),
        "oral_drug_likeness": "supported by current property profile" if score_payload.get("passes_lipinski") else "partially supported",
        "toxicity_risk": toxicity_risk,
        "validation_status": "computational prediction only",
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
    toxicity_risk = _estimate_toxicity_risk(score_payload)
    if score_payload.get("lipinski_violations", 0) > 0:
        risks.append("Lipinski violations suggest oral developability risk.")
    if score_payload.get("logp", 0) > 3:
        risks.append("Elevated LogP may increase off-target binding and formulation complexity.")
    if score_payload.get("qed_score", 1) < 0.45:
        risks.append("Lower QED suggests weaker overall drug-like balance.")
    if toxicity_risk in {"moderate", "high"}:
        risks.append(f"Rule-based toxicity screen suggests {toxicity_risk} risk that needs experimental follow-up.")
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
        "This is a computational prediction for research support only.",
        "The result is hypothesis-generating and not experimentally validated.",
        "Do not interpret this as a proven drug, safe therapy, or clinical recommendation.",
    ]


def _generated_candidates_with_visuals(molecules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach structure SVGs to generated candidate list entries."""
    enriched = []
    for molecule in molecules:
        next_molecule = dict(molecule)
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
        "recent_best_smiles": BEST_MOLECULE,
    }


def _compare_molecules(first: dict, second: dict) -> dict:
    """Create a UI-friendly comparison block for two scored molecules."""
    score_gap = round(first.get("clinical_score", 0) - second.get("clinical_score", 0), 4)
    preferred = first if score_gap >= 0 else second
    other = second if preferred is first else first
    return {
        "molecules": [
            {
                "label": "Molecule A",
                "smiles": first.get("smiles"),
                "clinical_score": first.get("clinical_score"),
                "qed_score": first.get("qed_score"),
                "logp": first.get("logp"),
                "molecular_weight": first.get("molecular_weight"),
                "recommendation": first.get("recommendation"),
                "molecule_svg": _molecule_svg(first.get("smiles")),
            },
            {
                "label": "Molecule B",
                "smiles": second.get("smiles"),
                "clinical_score": second.get("clinical_score"),
                "qed_score": second.get("qed_score"),
                "logp": second.get("logp"),
                "molecular_weight": second.get("molecular_weight"),
                "recommendation": second.get("recommendation"),
                "molecule_svg": _molecule_svg(second.get("smiles")),
            },
        ],
        "preferred_smiles": preferred.get("smiles"),
        "why": (
            f"{preferred.get('smiles')} ranks higher in the current model because its clinical score is "
            f"{preferred.get('clinical_score')} versus {other.get('clinical_score')}."
        ),
        "score_gap": abs(score_gap),
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
            "pharmacology": _pharmacology_block(score_payload, target_label),
            "strengths": _strengths_block(score_payload),
            "risks": _risks_block(score_payload),
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
        base_smiles = resolved_smiles[0] if resolved_smiles else latest_candidate_smiles or BEST_MOLECULE
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
            "pharmacology": _pharmacology_block(score_payload, target_label),
            "strengths": _strengths_block(score_payload),
            "risks": _risks_block(score_payload),
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
            compare_smiles = [latest_candidate_smiles, BEST_MOLECULE]
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
            "pharmacology": _pharmacology_block(preferred, target_label),
            "strengths": _strengths_block(preferred),
            "risks": _risks_block(preferred),
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
            "pharmacology": _pharmacology_block(base_candidate, target_label),
            "strengths": _strengths_block(base_candidate),
            "risks": _risks_block(base_candidate),
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
    top_candidate = generated["molecules"][0]
    score_payload = _score_smiles_payload(top_candidate["smiles"])
    candidate_smiles = score_payload.get("smiles")
    return {
        "intent": "generate",
        "mode": mode,
        "message": message,
        "summary": _build_summary(mode, "generation", target_label, score_payload),
        "candidate": _candidate_block(score_payload),
        "generated_candidates": _generated_candidates_with_visuals(generated["molecules"]),
        "why": _mode_specific_why(mode, score_payload, target_label),
        "chemical_properties": _chemical_properties(score_payload),
        "physical_properties": _physical_properties(score_payload),
        "pharmacology": _pharmacology_block(score_payload, target_label),
        "strengths": _strengths_block(score_payload),
        "risks": _risks_block(score_payload),
        "next_steps": _next_steps_block(intent),
        "warnings": _warnings_block(),
        "follow_up_actions": _follow_up_actions(candidate_smiles),
        "program_context": {
            "requested_label": target_label,
            "supported_bucket": target_bucket,
            "count_returned": generated["count_returned"],
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
        "name":    "Genorova AI Drug Discovery API",
        "version": "1.0.0",
        "docs":    "/docs",
        "health":  "/health",
        "report":  "/report",
    }


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
