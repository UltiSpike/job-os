"""jobs 表数据访问 — 取代 snapshot.json 内存读取"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from .base import hydrate_row, hydrate_rows, transaction
from .db import get_conn


class Job(BaseModel):
    href: str
    title: str
    company: str | None = None
    area: str | None = None
    salary: str | None = None
    experience: str | None = None
    jd: str | None = None
    tier: str | None = None
    final_score: float = 0.0
    cluster_hits: list[dict] = Field(default_factory=list)
    source: str | None = None
    source_keyword: str | None = None
    scraped_at: str | None = None


JSON_FIELDS = ("cluster_hits",)


# ─── 读 ───

def list_all(tier: str | None = None, limit: int = 0, offset: int = 0) -> list[Job]:
    sql = "SELECT * FROM jobs WHERE 1=1"
    params: list[Any] = []
    if tier:
        sql += " AND tier = ?"
        params.append(tier)
    sql += " ORDER BY tier ASC, final_score DESC"
    if limit:
        sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return hydrate_rows(rows, Job, json_fields=JSON_FIELDS)


def get(href: str) -> Job | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE href = ?", (href,)).fetchone()
    return hydrate_row(row, Job, json_fields=JSON_FIELDS)


def search(query: str, limit: int = 50) -> list[Job]:
    """模糊搜索：title / company / area / jd"""
    q = f"%{query}%"
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM jobs
               WHERE title LIKE ? OR company LIKE ? OR area LIKE ? OR jd LIKE ?
               ORDER BY final_score DESC LIMIT ?""",
            (q, q, q, q, limit),
        ).fetchall()
    return hydrate_rows(rows, Job, json_fields=JSON_FIELDS)


def count_by_tier() -> dict[str, int]:
    with get_conn() as conn:
        rows = conn.execute("SELECT tier, COUNT(*) AS n FROM jobs GROUP BY tier").fetchall()
    return {r["tier"] or "?": r["n"] for r in rows}


def total() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]


# ─── 写 ───

def upsert(job: dict):
    """爬虫产出新数据时调"""
    with transaction() as conn:
        conn.execute(
            """INSERT INTO jobs (href, title, company, area, salary, experience, jd, tier, final_score, cluster_hits, source, source_keyword, scraped_at, raw)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(href) DO UPDATE SET
                 title=excluded.title, company=excluded.company, area=excluded.area,
                 salary=excluded.salary, experience=excluded.experience, jd=excluded.jd,
                 tier=excluded.tier, final_score=excluded.final_score, cluster_hits=excluded.cluster_hits,
                 source=excluded.source, source_keyword=excluded.source_keyword,
                 scraped_at=excluded.scraped_at, raw=excluded.raw""",
            (
                job["href"],
                job.get("title", ""),
                job.get("company"),
                job.get("area"),
                job.get("salary"),
                job.get("experience") or job.get("exp"),
                job.get("jd"),
                job.get("tier"),
                float(job.get("final_score") or 0),
                json.dumps(job.get("cluster_hits") or [], ensure_ascii=False),
                job.get("source"),
                job.get("source_keyword"),
                job.get("scraped_at"),
                json.dumps(job, ensure_ascii=False),
            ),
        )
