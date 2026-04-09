"""岗位 / 岗位状态 / 面试 数据访问"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import get_conn, row_to_dict, rows_to_dicts

# snapshot.json 由 scraper 产出
SNAPSHOT_PATH = Path(__file__).parents[2] / "data" / "snapshot.json"
REJECTED_PATH = Path(__file__).parents[2] / "data" / "rejected.json"

_snapshot_cache: dict[str, Any] | None = None
_rejected_cache: list[dict[str, Any]] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── snapshot (read-only) ───

def load_snapshot() -> dict[str, list[dict]]:
    """读取爬虫产出的快照（带内存缓存）"""
    global _snapshot_cache
    if _snapshot_cache is None and SNAPSHOT_PATH.exists():
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            _snapshot_cache = json.load(f)
    return _snapshot_cache or {}


def load_rejected() -> list[dict]:
    global _rejected_cache
    if _rejected_cache is None and REJECTED_PATH.exists():
        with open(REJECTED_PATH, "r", encoding="utf-8") as f:
            _rejected_cache = json.load(f)
    return _rejected_cache or []


def reload_snapshot():
    """爬虫重跑后调用，清除缓存"""
    global _snapshot_cache, _rejected_cache
    _snapshot_cache = None
    _rejected_cache = None


def list_all_jobs() -> list[dict]:
    """合并所有 tier 的岗位"""
    snap = load_snapshot()
    out = []
    for tier in ("P0", "P1", "P2", "P3"):
        for job in snap.get(tier, []):
            out.append(job)
    return out


def find_job(job_id: str) -> dict | None:
    """job_id 用 href（与前端一致）"""
    for job in list_all_jobs():
        if job.get("href") == job_id:
            return job
    for job in load_rejected():
        if job.get("href") == job_id:
            return job
    return None


# ─── job_states ───

def get_job_state(job_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM job_states WHERE job_id = ?", (job_id,)
        ).fetchone()
    return row_to_dict(row)


def list_job_states() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM job_states").fetchall()
    return rows_to_dicts(rows)


def upsert_job_state(job_id: str, patch: dict) -> dict:
    """upsert：不存在则创建，存在则 patch 标量字段

    自动联动：
    - 如果 pipeline_col 发生变化（或 _force_stage_event 显式要求），
      往 job_state_events 表追加一条事件（from_col / to_col / reason / interview_id / at）
    - 如果新 col 是 'applied' 且原 applied_at 为空，自动 stamp applied_at

    内部协议字段（以 _ 开头，不会落库）：
    - _force_stage_event: True   强制写一条 self-loop 事件
    - _history_reason: str       事件 reason
    - _history_interview_id: int 关联的 interview id
    """
    from . import job_state_events_repo

    now = _now()
    cur = get_job_state(job_id)
    force_event = patch.pop("_force_stage_event", None)
    reason = patch.pop("_history_reason", None)
    interview_id = patch.pop("_history_interview_id", None)
    if interview_id is None:
        # 兼容老 caller
        interview_id = patch.pop("_history_iv_id", None)

    if cur is None:
        initial_col = patch.get("pipeline_col", "todo")
        merged = {
            "job_id": job_id,
            "intent": patch.get("intent", "unknown"),
            "pipeline_col": initial_col,
            "outcome": patch.get("outcome"),
            "triaged_at": patch.get("triaged_at"),
            "applied_at": patch.get("applied_at") or (now if initial_col == "applied" else None),
            "last_touch_at": now,
            "notes": patch.get("notes", ""),
            "extra": json.dumps(patch.get("extra")) if patch.get("extra") else None,
        }
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO job_states
                   (job_id, intent, pipeline_col, outcome, triaged_at, applied_at, last_touch_at, notes, extra)
                   VALUES (:job_id, :intent, :pipeline_col, :outcome, :triaged_at, :applied_at, :last_touch_at, :notes, :extra)""",
                merged,
            )
        # 起始事件（如果不是 todo）
        if initial_col != "todo":
            job_state_events_repo.add(job_id, "todo", initial_col, reason or "create", interview_id)
        return get_job_state(job_id)

    # update
    new_col = patch.get("pipeline_col")
    cur_col = cur.get("pipeline_col")

    needs_event = False
    event_to = None
    if new_col and new_col != cur_col:
        needs_event = True
        event_to = new_col
    elif force_event:
        needs_event = True
        event_to = new_col or cur_col

    if needs_event:
        job_state_events_repo.add(job_id, cur_col, event_to, reason or "manual", interview_id)
        if event_to == "applied" and not cur.get("applied_at"):
            patch["applied_at"] = now

    fields = []
    params: list[Any] = []
    for k in ("intent", "pipeline_col", "outcome", "triaged_at", "applied_at", "notes"):
        if k in patch:
            fields.append(f"{k} = ?")
            params.append(patch[k])
    if "extra" in patch:
        fields.append("extra = ?")
        params.append(json.dumps(patch["extra"]) if patch["extra"] else None)

    fields.append("last_touch_at = ?")
    params.append(now)
    params.append(job_id)

    with get_conn() as conn:
        conn.execute(
            f"UPDATE job_states SET {', '.join(fields)} WHERE job_id = ?",
            params,
        )
    return get_job_state(job_id)


def delete_job_state(job_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM job_states WHERE job_id = ?", (job_id,))


# ─── interviews ───

def list_interviews(job_id: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if job_id:
            rows = conn.execute(
                "SELECT * FROM interviews WHERE job_id = ? ORDER BY time", (job_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM interviews ORDER BY time DESC"
            ).fetchall()
    return rows_to_dicts(rows)


def create_interview(job_id: str, data: dict) -> dict:
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO interviews (job_id, type, time, location, result, reflection, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                data.get("type", ""),
                data.get("time"),
                data.get("location", ""),
                data.get("result", "pending"),
                data.get("reflection", ""),
                now,
            ),
        )
        iv_id = cur.lastrowid
        row = conn.execute("SELECT * FROM interviews WHERE id = ?", (iv_id,)).fetchone()
    return row_to_dict(row)


def update_interview(interview_id: int, patch: dict) -> dict | None:
    fields = []
    params: list[Any] = []
    for k in ("type", "time", "location", "result", "reflection"):
        if k in patch:
            fields.append(f"{k} = ?")
            params.append(patch[k])
    if not fields:
        return None
    params.append(interview_id)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE interviews SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        row = conn.execute("SELECT * FROM interviews WHERE id = ?", (interview_id,)).fetchone()
    return row_to_dict(row)


def delete_interview(interview_id: int):
    """删除面试 + 回滚 job_state_events + 必要时降级 pipeline_col

    回滚规则（用真 SQL 而不是 JSON 数组操作）：
    - DELETE FROM job_state_events WHERE interview_id = ?
    - 拿剩余 events 的最后一条 to_col 作为新的 pipeline_col
    - 如果没有剩余 events → pipeline_col = 'todo'
    """
    from . import job_state_events_repo

    with get_conn() as conn:
        row = conn.execute("SELECT job_id FROM interviews WHERE id = ?", (interview_id,)).fetchone()
        if row is None:
            return
        job_id = row["job_id"]
        conn.execute("DELETE FROM interviews WHERE id = ?", (interview_id,))

    # 删关联的 events（FK ON DELETE SET NULL 不会自动删 — 我们要主动 DELETE）
    deleted = job_state_events_repo.delete_for_interview(interview_id)
    if deleted == 0:
        return

    # 重新计算 pipeline_col：剩余 events 最后一条的 to_col
    remaining = job_state_events_repo.list_for_job(job_id)
    if remaining:
        new_col = remaining[-1].to_col
    else:
        new_col = "todo"

    now = _now()
    with get_conn() as conn:
        conn.execute(
            "UPDATE job_states SET pipeline_col = ?, last_touch_at = ? WHERE job_id = ?",
            (new_col, now, job_id),
        )
