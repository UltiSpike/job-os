"""提问会话 + 消息 数据访问 — 独立 schema 替代 questions.chat_sessions JSON"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .db import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_session_id() -> str:
    return f"s_{uuid.uuid4().hex[:12]}"


# ─── sessions ───

def list_sessions(question_id: str) -> list[dict]:
    """列某题的所有 sessions（按 updated_at 倒序），每个带 messages 数量"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT s.id, s.question_id, s.title, s.variant_ref, s.created_at, s.updated_at,
                      (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS msg_count
               FROM chat_sessions s
               WHERE s.question_id = ?
               ORDER BY s.updated_at DESC""",
            (question_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_session(session_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def create_session(question_id: str, title: str = "新会话", variant_ref: str | None = None) -> dict:
    sid = _new_session_id()
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO chat_sessions (id, question_id, title, variant_ref, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (sid, question_id, title or "新会话", variant_ref, now, now),
        )
    return get_session(sid)


def update_session(session_id: str, patch: dict) -> dict | None:
    fields = []
    params: list[Any] = []
    for k in ("title", "variant_ref"):
        if k in patch:
            fields.append(f"{k} = ?")
            params.append(patch[k])
    if not fields:
        return get_session(session_id)
    fields.append("updated_at = ?")
    params.append(_now())
    params.append(session_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE chat_sessions SET {', '.join(fields)} WHERE id = ?", params)
    return get_session(session_id)


def touch_session(session_id: str):
    """更新 updated_at — 在新增/删除消息后调"""
    with get_conn() as conn:
        conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (_now(), session_id))


def delete_session(session_id: str) -> dict | None:
    """删 session（messages 通过 FK CASCADE 自动删）。返回快照用于撤销"""
    sess = get_session(session_id)
    if sess is None:
        return None
    msgs = list_messages(session_id)
    with get_conn() as conn:
        conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    sess["messages"] = msgs
    return sess


def restore_session(snapshot: dict) -> dict:
    """从快照还原 session + messages（用于 undo delete）"""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO chat_sessions (id, question_id, title, variant_ref, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                snapshot["id"],
                snapshot["question_id"],
                snapshot.get("title", "未命名"),
                snapshot.get("variant_ref"),
                snapshot.get("created_at", _now()),
                snapshot.get("updated_at", _now()),
            ),
        )
        for m in snapshot.get("messages", []):
            conn.execute(
                "INSERT INTO chat_messages (session_id, role, content, at) VALUES (?, ?, ?, ?)",
                (snapshot["id"], m["role"], m["content"], m["at"]),
            )
    return get_session(snapshot["id"])


# ─── messages ───

def list_messages(session_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_message(session_id: str, role: str, content: str) -> dict:
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO chat_messages (session_id, role, content, at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, now),
        )
        msg_id = cur.lastrowid
        # touch session
        conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (msg_id,)).fetchone()
    return dict(row)


def get_message(message_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
    return dict(row) if row else None


def delete_message(message_id: int) -> dict | None:
    """删一条消息 + touch session。返回快照用于撤销"""
    msg = get_message(message_id)
    if msg is None:
        return None
    with get_conn() as conn:
        conn.execute("DELETE FROM chat_messages WHERE id = ?", (message_id,))
        conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (_now(), msg["session_id"]))
    return msg


def restore_message(snapshot: dict) -> dict:
    """重建消息（注意：自增 id 会变；前端需要用新 id）"""
    return add_message(snapshot["session_id"], snapshot["role"], snapshot["content"])
