"""从 localStorage 一次性迁移用户数据"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from server.redact import redact_secrets
from server.storage import db, jobs_repo, questions_repo, settings_repo

router = APIRouter(prefix="/api/v1/migrate", tags=["migration"])


class MigrationPayload(BaseModel):
    stores: dict[str, Any]


# 旧 status enum → 新 (intent, pipeline_col, outcome) 三元组
STATUS_MAP = {
    "未投递":      ("unknown",  "todo",          None),
    "已投递":      ("target",   "applied",       None),
    "简历筛中":    ("target",   "contacting",    None),
    "笔试中":      ("target",   "contacting",    None),
    "面试中":      ("target",   "interviewing",  None),
    "HR终面":      ("target",   "interviewing",  None),
    "谈薪中":      ("target",   "offer",         None),
    "已收到Offer": ("target",   "offer",         None),
    "已接受":      ("target",   "closed",        "accepted"),
    "已拒绝Offer": ("target",   "closed",        "rejected_by_me"),
    "我放弃":      ("target",   "closed",        "rejected_by_me"),
    "简历挂":      ("target",   "closed",        "rejected_by_them"),
    "笔试挂":      ("target",   "closed",        "rejected_by_them"),
    "面试挂":      ("target",   "closed",        "rejected_by_them"),
}


@router.post("/from-localstorage")
def from_localstorage(payload: MigrationPayload):
    stores = payload.stores
    counts = {"job_states": 0, "interviews": 0, "questions": 0, "settings": 0}

    # 1. job_tracker_v2/v3 → job_states + interviews
    job_store = stores.get("job_tracker_v3") or stores.get("job_tracker_v2") or {}
    for jid, st in job_store.items():
        # 兼容 v3 schema（已正交化）
        intent = st.get("intent")
        pipeline_col = st.get("pipelineCol")
        outcome = st.get("outcome")

        # 兼容 v2 schema（status enum）
        if not intent and st.get("status"):
            intent, pipeline_col, outcome = STATUS_MAP.get(
                st["status"], ("unknown", "todo", None)
            )

        jobs_repo.upsert_job_state(jid, {
            "intent": intent or "unknown",
            "pipeline_col": pipeline_col or "todo",
            "outcome": outcome,
            "applied_at": st.get("appliedAt"),
            "triaged_at": st.get("triagedAt"),
            "notes": st.get("notes", ""),
        })
        counts["job_states"] += 1

        # 面试
        for iv in (st.get("interviews") or []):
            jobs_repo.create_interview(jid, {
                "type": iv.get("type", ""),
                "time": iv.get("time"),
                "location": iv.get("location", ""),
                "result": iv.get("result", "pending"),
                "reflection": iv.get("reflection", ""),
            })
            counts["interviews"] += 1

    # 2. training_v1 → questions
    training_store = stores.get("training_v1") or {}
    for q in training_store.get("questions", []):
        try:
            questions_repo.create_question({
                "id": q.get("id"),
                "text": q.get("text") or q.get("q") or "",
                "topics": q.get("topics", []),
                "rating": q.get("rating"),
                "review_note": q.get("reviewNote", ""),
                "source": q.get("source", "manual"),
                "parent_id": q.get("parentId"),
                "review_count": q.get("reviewCount", 0),
                "last_reviewed_at": q.get("lastReviewedAt"),
                "next_review_at": q.get("nextReviewAt"),
                "note": q.get("note", ""),
                "answer": q.get("answer"),
                "best_practice_answer": q.get("bestPracticeAnswer"),
                "followup_answer": q.get("followupAnswer"),
                "decomposition": q.get("decomposition"),
                "speaking_logs": q.get("speakingLogs", []),
                "action_items": q.get("actionItems", []),
            })
            counts["questions"] += 1
        except Exception as e:
            print(f"skip question: {e}")

    # 3. settings
    for skey, target in [
        ("training_settings_v1", "llm"),
        ("training_asr_settings_v1", "asr"),
        ("training_resume_drill_v1", "resume_drill"),
        ("training_ui_v1", "ui"),
    ]:
        if skey in stores and stores[skey]:
            settings_repo.set_setting(target, stores[skey])
            counts["settings"] += 1

    return {"ok": True, "counts": counts}


@router.get("/export")
def export_all():
    """导出全量数据，作为备份（密钥字段脱敏后返回）"""
    payload = {
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "job_states": jobs_repo.list_job_states(),
        "interviews": jobs_repo.list_interviews(),
        "questions": questions_repo.list_questions(),
        "settings": settings_repo.list_settings(),
    }
    return redact_secrets(payload)
