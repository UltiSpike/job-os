"""Job profile (LLM 抽取的 JD 需求)"""
from __future__ import annotations

import json

from .base import now_iso, transaction
from .db import get_conn


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in ("required_skills", "nice_to_have", "scenarios"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except (json.JSONDecodeError, TypeError):
                d[k] = []
        else:
            d[k] = []
    return d


def get(job_href: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM job_profiles WHERE job_href = ?", (job_href,)).fetchone()
    return _row_to_dict(row)


def list_for_hrefs(hrefs: list[str]) -> list[dict]:
    if not hrefs:
        return []
    placeholders = ",".join("?" * len(hrefs))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM job_profiles WHERE job_href IN ({placeholders})",
            hrefs,
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def upsert(
    job_href: str,
    required_skills: list[str],
    nice_to_have: list[str],
    scenarios: list[str],
    raw: str = "",
) -> dict:
    with transaction() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO job_profiles
               (job_href, required_skills, nice_to_have, scenarios, raw, extracted_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                job_href,
                json.dumps(required_skills, ensure_ascii=False),
                json.dumps(nice_to_have, ensure_ascii=False),
                json.dumps(scenarios, ensure_ascii=False),
                raw,
                now_iso(),
            ),
        )
    return get(job_href)
