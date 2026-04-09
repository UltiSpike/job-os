"""AI 评估路由 — 取代 routers/analyze.py，使用独立 analyses 表"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from server.storage import analyses_repo, answers_repo, questions_repo

router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"])


class AnalysisCreateStream(BaseModel):
    question_id: str
    user_text: str
    source: str = "manual"
    against_answer_id: str | None = None  # 对照哪个答案 variant


def _build_analyze_messages(question: dict, req: AnalysisCreateStream) -> list[dict]:
    from server.routers.llm import _build_context_prompt

    reference = None
    if req.against_answer_id:
        a = answers_repo.get(req.against_answer_id)
        if a:
            reference = {"template_name": a.template_name, "content": a.content}
    if not reference:
        # 取该题最新的一个答案当对照
        recent = answers_repo.list_for_question(req.question_id)
        if recent:
            reference = {"template_name": recent[0].template_name, "content": recent[0].content}

    full_ctx = _build_context_prompt()
    profile_ctx = ("\n\n" + full_ctx) if full_ctx else ""

    sys = f"""你是一名后端方向的资深面试官，正在评估候选人对一道技术面试题的口头回答。
你的任务：对照参考答案（如果有）+ 你自己的工程经验，给出**结构化、可执行**的反馈。
{profile_ctx}

【硬性输出格式 — 必须严格遵守，前端会按这个格式解析】
SCORE: <0-100 的整数，单独一行>
STRENGTHS:
- <强项 1>
- <强项 2>
GAPS:
- <缺口 1>
- <缺口 2>
SUGGESTIONS:
<一段话 30-80 字>
TOPICS: <逗号分隔的 2-5 个英文小写技术标签>

【硬性禁止】
- 不要 markdown
- 不要除了上面 5 个 section 之外的任何文字
"""
    user_msg = f"""【题目】
{question.get("text", "")}

【候选人的回答（来源：{req.source}）】
{req.user_text}
"""
    if reference:
        user_msg += f"""
【参考答案（{reference['template_name']}）— 用作对照标准】
{reference['content']}
"""

    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": user_msg},
    ]


@router.get("")
def list_analyses(question_id: str | None = None, min_score: int | None = None, limit: int = 0):
    if question_id:
        items = analyses_repo.list_for_question(question_id)
    else:
        items = analyses_repo.list_all(limit=limit or 100)
    if min_score is not None:
        items = [a for a in items if (a.score or 0) >= min_score]
    return {"items": [a.model_dump() for a in items], "total": len(items)}


@router.get("/{analysis_id}")
def get_analysis(analysis_id: str):
    a = analyses_repo.get(analysis_id)
    if not a:
        raise HTTPException(404, "analysis not found")
    return a.model_dump()


@router.delete("/{analysis_id}")
def delete_analysis(analysis_id: str):
    snap = analyses_repo.delete(analysis_id)
    if not snap:
        raise HTTPException(404, "analysis not found")
    return {"ok": True, "snapshot": snap.model_dump()}


@router.post(":stream")
async def create_stream(req: AnalysisCreateStream):
    """流式生成评估 — 服务端不持久化，前端流式接收完成后再调 POST /analyses 写入"""
    from server.routers.llm import _resolve, _build_headers

    q = questions_repo.get_question(req.question_id)
    if not q:
        raise HTTPException(404, "question not found")

    target = _resolve(None, None)
    headers = _build_headers(target)
    messages = _build_analyze_messages(q, req)
    body = {
        "model": target.model,
        "messages": messages,
        "stream": True,
        "temperature": 0.4,
    }

    async def event_stream():
        try:
            timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)
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


class AnalysisCreate(BaseModel):
    question_id: str
    user_text: str
    source: str = "manual"
    against_answer_id: str | None = None
    score: int | None = None
    strengths: list[str] = []
    gaps: list[str] = []
    suggestions: str = ""
    topics_touched: list[str] = []


@router.post("")
def create_analysis(body: AnalysisCreate):
    """前端流式接收完后调用，把解析后的结构化数据持久化"""
    if not questions_repo.get_question(body.question_id):
        raise HTTPException(404, "question not found")
    a = analyses_repo.create({
        "question_id": body.question_id,
        "answer_id": body.against_answer_id,
        "user_text": body.user_text,
        "source": body.source,
        "score": body.score,
        "strengths": body.strengths,
        "gaps": body.gaps,
        "suggestions": body.suggestions,
        "topics_touched": body.topics_touched,
    })
    return a.model_dump()


@router.post("/restore")
def restore_analysis(snapshot: dict):
    from server.storage.analyses_repo import Analysis
    a = analyses_repo.restore(Analysis(**snapshot))
    return a.model_dump()
