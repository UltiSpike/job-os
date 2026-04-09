"""答案模板路由 — 题目的多个 AI/手写答案版本"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.storage import answers_repo

router = APIRouter(prefix="/api/v1/answers", tags=["answers"])


class AnswerCreate(BaseModel):
    question_id: str
    template_id: str
    template_name: str
    content: str


class AnswerPatch(BaseModel):
    content: str | None = None


@router.get("")
def list_answers(question_id: str | None = None, limit: int = 0):
    if question_id:
        items = answers_repo.list_for_question(question_id)
    else:
        items = answers_repo.list_all(limit=limit or 200)
    return {"items": [a.model_dump() for a in items], "total": len(items)}


@router.get("/{answer_id}")
def get_answer(answer_id: str):
    a = answers_repo.get(answer_id)
    if not a:
        raise HTTPException(404, "answer not found")
    return a.model_dump()


@router.post("")
def create_answer(body: AnswerCreate):
    a = answers_repo.upsert(body.question_id, body.template_id, body.template_name, body.content)
    return a.model_dump()


@router.patch("/{answer_id}")
def patch_answer(answer_id: str, body: AnswerPatch):
    if body.content is None:
        raise HTTPException(400, "content required")
    a = answers_repo.update_content(answer_id, body.content, mark_edited=True)
    if not a:
        raise HTTPException(404, "answer not found")
    return a.model_dump()


@router.delete("/{answer_id}")
def delete_answer(answer_id: str):
    snap = answers_repo.delete(answer_id)
    if not snap:
        raise HTTPException(404, "answer not found")
    return {"ok": True, "snapshot": snap.model_dump()}


@router.post("/restore")
def restore_answer(snapshot: dict):
    """从快照还原（用于 undo delete）"""
    from server.storage.answers_repo import Answer
    a = answers_repo.restore(Answer(**snapshot))
    return a.model_dump()
