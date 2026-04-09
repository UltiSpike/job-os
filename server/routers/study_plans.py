"""Study plans + job profile extraction + interview topic feedback.

POST /jobs/{href}:extract-requirements   LLM 抽 JD 需求
POST /study-plans                         给一组 target jobs 算一份 plan snapshot
GET  /study-plans/{id}
GET  /study-plans?resume_profile_id=...

POST /interview-topics                    记录某次面试命中的 lessons
GET  /interview-topics?interview_id=...
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.storage import (
    curriculum_repo,
    job_profiles_repo,
    jobs_table_repo,
    llm_presets_repo,
    resume_profiles_repo,
    study_plans_repo,
)
from server.storage.base import now_iso, transaction
from server.storage.db import get_conn

router = APIRouter(prefix="/api/v1", tags=["study-plans"])


# ─── module keyword 映射 (用于 study plan 算分) ───
# MVP 先硬编码 K8s track 的两个 module。后续可以挪进 lessons 元数据。
MODULE_KEYWORDS: dict[str, list[str]] = {
    "k8s-core-controllers": [
        "deployment", "statefulset", "daemonset", "job", "cronjob",
        "pod", "controller", "reconcile", "operator", "crd",
        "informer", "list-watch", "owner", "finalizer",
    ],
    "k8s-networking": [
        "service", "ingress", "gateway", "kube-proxy", "iptables", "ipvs",
        "endpointslice", "endpoints", "coredns", "dns",
        "networkpolicy", "cni", "calico", "cilium", "flannel",
        "ebpf", "vxlan", "bgp",
    ],
}


# ─── job profile extraction ───

JD_PROMPT = """从下面的岗位 JD 里抽取出'对候选人的技术要求'，输出严格 JSON（不要 markdown fence）：
{
  "required_skills": ["<硬性要求的关键词，按重要性排序>"],
  "nice_to_have": ["<加分项>"],
  "scenarios": ["<这个岗位会面对的典型场景，每条一句话>"]
}

JD：
---
{jd}
---
"""


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"no JSON in LLM output: {text[:200]}")
    return json.loads(text[start : end + 1])


async def _call_llm(prompt: str) -> str:
    preset = llm_presets_repo.get_active()
    if not preset:
        raise HTTPException(400, "no active LLM preset; configure one first")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {preset.api_key}",
    }
    body = {
        "model": preset.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{preset.base_url.rstrip('/')}/chat/completions",
            headers=headers, json=body,
        )
    if r.status_code >= 400:
        raise HTTPException(502, f"LLM upstream {r.status_code}: {r.text[:300]}")
    data = r.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


@router.post("/jobs/{href:path}:extract-requirements")
async def extract_job_requirements(href: str):
    job = jobs_table_repo.get(href)
    if not job:
        raise HTTPException(404, "job not found")
    jd = (job.jd if hasattr(job, "jd") else None) or ""
    if not jd.strip():
        raise HTTPException(400, "job has no JD content")
    raw = await _call_llm(JD_PROMPT.replace("{jd}", jd[:6000]))
    try:
        parsed = _extract_json(raw)
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(502, f"LLM returned invalid JSON: {e}")
    return job_profiles_repo.upsert(
        job_href=href,
        required_skills=parsed.get("required_skills") or [],
        nice_to_have=parsed.get("nice_to_have") or [],
        scenarios=parsed.get("scenarios") or [],
        raw=raw,
    )


# ─── study plan computation ───

class StudyPlanIn(BaseModel):
    resume_profile_id: str
    target_job_hrefs: list[str]


def _normalize(s: str) -> str:
    return re.sub(r"[\s\-_]", "", s.lower())


def _compute_priorities(
    resume_skills: list[str],
    job_profiles: list[dict],
) -> tuple[dict[str, float], str]:
    """Returns (module_priorities, rationale).

    Score per module = (#jobs requiring keywords in module) * (1 + 0.5 * gap_factor)
    gap_factor = fraction of those keywords NOT in user's resume_skills.
    """
    user_set = {_normalize(s) for s in resume_skills}
    rationale_lines = []
    priorities: dict[str, float] = {}
    for module_slug, keywords in MODULE_KEYWORDS.items():
        kw_norm = [_normalize(k) for k in keywords]
        jobs_hit = 0
        hit_kws: set[str] = set()
        for jp in job_profiles:
            req = [_normalize(s) for s in (jp.get("required_skills") or [])]
            this_hit = {k for k in kw_norm if any(k in r or r in k for r in req)}
            if this_hit:
                jobs_hit += 1
                hit_kws |= this_hit
        if not jobs_hit:
            priorities[module_slug] = 0.0
            continue
        gap_kws = [k for k in hit_kws if k not in user_set]
        gap_factor = len(gap_kws) / max(1, len(hit_kws))
        score = round(jobs_hit * (1 + 0.5 * gap_factor), 2)
        priorities[module_slug] = score
        rationale_lines.append(
            f"{module_slug}: {jobs_hit} 个目标岗位涉及，缺口率 {int(gap_factor*100)}% → {score}"
        )
    return priorities, "\n".join(rationale_lines) or "no overlap with target jobs"


@router.post("/study-plans")
def create_study_plan(body: StudyPlanIn):
    profile = resume_profiles_repo.get(body.resume_profile_id)
    if not profile:
        raise HTTPException(404, "resume profile not found")
    job_profiles = job_profiles_repo.list_for_hrefs(body.target_job_hrefs)
    if not job_profiles:
        # 没有 job_profile 也可以建一份空 plan，提示去 extract
        priorities, rationale = {}, "no job profiles available — run :extract-requirements first"
    else:
        priorities, rationale = _compute_priorities(
            profile.get("skills") or [], job_profiles
        )
    return study_plans_repo.create(
        resume_profile_id=body.resume_profile_id,
        target_job_hrefs=body.target_job_hrefs,
        module_priorities=priorities,
        rationale=rationale,
    )


@router.get("/study-plans")
def list_plans(resume_profile_id: str | None = None):
    if not resume_profile_id:
        raise HTTPException(400, "resume_profile_id query param is required")
    return {"items": study_plans_repo.list_for_profile(resume_profile_id)}


@router.get("/study-plans/{pid}")
def get_plan(pid: str):
    p = study_plans_repo.get(pid)
    if not p:
        raise HTTPException(404, "plan not found")
    return p


# ─── interview topic feedback ───

class InterviewTopicIn(BaseModel):
    interview_id: int
    lesson_slug: str
    asked_depth: int = 1
    note: str = ""


@router.post("/interview-topics")
def add_interview_topic(body: InterviewTopicIn):
    if not curriculum_repo.get_lesson(body.lesson_slug):
        raise HTTPException(404, "lesson not found")
    with transaction() as conn:
        cur = conn.execute(
            """INSERT INTO interview_topics
               (interview_id, lesson_slug, asked_depth, note, at)
               VALUES (?, ?, ?, ?, ?)""",
            (body.interview_id, body.lesson_slug, body.asked_depth, body.note, now_iso()),
        )
        new_id = cur.lastrowid
    return {"id": new_id, **body.model_dump()}


@router.get("/interview-topics")
def list_interview_topics(interview_id: int | None = None, lesson_slug: str | None = None):
    where, params = [], []
    if interview_id is not None:
        where.append("interview_id = ?"); params.append(interview_id)
    if lesson_slug:
        where.append("lesson_slug = ?"); params.append(lesson_slug)
    sql = "SELECT * FROM interview_topics"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY at DESC"
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.delete("/interview-topics/{topic_id}")
def delete_interview_topic(topic_id: int):
    with transaction() as conn:
        conn.execute("DELETE FROM interview_topics WHERE id = ?", (topic_id,))
    return {"ok": True}
