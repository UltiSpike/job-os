"""LLM presets — 从 /llm/presets 提到顶级 /llm-presets"""
from __future__ import annotations

from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.storage import llm_presets_repo

router = APIRouter(prefix="/api/v1/llm-presets", tags=["llm-presets"])


def _mask_extra_headers(raw: str) -> str:
    """extra_headers 常被用来塞第二个凭证（x-api-key / Authorization），展示时值必须打码。"""
    out: list[str] = []
    for line in (raw or "").splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if not k or not v:
            continue
        shown = f"{v[:2]}…{v[-2:]}" if len(v) > 6 else "***"
        out.append(f"{k}: {shown}")
    return "\n".join(out)


def _host(url: str) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""


class PresetCreate(BaseModel):
    name: str
    base_url: str
    model: str
    api_key: str = ""
    extra_headers: str = ""


class PresetPatch(BaseModel):
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    extra_headers: str | None = None


def _mask(p) -> dict:
    return {
        "name": p.name,
        "base_url": p.base_url,
        "model": p.model,
        "api_key": "",
        "api_key_masked": (f"{p.api_key[:6]}…{p.api_key[-4:]}" if p.api_key and len(p.api_key) > 12 else "***" if p.api_key else ""),
        # 原始 extra_headers 不回前端；只给脱敏展示值，前端留空即“保留原值”
        "extra_headers": "",
        "extra_headers_masked": _mask_extra_headers(p.extra_headers),
        "is_active": bool(p.is_active),
    }


@router.get("")
def list_presets():
    items = llm_presets_repo.list_all()
    active = llm_presets_repo.get_active()
    return {
        "items": [_mask(p) for p in items],
        "active": active.name if active else None,
    }


@router.get("/{name}")
def get_preset(name: str):
    p = llm_presets_repo.get(name)
    if not p:
        raise HTTPException(404, "preset not found")
    return _mask(p)


@router.post("")
def create_preset(body: PresetCreate):
    llm_presets_repo.upsert(body.name, body.base_url, body.model, body.api_key, body.extra_headers)
    if not llm_presets_repo.get_active():
        llm_presets_repo.activate(body.name)
    return {"ok": True}


@router.patch("/{name}")
def patch_preset(name: str, body: PresetPatch):
    existing = llm_presets_repo.get(name)
    if not existing:
        raise HTTPException(404, "preset not found")
    new_base = body.base_url if body.base_url is not None else existing.base_url
    # 安全约束：换 base_url 的 host 等于换目的地，必须重新提供 api_key，
    # 否则等于允许调用方把已保存的密钥静默指向自己的地址（再触发 :test 就外泄了）。
    if (
        existing.api_key
        and body.base_url is not None
        and _host(new_base) != _host(existing.base_url)
        and not (body.api_key or "").strip()
    ):
        raise HTTPException(400, "修改 Base URL 主域名时必须重新填写 API Key（已保存的密钥不会发往新地址）")
    llm_presets_repo.upsert(
        name,
        new_base,
        body.model if body.model is not None else existing.model,
        body.api_key or "",  # 空 → 保留旧值（repo 里处理）
        body.extra_headers if body.extra_headers is not None else existing.extra_headers,
    )
    return {"ok": True}


@router.delete("/{name}")
def delete_preset(name: str):
    llm_presets_repo.delete(name)
    return {"ok": True}


@router.post("/{name}:activate")
def activate_preset(name: str):
    p = llm_presets_repo.activate(name)
    if not p:
        raise HTTPException(404, "preset not found")
    return {"ok": True, "active": name}


@router.post("/{name}:test")
async def test_preset(name: str):
    p = llm_presets_repo.get(name)
    if not p:
        raise HTTPException(404, "preset not found")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {p.api_key}"}
    for line in (p.extra_headers or "").split("\n"):
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        if k.strip() and v.strip():
            headers[k.strip()] = v.strip()
    body = {
        "model": p.model,
        "messages": [{"role": "user", "content": "用一个字回答：1+1=?"}],
        "stream": False,
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{p.base_url.rstrip('/')}/chat/completions", headers=headers, json=body)
        if r.status_code >= 400:
            return {"ok": False, "status": r.status_code, "error": r.text[:300]}
        data = r.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"ok": True, "answer": text}
    except Exception as e:
        return {"ok": False, "error": str(e)}
