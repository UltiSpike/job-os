"""Job state 变化事件路由"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.storage import job_state_events_repo

router = APIRouter(prefix="/api/v1/job-state-events", tags=["job-state-events"])


@router.get("")
def list_events(job_id: str | None = None, days: int | None = None, limit: int = 0):
    if job_id:
        items = job_state_events_repo.list_for_job(job_id)
    elif days:
        items = job_state_events_repo.list_recent(days=days)
    else:
        items = job_state_events_repo.list_recent(days=30)
    if limit:
        items = items[:limit]
    return {"items": [e.model_dump() for e in items], "total": len(items)}
