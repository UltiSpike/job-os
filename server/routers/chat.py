"""提问会话 + 消息路由"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.storage import chat_repo

session_router = APIRouter(prefix="/api/v1/chat-sessions", tags=["chat"])
message_router = APIRouter(prefix="/api/v1/chat-messages", tags=["chat"])
router = session_router  # 兼容旧 import 路径


class SessionCreate(BaseModel):
    question_id: str
    title: str = "新会话"
    variant_ref: str | None = None


class SessionPatch(BaseModel):
    title: str | None = None
    variant_ref: str | None = None


class MessageCreate(BaseModel):
    role: str    # user / assistant
    content: str


# ─── sessions ───

@session_router.get("")
def list_sessions(question_id: str):
    return {"items": chat_repo.list_sessions(question_id)}


@session_router.get("/{session_id}")
def get_session(session_id: str):
    sess = chat_repo.get_session(session_id)
    if not sess:
        raise HTTPException(404, "session not found")
    sess["messages"] = chat_repo.list_messages(session_id)
    return sess


@session_router.post("")
def create_session(body: SessionCreate):
    return chat_repo.create_session(body.question_id, body.title, body.variant_ref)


@session_router.patch("/{session_id}")
def update_session(session_id: str, body: SessionPatch):
    out = chat_repo.update_session(session_id, body.model_dump(exclude_unset=True))
    if not out:
        raise HTTPException(404, "session not found")
    return out


@session_router.delete("/{session_id}")
def delete_session(session_id: str):
    snapshot = chat_repo.delete_session(session_id)
    if not snapshot:
        raise HTTPException(404, "session not found")
    return {"ok": True, "snapshot": snapshot}


@session_router.post("/restore")
def restore_session(snapshot: dict):
    return chat_repo.restore_session(snapshot)


@session_router.get("/{session_id}/messages")
def list_messages_for_session(session_id: str):
    return {"items": chat_repo.list_messages(session_id)}


@session_router.post("/{session_id}/messages")
def add_message_to_session(session_id: str, body: MessageCreate):
    if body.role not in ("user", "assistant", "system"):
        raise HTTPException(400, "role must be user/assistant/system")
    return chat_repo.add_message(session_id, body.role, body.content)


# ─── messages (扁平 endpoint) ───

@message_router.get("")
def list_messages(session_id: str):
    return {"items": chat_repo.list_messages(session_id)}


@message_router.post("")
def add_message(body: dict):
    sid = body.get("session_id")
    role = body.get("role")
    content = body.get("content", "")
    if not sid or not role:
        raise HTTPException(400, "session_id and role required")
    if role not in ("user", "assistant", "system"):
        raise HTTPException(400, "role must be user/assistant/system")
    return chat_repo.add_message(sid, role, content)


@message_router.delete("/{message_id}")
def delete_message(message_id: int):
    snapshot = chat_repo.delete_message(message_id)
    if not snapshot:
        raise HTTPException(404, "message not found")
    return {"ok": True, "snapshot": snapshot}
