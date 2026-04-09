"""Resume profile extraction (resume → 画像)

POST /resumes/{rid}:extract-profile  调 LLM 抽取，存一份新的 profile snapshot
GET  /resume-profiles?resume_id=...   列出某 resume 的画像历史
GET  /resume-profiles/{id}            单个画像
DELETE /resume-profiles/{id}
"""
from __future__ import annotations

import json
import re

import httpx
from fastapi import APIRouter, HTTPException

from server.storage import llm_presets_repo, resume_profiles_repo, resumes_repo

router = APIRouter(prefix="/api/v1", tags=["resume-profiles"])


EXTRACTION_PROMPT = """你是一个资深技术招聘官，需要从一份简历里抽取出"候选人画像"，用于后续的题库推荐。

请输出严格的 JSON（不要 markdown code fence，不要任何解释文字），格式：
{
  "role": "<角色锚点，如 Go 后端工程师 / 前端工程师 / SRE / 数据工程师>",
  "seniority": "<junior | mid | senior | staff>",
  "domain": "<业务领域，如 中间件 / 电商 / 金融基础设施 / 云原生>",
  "skills": ["<技术栈关键词，10-15 个，按重要性排序，每个不超过 4 个字>"],
  "projects": [
    {"name": "<项目名>", "summary": "<一句话讲清楚做什么>", "tech": ["<用到的关键技术>"]}
  ]
}

注意：
- skills 只放硬技能（语言/框架/中间件/工具），不要放"沟通能力"这种软技能
- projects 最多 4 个，挑最能代表能力的
- 如果简历内容不足以判断 seniority，按工作年限保守估计

简历内容：
---
{resume}
---
"""


def _extract_json(text: str) -> dict:
    """从 LLM 输出里抓 JSON。容忍 ```json ... ``` 包装。"""
    text = text.strip()
    # 去 fence
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # 找到第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"no JSON object found in LLM output: {text[:200]}")
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


@router.post("/resumes/{rid}:extract-profile")
async def extract_profile(rid: str):
    resume = resumes_repo.get_resume(rid)
    if not resume:
        raise HTTPException(404, "resume not found")
    if not (resume.get("content") or "").strip():
        raise HTTPException(400, "resume content is empty")

    prompt = EXTRACTION_PROMPT.replace("{resume}", resume["content"][:8000])
    raw = await _call_llm(prompt)
    try:
        parsed = _extract_json(raw)
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(502, f"LLM returned invalid JSON: {e}")

    profile = resume_profiles_repo.create(
        resume_id=rid,
        role=parsed.get("role"),
        seniority=parsed.get("seniority"),
        domain=parsed.get("domain"),
        skills=parsed.get("skills") or [],
        projects=parsed.get("projects") or [],
        raw=raw,
    )
    return profile


@router.get("/resume-profiles")
def list_profiles(resume_id: str | None = None):
    if not resume_id:
        raise HTTPException(400, "resume_id query param is required")
    return {"items": resume_profiles_repo.list_for_resume(resume_id)}


@router.get("/resume-profiles/{pid}")
def get_profile(pid: str):
    p = resume_profiles_repo.get(pid)
    if not p:
        raise HTTPException(404, "profile not found")
    return p


@router.delete("/resume-profiles/{pid}")
def delete_profile(pid: str):
    resume_profiles_repo.delete(pid)
    return {"ok": True}
