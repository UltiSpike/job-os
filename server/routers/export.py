"""数据导出 — 完整 JSON dump 用于备份"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server.storage import jobs_repo, questions_repo, resumes_repo, settings_repo

router = APIRouter(prefix="/api/v1/export", tags=["export"])


@router.get("")
def export_all():
    """导出所有用户数据 — 不包括 snapshot.json (爬虫产出，可重生)"""
    payload = {
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "schema": "job-os",
        "data": {
            "job_states": jobs_repo.list_job_states(),
            "interviews": jobs_repo.list_interviews(),
            "questions": questions_repo.list_questions(),
            "resumes": resumes_repo.list_resumes(),
            "settings": settings_repo.list_settings(),
        },
    }
    filename = f"job-os-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
