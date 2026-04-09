"""答案模板的历史回答 — 取代 questions.answer_variants JSON"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from .base import hydrate_row, hydrate_rows, now_iso, transaction
from .db import get_conn


class Answer(BaseModel):
    id: str
    question_id: str
    template_id: str
    template_name: str
    content: str
    user_edited: int = 0
    generated_at: str
    edited_at: str | None = None


def _new_id(question_id: str, template_id: str) -> str:
    return f"a_{question_id[:10]}_{template_id}_{uuid.uuid4().hex[:6]}"


# ─── 读 ───

def list_all(limit: int = 0) -> list[Answer]:
    sql = "SELECT * FROM answers ORDER BY generated_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    return hydrate_rows(rows, Answer)


def list_for_question(question_id: str) -> list[Answer]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM answers WHERE question_id = ? ORDER BY generated_at DESC",
            (question_id,),
        ).fetchall()
    return hydrate_rows(rows, Answer)


def get(answer_id: str) -> Answer | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM answers WHERE id = ?", (answer_id,)).fetchone()
    return hydrate_row(row, Answer)


def get_by_template(question_id: str, template_id: str) -> Answer | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM answers WHERE question_id = ? AND template_id = ?",
            (question_id, template_id),
        ).fetchone()
    return hydrate_row(row, Answer)


# ─── 写 ───

def upsert(question_id: str, template_id: str, template_name: str, content: str) -> Answer:
    """同 (question_id, template_id) 已存在则替换 content + 重置 edited_at；不存在则新建"""
    existing = get_by_template(question_id, template_id)
    now = now_iso()
    if existing:
        with transaction() as conn:
            conn.execute(
                """UPDATE answers SET content = ?, generated_at = ?, edited_at = NULL, user_edited = 0
                   WHERE id = ?""",
                (content, now, existing.id),
            )
        return get(existing.id)
    else:
        aid = _new_id(question_id, template_id)
        with transaction() as conn:
            conn.execute(
                """INSERT INTO answers (id, question_id, template_id, template_name, content, generated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (aid, question_id, template_id, template_name, content, now),
            )
        return get(aid)


def update_content(answer_id: str, content: str, mark_edited: bool = True) -> Answer | None:
    now = now_iso()
    with transaction() as conn:
        conn.execute(
            "UPDATE answers SET content = ?, edited_at = ?, user_edited = ? WHERE id = ?",
            (content, now if mark_edited else None, 1 if mark_edited else 0, answer_id),
        )
    return get(answer_id)


def delete(answer_id: str) -> Answer | None:
    snapshot = get(answer_id)
    if not snapshot:
        return None
    with transaction() as conn:
        conn.execute("DELETE FROM answers WHERE id = ?", (answer_id,))
    return snapshot


def restore(snap: Answer) -> Answer:
    with transaction() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO answers
               (id, question_id, template_id, template_name, content, user_edited, generated_at, edited_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (snap.id, snap.question_id, snap.template_id, snap.template_name, snap.content,
             snap.user_edited, snap.generated_at, snap.edited_at),
        )
    return get(snap.id)
