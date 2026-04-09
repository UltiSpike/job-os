"""Repo 基础设施 — 事务、JSON 列处理、行→模型 转换

设计原则：
- 不引入 ORM（单文件 SQLite + 简单 schema 不需要）
- 但提供一致的写入路径，强制 pydantic 校验
- 多步写入必须用 transaction()，不能多次开 conn
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Type, TypeVar

from pydantic import BaseModel

from .db import DB_PATH, get_conn

T = TypeVar("T", bound=BaseModel)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """跨多个写入的事务。优先用这个而不是多次 get_conn()。

    用法：
        with transaction() as conn:
            conn.execute("INSERT ...")
            conn.execute("UPDATE ...")
            # 任何异常 → 整个事务回滚
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def hydrate_row(row: sqlite3.Row | None, model: Type[T], json_fields: Iterable[str] = ()) -> T | None:
    """sqlite Row → pydantic 模型（自动反序列化指定 JSON 字段）"""
    if row is None:
        return None
    data = dict(row)
    for field in json_fields:
        v = data.get(field)
        if v and isinstance(v, str):
            try:
                data[field] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                pass
    return model(**data)


def hydrate_rows(rows: Iterable[sqlite3.Row], model: Type[T], json_fields: Iterable[str] = ()) -> list[T]:
    return [hydrate_row(r, model, json_fields) for r in rows if r is not None]


def serialize_for_db(data: dict, json_fields: Iterable[str]) -> dict:
    """把 dict 里指定字段（list/dict）序列化成 JSON 字符串供 INSERT/UPDATE"""
    out = dict(data)
    for field in json_fields:
        v = out.get(field)
        if v is not None and not isinstance(v, str):
            out[field] = json.dumps(v, ensure_ascii=False)
    return out


def patch_row(conn: sqlite3.Connection, table: str, key_col: str, key_val: Any, patch: dict, allowed: Iterable[str], json_fields: Iterable[str] = (), touch_field: str = "updated_at") -> None:
    """通用 UPDATE — 只更新 allowed 列表里的字段，自动 touch updated_at"""
    serialized = serialize_for_db(patch, json_fields)
    fields = []
    params: list[Any] = []
    for k in allowed:
        if k in serialized:
            fields.append(f"{k} = ?")
            params.append(serialized[k])
    if not fields:
        return
    if touch_field:
        fields.append(f"{touch_field} = ?")
        params.append(now_iso())
    params.append(key_val)
    conn.execute(f"UPDATE {table} SET {', '.join(fields)} WHERE {key_col} = ?", params)
