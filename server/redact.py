"""敏感字段脱敏 — API 响应 / 导出 / 日志统一走这里

背景：LLM api_key、火山 ASR apiAccessKey 都存在本地 SQLite 里，
任何对外返回 dict 的接口（导出、备份、配置读取）都必须先过一遍脱敏，
否则等于把本地密钥库直接暴露给调用方。
"""
from __future__ import annotations

from typing import Any

# 命中这些字段名（大小写不敏感）的值一律视为密钥
_SECRET_HINT = ("api_key", "apikey", "access_key", "accesskey", "secret", "token", "password", "passwd", "authorization")

PLACEHOLDER = "***"


def is_secret_field(name: str) -> bool:
    """字段名是否承载密钥。`*_masked` 是已经脱敏好的展示值，不再处理。"""
    low = (name or "").lower()
    if low.endswith("_masked"):
        return False
    return any(hint in low for hint in _SECRET_HINT)


def redact_secrets(value: Any, placeholder: str = PLACEHOLDER) -> Any:
    """递归脱敏 dict 中的密钥字段（list 内元素同样处理）。"""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if is_secret_field(str(k)) and v not in (None, "", [], {}):
                out[k] = placeholder
            else:
                out[k] = redact_secrets(v, placeholder)
        return out
    if isinstance(value, (list, tuple)):
        return [redact_secrets(v, placeholder) for v in value]
    return value
