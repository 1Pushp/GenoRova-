from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import chat_memory
import main_legacy_api
from chat_logic import handle_chat_message


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class NewConversationRequest(BaseModel):
    title: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


BEST_MOLECULE = "COc1cc2c(cc1OC)C(C)N(S(N)(=O)=O)CC2"
BEST_SCORE = 0.9649
BEST_MW = 286
BEST_DOCKING = -5.041
BEST_CA7_KI = "6.4 nM"
TOTAL_MOLECULES = 100


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


@app.get("/api/stats")
def api_stats():
    return {
        "total_molecules": TOTAL_MOLECULES,
        "best_score": BEST_SCORE,
        "best_molecule": BEST_MOLECULE,
        "best_molecular_weight": BEST_MW,
        "best_docking_affinity": BEST_DOCKING,
        "best_ca7_ki": BEST_CA7_KI,
    }


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
