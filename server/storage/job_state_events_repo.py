"""job_state 状态变化事件流 — 取代 stage_history JSON"""
from __future__ import annotations

from pydantic import BaseModel

from .base import hydrate_row, hydrate_rows, now_iso, transaction
from .db import get_conn


class JobStateEvent(BaseModel):
    id: int
    job_id: str
    from_col: str | None = None
    to_col: str
    reason: str | None = None
    interview_id: int | None = None
    at: str


def list_for_job(job_id: str) -> list[JobStateEvent]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM job_state_events WHERE job_id = ? ORDER BY at ASC, id ASC",
            (job_id,),
        ).fetchall()
    return hydrate_rows(rows, JobStateEvent)


def list_recent(days: int = 7) -> list[JobStateEvent]:
    """跨所有 job 取最近 N 天的 events"""
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM job_state_events WHERE at >= ? ORDER BY at DESC",
            (cutoff,),
        ).fetchall()
    return hydrate_rows(rows, JobStateEvent)


def add(job_id: str, from_col: str | None, to_col: str, reason: str | None = None, interview_id: int | None = None) -> JobStateEvent:
    with transaction() as conn:
        cur = conn.execute(
            "INSERT INTO job_state_events (job_id, from_col, to_col, reason, interview_id, at) VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, from_col, to_col, reason, interview_id, now_iso()),
        )
        eid = cur.lastrowid
        row = conn.execute("SELECT * FROM job_state_events WHERE id = ?", (eid,)).fetchone()
    return hydrate_row(row, JobStateEvent)


def delete_for_interview(interview_id: int) -> int:
    """删某个 interview 触发的所有 events（作为 interview delete 的级联清理）"""
    with transaction() as conn:
        cur = conn.execute("DELETE FROM job_state_events WHERE interview_id = ?", (interview_id,))
        return cur.rowcount


def clear_for_job(job_id: str):
    """清空某个 job 的所有 events（用于退回 Discover）"""
    with transaction() as conn:
        conn.execute("DELETE FROM job_state_events WHERE job_id = ?", (job_id,))
