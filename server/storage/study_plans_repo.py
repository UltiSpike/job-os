"""Study plan snapshot"""
from __future__ import annotations

import json
import uuid

from .base import now_iso, transaction
from .db import get_conn


def _new_id() -> str:
    return f"sp_{uuid.uuid4().hex[:10]}"


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in ("target_job_hrefs",):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except (json.JSONDecodeError, TypeError):
                d[k] = []
        else:
            d[k] = []
    if d.get("module_priorities"):
        try:
            d["module_priorities"] = json.loads(d["module_priorities"])
        except (json.JSONDecodeError, TypeError):
            d["module_priorities"] = {}
    else:
        d["module_priorities"] = {}
    return d


def get(plan_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM study_plans WHERE id = ?", (plan_id,)).fetchone()
    return _row_to_dict(row)


def list_for_profile(resume_profile_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM study_plans WHERE resume_profile_id = ? ORDER BY created_at DESC",
            (resume_profile_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def latest_for_profile(resume_profile_id: str) -> dict | None:
    items = list_for_profile(resume_profile_id)
    return items[0] if items else None


def create(
    resume_profile_id: str,
    target_job_hrefs: list[str],
    module_priorities: dict[str, float],
    rationale: str = "",
) -> dict:
    pid = _new_id()
    with transaction() as conn:
        conn.execute(
            """INSERT INTO study_plans
               (id, resume_profile_id, target_job_hrefs, module_priorities, rationale, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                pid,
                resume_profile_id,
                json.dumps(target_job_hrefs, ensure_ascii=False),
                json.dumps(module_priorities, ensure_ascii=False),
                rationale,
                now_iso(),
            ),
        )
    return get(pid)
