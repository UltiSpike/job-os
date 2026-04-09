"""Mastery Service — 中心化计算

设计原则:
1. **不存表**：mastery 是 derived value，每次请求实时算出来。
   存的是事件（analyses / interviews / ratings），mastery 是对事件流的投影。
2. **graceful degrade**：所有方法对空数据返回安全的空值，不抛错。
3. **single source of truth**：me / today / decision / curriculum 的徽章、数字、推荐
   都从这里取数，view 里不能有重复的计算逻辑。

mastery score 公式（简化版）：
  base_score = max_analysis_score(0..100) / 100   # 最高一次评估
  recency_decay = exp(-days_since_last_practice / HALF_LIFE_DAYS)
  rating_boost = +0.1 if rating='good', 0 if 'ok', -0.2 if 'bad'
  interview_signal = sum of (-0.15 if interview outcome='bad') for recent interviews
  score = clamp(base_score * recency_decay + rating_boost + interview_signal, 0, 1)
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from server.storage import (
    concepts_repo,
    job_profiles_repo,
    user_profile_repo,
)
from server.storage.db import get_conn

HALF_LIFE_DAYS = 14.0   # 14 天衰减一半 — 平衡硬技能的半衰期
RECENT_INTERVIEW_WINDOW_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _days_since(iso: str | None) -> float | None:
    dt = _parse_iso(iso)
    if dt is None:
        return None
    return max(0.0, (_now() - dt).total_seconds() / 86400.0)


def _decay(days: float | None) -> float:
    if days is None:
        return 0.0
    return math.exp(-days / HALF_LIFE_DAYS)


# ─── Concept-level mastery ───

def compute_mastery_for_concept(slug: str) -> dict:
    """返回单个 concept 的 mastery 详情。空数据时 score=0, status='untouched'."""
    if not concepts_repo.get_concept(slug):
        return _empty_mastery(slug)
    qids = concepts_repo.list_questions_for_concept(slug)
    if not qids:
        return _empty_mastery(slug)

    placeholders = ",".join("?" * len(qids))
    with get_conn() as conn:
        # 每道题：最高 analysis score, rating, last_reviewed_at, first_seen_at
        q_rows = conn.execute(
            f"""SELECT id, rating, review_count, last_reviewed_at, first_seen_at
                FROM questions WHERE id IN ({placeholders})""",
            qids,
        ).fetchall()
        a_rows = conn.execute(
            f"""SELECT question_id, MAX(score) AS max_score, MAX(at) AS last_at
                FROM analyses WHERE question_id IN ({placeholders}) GROUP BY question_id""",
            qids,
        ).fetchall()
        # 真实面试信号
        iv_rows = conn.execute(
            "SELECT outcome, asked_depth, at FROM interview_concepts WHERE concept_slug = ?",
            (slug,),
        ).fetchall()

    score_map = {r["question_id"]: (r["max_score"], r["last_at"]) for r in a_rows}

    n_touched = 0
    base_sum = 0.0
    last_practice_iso = None
    rating_boost = 0.0
    for q in q_rows:
        qid = q["id"]
        max_score, last_at = score_map.get(qid, (None, None))
        touched = (q["first_seen_at"] is not None) or (q["rating"] is not None) or (max_score is not None)
        if not touched:
            continue
        n_touched += 1
        base = (max_score or 0) / 100.0
        base_sum += base
        # rating boost
        if q["rating"] == "good":
            rating_boost += 0.10
        elif q["rating"] == "bad":
            rating_boost -= 0.20
        # latest practice timestamp
        for ts in (q["last_reviewed_at"], q["first_seen_at"], last_at):
            if ts and (last_practice_iso is None or ts > last_practice_iso):
                last_practice_iso = ts

    if n_touched == 0:
        m = _empty_mastery(slug)
        m["n_questions_total"] = len(qids)  # 题在那，只是没动过
        # 但仍要计算面试信号，因为可能直接从面试录入
        iv_signal = _interview_signal(iv_rows)
        if iv_signal != 0:
            m["score"] = max(0.0, min(1.0, m["score"] + iv_signal))
            m["interview_signal"] = iv_signal
            m["status"] = "interview-only"
        return m

    base_avg = base_sum / n_touched
    rating_avg = rating_boost / n_touched
    days = _days_since(last_practice_iso)
    decay = _decay(days)
    iv_signal = _interview_signal(iv_rows)
    score = max(0.0, min(1.0, base_avg * decay + rating_avg + iv_signal))

    status = _classify(score, n_touched, len(qids), days)
    return {
        "concept_slug": slug,
        "score": round(score, 3),
        "n_questions_total": len(qids),
        "n_questions_touched": n_touched,
        "last_practiced_at": last_practice_iso,
        "days_since_practice": round(days, 1) if days is not None else None,
        "decay_factor": round(decay, 3),
        "interview_signal": round(iv_signal, 3),
        "status": status,  # untouched / learning / mastered / rusty / interview-only
    }


def _interview_signal(iv_rows) -> float:
    """每条最近 30 天的真实面试 outcome 给 mastery 一点 +/- 信号。"""
    sig = 0.0
    for r in iv_rows:
        days = _days_since(r["at"])
        if days is None or days > RECENT_INTERVIEW_WINDOW_DAYS:
            continue
        outcome = r["outcome"]
        depth = r["asked_depth"] or 1
        if outcome == "good":
            sig += 0.05 * depth
        elif outcome == "bad":
            sig -= 0.10 * depth
        elif outcome == "ok":
            sig += 0.01 * depth
    return sig


def _classify(score: float, n_touched: int, n_total: int, days: float | None) -> str:
    if n_touched == 0:
        return "untouched"
    if score >= 0.75 and n_touched >= max(1, n_total // 2):
        if days is not None and days > HALF_LIFE_DAYS * 1.5:
            return "rusty"
        return "mastered"
    if days is not None and days > HALF_LIFE_DAYS:
        return "rusty"
    return "learning"


def _empty_mastery(slug: str) -> dict:
    return {
        "concept_slug": slug,
        "score": 0.0,
        "n_questions_total": 0,
        "n_questions_touched": 0,
        "last_practiced_at": None,
        "days_since_practice": None,
        "decay_factor": 0.0,
        "interview_signal": 0.0,
        "status": "untouched",
    }


# ─── Vector level ───

def get_mastery_vector() -> list[dict]:
    """所有 concept 的 mastery，按 score 升序（弱的在前）"""
    concepts = concepts_repo.list_concepts()
    out = [compute_mastery_for_concept(c["slug"]) for c in concepts]
    # enrich with concept name
    by_slug = {c["slug"]: c for c in concepts}
    for m in out:
        c = by_slug.get(m["concept_slug"])
        if c:
            m["concept_name"] = c["name"]
            m["track_slug"] = c.get("track_slug")
            m["module_slug"] = c.get("module_slug")
    out.sort(key=lambda m: (m["score"], -m["n_questions_touched"]))
    return out


# ─── Target ───

def get_target_vector() -> dict:
    """从 user_profile.active_target_job_hrefs 出发，
    用每个 job_profile.required_skills 模糊匹配 concept 名 / slug。
    返回 {concept_slug: weight}.
    Graceful: 没 active jobs / 没 job_profiles → 返回 {}
    """
    user = user_profile_repo.get()
    hrefs = user.get("active_target_job_hrefs") or []
    if not hrefs:
        return {}
    profiles = job_profiles_repo.list_for_hrefs(hrefs)
    if not profiles:
        return {}
    concepts = concepts_repo.list_concepts()
    target: dict[str, float] = {}
    for c in concepts:
        slug = c["slug"]
        name = (c["name"] or "").lower()
        # weight = 多少个 target jobs 的 required_skills 命中这个 concept
        hit = 0
        for jp in profiles:
            req = (jp.get("required_skills") or [])
            for r in req:
                rl = (r or "").lower()
                if not rl:
                    continue
                if rl in name or any(part in rl for part in slug.split("-")) or rl in slug:
                    hit += 1
                    break
        if hit > 0:
            target[slug] = round(hit / len(profiles), 3)
    return target


def get_gap() -> list[dict]:
    """target - mastery, 按缺口大的排前。
    Graceful: 没 target 时 fallback 到"按 mastery 升序排"，让用户至少看到弱项。
    """
    mastery = get_mastery_vector()
    target = get_target_vector()
    if not target:
        # 无 target 模式：返回所有 concept 的 mastery，弱的在前
        return [{**m, "target_weight": 0.0, "gap": 0.0, "fallback": True} for m in mastery]
    out = []
    for m in mastery:
        slug = m["concept_slug"]
        weight = target.get(slug, 0.0)
        if weight == 0:
            continue
        gap_value = (1.0 - m["score"]) * weight
        out.append({**m, "target_weight": weight, "gap": round(gap_value, 3)})
    out.sort(key=lambda x: -x["gap"])
    return out


# ─── Coverage 数字 ───

def get_target_coverage() -> dict:
    """目标覆盖度：target 涉及的 concepts 中，mastered 的占比"""
    target = get_target_vector()
    if not target:
        return {"covered": 0, "total": 0, "percentage": 0.0, "fallback": True}
    mastery = {m["concept_slug"]: m for m in get_mastery_vector()}
    total = len(target)
    covered = sum(1 for slug in target if (mastery.get(slug, {}).get("score") or 0) >= 0.75)
    return {
        "covered": covered,
        "total": total,
        "percentage": round(covered / total, 3) if total else 0.0,
        "fallback": False,
    }


# ─── Today 推荐 ───

def get_today_recommendation() -> dict:
    """根据当前 state 算今日推荐动作。
    优先级：
      1. 即将到来的面试 → 预习相关 concepts
      2. 真实面试 bad outcome 的 concept → 紧急复习
      3. 有 target 时的最大 gap concept
      4. 有 due 题的 concept (SRS 复习)
      5. fallback：第一个 untouched 的 concept

    Graceful: 任何上游空都不抛错。
    """
    # upcoming interview
    with get_conn() as conn:
        upcoming = conn.execute(
            """SELECT id, job_id, type, time FROM interviews
               WHERE time > datetime('now') AND result = 'pending'
               ORDER BY time ASC LIMIT 1"""
        ).fetchone()

    if upcoming:
        return {
            "kind": "upcoming-interview-prep",
            "label": f"明日预习 · {upcoming['type']}",
            "interview_id": upcoming["id"],
            "url": f"#/pipeline?interview={upcoming['id']}",
        }

    # bad-interview signals
    with get_conn() as conn:
        bad_iv = conn.execute(
            """SELECT concept_slug FROM interview_concepts
               WHERE outcome = 'bad' AND at > datetime('now', '-30 days')
               GROUP BY concept_slug ORDER BY MAX(at) DESC LIMIT 1"""
        ).fetchone()
    if bad_iv:
        c = concepts_repo.get_concept(bad_iv["concept_slug"])
        if c:
            return {
                "kind": "interview-followup",
                "label": f"复盘 · {c['name']}",
                "concept_slug": c["slug"],
                "url": _curriculum_url(c),
            }

    # max gap (target-driven)
    gap = get_gap()
    top = next((g for g in gap if g.get("gap", 0) > 0 or g.get("fallback")), None)
    if top:
        c = concepts_repo.get_concept(top["concept_slug"])
        if c:
            label_prefix = "补缺口" if not top.get("fallback") else "继续学"
            return {
                "kind": "gap-fill",
                "label": f"{label_prefix} · {c['name']}",
                "concept_slug": c["slug"],
                "url": _curriculum_url(c),
            }

    # due cards
    due_count = _count_due_questions()
    if due_count > 0:
        return {
            "kind": "review-due",
            "label": f"今日复习 · {due_count} 题",
            "url": "#/training",
        }

    return {
        "kind": "empty",
        "label": "暂时没有推荐 — 加一份简历或目标岗位让系统认识你",
        "url": "#/me",
    }


def _curriculum_url(concept: dict) -> str:
    track = concept.get("track_slug") or ""
    mod = concept.get("module_slug") or ""
    slug = concept.get("slug") or ""
    parts = ["curriculum"]
    if track: parts.append(track)
    if mod: parts.append(mod)
    if slug: parts.append(slug)
    return "#/" + "/".join(parts)


def _count_due_questions() -> int:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS n FROM questions
               WHERE (lesson_slug IS NULL OR first_seen_at IS NOT NULL)
                 AND (is_capstone IS NULL OR is_capstone = 0)
                 AND (next_review_at IS NULL OR next_review_at <= datetime('now'))"""
        ).fetchone()
    return int(row["n"]) if row else 0
