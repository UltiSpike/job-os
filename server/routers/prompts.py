"""Prompt 模板路由 — 从 /settings/prompts 提到顶级 /prompt-templates"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.storage import prompt_templates_repo

router = APIRouter(prefix="/api/v1/prompt-templates", tags=["prompts"])


class PromptIn(BaseModel):
    id: str
    name: str
    content: str


class PromptPatch(BaseModel):
    name: str | None = None
    content: str | None = None


@router.get("")
def list_prompts():
    items = prompt_templates_repo.list_all()
    return {"items": [p.model_dump() for p in items], "total": len(items)}


@router.get("/{pid}")
def get_prompt(pid: str):
    p = prompt_templates_repo.get(pid)
    if not p:
        raise HTTPException(404, "prompt not found")
    return p.model_dump()


@router.post("")
def create_prompt(body: PromptIn):
    p = prompt_templates_repo.upsert(body.id, body.name, body.content)
    return p.model_dump()


@router.patch("/{pid}")
def patch_prompt(pid: str, body: PromptPatch):
    existing = prompt_templates_repo.get(pid)
    if not existing:
        raise HTTPException(404, "prompt not found")
    p = prompt_templates_repo.upsert(
        pid,
        body.name if body.name is not None else existing.name,
        body.content if body.content is not None else existing.content,
    )
    return p.model_dump()


@router.delete("/{pid}")
def delete_prompt(pid: str):
    prompt_templates_repo.delete(pid)
    return {"ok": True}
