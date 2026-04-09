"""Curriculum: tracks / modules / lessons / lesson_progress

Curriculum 是 K8s track 的核心结构。读多写少：
- seed 脚本通过 upsert_* 灌入
- 路由层只读 list_*
- lesson_progress 由用户在做毕业题时写入
"""
from __future__ import annotations

import json
from typing import Any

from .base import now_iso, transaction
from .db import get_conn


# ─── tracks ───

def list_tracks() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM tracks ORDER BY slug").fetchall()
    return [dict(r) for r in rows]


def get_track(slug: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tracks WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def upsert_track(slug: str, name: str, description: str = "") -> dict:
    with transaction() as conn:
        existing = conn.execute("SELECT slug FROM tracks WHERE slug = ?", (slug,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE tracks SET name = ?, description = ? WHERE slug = ?",
                (name, description, slug),
            )
        else:
            conn.execute(
                "INSERT INTO tracks (slug, name, description, created_at) VALUES (?, ?, ?, ?)",
                (slug, name, description, now_iso()),
            )
    return get_track(slug)


# ─── modules ───

def list_modules(track_slug: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if track_slug:
            rows = conn.execute(
                "SELECT * FROM modules WHERE track_slug = ? ORDER BY order_index, slug",
                (track_slug,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM modules ORDER BY track_slug, order_index"
            ).fetchall()
    return [dict(r) for r in rows]


def get_module(slug: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM modules WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def upsert_module(slug: str, track_slug: str, order_index: int, name: str, description: str = "") -> dict:
    with transaction() as conn:
        existing = conn.execute("SELECT slug FROM modules WHERE slug = ?", (slug,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE modules SET track_slug = ?, order_index = ?, name = ?, description = ? WHERE slug = ?",
                (track_slug, order_index, name, description, slug),
            )
        else:
            conn.execute(
                """INSERT INTO modules (slug, track_slug, order_index, name, description, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (slug, track_slug, order_index, name, description, now_iso()),
            )
    return get_module(slug)


# ─── lessons ───

def _row_to_lesson(row: Any) -> dict:
    d = dict(row)
    d["prereq_slugs"] = [s for s in (d.get("prereq_slugs") or "").split(",") if s]
    return d


def list_lessons(module_slug: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if module_slug:
            rows = conn.execute(
                "SELECT * FROM lessons WHERE module_slug = ? ORDER BY order_index, slug",
                (module_slug,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM lessons ORDER BY module_slug, order_index"
            ).fetchall()
    return [_row_to_lesson(r) for r in rows]


def get_lesson(slug: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM lessons WHERE slug = ?", (slug,)).fetchone()
    return _row_to_lesson(row) if row else None


def upsert_lesson(
    slug: str,
    module_slug: str,
    order_index: int,
    name: str,
    concept_md: str = "",
    prereq_slugs: list[str] | None = None,
    est_minutes: int = 20,
    capstone_prompt: str = "",
    capstone_depth: int = 2,
) -> dict:
    prereq_csv = ",".join(prereq_slugs or [])
    with transaction() as conn:
        existing = conn.execute("SELECT slug FROM lessons WHERE slug = ?", (slug,)).fetchone()
        if existing:
            conn.execute(
                """UPDATE lessons SET module_slug = ?, order_index = ?, name = ?,
                   concept_md = ?, prereq_slugs = ?, est_minutes = ?,
                   capstone_prompt = ?, capstone_depth = ?
                   WHERE slug = ?""",
                (module_slug, order_index, name, concept_md, prereq_csv,
                 est_minutes, capstone_prompt, capstone_depth, slug),
            )
        else:
            conn.execute(
                """INSERT INTO lessons (slug, module_slug, order_index, name,
                   concept_md, prereq_slugs, est_minutes, capstone_prompt, capstone_depth, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (slug, module_slug, order_index, name, concept_md, prereq_csv,
                 est_minutes, capstone_prompt, capstone_depth, now_iso()),
            )
    return get_lesson(slug)


# ─── lesson_progress ───

def get_progress(lesson_slug: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM lesson_progress WHERE lesson_slug = ?", (lesson_slug,)
        ).fetchone()
    return dict(row) if row else None


def list_progress() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM lesson_progress").fetchall()
    return [dict(r) for r in rows]


def upsert_progress(
    lesson_slug: str,
    status: str | None = None,
    capstone_answer_id: str | None = None,
    capstone_score: int | None = None,
) -> dict:
    now = now_iso()
    with transaction() as conn:
        existing = conn.execute(
            "SELECT * FROM lesson_progress WHERE lesson_slug = ?", (lesson_slug,)
        ).fetchone()
        if existing:
            fields, params = [], []
            if status is not None:
                fields.append("status = ?"); params.append(status)
            if capstone_answer_id is not None:
                fields.append("capstone_answer_id = ?"); params.append(capstone_answer_id)
            if capstone_score is not None:
                fields.append("capstone_score = ?"); params.append(capstone_score)
            if status == "passed":
                fields.append("passed_at = ?"); params.append(now)
            fields.append("last_reviewed_at = ?"); params.append(now)
            params.append(lesson_slug)
            conn.execute(
                f"UPDATE lesson_progress SET {', '.join(fields)} WHERE lesson_slug = ?",
                params,
            )
        else:
            conn.execute(
                """INSERT INTO lesson_progress
                   (lesson_slug, status, capstone_answer_id, capstone_score, passed_at, last_reviewed_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    lesson_slug,
                    status or "in_progress",
                    capstone_answer_id,
                    capstone_score,
                    now if status == "passed" else None,
                    now,
                ),
            )
    return get_progress(lesson_slug)


# ─── tree (一次性给前端的 nested view) ───

def get_track_tree(track_slug: str) -> dict | None:
    """track → modules[] → lessons[]，每个 lesson 带 progress（若有）"""
    track = get_track(track_slug)
    if not track:
        return None
    progress_map = {p["lesson_slug"]: p for p in list_progress()}
    modules = list_modules(track_slug)
    for m in modules:
        lessons = list_lessons(m["slug"])
        for l in lessons:
            l["progress"] = progress_map.get(l["slug"])
        m["lessons"] = lessons
    track["modules"] = modules
    return track
