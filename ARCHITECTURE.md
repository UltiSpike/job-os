# Job OS — 架构文档

> 一个个人化的求职管理工具：候选岗位 → 投递 → 面试 → 题库练习 → 复盘成长。
> 单用户、本地优先、数据在 `data/app.db`（SQLite）+ `data/snapshot.json`（爬虫产出）。

## 目录

- [设计原则](#设计原则)
- [总体分层](#总体分层)
- [数据模型（领域模型）](#数据模型领域模型)
- [REST API 设计](#rest-api-设计)
- [前端分层](#前端分层)
- [写路径与读路径](#写路径与读路径)
- [迁移历史](#迁移历史)

---

## 设计原则

1. **资源优先 (Resource-Oriented REST)** —— 每个领域概念都有自己的 router、repo、表。聚合关系通过外键建模，不通过 JSON 列。
2. **关系数据库即真相 (DB is the Source of Truth)** —— 不在应用层缓存可派生的数据。表 schema 通过外键 + CASCADE 表达完整性约束。
3. **严格 PATCH (Strict PATCH)** —— 资源 PATCH 端点只接受属于该资源自身的标量字段。跨资源写要走对应资源的 dedicated endpoint。
4. **BFF 不做数据糖 (No Hydration in the BFF)** —— GET 接口返回干净的资源对象，不"贴心地"把子资源拼回来。前端按需要自己去拉。
5. **事件追加而非状态突变 (Append-only Events)** —— 状态变化（job_state_events、analyses）按事件流追加，而不是覆盖一个 JSON 数组。便于审计、撤销、聚合查询。
6. **没有兼容垫片 (No Compat Shims)** —— 旧字段一旦废弃就 drop。前端 view 必须直接调 dedicated routers。

## 总体分层

```
┌──────────────────────────────────────────────────────┐
│  Web (浏览器, ESM 原生模块, 无构建)                   │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │  views/     │→ │  store/      │→ │  api/      │  │
│  │  (UI 渲染)  │  │  (响应式状态) │  │  (HTTP)    │  │
│  └─────────────┘  └──────────────┘  └─────┬──────┘  │
└─────────────────────────────────────────────┼────────┘
                                              │ HTTP
┌─────────────────────────────────────────────▼────────┐
│  BFF (FastAPI, 同源, 端口 8891)                       │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │  routers/   │→ │  storage/    │→ │  SQLite    │  │
│  │  (REST)     │  │  *_repo.py   │  │  app.db    │  │
│  └─────────────┘  └──────────────┘  └────────────┘  │
└──────────────────────────────────────────────────────┘
                          │
                          ▼
                    data/snapshot.json (爬虫产出, 只读)
```

- **后端**: FastAPI + 原生 sqlite3（不用 ORM）。每个表配一个 `*_repo.py`，每个 router 专注一个资源。
- **前端**: 原生 ES Modules，无构建步骤，无框架。`createStore` 提供一个 200 行的迷你响应式 store；`api/client.js` 是一个 30 行的 fetch 包装。

## 数据模型（领域模型）

```
                  ┌──────────┐
                  │   jobs   │  (爬虫产出, 只读 snapshot 投影)
                  │  (href)  │
                  └─────┬────┘
                        │
                ┌───────▼────────┐         ┌───────────────────┐
                │   job_states   │←────────│ job_state_events  │
                │   (job_id PK)  │ 1     N │ (id, from, to,    │
                └───────┬────────┘         │  reason, iv_id)   │
                        │                  └─────────┬─────────┘
                  1     │                         N  │
                        ▼ N                          │
                ┌───────────────┐                    │
                │  interviews   │←───────────────────┘
                │  (id, job_id) │  (interview_id FK)
                └───────────────┘

  ┌────────────┐         ┌─────────┐         ┌─────────────┐
  │  topics    │←─ M:N ─→│questions│←─1   N─→│   answers   │
  │ (id slug)  │   q_t   │  (id)   │         │ (template_id│
  └────────────┘         └────┬────┘         │  per q)     │
                              │              └──────┬──────┘
                              │ 1                   │ 0..1
                              │                     │
                              ▼ N                   │
                       ┌──────────────┐             │
                       │   analyses   │←────────────┘
                       │  (against    │  (answer_id FK)
                       │   answer_id) │
                       └──────────────┘

  ┌────────────────┐         ┌──────────────┐
  │ chat_sessions  │← 1   N →│ chat_messages│
  │ (question_id   │         │ (session_id, │
  │  variant_ref)  │         │  role, text) │
  └────────────────┘         └──────────────┘
        ▲
        │ N
        │
        └──── questions

  ┌──────────────┐    ┌─────────────────┐    ┌──────────┐
  │ llm_presets  │    │ prompt_templates│    │  resumes │
  │ (name PK,    │    │ (id, name,      │    │ (id PK,  │
  │  is_active)  │    │  content)       │    │  default)│
  └──────────────┘    └─────────────────┘    └──────────┘
```

### 核心表

| 表 | 主键 | 关键字段 | 备注 |
|---|---|---|---|
| `jobs` | `href` | `tier, final_score, jd, raw` | 从 `snapshot.json` 一次性导入；爬虫重跑时通过 `/migrate` 路径刷新 |
| `job_states` | `job_id` | `intent, pipeline_col, applied_at, notes` | 用户对岗位的"观点"——是否目标岗、推到哪一列、决策时间 |
| `job_state_events` | `id` (auto) | `from_col, to_col, reason, interview_id, at` | 状态变化的**事件流**。代替旧的 `stage_history` JSON 列。`interview_id` 可为 null |
| `interviews` | `id` (auto) | `job_id, type, time, result` | 删除时通过 `delete_for_interview` 级联清理 events 并回放 pipeline_col |
| `questions` | `id` (`q_xxx`) | `text, rating, source, parent_id, answer (冗余)` | `answer` 字段是最近一次生成内容的快照，用于列表预览；权威数据在 `answers` 表 |
| `topics` + `question_topics` | slug | M:N 关联 | 取代旧的 `questions.topics` JSON |
| `answers` | `id` (`a_xxx`) | `question_id, template_id, content, user_edited` | 每 `(question_id, template_id)` 唯一。取代旧的 `answer_variants` JSON |
| `analyses` | `id` (`an_xxx`) | `question_id, answer_id, score, strengths, gaps` | AI 评估事件流。`answer_id` 指向被评估的 answer variant |
| `chat_sessions` | `id` (`s_xxx`) | `question_id, title, variant_ref` | 题目级追问会话。CASCADE 删 messages |
| `chat_messages` | `id` (auto) | `session_id, role, content, at` | 取代旧的 `chat_sessions.messages` JSON |
| `llm_presets` | `name` | `base_url, model, api_key, is_active` | LLM 接入配置，多个 preset 可并存 |
| `prompt_templates` | `id` | `name, content` | 用户自建答题模板 |
| `resumes` | `id` | `content, is_default` | 简历版本管理 |
| `settings` | `key` | `value (JSON)` | 仅剩下 `profile` 和 `asr` 两个 key |

### 不再有的表/列

| 已删除 | 取代方案 |
|---|---|
| `questions.answer_variants` (JSON) | `answers` 表 |
| `questions.analyses` (JSON) | `analyses` 表 |
| `questions.chat_sessions` (JSON) | `chat_sessions` + `chat_messages` 表 |
| `questions.topics` (JSON) | `topics` + `question_topics` |
| `job_states.stage_history` (JSON) | `job_state_events` |
| `settings.llm_presets` / `llm_active` | `llm_presets` 表 |
| `settings.prompt_templates` | `prompt_templates` 表 |

## REST API 设计

**惯例：**
- 资源用连字符复数：`/api/v1/job-states`、`/api/v1/llm-presets`、`/api/v1/chat-sessions`
- 动作端点用 Google API 风格的 `:verb` 后缀：`/api/v1/llm-presets/{name}:activate`、`/api/v1/profile:sync-prompt`、`/api/v1/analyses:stream`
- PATCH 严格：未声明的字段返回 400
- DELETE 返回 `{ok: true, snapshot: {...}}` 以支持撤销
- 流式端点用 SSE，而不是 WebSocket

### 路由清单

```
# Core
GET    /api/v1/jobs                          列表（可按 tier/q 过滤）
GET    /api/v1/jobs/{href}
GET    /api/v1/job-states
GET    /api/v1/job-states/{id}
PATCH  /api/v1/job-states/{id}
DELETE /api/v1/job-states/{id}
POST   /api/v1/job-states/{id}:reset         清空所有 events 回到 todo
GET    /api/v1/job-state-events              {job_id?, days?, limit?}

GET    /api/v1/interviews                    {job_id?}
GET    /api/v1/interviews/{id}
POST   /api/v1/interviews                    body: {job_id, type, ...}
PATCH  /api/v1/interviews/{id}
DELETE /api/v1/interviews/{id}

GET    /api/v1/questions                     {source?, topic?, rating?, due?, limit?, q?}
GET    /api/v1/questions/{id}                ★ 不含 answers/analyses/sessions
POST   /api/v1/questions
PATCH  /api/v1/questions/{id}                ★ 严格：拒绝 answer_variants/analyses/chat_sessions
DELETE /api/v1/questions/{id}
POST   /api/v1/questions/{id}/review         {rating}
POST   /api/v1/questions/bulk
POST   /api/v1/questions/classify            {text, max_topics}
POST   /api/v1/questions/generate            SSE 流

GET    /api/v1/answers                       {question_id?, limit?}
POST   /api/v1/answers
PATCH  /api/v1/answers/{id}
DELETE /api/v1/answers/{id}
POST   /api/v1/answers/restore

GET    /api/v1/analyses                      {question_id?, limit?, min_score?}
POST   /api/v1/analyses                      持久化（流式生成完后调）
POST   /api/v1/analyses:stream               SSE 流，不持久化
DELETE /api/v1/analyses/{id}
POST   /api/v1/analyses/restore

GET    /api/v1/topics
GET    /api/v1/topics:stats
GET    /api/v1/questions/{id}/topics
PUT    /api/v1/questions/{id}/topics

GET    /api/v1/chat-sessions                 {question_id}
POST   /api/v1/chat-sessions
PATCH  /api/v1/chat-sessions/{id}
DELETE /api/v1/chat-sessions/{id}
POST   /api/v1/chat-sessions/restore

GET    /api/v1/chat-messages                 {session_id}
POST   /api/v1/chat-messages
DELETE /api/v1/chat-messages/{id}

# AI
POST   /api/v1/llm/test
POST   /api/v1/llm/chat
POST   /api/v1/llm/chat/stream               SSE
GET    /api/v1/llm-presets
POST   /api/v1/llm-presets
PATCH  /api/v1/llm-presets/{name}
DELETE /api/v1/llm-presets/{name}
POST   /api/v1/llm-presets/{name}:activate
POST   /api/v1/llm-presets/{name}:test
POST   /api/v1/asr/ws                        WebSocket（语音 ASR）
GET    /api/v1/asr-config
PUT    /api/v1/asr-config
POST   /api/v1/asr-config:test

# Resources
GET/POST/PATCH/DELETE /api/v1/resumes[/{id}]
GET/POST/PATCH/DELETE /api/v1/prompt-templates[/{id}]

# Profile / Settings
GET    /api/v1/settings/profile
PUT    /api/v1/settings/profile
GET    /api/v1/profile/skills
GET    /api/v1/profile/trends
POST   /api/v1/profile:sync-prompt
POST   /api/v1/profile:weekly-report

# Ops
GET    /api/v1/health
GET    /api/v1/export
POST   /api/v1/migrate/from-localstorage
GET    /api/v1/migrate/export
```

## 前端分层

### `web/api/`

每个文件对应一个后端资源 router，纯函数风格。导出一个 `*Api` 对象：

```
api/
  client.js               fetch 包装 + 错误标准化
  jobs.js                 jobsApi
  jobStates.js            jobStatesApi
  jobStateEvents.js       jobStateEventsApi
  interviews.js           interviewsApi
  questions.js            questionsApi
  answers.js              answersApi
  analyses.js             analysesApi
  topics.js               topicsApi
  chat.js                 chatApi
  llm.js                  llmApi (chat / stream / test)
  llmPresets.js           llmPresetsApi
  asrConfig.js            asrConfigApi
  promptTemplates.js      promptTemplatesApi
  profile.js              profileApi
  settings.js             settingsApi + resumesApi
```

### `web/store/`

响应式状态——只放跨 view 的预聚合数据。每个 store 暴露 `state` + `patch()` + `subscribe()`，加少量 `loadX()` / `setX()` 操作函数。

```
store/
  createStore.js          迷你响应式实现
  jobs.js                 jobs/states/interviews/eventsByJob/byTier
  questions.js            questions/topics/recentAnalyses/answersByQuestion
  settings.js             llmPresets/asr/profile/prompts/resumes
```

`questionsStore.recentAnalyses` 和 `answersByQuestion` 是给 dashboard view（`today.js`、`decision.js`）的预聚合，避免每个 view 自己 N+1 查询。

### `web/views/`

每个 view 是一个对象 `{ name, label, render() }`，被 `app.js` 的 router 挂载。

实践模态 (`_practiceModal.js`) 维护一个**题目级缓存** `practiceData = { qid, answers, analyses, sessions }`：每次切换题目时通过 `loadPracticeData(qid)` 用 dedicated APIs 拉取。所有写路径都直接调 `answersApi` / `analysesApi` / `chatApi`，绝不通过 questions PATCH。

## 写路径与读路径

### 例：用户在练习中生成一个 AI 答案

1. View 调 `llmApi.chatStream(...)` 流式拿文本
2. 流完成后调 `answersApi.create({question_id, template_id, template_name, content})`
3. Repo 走 `INSERT OR REPLACE INTO answers (question_id, template_id, ...) VALUES ...`（唯一约束 `(question_id, template_id)` 保证 upsert 语义）
4. View 把返回的 Answer 对象塞进 `practiceData.answers`
5. View 同时调 `questionsApi.patch(qid, { answer: full })` 更新冗余的 `questions.answer` 字段（供 list 视图快速预览）

### 例：用户记录一次面试，自动推进 stage

1. View 调 `interviewsApi.create(jobId, {type, time, ...})`
2. Router 在 `create_interview` 后立即检查 `job_states.pipeline_col`：
   - 若为 `todo/applied/contacting`：调 `upsert_job_state(pipeline_col='interviewing', _history_interview_id=iv_id)`
   - 若已经是 `interviewing`：调 `upsert_job_state(_force_stage_event=True, _history_interview_id=iv_id)`
3. `upsert_job_state` 检测到 col 变化（或 `_force_stage_event`），调 `job_state_events_repo.add(job_id, from, to, reason, interview_id)`，再 UPDATE `job_states` 表
4. Router 返回的 interview 对象带上 `_auto_advanced_from`，前端用它弹一个"已自动推进，撤销?"的 toast

### 例：渲染 pipeline timeline

1. `loadJobs()` 一次性拉 jobs/job-states/interviews/job-state-events，把 events 按 `job_id` 分组放进 `jobsStore.eventsByJob`
2. `pipeline.js` 渲染卡片时直接读 `eventsByJob[jobId]`（已按 `at` 升序）
3. 时间线把 events 转成"叙事化事件流"（推进/回退/面试 chip）

## 迁移历史

老库（v1/v2）的所有 JSON 列在启动时通过 `db.py:init_db()` 一次性迁到独立表，迁完直接 `ALTER TABLE DROP COLUMN`。流程是幂等的：
- 检测列是否存在 → 存在才跑迁移函数 → 跑完 drop。新库不会触发任何迁移路径。

迁移函数：
- `_migrate_chat_sessions_json` —— `questions.chat_sessions` → `chat_sessions` + `chat_messages`
- `_migrate_answers_from_variants` —— `questions.answer_variants` → `answers`
- `_migrate_analyses_from_json` —— `questions.analyses` → `analyses`
- `_migrate_topics_from_questions` —— `questions.topics` → `topics` + `question_topics`
- `_migrate_stage_history_to_events` —— `job_states.stage_history` → `job_state_events`
- `_migrate_llm_presets_from_settings` —— `settings.llm_presets/llm_active` → `llm_presets`
- `_migrate_prompt_templates_from_settings` —— `settings.prompt_templates` → `prompt_templates`
- `_migrate_jobs_from_snapshot` —— `data/snapshot.json` → `jobs` 表（首次启动）

迁移完成后这些函数依然存在但不会被调用——可以等下一次架构重构时一并删除。

---

**最后更新**: 2026-04-09 · 完整重构后第一版（无兼容垫片）
