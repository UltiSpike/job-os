"""简历版本数据访问"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .db import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"r_{uuid.uuid4().hex[:10]}"


def list_resumes() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, content, is_default, created_at, updated_at FROM resumes ORDER BY is_default DESC, updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_resume(rid: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM resumes WHERE id = ?", (rid,)).fetchone()
    return dict(row) if row else None


def create_resume(name: str, content: str = "", is_default: bool = False) -> dict:
    rid = _new_id()
    now = _now()
    with get_conn() as conn:
        if is_default:
            conn.execute("UPDATE resumes SET is_default = 0")
        conn.execute(
            "INSERT INTO resumes (id, name, content, is_default, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (rid, name, content, 1 if is_default else 0, now, now),
        )
    return get_resume(rid)


def update_resume(rid: str, patch: dict) -> dict | None:
    fields = []
    params = []
    for k in ("name", "content"):
        if k in patch:
            fields.append(f"{k} = ?")
            params.append(patch[k])
    if "is_default" in patch:
        with get_conn() as conn:
            if patch["is_default"]:
                conn.execute("UPDATE resumes SET is_default = 0")
        fields.append("is_default = ?")
        params.append(1 if patch["is_default"] else 0)
    if not fields:
        return get_resume(rid)
    fields.append("updated_at = ?")
    params.append(_now())
    params.append(rid)
    with get_conn() as conn:
        conn.execute(f"UPDATE resumes SET {', '.join(fields)} WHERE id = ?", params)
    return get_resume(rid)


def delete_resume(rid: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM resumes WHERE id = ?", (rid,))
