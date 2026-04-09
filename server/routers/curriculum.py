"""Curriculum routes — tracks / modules / lessons / progress."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.storage import curriculum_repo, questions_repo
from server.storage.db import get_conn

router = APIRouter(prefix="/api/v1", tags=["curriculum"])


class ProgressIn(BaseModel):
    status: str | None = None  # locked/available/in_progress/passed
    capstone_answer_id: str | None = None
    capstone_score: int | None = None


@router.get("/tracks")
def list_tracks():
    return {"items": curriculum_repo.list_tracks()}


@router.get("/tracks/{slug}")
def get_track(slug: str):
    t = curriculum_repo.get_track(slug)
    if not t:
        raise HTTPException(404, "track not found")
    return t


@router.get("/tracks/{slug}/tree")
def get_track_tree(slug: str):
    """Track + nested modules + lessons + progress — 一次给前端要的全部"""
    tree = curriculum_repo.get_track_tree(slug)
    if not tree:
        raise HTTPException(404, "track not found")
    return tree


@router.get("/modules")
def list_modules(track: str | None = None):
    return {"items": curriculum_repo.list_modules(track)}


@router.get("/modules/{slug}")
def get_module(slug: str):
    m = curriculum_repo.get_module(slug)
    if not m:
        raise HTTPException(404, "module not found")
    return m


@router.get("/lessons")
def list_lessons(module: str | None = None):
    return {"items": curriculum_repo.list_lessons(module)}


@router.get("/lessons/{slug}")
def get_lesson(slug: str):
    l = curriculum_repo.get_lesson(slug)
    if not l:
        raise HTTPException(404, "lesson not found")
    l["progress"] = curriculum_repo.get_progress(slug)
    return l


@router.get("/lesson-progress")
def list_progress():
    return {"items": curriculum_repo.list_progress()}


@router.post("/lessons/{lesson_slug}/capstone-question")
def ensure_capstone_question(lesson_slug: str):
    """Lazily creates (or returns) the capstone question row for this lesson.

    The frontend uses this question_id to drive the existing analyses streaming
    flow, so capstone practice fully reuses the answers/analyses pipeline.
    """
    lesson = curriculum_repo.get_lesson(lesson_slug)
    if not lesson:
        raise HTTPException(404, "lesson not found")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM questions WHERE lesson_slug = ? AND is_capstone = 1 LIMIT 1",
            (lesson_slug,),
        ).fetchone()
    if row:
        return questions_repo.get_question(row["id"])
    q = questions_repo.create_question({
        "text": lesson.get("capstone_prompt") or f"[{lesson['name']}] 毕业题尚未配置",
        "source": "curriculum",
        "lesson_slug": lesson_slug,
        "is_capstone": True,
    })
    return q


@router.put("/lesson-progress/{lesson_slug}")
def upsert_progress(lesson_slug: str, body: ProgressIn):
    if not curriculum_repo.get_lesson(lesson_slug):
        raise HTTPException(404, "lesson not found")
    return curriculum_repo.upsert_progress(
        lesson_slug=lesson_slug,
        status=body.status,
        capstone_answer_id=body.capstone_answer_id,
        capstone_score=body.capstone_score,
    )
