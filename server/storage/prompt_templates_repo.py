"""Prompt templates — 取代 settings.prompt_templates"""
from __future__ import annotations

from pydantic import BaseModel

from .base import hydrate_row, hydrate_rows, now_iso, transaction
from .db import get_conn


class PromptTemplate(BaseModel):
    id: str
    name: str
    content: str
    created_at: str
    updated_at: str


def list_all() -> list[PromptTemplate]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM prompt_templates ORDER BY updated_at DESC").fetchall()
    return hydrate_rows(rows, PromptTemplate)


def get(template_id: str) -> PromptTemplate | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM prompt_templates WHERE id = ?", (template_id,)).fetchone()
    return hydrate_row(row, PromptTemplate)


def upsert(template_id: str, name: str, content: str) -> PromptTemplate:
    existing = get(template_id)
    now = now_iso()
    with transaction() as conn:
        if existing:
            conn.execute(
                "UPDATE prompt_templates SET name = ?, content = ?, updated_at = ? WHERE id = ?",
                (name, content, now, template_id),
            )
        else:
            conn.execute(
                "INSERT INTO prompt_templates (id, name, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (template_id, name, content, now, now),
            )
    return get(template_id)


def delete(template_id: str) -> PromptTemplate | None:
    snap = get(template_id)
    if not snap:
        return None
    with transaction() as conn:
        conn.execute("DELETE FROM prompt_templates WHERE id = ?", (template_id,))
    return snap
