"""题库 + 评分 + 复习 路由"""
from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from server.storage import questions_repo

router = APIRouter(prefix="/api/v1", tags=["questions"])


class QuestionIn(BaseModel):
    text: str
    topics: list[str] = []
    rating: str | None = None
    review_note: str = ""
    source: str = "manual"
    parent_id: str | None = None
    job_id: str | None = None
    answer: str | None = None
    note: str = ""
    speaking_logs: list | None = None
    action_items: list | None = None
    review_count: int | None = None
    last_reviewed_at: str | None = None
    next_review_at: str | None = None
    best_practice_answer: str | None = None
    followup_answer: str | None = None
    decomposition: dict | None = None


class QuestionPatch(BaseModel):
    text: str | None = None
    topics: list[str] | None = None
    rating: str | None = None
    review_note: str | None = None
    answer: str | None = None
    best_practice_answer: str | None = None
    followup_answer: str | None = None
    decomposition: dict | None = None
    speaking_logs: list | None = None
    action_items: list | None = None
    note: str | None = None
    parent_id: str | None = None
    job_id: str | None = None
    source: str | None = None
    review_count: int | None = None
    last_reviewed_at: str | None = None
    next_review_at: str | None = None


class BulkImportIn(BaseModel):
    items: list[QuestionIn]


# ─── CRUD ───

@router.get("/questions")
def list_questions(
    source: str | None = None,
    topic: str | None = None,
    rating: str | None = None,
    due: bool = False,
    limit: int = 0,
):
    items = questions_repo.list_questions(
        source=source, topic=topic, rating=rating, due_only=due, limit=limit
    )
    return {"items": items, "total": len(items)}


@router.get("/questions/topics")
def topics_aggregate():
    """技能点聚合，给训练场热力图用"""
    return questions_repo.aggregate_topics()


@router.get("/questions/due")
def list_due():
    """今日待复习"""
    items = questions_repo.list_questions(due_only=True)
    return {"items": items, "total": len(items)}


@router.get("/questions/{qid}")
def get_one(qid: str):
    q = questions_repo.get_question(qid)
    if q is None:
        raise HTTPException(404, "question not found")
    return q


@router.post("/questions")
def create_one(q: QuestionIn):
    return questions_repo.create_question(q.model_dump())


@router.post("/questions/bulk")
def bulk_create(payload: BulkImportIn):
    n = questions_repo.bulk_create([item.model_dump() for item in payload.items])
    return {"created": n}


@router.patch("/questions/{qid}")
def patch_one(qid: str, patch: QuestionPatch):
    out = questions_repo.update_question(qid, patch.model_dump(exclude_unset=True))
    if out is None:
        raise HTTPException(404, "question not found")
    return out


@router.delete("/questions/{qid}")
def delete_one(qid: str):
    questions_repo.delete_question(qid)
    return {"ok": True}


@router.post("/questions/{qid}/review")
def review(qid: str, body: dict):
    rating = body.get("rating")
    if rating not in ("good", "ok", "bad"):
        raise HTTPException(400, "rating must be good/ok/bad")
    out = questions_repo.submit_review(qid, rating)
    if out is None:
        raise HTTPException(404, "question not found")
    return out


# ─── AI 出题 ───

class GenerateRequest(BaseModel):
    topic: str           # 例如 "k8s scheduler"
    count: int = 5
    difficulty: str = "medium"  # easy / medium / hard
    style: str = "技术原理"      # 技术原理 / 项目深挖 / 系统设计 / Trade-off
    avoid: list[str] = []         # 已有题目的 text 列表，避免重复


class ClassifyRequest(BaseModel):
    text: str
    max_topics: int = 5


@router.post("/questions/classify")
async def classify_question(req: ClassifyRequest):
    """让 LLM 从题目文本里抽取技能 topic 标签"""
    from server.routers.llm import _resolve, _build_headers

    target = _resolve(None, None)
    headers = _build_headers(target)

    sys = f"""你是一名后端方向的技术分类器。给一道技术面试题，提取 2-{req.max_topics} 个技能 topic 标签。

【硬性要求】
- 输出**逗号分隔**的英文小写 topic（不要中文，不要 markdown）
- 每个 topic 1-3 个单词，常用术语，例如：k8s / golang / scheduler / informer / distributed-lock / mysql / redis
- 不要泛泛标签如 "backend" "system" "interview"，要具体技术点
- 不要超出 {req.max_topics} 个
- 只输出标签本身，不要任何前后缀

示例输入: 解释 K8s scheduler 的扩展点 framework 和 plugin 机制
示例输出: k8s, scheduler, framework, plugin"""

    body = {
        "model": target.model,
        "messages": [
            {"role": "system", "content": sys},
            {"role": "user", "content": req.text},
        ],
        "stream": False,
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{target.base_url.rstrip('/')}/chat/completions",
            headers=headers, json=body,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:300])
    data = r.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    # 解析：split + clean + lower
    topics = []
    for t in text.replace("、", ",").replace("，", ",").split(","):
        t = t.strip().strip("`").strip("'").strip('"').lower()
        if t and len(t) <= 30:
            topics.append(t)
    return {"topics": topics[:req.max_topics]}


@router.post("/questions/generate")
async def generate_questions(req: GenerateRequest):
    """流式生成 N 道题。
    输出格式（一行一题）：
      Q1: ...
      Q2: ...
    前端按行解析，全部完成后再统一调 /questions/bulk 入库。
    """
    from server.routers.llm import _resolve, _build_headers, _build_context_prompt

    target = _resolve(None, None)
    headers = _build_headers(target)

    ctx = _build_context_prompt()
    avoid_block = ""
    if req.avoid:
        avoid_block = "\n\n已有题目（务必避免重复或高度相似）：\n" + "\n".join(f"- {t[:60]}" for t in req.avoid[:30])

    sys = f"""你是一名资深后端面试官，正在为候选人准备一组面试题。

【题目要求】
- topic: {req.topic}
- 数量: {req.count}
- 难度: {req.difficulty}
- 风格: {req.style}
- 每道题独立可答，不依赖前面的题
- 题目要"具体、可深挖"，不要泛泛而谈
- 包含至少一道追问类（"如果...会怎样"）

【输出格式 — 严格遵守，前端会按行解析】
一行一题，每题以 `Q1:` `Q2:` ... 开头，后跟题干。例如：
Q1: 解释 K8s scheduler 的扩展点 framework 是怎么设计的，为什么这么设计
Q2: 如果你要给 scheduler 加一个新的 plugin，从 0 到 1 的步骤是什么
Q3: ...

【硬性禁止】
- 不要 markdown
- 不要前言后记
- 不要"以下是..."等套话
- 不要重复已有题目
{ctx}{avoid_block}
"""
    body_msg = f"为「{req.topic}」生成 {req.count} 道{req.difficulty}难度的{req.style}面试题。"

    body = {
        "model": target.model,
        "messages": [
            {"role": "system", "content": sys},
            {"role": "user", "content": body_msg},
        ],
        "stream": True,
        "temperature": 0.7,
    }

    async def event_stream():
        try:
            timeout = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=5.0)
            async with httpx.AsyncClient(timeout=timeout, http2=False) as client:
                async with client.stream(
                    "POST",
                    f"{target.base_url.rstrip('/')}/chat/completions",
                    headers={**headers, "Accept": "text/event-stream"},
                    json=body,
                ) as r:
                    if r.status_code >= 400:
                        text = await r.aread()
                        yield f'data: {{"error":"upstream {r.status_code}: {text.decode()[:200]}"}}\n\n'
                        return
                    buf = b""
                    async for chunk in r.aiter_bytes():
                        if not chunk:
                            continue
                        buf += chunk
                        while b"\n\n" in buf:
                            event, _, buf = buf.partition(b"\n\n")
                            yield event.decode("utf-8", "replace") + "\n\n"
        except Exception as e:
            yield f'data: {{"error":"{str(e)}"}}\n\n'
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
