"""Concept layer — 知识点中心实体

设计:
- 1 lesson = 1 concept (slug 相同) 是 MVP 的简化
- 一道 question 可以挂多个 concept (concept_questions 多对多)
- mastery 不存表 — 由 mastery_service 实时算
"""
from __future__ import annotations

from .base import now_iso, transaction
from .db import get_conn


# ─── concepts ───

def upsert_concept(slug: str, name: str, description: str = "",
                   track_slug: str | None = None, module_slug: str | None = None) -> dict:
    with transaction() as conn:
        existing = conn.execute("SELECT slug FROM concepts WHERE slug = ?", (slug,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE concepts SET name = ?, description = ?, track_slug = ?, module_slug = ? WHERE slug = ?",
                (name, description, track_slug, module_slug, slug),
            )
        else:
            conn.execute(
                """INSERT INTO concepts (slug, name, description, track_slug, module_slug, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (slug, name, description, track_slug, module_slug, now_iso()),
            )
    return get_concept(slug)


def get_concept(slug: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM concepts WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def list_concepts(track_slug: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if track_slug:
            rows = conn.execute(
                "SELECT * FROM concepts WHERE track_slug = ? ORDER BY slug",
                (track_slug,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM concepts ORDER BY slug").fetchall()
    return [dict(r) for r in rows]


# ─── concept ↔ question 关联 ───

def link_question(concept_slug: str, question_id: str) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO concept_questions (concept_slug, question_id) VALUES (?, ?)",
            (concept_slug, question_id),
        )


def unlink_question(concept_slug: str, question_id: str) -> None:
    with transaction() as conn:
        conn.execute(
            "DELETE FROM concept_questions WHERE concept_slug = ? AND question_id = ?",
            (concept_slug, question_id),
        )


def list_questions_for_concept(concept_slug: str) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT question_id FROM concept_questions WHERE concept_slug = ?",
            (concept_slug,),
        ).fetchall()
    return [r["question_id"] for r in rows]


def list_concepts_for_question(question_id: str) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT concept_slug FROM concept_questions WHERE question_id = ?",
            (question_id,),
        ).fetchall()
    return [r["concept_slug"] for r in rows]
