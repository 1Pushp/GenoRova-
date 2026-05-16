from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from . import chat_memory
    from .chat_logic import handle_chat_message
except ImportError:
    import chat_memory
    from chat_logic import handle_chat_message

from genorova.src import api as core_api
from genorova.src import auth_store
from genorova.api.main import metrics as cvae_metrics


LOGGER = logging.getLogger("genorova.backend")
app = core_api.app
DIST = Path(__file__).parent.parent / "frontend" / "dist"


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class NewConversationRequest(BaseModel):
    title: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


def _route_exists(path: str, method: str) -> bool:
    target_method = method.upper()
    for route in app.router.routes:
        if getattr(route, "path", None) != path:
            continue
        methods = getattr(route, "methods", set()) or set()
        if target_method in methods:
            return True
    return False


def _wrap_core_lifespan() -> None:
    if getattr(app.state, "canonical_backend_lifespan_wrapped", False):
        return

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def canonical_lifespan(inner_app: FastAPI):
        async with original_lifespan(inner_app):
            try:
                chat_memory.init_db()
            except Exception:
                LOGGER.exception("Chat storage initialization failed during startup.")
            yield

    app.router.lifespan_context = canonical_lifespan
    app.state.canonical_backend_lifespan_wrapped = True


def _register_route(path: str, method: str, endpoint, **kwargs: Any) -> None:
    if _route_exists(path, method):
        return
    app.add_api_route(path, endpoint, methods=[method], **kwargs)
    catch_all_index = next(
        (index for index, route in enumerate(app.router.routes) if getattr(route, "path", None) == "/{full_path:path}"),
        None,
    )
    route_index = next(
        (
            index
            for index, route in enumerate(app.router.routes)
            if getattr(route, "path", None) == path and method.upper() in (getattr(route, "methods", set()) or set())
        ),
        None,
    )
    if catch_all_index is not None and route_index is not None and route_index > catch_all_index:
        route = app.router.routes.pop(route_index)
        app.router.routes.insert(catch_all_index, route)


def _mount_exists(path: str) -> bool:
    for route in app.router.routes:
        if getattr(route, "path", None) == path:
            return True
    return False


def _frontend_index_response() -> FileResponse | dict[str, str]:
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"error": "Frontend not built"}


async def serve_root(request: Request):
    if request.method == "HEAD":
        return Response(status_code=200)
    return _frontend_index_response()


async def serve_spa(request: Request, full_path: str):
    if request.method == "HEAD":
        return Response(status_code=200)
    return _frontend_index_response()


async def docs_redirect():
    return RedirectResponse(url="/api-docs")


def _register_frontend_serving() -> None:
    assets_dir = DIST / "assets"
    if assets_dir.exists() and not _mount_exists("/assets"):
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    _register_route("/", "GET", serve_root, include_in_schema=False)
    _register_route("/", "HEAD", serve_root, include_in_schema=False)
    _register_route("/{full_path:path}", "GET", serve_spa, include_in_schema=False)
    _register_route("/{full_path:path}", "HEAD", serve_spa, include_in_schema=False)


def _optional_user_id(request: Request) -> str | None:
    session_id = request.cookies.get(core_api.AUTH_COOKIE_NAME, "").strip()
    if not session_id:
        return None
    try:
        user = auth_store.get_user_for_session(core_api.AUTH_DB_PATH, session_id=session_id)
        return user["id"] if user else None
    except Exception:
        return None


def chat_storage() -> dict[str, Any]:
    return {"chat_storage": chat_memory.get_storage_status()}


def chat(req: ChatRequest, request: Request) -> dict[str, Any]:
    user_id = _optional_user_id(request)
    return handle_chat_message(req.message, req.conversation_id, user_id=user_id)


def list_conversations(request: Request) -> dict[str, Any]:
    user_id = _optional_user_id(request)
    return {"conversations": chat_memory.list_conversations(user_id=user_id)}


def create_conversation(request: Request, req: NewConversationRequest | None = None) -> dict[str, Any]:
    request_payload = req or NewConversationRequest()
    user_id = _optional_user_id(request)
    conversation = chat_memory.create_conversation(
        title=request_payload.title,
        metadata=request_payload.metadata,
        user_id=user_id,
    )
    return {"conversation": conversation}


def get_conversation(conversation_id: str) -> dict[str, Any]:
    conversation = chat_memory.get_conversation_with_messages(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


_wrap_core_lifespan()
_register_frontend_serving()
_register_route("/docs", "GET", docs_redirect, include_in_schema=False)
_register_route("/metrics", "GET", cvae_metrics, tags=["System"], summary="Benchmark results and novelty stats")
_register_route("/chat/storage", "GET", chat_storage, summary="Inspect chat storage mode")
_register_route("/chat", "POST", chat, summary="Chat with Genorova")
_register_route("/conversations", "GET", list_conversations, summary="List stored conversations")
_register_route("/conversations/new", "POST", create_conversation, summary="Create a new conversation")
_register_route(
    "/conversations/{conversation_id}",
    "GET",
    get_conversation,
    summary="Load a stored conversation with messages",
)


@app.on_event("startup")
async def _eager_model_load():
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        print("[STARTUP] Pre-loading CVAE model...")
        from genorova.api.main import _get_model
        await loop.run_in_executor(None, _get_model)
        print("[STARTUP] CVAE model ready")
    except Exception as e:
        print(f"[STARTUP] Model pre-load warning: {e}")


@app.get("/ready")
def ready():
    try:
        from genorova.api.main import _model
        return {
            "ready": _model is not None,
            "status": "model loaded" if _model is not None else "model not yet loaded",
        }
    except Exception as e:
        return {"ready": False, "error": str(e)}


def _prefer_backend_ready_route() -> None:
    backend_ready_index = next(
        (
            index
            for index, route in enumerate(app.router.routes)
            if getattr(route, "path", None) == "/ready"
            and getattr(getattr(route, "endpoint", None), "__module__", "") == __name__
        ),
        None,
    )
    first_ready_index = next(
        (
            index
            for index, route in enumerate(app.router.routes)
            if getattr(route, "path", None) == "/ready"
        ),
        None,
    )
    if (
        backend_ready_index is not None
        and first_ready_index is not None
        and backend_ready_index > first_ready_index
    ):
        route = app.router.routes.pop(backend_ready_index)
        app.router.routes.insert(first_ready_index, route)


_prefer_backend_ready_route()
