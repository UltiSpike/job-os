"""面试路由 — 扁平资源，不再嵌套在 /jobs"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.storage import jobs_repo

router = APIRouter(prefix="/api/v1/interviews", tags=["interviews"])


class InterviewCreate(BaseModel):
    job_id: str
    type: str
    time: str | None = None
    location: str | None = ""
    result: str | None = "pending"
    reflection: str | None = ""


class InterviewPatch(BaseModel):
    type: str | None = None
    time: str | None = None
    location: str | None = None
    result: str | None = None
    reflection: str | None = None


@router.get("")
def list_interviews(job_id: str | None = None, result: str | None = None):
    items = jobs_repo.list_interviews(job_id)
    if result:
        items = [i for i in items if i.get("result") == result]
    return {"items": items, "total": len(items)}


@router.get("/{interview_id}")
def get_interview(interview_id: int):
    items = jobs_repo.list_interviews()
    for it in items:
        if it["id"] == interview_id:
            return it
    raise HTTPException(404, "interview not found")


@router.post("")
def create_interview(body: InterviewCreate):
    """创建面试 — 自动联动 stage（在 jobs.py 里 share 同一个逻辑，先在这里调）"""
    from server.storage import job_state_events_repo

    iv_data = body.model_dump(exclude={"job_id"})
    result = jobs_repo.create_interview(body.job_id, iv_data)
    iv_id = result["id"]

    state = jobs_repo.get_job_state(body.job_id)
    advanced_from = None
    if state is None:
        jobs_repo.upsert_job_state(body.job_id, {
            "intent": "target",
            "pipeline_col": "interviewing",
            "_history_interview_id": iv_id,
        })
        advanced_from = "todo"
    else:
        cur_col = state.get("pipeline_col")
        if cur_col in ("todo", "applied", "contacting"):
            jobs_repo.upsert_job_state(body.job_id, {
                "pipeline_col": "interviewing",
                "_history_interview_id": iv_id,
            })
            advanced_from = cur_col
        elif cur_col == "interviewing":
            jobs_repo.upsert_job_state(body.job_id, {
                "_force_stage_event": True,
                "_history_interview_id": iv_id,
            })

    if advanced_from:
        result["_auto_advanced_from"] = advanced_from
    return result


@router.patch("/{interview_id}")
def patch_interview(interview_id: int, body: InterviewPatch):
    out = jobs_repo.update_interview(interview_id, body.model_dump(exclude_unset=True))
    if out is None:
        raise HTTPException(404, "interview not found")
    return out


@router.delete("/{interview_id}")
def delete_interview(interview_id: int):
    jobs_repo.delete_interview(interview_id)
    return {"ok": True}
