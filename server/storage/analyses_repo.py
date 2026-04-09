"""AI 评估记录 — 取代 questions.analyses JSON"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from .base import hydrate_row, hydrate_rows, now_iso, transaction
from .db import get_conn


JSON_FIELDS = ("strengths", "gaps", "topics_touched")


class Analysis(BaseModel):
    id: str
    question_id: str
    answer_id: str | None = None
    source: str | None = None
    user_text: str
    score: int | None = None
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    suggestions: str = ""
    topics_touched: list[str] = Field(default_factory=list)
    at: str


def _new_id() -> str:
    return f"an_{uuid.uuid4().hex[:12]}"


# ─── 读 ───

def list_for_question(question_id: str) -> list[Analysis]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM analyses WHERE question_id = ? ORDER BY at ASC",
            (question_id,),
        ).fetchall()
    return hydrate_rows(rows, Analysis, json_fields=JSON_FIELDS)


def list_all(limit: int = 0) -> list[Analysis]:
    sql = "SELECT * FROM analyses ORDER BY at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    return hydrate_rows(rows, Analysis, json_fields=JSON_FIELDS)


def get(analysis_id: str) -> Analysis | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    return hydrate_row(row, Analysis, json_fields=JSON_FIELDS)


# ─── 写 ───

def create(data: dict) -> Analysis:
    """创建一条 analysis。data 是 dict（来自路由层 patch）"""
    import json as _j
    aid = data.get("id") or _new_id()
    with transaction() as conn:
        conn.execute(
            """INSERT INTO analyses
               (id, question_id, answer_id, source, user_text, score, strengths, gaps, suggestions, topics_touched, at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                aid,
                data["question_id"],
                data.get("answer_id"),
                data.get("source"),
                data.get("user_text", ""),
                data.get("score"),
                _j.dumps(data.get("strengths") or [], ensure_ascii=False),
                _j.dumps(data.get("gaps") or [], ensure_ascii=False),
                data.get("suggestions") or "",
                _j.dumps(data.get("topics_touched") or [], ensure_ascii=False),
                data.get("at") or now_iso(),
            ),
        )
    return get(aid)


def delete(analysis_id: str) -> Analysis | None:
    snap = get(analysis_id)
    if not snap:
        return None
    with transaction() as conn:
        conn.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
    return snap


def restore(snap: Analysis) -> Analysis:
    return create(snap.model_dump())


# ─── 聚合查询（database-optimizer 应用：用真 SQL 而非内存遍历） ───

def aggregate_by_topic() -> list[dict]:
    """按 topics_touched 聚合（注意：仍然要 LIKE 因为 topics_touched 是 JSON 字符串）

    更准的版本应该让 analyses.topics 也走 question_topics 关联，但 topics_touched 是 LLM 抽出来的（可能不在 canonical topic 表里），暂保留 JSON 形式。
    """
    return []


def stats() -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT
                COUNT(*) AS total,
                AVG(score) AS avg_score,
                SUM(CASE WHEN score >= 80 THEN 1 ELSE 0 END) AS high,
                SUM(CASE WHEN score >= 60 AND score < 80 THEN 1 ELSE 0 END) AS mid,
                SUM(CASE WHEN score < 60 THEN 1 ELSE 0 END) AS low
               FROM analyses"""
        ).fetchone()
    return dict(row) if row else {"total": 0}
