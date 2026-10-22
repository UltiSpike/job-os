"""LLM presets — 取代 settings.llm_presets / llm_active"""
from __future__ import annotations

from pydantic import BaseModel

from .base import hydrate_row, hydrate_rows, now_iso, transaction
from .db import get_conn


class LLMPreset(BaseModel):
    name: str
    base_url: str
    model: str
    api_key: str
    extra_headers: str = ""
    is_active: int = 0
    created_at: str
    updated_at: str


def list_all() -> list[LLMPreset]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM llm_presets ORDER BY name").fetchall()
    return hydrate_rows(rows, LLMPreset)


def get(name: str) -> LLMPreset | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM llm_presets WHERE name = ?", (name,)).fetchone()
    return hydrate_row(row, LLMPreset)


def get_active() -> LLMPreset | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM llm_presets WHERE is_active = 1 LIMIT 1").fetchone()
    if row:
        return hydrate_row(row, LLMPreset)
    # 没激活的就拿第一个
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM llm_presets ORDER BY name LIMIT 1").fetchone()
    return hydrate_row(row, LLMPreset)


def upsert(name: str, base_url: str, model: str, api_key: str, extra_headers: str = "") -> LLMPreset:
    existing = get(name)
    now = now_iso()
    with transaction() as conn:
        if existing:
            # 空 api_key / 空 extra_headers 时保留原值（GET 只回掩码，前端留空即“不改”）
            new_key = api_key or existing.api_key
            new_extra = extra_headers or existing.extra_headers
            conn.execute(
                """UPDATE llm_presets SET base_url = ?, model = ?, api_key = ?, extra_headers = ?, updated_at = ?
                   WHERE name = ?""",
                (base_url, model, new_key, new_extra, now, name),
            )
        else:
            conn.execute(
                """INSERT INTO llm_presets (name, base_url, model, api_key, extra_headers, is_active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, base_url, model, api_key, extra_headers, 0, now, now),
            )
    return get(name)


def activate(name: str) -> LLMPreset | None:
    if not get(name):
        return None
    with transaction() as conn:
        conn.execute("UPDATE llm_presets SET is_active = 0")
        conn.execute("UPDATE llm_presets SET is_active = 1, updated_at = ? WHERE name = ?", (now_iso(), name))
    return get(name)


def delete(name: str) -> LLMPreset | None:
    snap = get(name)
    if not snap:
        return None
    with transaction() as conn:
        conn.execute("DELETE FROM llm_presets WHERE name = ?", (name,))
        # 如果删的是 active，自动激活下一个
        if snap.is_active:
            row = conn.execute("SELECT name FROM llm_presets ORDER BY name LIMIT 1").fetchone()
            if row:
                conn.execute("UPDATE llm_presets SET is_active = 1 WHERE name = ?", (row["name"],))
    return snap
