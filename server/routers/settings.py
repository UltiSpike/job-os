"""profile 通用设置（asr / prompts 已经拆到 dedicated routers）"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from server.storage import settings_repo

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class Profile(BaseModel):
    role: str = ""
    target: str = ""
    experience: str = ""
    system_prompt: str = ""


@router.get("/profile")
def get_profile():
    return settings_repo.get_setting("profile") or Profile().model_dump()


@router.put("/profile")
def put_profile(p: Profile):
    settings_repo.set_setting("profile", p.model_dump())
    return {"ok": True}
