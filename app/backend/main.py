import csv
import sqlite3
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import chat_memory
import main_legacy_api
from chat_logic import handle_chat_message

# ── Paths to genorova data (written by genorova/src/api.py) ──────────────────
_ROOT_DIR       = Path(__file__).resolve().parents[2]
_GENOROVA_DB    = _ROOT_DIR / "genorova" / "outputs" / "genorova_memory.db"
_GENERATED_DIR  = _ROOT_DIR / "genorova" / "outputs" / "generated"


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class NewConversationRequest(BaseModel):
    title: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


app = FastAPI(
    title="Genorova SaaS MVP API",
    description="ChatGPT-style product shell for the Genorova drug discovery backend.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    chat_memory.init_db()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):  # noqa: ANN001
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "name": "Genorova SaaS MVP",
        "frontend": "http://localhost:5173",
        "health": "/health",
        "chat": "/chat",
        "conversations": "/conversations",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return main_legacy_api.health()


@app.post("/generate")
def generate(req: main_legacy_api.GenerateRequest):
    return main_legacy_api.generate(req)


@app.post("/api/generate")
def api_generate(req: main_legacy_api.GenerateRequest):
    return main_legacy_api.generate(req)


@app.post("/score")
def score(req: main_legacy_api.ScoreRequest):
    return main_legacy_api.score(req)


@app.post("/api/score")
def api_score(req: main_legacy_api.ScoreRequest):
    return main_legacy_api.score(req)


@app.get("/best_molecules")
def best_molecules(n: int = 10):
    return main_legacy_api.best_molecules(n=n)


@app.get("/api/best")
def api_best():
    return main_legacy_api.best_molecules(n=5)


def _live_stats() -> dict[str, Any]:
    """
    Compute platform statistics from the genorova molecule database and CSV
    outputs.  Returns an honest empty-state dict when no molecules exist yet
    rather than fabricated placeholder values.
    """
    total = 0
    best_score: float | None = None
    best_molecule: str | None = None
    best_mw: float | None = None
    avg_qed: float | None = None
    avg_sa: float | None = None
    data_source = "none"

    # ── Primary: SQLite database written by genorova/src/api.py ──────────────
    if _GENOROVA_DB.exists():
        try:
            conn = sqlite3.connect(str(_GENOROVA_DB))
            conn.row_factory = sqlite3.Row

            row = conn.execute("SELECT COUNT(*) AS cnt FROM molecules").fetchone()
            total = row["cnt"] if row else 0

            top = conn.execute(
                "SELECT smiles, clinical_score, molecular_weight "
                "FROM molecules ORDER BY clinical_score DESC LIMIT 1"
            ).fetchone()
            if top:
                best_molecule = top["smiles"]
                best_score    = round(float(top["clinical_score"] or 0), 4)
                try:
                    best_mw = round(float(top["molecular_weight"] or 0), 2)
                except (TypeError, ValueError):
                    best_mw = None

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
    if total == 0 and _GENERATED_DIR.exists():
        all_rows: list[dict] = []
        for csv_path in _GENERATED_DIR.glob("*.csv"):
            try:
                with open(csv_path, encoding="utf-8") as f:
                    all_rows.extend(csv.DictReader(f))
            except Exception:
                pass
        total = len(all_rows)
        if all_rows:
            data_source = "csv"
            all_rows.sort(
                key=lambda r: float(r.get("clinical_score") or 0), reverse=True
            )
            top_row = all_rows[0]
            best_molecule = top_row.get("smiles")
            try:
                best_score = round(float(top_row.get("clinical_score") or 0), 4)
            except (TypeError, ValueError):
                best_score = None
            try:
                best_mw = round(float(top_row.get("molecular_weight") or 0), 2)
            except (TypeError, ValueError):
                best_mw = None

    if total == 0:
        return {
            "total_molecules":       0,
            "best_score":            None,
            "best_molecule":         None,
            "best_molecular_weight": None,
            "avg_qed_score":         None,
            "avg_sa_score":          None,
            "data_source":           "none",
            "message": (
                "No molecules generated yet. "
                "Run the Genorova pipeline first."
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


@app.get("/api/stats")
def api_stats():
    return _live_stats()


@app.get("/report")
def report():
    return main_legacy_api.report()


@app.post("/chat")
def chat(req: ChatRequest):
    return handle_chat_message(req.message, req.conversation_id)


@app.get("/conversations")
def list_conversations():
    return {"conversations": chat_memory.list_conversations()}


@app.post("/conversations/new")
def create_conversation(req: NewConversationRequest | None = None):
    request_payload = req or NewConversationRequest()
    conversation = chat_memory.create_conversation(
        title=request_payload.title,
        metadata=request_payload.metadata,
    )
    return {"conversation": conversation}


@app.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    conversation = chat_memory.get_conversation_with_messages(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation
