"""LLM 代理路由 — 多 preset + 当前激活源（走独立表 llm_presets）"""
from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from server.storage import llm_presets_repo, settings_repo

router = APIRouter(prefix="/api/v1", tags=["llm"])


class LLMPreset(BaseModel):
    name: str
    base_url: str
    model: str
    api_key: str
    extra_headers: str | None = ""


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    target: LLMPreset | None = None
    preset: str | None = None  # 用 preset name 选源，None = 用激活的
    messages: list[ChatMessage]
    temperature: float = 0.5
    stream: bool = False


def _build_headers(cfg: LLMPreset) -> dict[str, str]:
    h = {"Content-Type": "application/json", "Authorization": f"Bearer {cfg.api_key}"}
    for line in (cfg.extra_headers or "").split("\n"):
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if k and v:
            h[k] = v
    return h


def _resolve(req_target: LLMPreset | None, preset_name: str | None) -> LLMPreset:
    if req_target:
        return req_target
    if preset_name:
        p = llm_presets_repo.get(preset_name)
        if not p:
            raise HTTPException(404, f"preset '{preset_name}' not found")
        return LLMPreset(name=p.name, base_url=p.base_url, model=p.model, api_key=p.api_key, extra_headers=p.extra_headers)
    active = llm_presets_repo.get_active()
    if active:
        return LLMPreset(name=active.name, base_url=active.base_url, model=active.model, api_key=active.api_key, extra_headers=active.extra_headers)
    raise HTTPException(400, "未配置任何 LLM preset，请先 POST /api/v1/llm/presets")


def _mask_preset(p) -> dict:
    """把 LLMPreset (db model) 序列化成前端 dict + 掩码 api_key"""
    out = {
        "name": p.name,
        "base_url": p.base_url,
        "model": p.model,
        "api_key": "",
        "extra_headers": p.extra_headers,
        "is_active": bool(p.is_active),
    }
    if p.api_key:
        out["api_key_masked"] = f"{p.api_key[:6]}…{p.api_key[-4:]}" if len(p.api_key) > 12 else "***"
    return out


# presets CRUD 已经移到 routers/llm_presets.py /api/v1/llm-presets/*


# ─── chat / test ───

@router.post("/llm/test")
async def test(req: dict | None = None):
    """测试连接"""
    if req and "target" in req:
        target = LLMPreset(**req["target"])
    elif req and "preset" in req:
        target = _resolve(None, req["preset"])
    else:
        target = _resolve(None, None)
    headers = _build_headers(target)
    body = {
        "model": target.model,
        "messages": [{"role": "user", "content": "用一个字回答：1+1=?"}],
        "stream": False,
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{target.base_url.rstrip('/')}/chat/completions",
                headers=headers, json=body,
            )
        if r.status_code >= 400:
            return {"ok": False, "status": r.status_code, "error": r.text[:300]}
        data = r.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"ok": True, "answer": text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _build_context_prompt() -> str:
    """组装"全局上下文" — profile.system_prompt + 当前默认简历摘要"""
    parts = []
    profile = settings_repo.get_setting("profile") or {}
    if isinstance(profile, dict) and profile.get("system_prompt"):
        parts.append(profile["system_prompt"].strip())
    # 默认简历
    from server.storage import resumes_repo
    resumes = resumes_repo.list_resumes()
    default_resume = next((r for r in resumes if r.get("is_default")), None) or (resumes[0] if resumes else None)
    if default_resume and default_resume.get("content"):
        parts.append(
            "【候选人简历（用作答题与评估的事实来源 — 涉及个人经历时优先引用）】\n"
            + default_resume["content"].strip()[:3000]
        )
    return "\n\n".join(parts) if parts else ""


@router.post("/llm/chat")
async def chat(req: ChatRequest):
    target = _resolve(req.target, req.preset)
    headers = _build_headers(target)
    # 自动注入：profile system prompt + 简历摘要
    sys_prompt = _build_context_prompt()
    msgs = [m.model_dump() for m in req.messages]
    if sys_prompt and not any(m.get("role") == "system" for m in msgs):
        msgs.insert(0, {"role": "system", "content": sys_prompt})
    body = {
        "model": target.model,
        "messages": msgs,
        "stream": False,
        "temperature": req.temperature,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{target.base_url.rstrip('/')}/chat/completions",
            headers=headers, json=body,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:500])
    data = r.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return {"id": f"chat_{uuid.uuid4().hex[:8]}", "output_text": text, "raw": data}


@router.post("/llm/chat/stream")
async def chat_stream(req: ChatRequest):
    target = _resolve(req.target, req.preset)
    headers = _build_headers(target)
    sys_prompt = _build_context_prompt()
    msgs = [m.model_dump() for m in req.messages]
    if sys_prompt and not any(m.get("role") == "system" for m in msgs):
        msgs.insert(0, {"role": "system", "content": sys_prompt})
    body = {
        "model": target.model,
        "messages": msgs,
        "stream": True,
        "temperature": req.temperature,
    }

    async def event_stream():
        try:
            # 关闭 httpx 的连接复用和压缩，避免任何中间缓冲
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
                    # 逐字节透传 — 不等行结束，最大化首字节延迟
                    buf = b""
                    async for chunk in r.aiter_bytes():
                        if not chunk:
                            continue
                        buf += chunk
                        # SSE 以 \n\n 结尾分包；按出现的位置切片，立即推送已完整的事件
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
