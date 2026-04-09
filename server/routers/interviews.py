"""面试路由 — 扁平资源，不再嵌套在 /jobs"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.storage import jobs_repo

router = APIRouter(prefix="/api/v1/interviews", tags=["interviews"])


class InterviewCreate(BaseModel):
    job_id: str
    type: str
    time: str | None = None
    location: str | None = ""
    result: str | None = "pending"
    reflection: str | None = ""


class InterviewPatch(BaseModel):
    type: str | None = None
    time: str | None = None
    location: str | None = None
    result: str | None = None
    reflection: str | None = None


@router.get("")
def list_interviews(job_id: str | None = None, result: str | None = None):
    items = jobs_repo.list_interviews(job_id)
    if result:
        items = [i for i in items if i.get("result") == result]
    return {"items": items, "total": len(items)}


@router.get("/{interview_id}")
def get_interview(interview_id: int):
    items = jobs_repo.list_interviews()
    for it in items:
        if it["id"] == interview_id:
            return it
    raise HTTPException(404, "interview not found")


@router.post("")
def create_interview(body: InterviewCreate):
    """创建面试 — 自动联动 stage（在 jobs.py 里 share 同一个逻辑，先在这里调）"""
    from server.storage import job_state_events_repo

    iv_data = body.model_dump(exclude={"job_id"})
    result = jobs_repo.create_interview(body.job_id, iv_data)
    iv_id = result["id"]

    state = jobs_repo.get_job_state(body.job_id)
    advanced_from = None
    if state is None:
        jobs_repo.upsert_job_state(body.job_id, {
            "intent": "target",
            "pipeline_col": "interviewing",
            "_history_interview_id": iv_id,
        })
        advanced_from = "todo"
    else:
        cur_col = state.get("pipeline_col")
        if cur_col in ("todo", "applied", "contacting"):
            jobs_repo.upsert_job_state(body.job_id, {
                "pipeline_col": "interviewing",
                "_history_interview_id": iv_id,
            })
            advanced_from = cur_col
        elif cur_col == "interviewing":
            jobs_repo.upsert_job_state(body.job_id, {
                "_force_stage_event": True,
                "_history_interview_id": iv_id,
            })

    if advanced_from:
        result["_auto_advanced_from"] = advanced_from
    return result


@router.patch("/{interview_id}")
def patch_interview(interview_id: int, body: InterviewPatch):
    out = jobs_repo.update_interview(interview_id, body.model_dump(exclude_unset=True))
    if out is None:
        raise HTTPException(404, "interview not found")
    return out


@router.delete("/{interview_id}")
def delete_interview(interview_id: int):
    jobs_repo.delete_interview(interview_id)
    return {"ok": True}


# ─── Interview ↔ Concept 关联 (verification 闭环) ───
import json as _json
import re as _re

import httpx
from server.storage import concepts_repo, llm_presets_repo
from server.storage.base import now_iso, transaction
from server.storage.db import get_conn


class InterviewConceptIn(BaseModel):
    concept_slug: str
    asked_depth: int = 1   # 1 浅 / 2 中 / 3 深
    outcome: str = "unknown"  # good / ok / bad / unknown
    note: str = ""


@router.get("/{interview_id}/concepts")
def list_interview_concepts(interview_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT ic.*, c.name AS concept_name
               FROM interview_concepts ic
               LEFT JOIN concepts c ON c.slug = ic.concept_slug
               WHERE ic.interview_id = ?
               ORDER BY ic.at""",
            (interview_id,),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("/{interview_id}/concepts")
def add_interview_concept(interview_id: int, body: InterviewConceptIn):
    if not concepts_repo.get_concept(body.concept_slug):
        raise HTTPException(404, "concept not found")
    with transaction() as conn:
        cur = conn.execute(
            """INSERT INTO interview_concepts
               (interview_id, concept_slug, asked_depth, outcome, note, at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (interview_id, body.concept_slug, body.asked_depth, body.outcome, body.note, now_iso()),
        )
        new_id = cur.lastrowid
    return {"id": new_id, "interview_id": interview_id, **body.model_dump()}


@router.delete("/concepts/{record_id}")
def delete_interview_concept(record_id: int):
    with transaction() as conn:
        conn.execute("DELETE FROM interview_concepts WHERE id = ?", (record_id,))
    return {"ok": True}


class ExtractConceptsIn(BaseModel):
    notes: str


def _strip_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = _re.sub(r"^```(?:json)?\s*", "", text)
        text = _re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON in LLM output")
    return _json.loads(text[start : end + 1])


@router.post("/{interview_id}:extract-concepts")
async def extract_concepts_from_notes(interview_id: int, body: ExtractConceptsIn):
    """LLM 从面试笔记里抽取涉及的 concepts + 估算 outcome.
    返回结构 [{concept_slug, name, asked_depth, outcome, evidence}]，前端 review 后选择性 insert.
    """
    if not body.notes.strip():
        raise HTTPException(400, "notes is empty")
    all_concepts = concepts_repo.list_concepts()
    if not all_concepts:
        return {"items": [], "warning": "no concepts in DB; nothing to match"}
    catalog = "\n".join(f"- {c['slug']}: {c['name']}" for c in all_concepts)

    preset = llm_presets_repo.get_active()
    if not preset:
        raise HTTPException(400, "no active LLM preset; configure one first")

    prompt = f"""你是一个面试复盘助手。下面是用户对一次真实技术面试的笔记。
请从用户的描述中识别出面试中涉及到的"知识点（concept）"，从下面的目录中选择匹配项：

【concept 目录】
{catalog}

【用户的面试笔记】
{body.notes[:4000]}

请输出严格 JSON（不要 markdown fence）：
{{
  "items": [
    {{
      "concept_slug": "<必须是上面目录里的 slug>",
      "asked_depth": 1|2|3,         // 1 浅问，2 中等深度追问，3 深入到原理 / 反复追问
      "outcome": "good"|"ok"|"bad", // 用户表现：good=自信清晰回答 / ok=磕磕巴巴 / bad=明显翻车或没答出
      "evidence": "<来自笔记的一句话原文，证明这个判断>"
    }}
  ]
}}

注意：
- 只输出确实在笔记里被提到的 concept，不要无中生有
- 如果笔记完全没匹配上任何 concept，items 返回空数组
- 一次面试最多 8 个 concept
"""
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {preset.api_key}"}
    payload = {
        "model": preset.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{preset.base_url.rstrip('/')}/chat/completions",
            headers=headers, json=payload,
        )
    if r.status_code >= 400:
        raise HTTPException(502, f"LLM upstream {r.status_code}: {r.text[:300]}")
    raw_text = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    try:
        parsed = _strip_json(raw_text)
    except (ValueError, _json.JSONDecodeError) as e:
        raise HTTPException(502, f"LLM JSON parse failed: {e}")

    # 校验：丢掉不在目录里的 concept_slug
    valid_slugs = {c["slug"] for c in all_concepts}
    items = []
    by_slug = {c["slug"]: c for c in all_concepts}
    for it in parsed.get("items") or []:
        slug = it.get("concept_slug")
        if slug not in valid_slugs:
            continue
        items.append({
            "concept_slug": slug,
            "concept_name": by_slug[slug]["name"],
            "asked_depth": int(it.get("asked_depth", 1) or 1),
            "outcome": (it.get("outcome") or "unknown").lower(),
            "evidence": it.get("evidence", "")[:300],
        })
    return {"items": items, "raw": raw_text[:1000]}
