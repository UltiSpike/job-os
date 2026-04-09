"""简历版本路由"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.storage import resumes_repo

router = APIRouter(prefix="/api/v1/resumes", tags=["resumes"])


class ResumeIn(BaseModel):
    name: str
    content: str = ""
    is_default: bool = False


class ResumePatch(BaseModel):
    name: str | None = None
    content: str | None = None
    is_default: bool | None = None


@router.get("")
def list_all():
    return {"items": resumes_repo.list_resumes()}


@router.post("")
def create(r: ResumeIn):
    return resumes_repo.create_resume(r.name, r.content, r.is_default)


@router.get("/{rid}")
def get_one(rid: str):
    r = resumes_repo.get_resume(rid)
    if not r:
        raise HTTPException(404, "not found")
    return r


@router.patch("/{rid}")
def patch_one(rid: str, patch: ResumePatch):
    out = resumes_repo.update_resume(rid, patch.model_dump(exclude_unset=True))
    if not out:
        raise HTTPException(404, "not found")
    return out


@router.delete("/{rid}")
def delete_one(rid: str):
    resumes_repo.delete_resume(rid)
    return {"ok": True}
