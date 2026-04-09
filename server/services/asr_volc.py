"""火山引擎实时 ASR 二进制协议"""
from __future__ import annotations

import gzip
import json
import struct
import uuid
from typing import Any


def _pack_header(message_type: int, flags: int, serialization: int, compression: int) -> bytes:
    b0 = (1 << 4) | 1  # version=1, header_size=1(=4bytes)
    b1 = ((message_type & 0x0F) << 4) | (flags & 0x0F)
    b2 = ((serialization & 0x0F) << 4) | (compression & 0x0F)
    b3 = 0
    return bytes([b0, b1, b2, b3])


def _pack_frame(message_type: int, flags: int, serialization: int, compression: int, payload: bytes) -> bytes:
    payload = payload or b""
    header = _pack_header(message_type, flags, serialization, compression)
    return header + struct.pack(">I", len(payload)) + payload


def build_full_client_request(cfg: dict[str, Any]) -> bytes:
    """火山 bigmodel sauc — 三段式请求体 (user / audio / request)"""
    req = {
        "user": {
            "uid": cfg.get("uid") or "web_user",
        },
        "audio": {
            "format": cfg.get("audioFormat", "pcm"),
            "codec": "raw",
            "rate": int(cfg.get("sampleRate", 16000)),
            "bits": 16,
            "channel": 1,
            "language": cfg.get("language", "zh-CN"),
        },
        "request": {
            "reqid": f"req_{uuid.uuid4().hex}",
            "sequence": 1,
            "model_name": cfg.get("modelName", "bigmodel"),
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": True,
            "show_utterances": True,
            "result_type": "full",   # 累积全文（"single" 只返回当前一句会刷掉之前的）
        },
    }
    raw = json.dumps(req, ensure_ascii=False).encode("utf-8")
    payload = gzip.compress(raw)
    # message_type=0x1 (full client request), flags=0, serialization=0x1 (json), compression=0x1 (gzip)
    return _pack_frame(0x1, 0x0, 0x1, 0x1, payload)


def build_audio_frame(audio_bytes: bytes, sequence: int, is_last: bool = False) -> bytes:
    """音频帧 — bigmodel sauc 协议
    - message_type=0x2 (audio request)
    - flags 低位：0x0=正常帧, 0x2=last 帧
    - payload 直接是 raw PCM 字节，**不要 gzip**（服务端按 raw 解码）
    - compression bit 也设为 0x0，明确告诉服务端这是未压缩
    """
    flags = 0x2 if is_last else 0x0
    return _pack_frame(0x2, flags, 0x0, 0x0, audio_bytes or b"")


def parse_server_text(msg: bytes) -> str:
    """解析火山服务端二进制响应帧

    帧结构：
      [byte 0]  version(4b) | header_size(4b)
      [byte 1]  message_type(4b) | flags(4b)
      [byte 2]  serialization(4b) | compression(4b)
      [byte 3]  reserved
      ─────────────────────────────────────────
      message_type=0x9 (full server response) flags=0:
        [4..7]   payload_size (uint32 BE)
        [8..]    payload
      message_type=0x9 flags=0x1 (带 sequence):
        [4..7]   sequence (int32 BE)
        [8..11]  payload_size (uint32 BE)
        [12..]   payload
      message_type=0xf (error):
        [4..7]   error_code (uint32 BE)
        [8..11]  payload_size (uint32 BE)
        [12..]   payload (error message JSON)
    """
    if not msg or len(msg) < 8:
        return ""
    b1, b2 = msg[1], msg[2]
    message_type = (b1 >> 4) & 0x0F
    flags = b1 & 0x0F
    serialization = (b2 >> 4) & 0x0F
    compression = b2 & 0x0F

    # error 帧：bytes 4-7 是 error_code，payload_size 在 8-11
    if message_type == 0xf:
        if len(msg) < 12:
            return ""
        payload_size = struct.unpack(">I", msg[8:12])[0]
        payload = msg[12:12 + payload_size]
    elif flags & 0x1:  # full_server_response 带 sequence
        if len(msg) < 12:
            return ""
        payload_size = struct.unpack(">I", msg[8:12])[0]
        payload = msg[12:12 + payload_size]
    else:
        payload_size = struct.unpack(">I", msg[4:8])[0]
        payload = msg[8:8 + payload_size]
    if compression == 0x1:
        try:
            payload = gzip.decompress(payload)
        except Exception:
            pass
    if serialization == 0x1:
        try:
            data = json.loads(payload.decode("utf-8", "replace"))
            # bigmodel sauc 常见返回路径：
            #   { "result": { "text": "...", "utterances": [...] } }
            #   { "result": [{"text": "..."}] }
            #   { "payload_msg": { "result": ... } }
            result = data.get("result")
            if isinstance(result, dict):
                if result.get("text"):
                    return result["text"]
                utts = result.get("utterances") or []
                if utts and isinstance(utts, list):
                    return "".join(u.get("text", "") for u in utts)
            if isinstance(result, list) and result:
                return result[0].get("text", "")
            if data.get("text"):
                return data["text"]
            pm = data.get("payload_msg") or {}
            if isinstance(pm, dict):
                pr = pm.get("result")
                if isinstance(pr, dict) and pr.get("text"):
                    return pr["text"]
                if isinstance(pr, list) and pr:
                    return pr[0].get("text", "")
            return ""
        except Exception:
            return ""
    if message_type in (0x9,):
        try:
            return payload.decode("utf-8", "replace")
        except Exception:
            return ""
    return ""
