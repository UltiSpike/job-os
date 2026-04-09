"""题库 / 评分 / 复习 数据访问

只处理 questions 表本身的字段。
answers / analyses / topics 是独立资源，前端走对应的 dedicated endpoints。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from . import topics_repo
from .db import get_conn, row_to_dict, rows_to_dicts


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"q_{uuid.uuid4().hex[:12]}"


def _serialize(q: dict) -> dict:
    """剩余的 JSON 字段（已经从 questions 表里排除掉拆出去的）"""
    out = dict(q)
    for k in ("decomposition", "speaking_logs", "action_items"):
        if k in out and not isinstance(out[k], (str, type(None))):
            out[k] = json.dumps(out[k], ensure_ascii=False)
    return out


# 仅给 question 加一个 topic_ids 字段（轻量，从 question_topics join 出来）— 训练场列表常用
def _attach_topic_ids(q: dict) -> dict:
    if not q:
        return q
    topic_objs = topics_repo.list_for_question(q["id"])
    q["topics"] = [t.id for t in topic_objs]
    return q


# ─── CRUD ───

def list_questions(
    *,
    source: str | None = None,
    topic: str | None = None,
    rating: str | None = None,
    due_only: bool = False,
    limit: int = 0,
    offset: int = 0,
    q: str | None = None,
    include_capstone: bool = False,
) -> list[dict]:
    sql = "SELECT * FROM questions WHERE 1=1"
    params: list[Any] = []
    if not include_capstone:
        # 课程的 capstone 永远不进通用题库（毕业题是收口测试，不是日常复习卡）。
        # drill 题（lesson_slug != NULL, is_capstone = 0）只有用户至少做过一次 (first_seen_at) 才进入 SRS 池。
        sql += """ AND (is_capstone IS NULL OR is_capstone = 0)
                   AND (lesson_slug IS NULL OR first_seen_at IS NOT NULL)"""
    if source:
        sql += " AND source = ?"
        params.append(source)
    if rating == "unrated":
        sql += " AND rating IS NULL"
    elif rating:
        sql += " AND rating = ?"
        params.append(rating)
    if due_only:
        now = _now()
        sql += " AND (next_review_at IS NULL OR next_review_at <= ?)"
        params.append(now)
    if topic:
        sql += """ AND EXISTS (
            SELECT 1 FROM question_topics qt
            WHERE qt.question_id = questions.id AND qt.topic_id = ?
        )"""
        params.append(topics_repo.slugify(topic))
    if q:
        sql += " AND text LIKE ?"
        params.append(f"%{q}%")
    sql += " ORDER BY created_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    out = rows_to_dicts(rows)
    return [_attach_topic_ids(q) for q in out]


def get_question(qid: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
    return _attach_topic_ids(row_to_dict(row))


def create_question(q: dict) -> dict:
    qid = q.get("id") or _new_id()
    now = _now()
    data = _serialize({
        "id": qid,
        "text": q["text"],
        "rating": q.get("rating"),
        "review_note": q.get("review_note", ""),
        "source": q.get("source", "manual"),
        "parent_id": q.get("parent_id"),
        "interview_id": q.get("interview_id"),
        "job_id": q.get("job_id"),
        "review_count": q.get("review_count", 0),
        "last_reviewed_at": q.get("last_reviewed_at"),
        "next_review_at": q.get("next_review_at"),
        "note": q.get("note", ""),
        "answer": q.get("answer"),
        "best_practice_answer": q.get("best_practice_answer"),
        "followup_answer": q.get("followup_answer"),
        "decomposition": q.get("decomposition"),
        "speaking_logs": q.get("speaking_logs") or [],
        "action_items": q.get("action_items") or [],
        "lesson_slug": q.get("lesson_slug"),
        "is_capstone": 1 if q.get("is_capstone") else 0,
        "created_at": now,
        "updated_at": now,
    })

    with get_conn() as conn:
        conn.execute(
            """INSERT INTO questions (
                id, text, rating, review_note, source, parent_id, interview_id, job_id,
                review_count, last_reviewed_at, next_review_at, note,
                answer, best_practice_answer, followup_answer, decomposition,
                speaking_logs, action_items, lesson_slug, is_capstone, created_at, updated_at
            ) VALUES (
                :id, :text, :rating, :review_note, :source, :parent_id, :interview_id, :job_id,
                :review_count, :last_reviewed_at, :next_review_at, :note,
                :answer, :best_practice_answer, :followup_answer, :decomposition,
                :speaking_logs, :action_items, :lesson_slug, :is_capstone, :created_at, :updated_at
            )""",
            data,
        )
    # 写 topics（仍保留 — 创建题目时常常会带上 topics）
    if q.get("topics"):
        topics_repo.set_question_topics(qid, q["topics"])
    return get_question(qid)


def update_question(qid: str, patch: dict) -> dict | None:
    """只更新 questions 表自身的字段。
    answers / analyses / topics 是独立资源，请走对应的 dedicated endpoints。
    """
    # 严格 PATCH：answer_variants / analyses / chat_sessions 是独立资源，必须走 dedicated routers
    forbidden = {"answer_variants", "analyses", "chat_sessions"}
    bad = forbidden & set(patch.keys())
    if bad:
        raise ValueError(
            f"PATCH /questions/{{id}} 不接受字段 {sorted(bad)}。"
            f"answer_variants → /api/v1/answers, "
            f"analyses → /api/v1/analyses, "
            f"chat_sessions → /api/v1/chat-sessions"
        )

    # topics 单独处理（仍允许通过 questions PATCH 设置 — 因为属于 question 的属性）
    if "topics" in patch:
        topics_repo.set_question_topics(qid, patch.pop("topics") or [])

    if not patch:
        return get_question(qid)

    patch = _serialize(patch)
    fields = []
    params: list[Any] = []
    for k in (
        "text", "rating", "review_note", "parent_id", "job_id", "source",
        "review_count", "last_reviewed_at", "next_review_at", "note",
        "answer", "best_practice_answer", "followup_answer", "decomposition",
        "speaking_logs", "action_items",
    ):
        if k in patch:
            fields.append(f"{k} = ?")
            params.append(patch[k])
    if fields:
        fields.append("updated_at = ?")
        params.append(_now())
        params.append(qid)
        with get_conn() as conn:
            conn.execute(
                f"UPDATE questions SET {', '.join(fields)} WHERE id = ?",
                params,
            )
    return get_question(qid)


def delete_question(qid: str):
    """CASCADE 通过 FK 自动删 answers / analyses / question_topics / chat_sessions"""
    with get_conn() as conn:
        conn.execute("DELETE FROM questions WHERE id = ?", (qid,))


def bulk_create(questions: list[dict]) -> int:
    n = 0
    for q in questions:
        create_question(q)
        n += 1
    return n


# ─── 间隔复习算法（SM-2 简化版） ───

def review_interval_days(rating: str | None, review_count: int) -> int:
    if rating == "bad":
        return 1
    if rating == "ok":
        return 5 if review_count >= 5 else 3
    if rating == "good":
        if review_count >= 6:
            return 21
        if review_count >= 3:
            return 7
        return 3
    return 2


def submit_review(qid: str, rating: str) -> dict | None:
    q = get_question(qid)
    if not q:
        return None
    review_count = (q.get("review_count") or 0) + 1
    interval = review_interval_days(rating, review_count)
    now = datetime.now(timezone.utc)
    next_at = (now.timestamp() + interval * 86400)
    next_iso = datetime.fromtimestamp(next_at, tz=timezone.utc).isoformat()

    return update_question(qid, {
        "rating": rating,
        "review_count": review_count,
        "last_reviewed_at": now.isoformat(),
        "next_review_at": next_iso,
    })


# ─── 技能点聚合 — 走真 SQL ───

def aggregate_topics() -> dict[str, dict]:
    """从 question_topics + questions 走 SQL 聚合，性能好"""
    rows = topics_repo.aggregate_with_stats()
    out = {}
    for r in rows:
        topic_id = r["id"]
        n = r["question_count"] or 0
        good = r["good"] or 0
        ok = r["ok"] or 0
        bad = r["bad"] or 0
        none = r["unrated"] or 0
        rated = good + ok + bad
        out[topic_id] = {
            "topic": topic_id,
            "display_name": r["display_name"],
            "total": n,
            "good": good,
            "ok": ok,
            "bad": bad,
            "none": none,
            "rated": rated,
            "score": (good + ok * 0.5) / rated if rated > 0 else 0,
        }
    return out
