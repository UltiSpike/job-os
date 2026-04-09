"""个人技能档案 — 从 questions.analyses + ratings 聚合"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.storage import questions_repo, settings_repo
from server.routers.llm import _build_headers, _resolve

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


def _aggregate_skills() -> dict:
    """从所有 questions 的 analyses + ratings 聚合技能档案"""
    questions = questions_repo.list_questions()
    topic_stats: dict[str, dict] = defaultdict(lambda: {
        "topic": "",
        "n": 0,
        "avg_score": 0.0,
        "rating_dist": {"good": 0, "ok": 0, "bad": 0, "none": 0},
        "score_sum": 0.0,
        "score_n": 0,
        "common_gaps": [],
    })
    recent_gaps: list[str] = []
    total_analyses = 0
    questions_practiced = 0

    for q in questions:
        topics = q.get("topics") or []
        analyses = q.get("analyses") or []
        rating = q.get("rating")
        has_practice = bool(analyses) or bool(rating)
        if has_practice:
            questions_practiced += 1

        # 把这道题的 topics 和 analyses 关联到所有相关 topic
        # 候选 topics 来源：question.topics + analyses 里的 topics_touched
        all_topics: set[str] = set(topics)
        for a in analyses:
            for t in (a.get("topics_touched") or []):
                all_topics.add(t)

        if not all_topics:
            all_topics = {"未分类"}

        for topic in all_topics:
            ts = topic_stats[topic]
            ts["topic"] = topic
            ts["n"] += 1
            if rating in ("good", "ok", "bad"):
                ts["rating_dist"][rating] += 1
            else:
                ts["rating_dist"]["none"] += 1
            for a in analyses:
                score = a.get("score")
                if isinstance(score, (int, float)):
                    ts["score_sum"] += float(score)
                    ts["score_n"] += 1
                    total_analyses += 1
                gaps = a.get("gaps") or []
                ts["common_gaps"].extend(gaps[:2])

        # 收集所有 gaps 用于 recent_gaps（按时间逆序）
        for a in sorted(analyses, key=lambda x: x.get("at", ""), reverse=True):
            for gap in (a.get("gaps") or [])[:1]:
                if gap not in recent_gaps:
                    recent_gaps.append(gap)
                    if len(recent_gaps) >= 12:
                        break
            if len(recent_gaps) >= 12:
                break

    # 后处理 — 计算 avg_score
    items = []
    for ts in topic_stats.values():
        if ts["score_n"] > 0:
            ts["avg_score"] = round(ts["score_sum"] / ts["score_n"], 1)
        del ts["score_sum"]
        del ts["score_n"]
        # common_gaps 去重保留 top 3
        seen = set()
        deduped = []
        for g in ts["common_gaps"]:
            if g not in seen:
                seen.add(g)
                deduped.append(g)
                if len(deduped) >= 3:
                    break
        ts["common_gaps"] = deduped
        items.append(ts)

    items.sort(key=lambda x: (-x["n"], -x["avg_score"]))

    # 强项：avg_score >= 75 OR rating good 占比 >= 0.6
    strong = [
        x for x in items
        if (x["avg_score"] and x["avg_score"] >= 75)
        or (x["n"] >= 2 and x["rating_dist"]["good"] / max(x["n"], 1) >= 0.6)
    ]
    # 弱项：avg_score <= 60 OR bad 占比 >= 0.4
    weak = [
        x for x in items
        if (x["avg_score"] and x["avg_score"] <= 60)
        or (x["n"] >= 2 and x["rating_dist"]["bad"] / max(x["n"], 1) >= 0.4)
    ]

    return {
        "strong": strong[:8],
        "weak": weak[:8],
        "all_topics": items[:20],
        "recent_gaps": recent_gaps[:12],
        "total_analyses": total_analyses,
        "questions_practiced": questions_practiced,
        "last_synced_at": (settings_repo.get_setting("profile_sync_meta") or {}).get("last_synced_at"),
        "analyses_at_last_sync": (settings_repo.get_setting("profile_sync_meta") or {}).get("analyses_at_last_sync", 0),
    }


@router.get("/skills")
def get_skills():
    return _aggregate_skills()


@router.get("/trends")
def get_trends(days: int = 30):
    """最近 N 天每日活动量 (interviews + analyses + ratings + stage transitions)"""
    from datetime import datetime, timezone, timedelta
    from server.storage import jobs_repo
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()

    daily: dict[str, dict] = {}
    def bucket(iso):
        if not iso:
            return None
        try:
            d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except Exception:
            return None
        if d < cutoff:
            return None
        key = d.strftime("%Y-%m-%d")
        if key not in daily:
            daily[key] = {"date": key, "interviews": 0, "analyses": 0, "ratings": 0, "transitions": 0}
        return daily[key]

    # interviews
    for iv in jobs_repo.list_interviews():
        b = bucket(iv.get("created_at"))
        if b:
            b["interviews"] += 1

    # questions: analyses + ratings
    for q in questions_repo.list_questions():
        for a in (q.get("analyses") or []):
            b = bucket(a.get("at"))
            if b:
                b["analyses"] += 1
        if q.get("last_reviewed_at"):
            b = bucket(q.get("last_reviewed_at"))
            if b:
                b["ratings"] += 1

    # stage transitions —— 走 job_state_events 表
    from server.storage import job_state_events_repo
    for ev in job_state_events_repo.list_recent(days=days):
        if ev.interview_id is not None:
            continue  # 算在 interviews 里
        b = bucket(ev.at)
        if b:
            b["transitions"] += 1

    items = sorted(daily.values(), key=lambda x: x["date"])
    return {
        "days": days,
        "items": items,
        "total": {
            "interviews": sum(d["interviews"] for d in items),
            "analyses": sum(d["analyses"] for d in items),
            "ratings": sum(d["ratings"] for d in items),
            "transitions": sum(d["transitions"] for d in items),
        },
    }


@router.post(":weekly-report")
async def weekly_report():
    """LLM 生成本周复盘 — 用 stage_history + analyses + interviews 摘要"""
    skills = _aggregate_skills()
    trends = get_trends(7)
    if trends["total"]["interviews"] == 0 and trends["total"]["analyses"] == 0 and trends["total"]["ratings"] == 0:
        raise HTTPException(400, "本周还没有任何活动")

    target = _resolve(None, None)
    headers = _build_headers(target)

    sys = """你是一名求职教练，给候选人写一份本周复盘周报。

要求：
- 4 段：本周做了什么、亮点、问题/警示、下周该聚焦的 1-2 件事
- 每段 2-4 句话，自然口语
- 不要 markdown，不要 bullet
- 不要寒暄开场，直接进入第一段
- 总长 250-400 字
- 多用具体数字（来自数据），少空话"""

    user = f"""【本周数据 (last 7d)】
- 投递 / stage 推进: {trends['total']['transitions']} 次
- 面试: {trends['total']['interviews']} 次
- AI 评估: {trends['total']['analyses']} 次
- 题目评分: {trends['total']['ratings']} 次

【强项 topics】
{', '.join([f"{x['topic']} (avg {x['avg_score']})" for x in skills['strong'][:5]]) or '暂无'}

【弱项 topics】
{', '.join([f"{x['topic']} (avg {x['avg_score']})" for x in skills['weak'][:5]]) or '暂无'}

【最近的具体 gaps】
{chr(10).join('- ' + g for g in skills['recent_gaps'][:6]) or '暂无'}
"""

    body = {
        "model": target.model,
        "messages": [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        "stream": False,
        "temperature": 0.55,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{target.base_url.rstrip('/')}/chat/completions",
            headers=headers, json=body,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:500])
    data = r.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    return {"ok": True, "report": text, "trends": trends, "generated_at": __import__("datetime").datetime.now().isoformat()}


@router.post(":sync-prompt")
async def sync_prompt():
    """用 LLM 把聚合数据 → system_prompt"""
    skills = _aggregate_skills()
    if skills["total_analyses"] == 0 and skills["questions_practiced"] == 0:
        raise HTTPException(400, "还没有任何练习数据，先做几道题再同步")

    target = _resolve(None, None)
    headers = _build_headers(target)

    profile = settings_repo.get_setting("profile") or {}
    base_role = profile.get("role", "") if isinstance(profile, dict) else ""
    base_target = profile.get("target", "") if isinstance(profile, dict) else ""

    sys = """你的任务是把候选人的练习数据聚合成一段 LLM system prompt。
这段 prompt 会注入到所有后续的答题生成 / 答案分析调用里。
要求：
- 中文，2-4 段，总共 200-350 字
- 第一段：候选人是谁（基础信息 + 求职方向）
- 第二段：技术强项，必须列具体的 topic
- 第三段：弱项 / 最近的 gap，列具体内容
- 最后一段：1 句话告诉 LLM 在生成或分析时如何利用这些信息
- 不要用 markdown，不要 bullet，不要 "首先/其次"
直接输出 system prompt 正文，不要前言后记。"""

    user = f"""候选人基础信息：
- 角色定位：{base_role or '后端 / 平台开发'}
- 求职目标：{base_target or '后端工程师'}

练习统计：
- 已练习题目数：{skills['questions_practiced']}
- 累计 AI 评估次数：{skills['total_analyses']}

强项 topics（按数量排序）：
{', '.join([f"{x['topic']} (n={x['n']}, avg={x['avg_score']})" for x in skills['strong'][:6]]) or '（暂无）'}

弱项 topics：
{', '.join([f"{x['topic']} (n={x['n']}, avg={x['avg_score']})" for x in skills['weak'][:6]]) or '（暂无）'}

最近的具体缺口：
{chr(10).join('- ' + g for g in skills['recent_gaps'][:8]) or '（暂无）'}
"""

    body = {
        "model": target.model,
        "messages": [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        "stream": False,
        "temperature": 0.4,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{target.base_url.rstrip('/')}/chat/completions",
            headers=headers, json=body,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:500])
    data = r.json()
    new_prompt = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

    # 写回 profile.system_prompt + 同步元信息
    new_profile = dict(profile) if isinstance(profile, dict) else {}
    new_profile["system_prompt"] = new_prompt
    settings_repo.set_setting("profile", new_profile)
    from datetime import datetime, timezone
    settings_repo.set_setting("profile_sync_meta", {
        "last_synced_at": datetime.now(timezone.utc).isoformat(),
        "analyses_at_last_sync": skills["total_analyses"],
    })

    return {"ok": True, "system_prompt": new_prompt}
