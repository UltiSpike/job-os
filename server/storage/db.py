"""SQLite 持久化层"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).parents[2] / "data" / "app.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


SCHEMA = """
-- 岗位（爬虫产出 + 用户管理；取代 snapshot.json 内存读取）
CREATE TABLE IF NOT EXISTS jobs (
    href TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT,
    area TEXT,
    salary TEXT,
    experience TEXT,
    jd TEXT,
    tier TEXT,
    final_score REAL,
    cluster_hits TEXT DEFAULT '[]',
    source TEXT,
    source_keyword TEXT,
    scraped_at TEXT,
    raw TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_tier ON jobs(tier);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(final_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);

-- 岗位状态（取代 localStorage 的 job_tracker_v3）
CREATE TABLE IF NOT EXISTS job_states (
    job_id TEXT PRIMARY KEY,
    intent TEXT NOT NULL DEFAULT 'unknown',  -- unknown/target/practice/backup/ignored
    pipeline_col TEXT NOT NULL DEFAULT 'todo', -- todo/applied/contacting/interviewing/offer/closed
    outcome TEXT,
    triaged_at TEXT,
    applied_at TEXT,
    last_touch_at TEXT,
    notes TEXT DEFAULT '',
    extra TEXT  -- JSON 杂项
);

CREATE INDEX IF NOT EXISTS idx_job_states_intent ON job_states(intent);
CREATE INDEX IF NOT EXISTS idx_job_states_pipeline ON job_states(pipeline_col);

-- 面试
CREATE TABLE IF NOT EXISTS interviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    type TEXT NOT NULL,           -- HR沟通 / 一面 / 二面 / Onsite ...
    time TEXT,
    location TEXT,
    result TEXT DEFAULT 'pending', -- pass/fail/pending
    reflection TEXT DEFAULT '',
    created_at TEXT,
    FOREIGN KEY (job_id) REFERENCES job_states(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_interviews_job ON interviews(job_id);

-- 题库（取代 training_v1）
CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    rating TEXT,                  -- good/ok/bad/null
    review_note TEXT DEFAULT '',
    source TEXT DEFAULT 'manual', -- manual/interview/derived
    parent_id TEXT,               -- 母题 id
    interview_id INTEGER,         -- 关联的面试
    job_id TEXT,                  -- 关联的岗位
    review_count INTEGER DEFAULT 0,
    last_reviewed_at TEXT,
    next_review_at TEXT,
    note TEXT DEFAULT '',
    answer TEXT,                  -- 最新一次答案（冗余字段，供 list 视图快速预览；权威数据走 answers 表）
    lesson_slug TEXT,             -- 所属 lesson（curriculum 题），可为空（自由题）
    is_capstone INTEGER DEFAULT 0,
    best_practice_answer TEXT,
    followup_answer TEXT,
    decomposition TEXT,           -- JSON
    speaking_logs TEXT DEFAULT '[]', -- JSON 数组
    action_items TEXT DEFAULT '[]',
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (parent_id) REFERENCES questions(id) ON DELETE SET NULL,
    FOREIGN KEY (interview_id) REFERENCES interviews(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_questions_source ON questions(source);
CREATE INDEX IF NOT EXISTS idx_questions_parent ON questions(parent_id);
CREATE INDEX IF NOT EXISTS idx_questions_job ON questions(job_id);
CREATE INDEX IF NOT EXISTS idx_questions_next_review ON questions(next_review_at);

-- 设置（LLM presets / ASR / profile / prompt templates / 等等）
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,        -- JSON
    updated_at TEXT
);

-- ─── topics 规范化 ───
CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,                  -- 规范形式如 'k8s'
    display_name TEXT NOT NULL,
    parent_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (parent_id) REFERENCES topics(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS question_topics (
    question_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    PRIMARY KEY (question_id, topic_id),
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_qt_topic ON question_topics(topic_id);

-- ─── answers 拆出（取代 questions.answer_variants JSON）───
CREATE TABLE IF NOT EXISTS answers (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL,
    template_id TEXT NOT NULL,
    template_name TEXT NOT NULL,
    content TEXT NOT NULL,
    user_edited INTEGER DEFAULT 0,
    generated_at TEXT NOT NULL,
    edited_at TEXT,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_answers_question ON answers(question_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_answers_qid_tpl ON answers(question_id, template_id);

-- ─── analyses 拆出（取代 questions.analyses JSON）───
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL,
    answer_id TEXT,
    source TEXT,
    user_text TEXT NOT NULL,
    score INTEGER,
    strengths TEXT DEFAULT '[]',
    gaps TEXT DEFAULT '[]',
    suggestions TEXT DEFAULT '',
    topics_touched TEXT DEFAULT '[]',
    at TEXT NOT NULL,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
    FOREIGN KEY (answer_id) REFERENCES answers(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_question ON analyses(question_id);
CREATE INDEX IF NOT EXISTS idx_analyses_at ON analyses(at DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_score ON analyses(score);

-- ─── job_state_events 拆出（取代 job_states.stage_history JSON）───
CREATE TABLE IF NOT EXISTS job_state_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    from_col TEXT,
    to_col TEXT NOT NULL,
    reason TEXT,
    interview_id INTEGER,
    at TEXT NOT NULL,
    FOREIGN KEY (interview_id) REFERENCES interviews(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_jse_job ON job_state_events(job_id);
CREATE INDEX IF NOT EXISTS idx_jse_at ON job_state_events(at DESC);
CREATE INDEX IF NOT EXISTS idx_jse_interview ON job_state_events(interview_id);

-- ─── llm_presets 拆出（取代 settings 里的 llm_presets/llm_active）───
CREATE TABLE IF NOT EXISTS llm_presets (
    name TEXT PRIMARY KEY,
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    api_key TEXT NOT NULL,
    extra_headers TEXT DEFAULT '',
    is_active INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ─── prompt_templates 拆出（取代 settings 里的 prompt_templates）───
CREATE TABLE IF NOT EXISTS prompt_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 提问会话（独立 schema，取代 questions.chat_sessions JSON）
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '新会话',
    variant_ref TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_question ON chat_sessions(question_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated ON chat_sessions(updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);

-- 简历版本
CREATE TABLE IF NOT EXISTS resumes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    is_default INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);

-- ─── Curriculum: tracks → modules → lessons ───
CREATE TABLE IF NOT EXISTS tracks (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS modules (
    slug TEXT PRIMARY KEY,
    track_slug TEXT NOT NULL,
    order_index INTEGER NOT NULL DEFAULT 0,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (track_slug) REFERENCES tracks(slug) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_modules_track ON modules(track_slug, order_index);

CREATE TABLE IF NOT EXISTS lessons (
    slug TEXT PRIMARY KEY,
    module_slug TEXT NOT NULL,
    order_index INTEGER NOT NULL DEFAULT 0,
    name TEXT NOT NULL,
    concept_md TEXT DEFAULT '',
    prereq_slugs TEXT DEFAULT '',  -- comma-separated
    est_minutes INTEGER DEFAULT 20,
    capstone_prompt TEXT DEFAULT '',
    capstone_depth INTEGER DEFAULT 2,
    created_at TEXT NOT NULL,
    FOREIGN KEY (module_slug) REFERENCES modules(slug) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_lessons_module ON lessons(module_slug, order_index);

-- 学习进度（单用户，lesson 维度）
CREATE TABLE IF NOT EXISTS lesson_progress (
    lesson_slug TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'available',  -- locked/available/in_progress/passed
    capstone_answer_id TEXT,
    capstone_score INTEGER,
    passed_at TEXT,
    last_reviewed_at TEXT,
    FOREIGN KEY (lesson_slug) REFERENCES lessons(slug) ON DELETE CASCADE,
    FOREIGN KEY (capstone_answer_id) REFERENCES answers(id) ON DELETE SET NULL
);

-- ─── Resume profile (LLM 抽取出的画像) ───
CREATE TABLE IF NOT EXISTS resume_profiles (
    id TEXT PRIMARY KEY,
    resume_id TEXT NOT NULL,
    role TEXT,
    seniority TEXT,
    domain TEXT,
    skills TEXT DEFAULT '[]',          -- JSON array of strings
    projects TEXT DEFAULT '[]',        -- JSON array of {name, summary, tech[]}
    raw TEXT,                          -- 原始 LLM 输出
    created_at TEXT NOT NULL,
    FOREIGN KEY (resume_id) REFERENCES resumes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_resume_profiles_resume ON resume_profiles(resume_id);

-- ─── Job profile (LLM 抽取 JD 的需求) ───
CREATE TABLE IF NOT EXISTS job_profiles (
    job_href TEXT PRIMARY KEY,
    required_skills TEXT DEFAULT '[]',
    nice_to_have TEXT DEFAULT '[]',
    scenarios TEXT DEFAULT '[]',
    raw TEXT,
    extracted_at TEXT NOT NULL,
    FOREIGN KEY (job_href) REFERENCES jobs(href) ON DELETE CASCADE
);

-- ─── Study plan (snapshot) ───
CREATE TABLE IF NOT EXISTS study_plans (
    id TEXT PRIMARY KEY,
    resume_profile_id TEXT NOT NULL,
    target_job_hrefs TEXT DEFAULT '[]',  -- JSON array
    module_priorities TEXT DEFAULT '{}', -- JSON {module_slug: priority_score}
    rationale TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (resume_profile_id) REFERENCES resume_profiles(id) ON DELETE CASCADE
);

-- ─── Interview topic feedback (lesson 实际命中) ───
CREATE TABLE IF NOT EXISTS interview_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_id INTEGER NOT NULL,
    lesson_slug TEXT NOT NULL,
    asked_depth INTEGER DEFAULT 1,  -- 1 浅 / 2 中 / 3 深
    note TEXT DEFAULT '',
    at TEXT NOT NULL,
    FOREIGN KEY (interview_id) REFERENCES interviews(id) ON DELETE CASCADE,
    FOREIGN KEY (lesson_slug) REFERENCES lessons(slug) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_iv_topics_iv ON interview_topics(interview_id);
CREATE INDEX IF NOT EXISTS idx_iv_topics_lesson ON interview_topics(lesson_slug);

-- ─── Concepts: 知识点中心实体 (1 lesson = 1 concept 起步) ───
CREATE TABLE IF NOT EXISTS concepts (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    track_slug TEXT,                 -- 来自哪个 track，便于按 track 聚合
    module_slug TEXT,                -- 来自哪个 module
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_concepts_track ON concepts(track_slug);

-- 一道 question 可以 probe 多个 concept；一个 concept 被多道 question 探查
CREATE TABLE IF NOT EXISTS concept_questions (
    concept_slug TEXT NOT NULL,
    question_id TEXT NOT NULL,
    PRIMARY KEY (concept_slug, question_id),
    FOREIGN KEY (concept_slug) REFERENCES concepts(slug) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cq_question ON concept_questions(question_id);

-- 真实面试涉及的 concept (与 interview_topics 不同：这是 concept 级，那是 lesson 级)
CREATE TABLE IF NOT EXISTS interview_concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_id INTEGER NOT NULL,
    concept_slug TEXT NOT NULL,
    asked_depth INTEGER DEFAULT 1,    -- 1 浅 / 2 中 / 3 深
    outcome TEXT DEFAULT 'unknown',   -- good / ok / bad / unknown
    note TEXT DEFAULT '',
    at TEXT NOT NULL,
    FOREIGN KEY (interview_id) REFERENCES interviews(id) ON DELETE CASCADE,
    FOREIGN KEY (concept_slug) REFERENCES concepts(slug) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_iv_concepts_iv ON interview_concepts(interview_id);
CREATE INDEX IF NOT EXISTS idx_iv_concepts_concept ON interview_concepts(concept_slug);

-- ─── User: 这个 app 的主语 (singleton, id=1) ───
CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY DEFAULT 1,
    display_name TEXT DEFAULT '',
    current_role TEXT DEFAULT '',
    target_role TEXT DEFAULT '',
    target_seniority TEXT DEFAULT '',
    bio TEXT DEFAULT '',
    active_resume_id TEXT,
    active_target_job_hrefs TEXT DEFAULT '[]',  -- JSON array
    target_vector_cache TEXT DEFAULT '{}',      -- JSON {concept_slug: weight}
    target_vector_synced_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (id = 1)
);
"""


def init_db():
    """首次启动建表 + 一次性迁移老 JSON 列 → 独立表 + drop 老列"""
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # 老库可能仍有 answer_variants/analyses/chat_sessions/stage_history 列；先检测
        q_cols = {r["name"] for r in conn.execute("PRAGMA table_info(questions)").fetchall()}
        st_cols = {r["name"] for r in conn.execute("PRAGMA table_info(job_states)").fetchall()}
        # additive: questions.lesson_slug / is_capstone / first_seen_at
        if "lesson_slug" not in q_cols:
            try:
                conn.execute("ALTER TABLE questions ADD COLUMN lesson_slug TEXT")
            except Exception:
                pass
        if "is_capstone" not in q_cols:
            try:
                conn.execute("ALTER TABLE questions ADD COLUMN is_capstone INTEGER DEFAULT 0")
            except Exception:
                pass
        if "first_seen_at" not in q_cols:
            try:
                conn.execute("ALTER TABLE questions ADD COLUMN first_seen_at TEXT")
            except Exception:
                pass
        # 单例 user_profile 默认行
        try:
            conn.execute(
                """INSERT OR IGNORE INTO user_profile
                   (id, display_name, bio, active_target_job_hrefs, target_vector_cache, created_at, updated_at)
                   VALUES (1, '', '', '[]', '{}', ?, ?)""",
                (_now_iso_local(), _now_iso_local()),
            )
        except Exception:
            pass
        # 兼容启动：旧库需要为迁移函数提供这些列；新库 SCHEMA 已不含 → 无需 ADD
        # 旧列存在 = 还没迁过 = 走迁移路径

    # 一次性迁移：所有老 JSON 数据 → 独立表（按列存在性触发；幂等）
    if "chat_sessions" in q_cols:
        _migrate_chat_sessions_json()
    if "answer_variants" in q_cols:
        _migrate_answers_from_variants()
    if "analyses" in q_cols:
        _migrate_analyses_from_json()
    if "topics" in q_cols:
        _migrate_topics_from_questions()
    if "stage_history" in st_cols:
        _migrate_stage_history_to_events()
    _migrate_llm_presets_from_settings()
    _migrate_prompt_templates_from_settings()
    _migrate_jobs_from_snapshot()

    # Phase D：drop 旧列（SQLite ≥ 3.35 支持 ALTER TABLE DROP COLUMN）
    with get_conn() as conn:
        for col in ("answer_variants", "analyses", "chat_sessions", "topics"):
            if col in q_cols:
                try:
                    conn.execute(f"ALTER TABLE questions DROP COLUMN {col}")
                except Exception:
                    pass
        if "stage_history" in st_cols:
            try:
                conn.execute("ALTER TABLE job_states DROP COLUMN stage_history")
            except Exception:
                pass
        # settings 里的旧 key 也清掉（注意：'asr' 仍然是 asr_config router 的后端，保留）
        for k in ("llm_presets", "llm_active", "prompt_templates"):
            try:
                conn.execute("DELETE FROM settings WHERE key = ?", (k,))
            except Exception:
                pass


def _migrate_chat_sessions_json():
    """把老的 questions.chat_sessions JSON 迁到独立表。已迁移的不动。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, chat_sessions FROM questions WHERE chat_sessions IS NOT NULL AND chat_sessions != '[]' AND chat_sessions != ''"
        ).fetchall()
        if not rows:
            return
        existing_sids = {r["id"] for r in conn.execute("SELECT id FROM chat_sessions").fetchall()}
        migrated = 0
        for row in rows:
            try:
                sessions = json.loads(row["chat_sessions"])
                if not isinstance(sessions, list):
                    continue
                for sess in sessions:
                    sid = sess.get("id")
                    if not sid or sid in existing_sids:
                        continue
                    conn.execute(
                        """INSERT INTO chat_sessions (id, question_id, title, variant_ref, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            sid,
                            row["id"],
                            sess.get("title", "未命名"),
                            sess.get("variant_ref"),
                            sess.get("created_at") or _now_iso_local(),
                            sess.get("updated_at") or _now_iso_local(),
                        ),
                    )
                    for m in (sess.get("messages") or []):
                        conn.execute(
                            "INSERT INTO chat_messages (session_id, role, content, at) VALUES (?, ?, ?, ?)",
                            (sid, m.get("role", "user"), m.get("content", ""), m.get("at") or _now_iso_local()),
                        )
                    migrated += 1
                # 清空老 JSON 字段
                conn.execute("UPDATE questions SET chat_sessions = '[]' WHERE id = ?", (row["id"],))
            except Exception:
                pass
        if migrated > 0:
            import logging
            logging.getLogger("server.main").info(f"chat sessions migrated to new schema: {migrated}")


def _now_iso_local():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _migrate_answers_from_variants():
    """questions.answer_variants JSON → answers 表"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, answer_variants FROM questions WHERE answer_variants IS NOT NULL AND answer_variants NOT IN ('[]', '')"
        ).fetchall()
        if not rows:
            return
        existing_aids = {r["id"] for r in conn.execute("SELECT id FROM answers").fetchall()}
        migrated = 0
        for row in rows:
            try:
                variants = json.loads(row["answer_variants"])
                if not isinstance(variants, list):
                    continue
                for v in variants:
                    aid = f"a_{row['id'][:10]}_{v.get('template_id', 'unknown')}"
                    if aid in existing_aids:
                        continue
                    conn.execute(
                        """INSERT OR IGNORE INTO answers
                           (id, question_id, template_id, template_name, content, user_edited, generated_at, edited_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            aid,
                            row["id"],
                            v.get("template_id", "unknown"),
                            v.get("template_name", "未命名"),
                            v.get("content", ""),
                            1 if v.get("user_edited") else 0,
                            v.get("generated_at") or _now_iso_local(),
                            v.get("edited_at"),
                        ),
                    )
                    migrated += 1
                # 清空老字段
                conn.execute("UPDATE questions SET answer_variants = '[]' WHERE id = ?", (row["id"],))
            except Exception:
                pass
        if migrated > 0:
            import logging
            logging.getLogger("server.main").info(f"answers migrated to new schema: {migrated}")


def _migrate_analyses_from_json():
    """questions.analyses JSON → analyses 表"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, analyses FROM questions WHERE analyses IS NOT NULL AND analyses NOT IN ('[]', '')"
        ).fetchall()
        if not rows:
            return
        existing = {r["id"] for r in conn.execute("SELECT id FROM analyses").fetchall()}
        migrated = 0
        for row in rows:
            try:
                items = json.loads(row["analyses"])
                if not isinstance(items, list):
                    continue
                for a in items:
                    aid = a.get("id") or f"an_{row['id'][:6]}_{migrated}"
                    if aid in existing:
                        continue
                    conn.execute(
                        """INSERT OR IGNORE INTO analyses
                           (id, question_id, answer_id, source, user_text, score, strengths, gaps, suggestions, topics_touched, at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            aid,
                            row["id"],
                            None,  # 老数据没有 answer_id 关联
                            a.get("source"),
                            a.get("user_text", ""),
                            a.get("score"),
                            json.dumps(a.get("strengths") or [], ensure_ascii=False),
                            json.dumps(a.get("gaps") or [], ensure_ascii=False),
                            a.get("suggestions") or "",
                            json.dumps(a.get("topics_touched") or [], ensure_ascii=False),
                            a.get("at") or _now_iso_local(),
                        ),
                    )
                    migrated += 1
                conn.execute("UPDATE questions SET analyses = '[]' WHERE id = ?", (row["id"],))
            except Exception:
                pass
        if migrated > 0:
            import logging
            logging.getLogger("server.main").info(f"analyses migrated to new schema: {migrated}")


def _slugify_topic(name: str) -> str:
    """把 'K8s' / 'Kubernetes' / 'k8s' 都规范成 'k8s'"""
    s = name.strip().lower()
    # 简单同义词映射
    aliases = {
        "kubernetes": "k8s",
        "go": "golang",
        "k8s": "k8s",
    }
    return aliases.get(s, s)


def _migrate_topics_from_questions():
    """questions.topics JSON → topics + question_topics 表"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, topics FROM questions WHERE topics IS NOT NULL AND topics NOT IN ('[]', '')"
        ).fetchall()
        if not rows:
            return
        # 已存在的 topic id
        existing_topics = {r["id"] for r in conn.execute("SELECT id FROM topics").fetchall()}
        existing_links = {(r["question_id"], r["topic_id"]) for r in conn.execute("SELECT question_id, topic_id FROM question_topics").fetchall()}
        migrated_topics = 0
        migrated_links = 0
        now = _now_iso_local()
        for row in rows:
            try:
                topic_list = json.loads(row["topics"])
                if not isinstance(topic_list, list):
                    continue
                for t_raw in topic_list:
                    if not isinstance(t_raw, str):
                        continue
                    tid = _slugify_topic(t_raw)
                    if not tid:
                        continue
                    if tid not in existing_topics:
                        conn.execute(
                            "INSERT OR IGNORE INTO topics (id, display_name, created_at) VALUES (?, ?, ?)",
                            (tid, t_raw, now),
                        )
                        existing_topics.add(tid)
                        migrated_topics += 1
                    if (row["id"], tid) not in existing_links:
                        conn.execute(
                            "INSERT OR IGNORE INTO question_topics (question_id, topic_id) VALUES (?, ?)",
                            (row["id"], tid),
                        )
                        existing_links.add((row["id"], tid))
                        migrated_links += 1
            except Exception:
                pass
        if migrated_topics > 0 or migrated_links > 0:
            import logging
            logging.getLogger("server.main").info(f"topics migrated: {migrated_topics} topics, {migrated_links} links")


def _migrate_stage_history_to_events():
    """job_states.stage_history JSON → job_state_events 表

    注意：reason 里 'interview:N' 的 N 是 interview id，迁移时尝试关联 FK
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT job_id, stage_history FROM job_states WHERE stage_history IS NOT NULL AND stage_history NOT IN ('[]', '')"
        ).fetchall()
        if not rows:
            return
        # 检查是否已经有 events（避免重复迁移）
        existing_count = conn.execute("SELECT COUNT(*) FROM job_state_events").fetchone()[0]
        if existing_count > 0:
            return
        migrated = 0
        for row in rows:
            try:
                events = json.loads(row["stage_history"])
                if not isinstance(events, list):
                    continue
                for e in events:
                    iv_id = None
                    reason = e.get("reason")
                    if reason and reason.startswith("interview:"):
                        try:
                            iv_id = int(reason.split(":", 1)[1])
                        except (ValueError, IndexError):
                            iv_id = None
                    conn.execute(
                        "INSERT INTO job_state_events (job_id, from_col, to_col, reason, interview_id, at) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            row["job_id"],
                            e.get("from"),
                            e.get("to") or "todo",
                            reason if not iv_id else None,  # 如果有 FK 就不重复存字符串
                            iv_id,
                            e.get("at") or _now_iso_local(),
                        ),
                    )
                    migrated += 1
            except Exception:
                pass
        if migrated > 0:
            import logging
            logging.getLogger("server.main").info(f"job_state_events migrated: {migrated}")


def _migrate_llm_presets_from_settings():
    """settings.llm_presets / llm_active → llm_presets 表"""
    with get_conn() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM llm_presets").fetchone()[0]
        if existing > 0:
            return
        row = conn.execute("SELECT value FROM settings WHERE key = 'llm_presets'").fetchone()
        if not row:
            return
        try:
            presets = json.loads(row["value"])
            if not isinstance(presets, list):
                return
        except Exception:
            return
        active_row = conn.execute("SELECT value FROM settings WHERE key = 'llm_active'").fetchone()
        active_name = None
        if active_row:
            try:
                active_name = json.loads(active_row["value"])
            except Exception:
                active_name = None
        now = _now_iso_local()
        migrated = 0
        for p in presets:
            if not isinstance(p, dict) or not p.get("name"):
                continue
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO llm_presets
                       (name, base_url, model, api_key, extra_headers, is_active, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        p["name"],
                        p.get("base_url", ""),
                        p.get("model", ""),
                        p.get("api_key", ""),
                        p.get("extra_headers", ""),
                        1 if p["name"] == active_name else 0,
                        now,
                        now,
                    ),
                )
                migrated += 1
            except Exception:
                pass
        if migrated > 0:
            import logging
            logging.getLogger("server.main").info(f"llm_presets migrated: {migrated}")


def _migrate_jobs_from_snapshot():
    """data/snapshot.json → jobs 表（幂等：href 已存在则跳过）"""
    snap_path = DB_PATH.parent / "snapshot.json"
    if not snap_path.exists():
        return
    with get_conn() as conn:
        # 已经迁过就不重复
        existing = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        if existing > 0:
            return
        try:
            with open(snap_path, "r", encoding="utf-8") as f:
                snap = json.load(f)
        except Exception:
            return
        migrated = 0
        for tier in ("P0", "P1", "P2", "P3"):
            for job in snap.get(tier, []):
                href = job.get("href")
                if not href:
                    continue
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO jobs
                           (href, title, company, area, salary, experience, jd, tier, final_score, cluster_hits, source, source_keyword, scraped_at, raw)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            href,
                            job.get("title", ""),
                            job.get("company"),
                            job.get("area"),
                            job.get("salary"),
                            job.get("experience") or job.get("exp"),
                            job.get("jd"),
                            tier,
                            float(job.get("final_score") or 0),
                            json.dumps(job.get("cluster_hits") or [], ensure_ascii=False),
                            job.get("source"),
                            job.get("source_keyword"),
                            _now_iso_local(),
                            json.dumps(job, ensure_ascii=False),
                        ),
                    )
                    migrated += 1
                except Exception:
                    pass
        if migrated > 0:
            import logging
            logging.getLogger("server.main").info(f"jobs migrated from snapshot.json: {migrated}")


def _migrate_prompt_templates_from_settings():
    """settings.prompt_templates → prompt_templates 表"""
    with get_conn() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM prompt_templates").fetchone()[0]
        if existing > 0:
            return
        row = conn.execute("SELECT value FROM settings WHERE key = 'prompt_templates'").fetchone()
        if not row:
            return
        try:
            items = json.loads(row["value"])
            if not isinstance(items, list):
                return
        except Exception:
            return
        now = _now_iso_local()
        migrated = 0
        for p in items:
            if not isinstance(p, dict) or not p.get("id"):
                continue
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO prompt_templates (id, name, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (p["id"], p.get("name", ""), p.get("content", ""), now, now),
                )
                migrated += 1
            except Exception:
                pass
        if migrated > 0:
            import logging
            logging.getLogger("server.main").info(f"prompt_templates migrated: {migrated}")


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """上下文管理的 SQLite 连接"""
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


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    # JSON 字段反序列化
    for k in ("decomposition", "speaking_logs", "action_items", "extra"):
        if k in d and d[k]:
            try:
                d[k] = json.loads(d[k])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(r) for r in rows if r is not None]
