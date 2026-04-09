"""结构化日志 + request id 关联

按 python-runtime-operations 推荐：
- 一致的 severity 级别
- 单行结构化输出（key=value 形式，便于 grep / parse）
- request_id 通过 contextvar 传播
- 启动时配置一次，所有 router 共享
"""
from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

# 跨 async 任务传播的 request id
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(rid: str | None = None) -> str:
    rid = rid or uuid.uuid4().hex[:12]
    _request_id.set(rid)
    return rid


def get_request_id() -> str | None:
    return _request_id.get()


class StructuredFormatter(logging.Formatter):
    """单行 key=value 输出 — 比纯文本可解析，比 JSON 更易读"""

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, "%H:%M:%S")
        rid = get_request_id() or "-"
        base = f"{ts} {record.levelname[0]} [{record.name}] rid={rid} {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        # 附加 extra 字段
        skip = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "taskName",
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in skip and not k.startswith("_")}
        if extras:
            kv = " ".join(f"{k}={v!r}" for k, v in extras.items())
            base += f" | {kv}"
        return base


def configure_logging(level: str = "INFO") -> None:
    """启动时调一次"""
    root = logging.getLogger()
    # 清掉 uvicorn / fastapi 默认 handler，避免重复输出
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root.addHandler(handler)
    root.setLevel(level)
    # uvicorn 的 access log 太啰嗦，单独降级
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
