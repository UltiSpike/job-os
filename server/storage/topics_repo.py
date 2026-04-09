"""topics 规范化表 + question 关联"""
from __future__ import annotations

from pydantic import BaseModel

from .base import hydrate_row, hydrate_rows, now_iso, transaction
from .db import get_conn


class Topic(BaseModel):
    id: str
    display_name: str
    parent_id: str | None = None
    created_at: str


def slugify(name: str) -> str:
    """规范化 topic 字符串"""
    s = (name or "").strip().lower()
    aliases = {
        "kubernetes": "k8s",
        "go": "golang",
    }
    return aliases.get(s, s)


# ─── 读 ───

def list_all() -> list[Topic]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM topics ORDER BY id").fetchall()
    return hydrate_rows(rows, Topic)


def get(topic_id: str) -> Topic | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
    return hydrate_row(row, Topic)


def list_for_question(question_id: str) -> list[Topic]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT t.* FROM topics t
               JOIN question_topics qt ON qt.topic_id = t.id
               WHERE qt.question_id = ?
               ORDER BY t.id""",
            (question_id,),
        ).fetchall()
    return hydrate_rows(rows, Topic)


def list_question_ids_for_topic(topic_id: str) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT question_id FROM question_topics WHERE topic_id = ?",
            (topic_id,),
        ).fetchall()
    return [r["question_id"] for r in rows]


# ─── 写 ───

def upsert_topic(name: str, display_name: str | None = None) -> Topic:
    tid = slugify(name)
    if not tid:
        raise ValueError("topic name empty")
    existing = get(tid)
    if existing:
        return existing
    with transaction() as conn:
        conn.execute(
            "INSERT INTO topics (id, display_name, created_at) VALUES (?, ?, ?)",
            (tid, display_name or name, now_iso()),
        )
    return get(tid)


def set_question_topics(question_id: str, topic_names: list[str]):
    """覆盖式更新某题的 topics"""
    with transaction() as conn:
        conn.execute("DELETE FROM question_topics WHERE question_id = ?", (question_id,))
        for name in topic_names:
            tid = slugify(name)
            if not tid:
                continue
            # 先确保 topic 存在
            conn.execute(
                "INSERT OR IGNORE INTO topics (id, display_name, created_at) VALUES (?, ?, ?)",
                (tid, name, now_iso()),
            )
            conn.execute(
                "INSERT OR IGNORE INTO question_topics (question_id, topic_id) VALUES (?, ?)",
                (question_id, tid),
            )


def aggregate_with_stats() -> list[dict]:
    """每个 topic 的统计：题目数 + good/ok/bad rating 分布 + 平均 score"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT
                t.id,
                t.display_name,
                COUNT(DISTINCT qt.question_id) AS question_count,
                SUM(CASE WHEN q.rating = 'good' THEN 1 ELSE 0 END) AS good,
                SUM(CASE WHEN q.rating = 'ok' THEN 1 ELSE 0 END) AS ok,
                SUM(CASE WHEN q.rating = 'bad' THEN 1 ELSE 0 END) AS bad,
                SUM(CASE WHEN q.rating IS NULL THEN 1 ELSE 0 END) AS unrated
               FROM topics t
               LEFT JOIN question_topics qt ON qt.topic_id = t.id
               LEFT JOIN questions q ON q.id = qt.question_id
               GROUP BY t.id, t.display_name
               ORDER BY question_count DESC"""
        ).fetchall()
    return [dict(r) for r in rows]
