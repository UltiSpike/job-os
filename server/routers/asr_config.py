"""ASR 配置路由 — 从 /settings/asr 提到顶级 /asr-config"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from server.storage import settings_repo

router = APIRouter(prefix="/api/v1/asr-config", tags=["asr-config"])


class ASRConfig(BaseModel):
    wsUrl: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
    apiAppId: str = ""
    apiAccessKey: str = ""
    apiResourceId: str = "volc.bigasr.sauc.duration"
    audioFormat: str = "pcm"


@router.get("")
def get_config():
    saved = settings_repo.get_setting("asr") or {}
    base = ASRConfig().model_dump()
    base.update(saved)
    if base.get("apiAccessKey"):
        k = base["apiAccessKey"]
        base["apiAccessKey_masked"] = f"{k[:6]}…{k[-4:]}" if len(k) > 12 else "***"
    return base


@router.put("")
def put_config(cfg: ASRConfig):
    saved = settings_repo.get_setting("asr") or {}
    data = cfg.model_dump()
    if not data.get("apiAccessKey") and saved.get("apiAccessKey"):
        data["apiAccessKey"] = saved["apiAccessKey"]
    settings_repo.set_setting("asr", data)
    return {"ok": True}


@router.post(":test")
async def test_config(cfg: dict | None = None):
    """测试 ASR 握手 — 接受 dict 是为了允许传部分覆盖字段"""
    import asyncio
    import json
    import uuid as _uuid

    import websockets

    from server.services.asr_volc import build_full_client_request, parse_server_text

    saved = settings_repo.get_setting("asr") or {}
    merged = {}
    base_default = ASRConfig().model_dump()
    for k in base_default:
        merged[k] = (cfg.get(k) if cfg else None) or saved.get(k) or base_default[k]

    ws_url = merged.get("wsUrl") or ""
    if not ws_url:
        return {"ok": False, "stage": "config", "error": "wsUrl required"}
    if not merged.get("apiAppId") or not merged.get("apiAccessKey"):
        return {"ok": False, "stage": "config", "error": "apiAppId/apiAccessKey required"}

    headers = {
        "X-Api-App-Key": merged["apiAppId"],
        "X-Api-Access-Key": merged["apiAccessKey"],
        "X-Api-Resource-Id": merged.get("apiResourceId") or "volc.bigasr.sauc.duration",
        "X-Api-Connect-Id": str(_uuid.uuid4()),
    }
    try:
        upstream = await asyncio.wait_for(
            websockets.connect(ws_url, additional_headers=headers, max_size=4 * 1024 * 1024),
            timeout=10,
        )
    except asyncio.TimeoutError:
        return {"ok": False, "stage": "connect", "error": "timeout"}
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        if hasattr(e, "response"):
            try:
                msg += f" | status={e.response.status_code}"
            except Exception:
                pass
        return {"ok": False, "stage": "handshake" if "Invalid" in type(e).__name__ else "connect", "error": msg}

    try:
        await upstream.send(build_full_client_request(merged))
        try:
            msg = await asyncio.wait_for(upstream.recv(), timeout=5)
            if isinstance(msg, bytes):
                text = parse_server_text(msg)
                return {"ok": True, "first_response": text or "(binary, no text)"}
            return {"ok": True, "first_response": str(msg)[:200]}
        except asyncio.TimeoutError:
            return {"ok": True, "first_response": None, "note": "connected, no response in 5s"}
    finally:
        try:
            await upstream.close()
        except Exception:
            pass
