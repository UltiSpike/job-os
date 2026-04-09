"""岗位 + 状态 + 面试 路由"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.storage import jobs_repo, jobs_table_repo

router = APIRouter(prefix="/api/v1", tags=["jobs"])


class JobStatePatch(BaseModel):
    """注意：stage_history 不接受 — 状态变化通过 pipeline_col 字段隐式触发，
    或调用 :reset 端点清空所有 events。"""
    intent: str | None = None
    pipeline_col: str | None = None
    outcome: str | None = None
    triaged_at: str | None = None
    applied_at: str | None = None
    notes: str | None = None
    extra: dict | None = None




# ─── jobs (从 jobs 表读) ───

@router.get("/jobs")
def list_jobs(tier: str | None = None, q: str | None = None, limit: int = 0, offset: int = 0):
    if q:
        items = [j.model_dump() for j in jobs_table_repo.search(q, limit=limit or 100)]
    else:
        items = [j.model_dump() for j in jobs_table_repo.list_all(tier=tier, limit=limit, offset=offset)]
    return {
        "items": items,
        "total": jobs_table_repo.total() if not tier else len(items),
        "by_tier": jobs_table_repo.count_by_tier(),
    }


@router.get("/jobs/{job_id:path}")
def get_job(job_id: str):
    job = jobs_table_repo.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job.model_dump()


@router.post("/jobs/reload")
def reload_jobs():
    """从 snapshot.json 重新导入到 jobs 表（会覆盖现有）"""
    from server.storage.db import _migrate_jobs_from_snapshot
    # 强制重新迁移：先 truncate
    from server.storage.db import get_conn
    with get_conn() as conn:
        conn.execute("DELETE FROM jobs")
    _migrate_jobs_from_snapshot()
    return {"ok": True, "total": jobs_table_repo.total()}


# ─── job_state ───

@router.get("/job-states")
def list_states():
    return {"items": jobs_repo.list_job_states()}


@router.get("/job-states/{job_id:path}")
def get_state(job_id: str):
    state = jobs_repo.get_job_state(job_id)
    if state is None:
        # 默认 state（未操作过的岗位）
        return {
            "job_id": job_id,
            "intent": "unknown",
            "pipeline_col": "todo",
            "outcome": None,
        }
    return state


@router.patch("/job-states/{job_id:path}")
def patch_state(job_id: str, patch: JobStatePatch):
    data = patch.model_dump(exclude_unset=True)
    return jobs_repo.upsert_job_state(job_id, data)


@router.post("/job-states/{job_id:path}:reset")
def reset_state(job_id: str):
    """退回 Discover：清空 events + intent=unknown + pipeline_col=todo"""
    from server.storage import job_state_events_repo
    job_state_events_repo.clear_for_job(job_id)
    return jobs_repo.upsert_job_state(job_id, {
        "intent": "unknown",
        "pipeline_col": "todo",
        "applied_at": None,
        "triaged_at": None,
    })


@router.delete("/job-states/{job_id:path}")
def delete_state(job_id: str):
    jobs_repo.delete_job_state(job_id)
    return {"ok": True}


# interviews 已经移到独立 router /api/v1/interviews
