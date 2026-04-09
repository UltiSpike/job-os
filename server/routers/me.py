"""User profile + mastery — /me 第一人称 API

设计：
- 单例 user_profile 是 app 的主语
- 所有 mastery / target / gap / today 推荐都从这里出
- graceful：任何子查询为空都返回安全空值
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.services import mastery_service
from server.storage import user_profile_repo

router = APIRouter(prefix="/api/v1/me", tags=["me"])


class MePatch(BaseModel):
    display_name: str | None = None
    current_role: str | None = None
    target_role: str | None = None
    target_seniority: str | None = None
    bio: str | None = None
    active_resume_id: str | None = None
    active_target_job_hrefs: list[str] | None = None


@router.get("")
def get_me():
    return user_profile_repo.get()


@router.patch("")
def patch_me(body: MePatch):
    updates = body.model_dump(exclude_unset=True)
    return user_profile_repo.patch(updates)


@router.get("/mastery")
def mastery_vector():
    return {"items": mastery_service.get_mastery_vector()}


@router.get("/target")
def target_vector():
    target = mastery_service.get_target_vector()
    return {"vector": target, "concept_count": len(target)}


@router.get("/gap")
def gap():
    return {"items": mastery_service.get_gap()}


@router.get("/coverage")
def coverage():
    return mastery_service.get_target_coverage()


@router.get("/today-recommendation")
def today_recommendation():
    return mastery_service.get_today_recommendation()
