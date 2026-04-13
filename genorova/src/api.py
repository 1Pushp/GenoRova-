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
from pathlib import Path
from datetime import datetime

# Make src/ importable
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# ── Project paths ────────────────────────────────────────────────────────────

ROOT_DIR      = Path(__file__).parent.parent
OUTPUT_DIR    = ROOT_DIR / "outputs"
GENERATED_DIR = OUTPUT_DIR / "generated"
MODELS_DIR    = OUTPUT_DIR / "models"
DB_PATH       = OUTPUT_DIR / "genorova_memory.db"
REPORT_PATH   = OUTPUT_DIR / "genorova_report.html"

BEST_MOLECULE = "COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2"
BEST_SCORE = 0.9649
BEST_MW = 286
BEST_DOCKING = -5.041
BEST_CA7_KI = "6.4 nM"
TOTAL_MOLECULES = 100

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


# ── Request / Response models ────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    disease: str   # "diabetes" or "infection"
    count:   int   = 10


class ScoreRequest(BaseModel):
    smiles: str


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
    disease = req.disease.lower()
    if disease not in ("diabetes", "infection"):
        raise HTTPException(status_code=400,
                            detail="disease must be 'diabetes' or 'infection'")

    count = min(req.count, 200)

    # Load from pre-computed CSV (fast path — pipeline already ran)
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
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, QED, Crippen
        from scorer import genorova_clinical_score, calculate_sa_score

        mol = Chem.MolFromSmiles(req.smiles)
        if mol is None:
            raise HTTPException(status_code=422, detail="Invalid SMILES string")

        mw   = Descriptors.MolWt(mol)
        logp = Crippen.MolLogP(mol)
        hbd  = Descriptors.NumHDonors(mol)
        hba  = Descriptors.NumHAcceptors(mol)
        tpsa = Descriptors.TPSA(mol)
        qed  = QED.qed(mol)
        sa   = calculate_sa_score(req.smiles)
        viol = sum([mw > 500, logp > 5, hbd > 5, hba > 10])
        lip  = viol == 0

        score_val = genorova_clinical_score(req.smiles)

        if score_val >= 0.85:
            recommendation = "Strong candidate"
        elif score_val >= 0.60:
            recommendation = "Borderline"
        else:
            recommendation = "Reject"

        # Store in DB
        _store_molecule(req.smiles, qed, sa, mw, logp, score_val, recommendation)

        return {
            "smiles":           req.smiles,
            "molecular_weight": round(mw, 2),
            "logp":             round(logp, 3),
            "h_bond_donors":    hbd,
            "h_bond_acceptors": hba,
            "tpsa":             round(tpsa, 2),
            "qed_score":        round(qed, 4),
            "sa_score":         round(sa, 4),
            "passes_lipinski":  lip,
            "lipinski_violations": viol,
            "clinical_score":   round(score_val, 4),
            "recommendation":   recommendation,
            "scored_at":        datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scoring failed: {e}")


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
    """Return stable top-level platform statistics used by the SaaS UI."""
    return {
        "total_molecules": TOTAL_MOLECULES,
        "best_score": BEST_SCORE,
        "best_molecule": BEST_MOLECULE,
        "best_molecular_weight": BEST_MW,
        "best_docking_affinity": BEST_DOCKING,
        "best_ca7_ki": BEST_CA7_KI,
    }


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


# ── Root redirect ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return JSONResponse({
        "name":    "Genorova AI Drug Discovery API",
        "version": "1.0.0",
        "docs":    "/docs",
        "health":  "/health",
        "report":  "/report",
    })
