"""Resume profile (LLM 抽取出的画像) 数据访问"""
from __future__ import annotations

import json
import uuid

from .base import now_iso, transaction
from .db import get_conn


def _new_id() -> str:
    return f"rp_{uuid.uuid4().hex[:10]}"


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in ("skills", "projects"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except (json.JSONDecodeError, TypeError):
                d[k] = []
        else:
            d[k] = []
    return d


def get(profile_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM resume_profiles WHERE id = ?", (profile_id,)).fetchone()
    return _row_to_dict(row)


def list_for_resume(resume_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM resume_profiles WHERE resume_id = ? ORDER BY created_at DESC",
            (resume_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def latest_for_resume(resume_id: str) -> dict | None:
    items = list_for_resume(resume_id)
    return items[0] if items else None


def create(
    resume_id: str,
    role: str | None,
    seniority: str | None,
    domain: str | None,
    skills: list[str],
    projects: list[dict],
    raw: str = "",
) -> dict:
    pid = _new_id()
    with transaction() as conn:
        conn.execute(
            """INSERT INTO resume_profiles
               (id, resume_id, role, seniority, domain, skills, projects, raw, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pid,
                resume_id,
                role,
                seniority,
                domain,
                json.dumps(skills, ensure_ascii=False),
                json.dumps(projects, ensure_ascii=False),
                raw,
                now_iso(),
            ),
        )
    return get(pid)


def delete(profile_id: str) -> None:
    with transaction() as conn:
        conn.execute("DELETE FROM resume_profiles WHERE id = ?", (profile_id,))
