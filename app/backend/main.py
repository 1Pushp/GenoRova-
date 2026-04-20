from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

try:
    from . import chat_memory
    from .chat_logic import handle_chat_message
except ImportError:
    import chat_memory
    from chat_logic import handle_chat_message

from genorova.src import api as core_api


LOGGER = logging.getLogger("genorova.backend")
app = core_api.app


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


def chat_storage() -> dict[str, Any]:
    return {"chat_storage": chat_memory.get_storage_status()}


def chat(req: ChatRequest) -> dict[str, Any]:
    return handle_chat_message(req.message, req.conversation_id)


def list_conversations() -> dict[str, Any]:
    return {"conversations": chat_memory.list_conversations()}


def create_conversation(req: NewConversationRequest | None = None) -> dict[str, Any]:
    request_payload = req or NewConversationRequest()
    conversation = chat_memory.create_conversation(
        title=request_payload.title,
        metadata=request_payload.metadata,
    )
    return {"conversation": conversation}


def get_conversation(conversation_id: str) -> dict[str, Any]:
    conversation = chat_memory.get_conversation_with_messages(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


_wrap_core_lifespan()
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
