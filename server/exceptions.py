"""领域异常层级

按 python-errors-reliability 推荐：
- 每个 boundary 抛具体类型，HTTP 层负责翻译成 status
- 保留 cause chain (`raise X from e`)
- 调用方可以根据类型决定 retry/log/abort
"""
from __future__ import annotations


class JobOsError(Exception):
    """所有自定义异常的基类"""


class ConfigError(JobOsError):
    """启动配置错误（DB 不可写 / snapshot 缺失 / 必需 env 缺失）"""


class NotFoundError(JobOsError):
    """资源不存在 — HTTP 404"""


class ValidationError(JobOsError):
    """请求参数无效 — HTTP 400"""


class UpstreamError(JobOsError):
    """上游服务错误（LLM / ASR / 火山引擎）— HTTP 502"""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class StorageError(JobOsError):
    """SQLite 操作失败 — HTTP 500"""
