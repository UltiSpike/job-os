"""ASR 转写 + 实时桥接路由"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

import httpx
import websockets
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from server.services.asr_volc import (
    build_audio_frame,
    build_full_client_request,
    parse_server_text,
)

logger = logging.getLogger("asr")
logger.setLevel(logging.INFO)
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(levelname)s asr] %(message)s"))
    logger.addHandler(h)

router = APIRouter(prefix="/api/v1", tags=["asr"])


@router.post("/asr/test")
async def test_asr_config(cfg: dict):
    """快速验证火山 ASR 配置是否能握手成功（不发音频，只 connect + close）

    任何空字段会从 settings.asr 里 fallback，方便前端「点测试就能用」。
    """
    from server.storage import settings_repo
    cfg = cfg or {}
    saved = settings_repo.get_setting("asr") or {}

    caller_ws = (cfg.get("wsUrl") or "").strip()
    saved_ws = (saved.get("wsUrl") or "").strip()
    ws_url = caller_ws or saved_ws

    # 安全约束：已保存的凭据只能发往已保存的地址（否则等于把密钥交给调用方指定的目标）
    if caller_ws and caller_ws != saved_ws:
        app_id = (cfg.get("apiAppId") or "").strip()
        access_key = (cfg.get("apiAccessKey") or "").strip()
        if not access_key:
            return {
                "ok": False,
                "stage": "config",
                "error": "测试自定义 wsUrl 时必须同时提供 apiAppId/apiAccessKey（已保存的凭据不会发往新地址）",
            }
    else:
        app_id = (cfg.get("apiAppId") or "").strip() or saved.get("apiAppId", "")
        access_key = (cfg.get("apiAccessKey") or "").strip() or saved.get("apiAccessKey", "")

    if not ws_url:
        return {"ok": False, "stage": "config", "error": "wsUrl required"}
    if not app_id or not access_key:
        return {"ok": False, "stage": "config", "error": "apiAppId/apiAccessKey required"}

    cfg = {
        "wsUrl": ws_url,
        "apiAppId": app_id,
        "apiAccessKey": access_key,
        "apiResourceId": (cfg.get("apiResourceId") or "").strip() or saved.get("apiResourceId", ""),
        "connectId": cfg.get("connectId") or "",
    }

    headers = {
        "X-Api-App-Key":     cfg.get("apiAppId", ""),       # 火山的 App-Key 字段值是 APP ID
        "X-Api-Access-Key":  cfg.get("apiAccessKey", ""),
        "X-Api-Resource-Id": cfg.get("apiResourceId") or "volc.bigasr.sauc.duration",
        "X-Api-Connect-Id":  cfg.get("connectId") or str(uuid.uuid4()),
    }
    try:
        upstream = await asyncio.wait_for(
            websockets.connect(ws_url, additional_headers=headers, max_size=4 * 1024 * 1024),
            timeout=10,
        )
    except asyncio.TimeoutError:
        return {"ok": False, "stage": "connect", "error": "timeout"}
    except Exception as e:
        # 兼容 websockets 15.x 的 InvalidStatus / 13.x 的 InvalidStatusCode
        msg = f"{type(e).__name__}: {e}"
        if hasattr(e, "response"):  # InvalidStatus
            try:
                msg += f" | status={e.response.status_code}"
            except Exception:
                pass
        elif hasattr(e, "status_code"):  # InvalidStatusCode (老版)
            msg += f" | status={e.status_code}"
        return {"ok": False, "stage": "handshake" if "Invalid" in type(e).__name__ else "connect", "error": msg}

    try:
        await upstream.send(build_full_client_request(cfg))
        try:
            msg = await asyncio.wait_for(upstream.recv(), timeout=5)
            if isinstance(msg, bytes):
                text = parse_server_text(msg)
                return {"ok": True, "first_response": text or "(binary, no text)"}
            return {"ok": True, "first_response": str(msg)[:200]}
        except asyncio.TimeoutError:
            return {"ok": True, "first_response": None, "note": "connected but no response in 5s (可能正常)"}
    finally:
        try:
            await upstream.close()
        except Exception:
            pass


@router.post("/asr/transcribe")
async def asr_transcribe(
    file: UploadFile = File(...),
    model: str = Form(...),
    language: str = Form("zh"),
    x_target_base_url: str = Header(""),
    x_target_api_key: str = Header(""),
    x_target_extra_headers: str = Header(""),
):
    if not x_target_base_url:
        raise HTTPException(400, "X-Target-Base-Url required")
    data = await file.read()
    files = {"file": (file.filename or "audio.webm", data, file.content_type or "application/octet-stream")}
    form = {"model": model, "language": language}
    headers = {}
    if x_target_api_key:
        headers["Authorization"] = f"Bearer {x_target_api_key}"
    for line in (x_target_extra_headers or "").split("\n"):
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if k and v:
            headers[k] = v
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(
            f"{x_target_base_url.rstrip('/')}/audio/transcriptions",
            headers=headers,
            data=form,
            files=files,
        )
    if r.status_code >= 400:
        return JSONResponse(status_code=r.status_code, content={"error": r.text[:500]})
    out = r.json()
    return {"id": f"asr_{uuid.uuid4().hex[:8]}", "text": out.get("text", ""), "raw": out}


@router.websocket("/asr/ws")
async def asr_ws_bridge(ws: WebSocket):
    """浏览器 ↔ BFF ↔ 火山引擎 实时 ASR 桥接"""
    await ws.accept()
    logger.info("client connected")
    upstream = None
    try:
        init_raw = await ws.receive_text()
        try:
            init = json.loads(init_raw)
        except json.JSONDecodeError as e:
            logger.warning(f"invalid init JSON: {e}")
            await ws.send_text(json.dumps({"type": "error", "message": f"init must be valid JSON: {e}"}))
            await ws.close()
            return

        if init.get("type") != "init":
            logger.warning(f"first message not init: type={init.get('type')!r}")
            await ws.send_text(json.dumps({"type": "error", "message": "first message must be type=init"}))
            await ws.close()
            return

        caller_cfg = init.get("config") or {}
        from server.storage import settings_repo

        saved = settings_repo.get_setting("asr") or {}

        # 目的地与凭据以服务端保存的配置为准；浏览器的 init.config 只作为补充参数。
        # 这样已保存的 apiAccessKey 永远不会被发往调用方指定的地址。
        ws_url = (saved.get("wsUrl") or "").strip() or (caller_cfg.get("wsUrl") or "").strip()
        app_id = saved.get("apiAppId") or caller_cfg.get("apiAppId") or ""
        access_key = saved.get("apiAccessKey") or caller_cfg.get("apiAccessKey") or ""

        if not ws_url:
            logger.warning("wsUrl missing")
            await ws.send_text(json.dumps({"type": "error", "message": "ASR 未配置，请先在设置里保存 WebSocket URL"}))
            await ws.close()
            return

        if not app_id or not access_key:
            logger.warning("apiAppId/apiAccessKey missing")
            await ws.send_text(json.dumps({
                "type": "error",
                "message": "ASR 未配置，请先在设置里保存 App ID / Access Token",
            }))
            await ws.close()
            return

        cfg = {
            **caller_cfg,
            **{k: v for k, v in saved.items() if k != "apiAccessKey"},
            "wsUrl": ws_url,
            "apiAppId": app_id,
            "apiAccessKey": access_key,
        }

        headers = {
            "X-Api-App-Key":     cfg.get("apiAppId", ""),
            "X-Api-Access-Key":  cfg.get("apiAccessKey", ""),
            "X-Api-Resource-Id": cfg.get("apiResourceId", "volc.bigasr.sauc.duration"),
            "X-Api-Connect-Id":  cfg.get("connectId") or str(uuid.uuid4()),
        }

        logger.info(f"connecting upstream: {ws_url} resource={headers['X-Api-Resource-Id']}")
        try:
            upstream = await websockets.connect(
                ws_url,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=20,
                max_size=4 * 1024 * 1024,
            )
        except Exception as e:
            logger.error(f"upstream connect failed: {type(e).__name__}: {e}")
            await ws.send_text(json.dumps({
                "type": "upstream_error",
                "message": f"upstream connect failed: {type(e).__name__}: {e}",
            }))
            await ws.close()
            return

        logger.info("upstream connected, sending full_client_request")
        init_frame = build_full_client_request(cfg)
        # 只校验帧可解压，不打印内容（避免口述正文进日志）
        import gzip as _gz
        try:
            _gz.decompress(init_frame[8:])  # 跳过 header(4) + size(4)
            logger.info(f"INIT frame total={len(init_frame)} header={init_frame[:8].hex()}")
        except Exception as e:
            logger.warning(f"failed to decode init frame: {e}")
        await upstream.send(init_frame)
        await ws.send_text(json.dumps({"type": "bridge_open"}))
        upstream_msg_count = 0
        client_audio_count = 0

        async def from_upstream():
            nonlocal upstream_msg_count
            try:
                async for msg in upstream:
                    upstream_msg_count += 1
                    if isinstance(msg, bytes):
                        text = parse_server_text(msg)
                        # 前 5 个回包详细 dump
                        if upstream_msg_count <= 5:
                            try:
                                import struct as _st
                                b1, b2 = msg[1], msg[2]
                                mtype = (b1 >> 4) & 0x0F
                                flags = b1 & 0x0F
                                ser = (b2 >> 4) & 0x0F
                                comp = b2 & 0x0F
                                # 尝试解 payload
                                if flags & 0x1:
                                    seq = _st.unpack(">i", msg[4:8])[0]
                                    psize = _st.unpack(">I", msg[8:12])[0]
                                    payload = msg[12:12 + psize]
                                else:
                                    seq = None
                                    psize = _st.unpack(">I", msg[4:8])[0]
                                    payload = msg[8:8 + psize]
                                if comp == 0x1:
                                    import gzip as _gz2
                                    payload = _gz2.decompress(payload)
                                payload_str = payload.decode('utf-8', 'replace')[:600]
                                logger.info(
                                    f"upstream→client #{upstream_msg_count} type={mtype:#x} flags={flags:#x} "
                                    f"ser={ser:#x} comp={comp:#x} seq={seq} psize={psize} payload={payload_str}"
                                )
                            except Exception as e:
                                logger.warning(f"  parse fail: {e}, raw_hex={msg[:64].hex()}")
                        else:
                            logger.info(f"upstream→client #{upstream_msg_count} bytes={len(msg)} text={text!r}")
                        if text:
                            try:
                                await ws.send_text(json.dumps({"type": "partial", "text": text}))
                            except Exception as se:
                                logger.warning(f"send to client failed: {se}")
                                break
                    else:
                        logger.info(f"upstream→client #{upstream_msg_count} text={msg[:300]}")
                        try:
                            await ws.send_text(msg)
                        except Exception:
                            break
                logger.info(f"upstream stream ended after {upstream_msg_count} msgs")
            except websockets.ConnectionClosed as e:
                logger.warning(f"upstream closed: code={e.code} reason={e.reason!r}")
                try:
                    await ws.send_text(json.dumps({
                        "type": "upstream_error",
                        "message": f"upstream closed: code={e.code} reason={e.reason}",
                    }))
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"upstream loop error: {type(e).__name__}: {e}")
                try:
                    await ws.send_text(json.dumps({"type": "upstream_error", "message": str(e)}))
                except Exception:
                    pass

        async def from_client():
            nonlocal client_audio_count
            while True:
                try:
                    packet = await ws.receive()
                except Exception as e:
                    logger.warning(f"client receive error: {e}")
                    break
                if packet.get("type") == "websocket.disconnect":
                    logger.info("client disconnected")
                    try:
                        await upstream.send(build_audio_frame(b"", 0, is_last=True))
                    except Exception:
                        pass
                    break
                if packet.get("bytes") is not None:
                    client_audio_count += 1
                    audio_bytes = packet["bytes"]
                    if client_audio_count <= 3:
                        # 前三包详细 dump 帮助验证 PCM 格式
                        sample_int16 = []
                        if len(audio_bytes) >= 8:
                            import struct
                            sample_int16 = list(struct.unpack("<4h", audio_bytes[:8]))
                        logger.info(
                            f"client→upstream audio #{client_audio_count} bytes={len(audio_bytes)} "
                            f"first8_hex={audio_bytes[:8].hex()} first4_int16={sample_int16}"
                        )
                    elif client_audio_count % 50 == 0:
                        logger.info(f"client→upstream audio #{client_audio_count} bytes={len(audio_bytes)}")
                    try:
                        frame = build_audio_frame(audio_bytes, 0, is_last=False)
                        if client_audio_count <= 2:
                            logger.info(f"  → frame_total={len(frame)} header_hex={frame[:8].hex()}")
                        await upstream.send(frame)
                    except Exception as e:
                        logger.error(f"upstream send failed: {e}")
                        break
                elif packet.get("text") is not None:
                    txt = packet["text"]
                    logger.info(f"client→bridge text: {txt[:100]}")
                    if txt == "__END__":
                        try:
                            await upstream.send(build_audio_frame(b"", 0, is_last=True))
                        except Exception:
                            pass
                        break
                    continue

        t1 = asyncio.create_task(from_upstream(), name="from_upstream")
        t2 = asyncio.create_task(from_client(), name="from_client")
        done, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            logger.info(f"task done first: {t.get_name()}")
        for t in pending:
            t.cancel()
        logger.info(f"bridge closing: upstream_msgs={upstream_msg_count} client_audio={client_audio_count}")
    except WebSocketDisconnect:
        logger.info("client websocket disconnect")
    except Exception as e:
        logger.error(f"bridge error: {type(e).__name__}: {e}", exc_info=True)
        try:
            await ws.send_text(json.dumps({"type": "bridge_error", "message": str(e)}))
        except Exception as send_err:
            logger.warning(f"failed to notify client of bridge error: {send_err}")
    finally:
        if upstream is not None:
            try:
                await upstream.close()
            except Exception as e:
                logger.warning(f"upstream close failed: {e}")
        try:
            await ws.close()
        except Exception as e:
            logger.debug(f"client ws close failed (likely already closed): {e}")
