"""User profile — singleton 主语对象

设计：
- 永远只有一行 (id=1)，CHECK 约束保证
- 是 app 里所有'我'相关 API (/me) 的真相源
- target_vector_cache 是计算缓存，重算时刷新
"""
from __future__ import annotations

import json

from .base import now_iso, transaction
from .db import get_conn


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in ("active_target_job_hrefs", "target_vector_cache"):
        v = d.get(k)
        if v:
            try:
                d[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                d[k] = [] if k.endswith("hrefs") else {}
        else:
            d[k] = [] if k.endswith("hrefs") else {}
    return d


def get() -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
    if row is None:
        # 兜底：如果初始化没建出来，建一行
        with transaction() as conn:
            now = now_iso()
            conn.execute(
                """INSERT OR IGNORE INTO user_profile
                   (id, display_name, bio, active_target_job_hrefs, target_vector_cache, created_at, updated_at)
                   VALUES (1, '', '', '[]', '{}', ?, ?)""",
                (now, now),
            )
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
    return _row_to_dict(row)


_PATCH_FIELDS = ("display_name", "current_role", "target_role", "target_seniority", "bio", "active_resume_id")


def patch(updates: dict) -> dict:
    fields, params = [], []
    for k in _PATCH_FIELDS:
        if k in updates:
            fields.append(f"{k} = ?")
            params.append(updates[k])
    if "active_target_job_hrefs" in updates:
        fields.append("active_target_job_hrefs = ?")
        params.append(json.dumps(updates["active_target_job_hrefs"], ensure_ascii=False))
    if not fields:
        return get()
    fields.append("updated_at = ?")
    params.append(now_iso())
    with transaction() as conn:
        conn.execute(f"UPDATE user_profile SET {', '.join(fields)} WHERE id = 1", params)
    return get()


def set_target_vector_cache(vec: dict) -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE user_profile SET target_vector_cache = ?, target_vector_synced_at = ?, updated_at = ? WHERE id = 1",
            (json.dumps(vec, ensure_ascii=False), now_iso(), now_iso()),
        )
