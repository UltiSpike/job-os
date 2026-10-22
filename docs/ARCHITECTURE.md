# Job Scraper / Training OS — 项目结构文档

> 重构基线快照（撰写时间：2026-04-08）。
> 产品当前形态：**求职 OS** = 岗位召回 + 岗位 Pipeline 跟踪 + 训练场（八股/拷打/口述/间隔复习）

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                       离线 Pipeline（一次性运行）                  │
│                                                                  │
│  BOSS 直聘                                                       │
│      │                                                           │
│      │  v4.py (CDP via Playwright)                               │
│      ▼                                                           │
│  raw.json (~1000 条岗位)                                         │
│      │                                                           │
│      │  v4_1.py / v3_1.py (评分 + 簇匹配 + 分层)                  │
│      ▼                                                           │
│  v4_1_output/                                                   │
│      ├── tiered.json     ← 分层后的岗位（P0/P1/P2/P3）            │
│      ├── rejected.json   ← 被剔除的岗位（带原因）                  │
│      ├── jobs.xlsx       ← Excel 导出（旧版）                     │
│      └── v5.html         ← 由 build_html_v5.py 生成的 SPA         │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       在线运行（用户每天用）                        │
│                                                                  │
│  python3 training_bff_v2.py --port 8891 --root <project>         │
│                                                                  │
│  ┌────────────────┐         ┌──────────────────────────┐         │
│  │ Browser        │  HTTP   │ FastAPI BFF              │         │
│  │ (Chrome/Safari)│ ◄─────► │ training_bff_v2.py       │         │
│  │                │         │                          │         │
│  │ v5.html (SPA)  │         │ - 静态文件 mount          │         │
│  │   localStorage │         │ - /api/v1/chat            │         │
│  └────────────────┘         │ - /api/v1/asr/transcribe  │         │
│         │                   │ - /api/v1/asr/ws (桥接)    │         │
│         │                   └─────┬────────────────────┘         │
│         │ 同源 fetch /                ││ httpx / websockets       │
│         └──────────────►              ▼▼                         │
│                                 ┌───────────────────────┐         │
│                                 │ 上游 LLM / ASR        │         │
│                                 │ - DeepSeek / hpc-ai   │         │
│                                 │ - 火山引擎 实时 ASR    │         │
│                                 └───────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

**核心设计原则**：
1. **离线和在线分离** —— 爬虫/评分一次性跑出 `tiered.json`，前端只消费快照，不依赖爬虫存活
2. **同源 BFF** —— 浏览器走 `http://127.0.0.1:8891`，HTML 和 API 同源，CORS 一次性解决
3. **本地数据所有权** —— 用户的状态/题库/录音全在 `localStorage`，BFF 不存任何业务数据，纯转发
4. **OpenAI 兼容** —— LLM 上游统一抽象成 OpenAI 协议，用户填 base_url/model/api_key，可用任何兼容供应商

---

## 二、目录结构（按职责分类）

```
job-scraper/
│
├── 📦 离线 Pipeline（爬取 + 评分）
│   ├── v4.py              ← 当前主用爬虫（CDP + Playwright + 召回扩展）
│   ├── v4_1.py            ← v4 升级版评分
│   ├── v3.py / v3_1.py    ← 上一代评分（簇匹配 v3）
│   ├── v2.py              ← 上上代（独立技能加分）
│   ├── enrich.py          ← 旧版详情补全
│   ├── enrich_junior.py   ← 初级岗位特化
│   ├── run.py             ← 早期 simple scraper
│   ├── run_junior.py      ← 早期 junior scraper
│   ├── score_v4.py        ← v4 评分独立脚本
│   └── inspect_dom.py     ← 调试用（看 BOSS 直聘 DOM 结构）
│
├── 📊 数据快照（按版本归档）
│   ├── v4_1_output/       ← 当前生产快照 ⭐
│   │   ├── tiered.json    ← P0/P1/P2/P3 + 原始字段（数据源）
│   │   ├── rejected.json  ← 被剔除岗位 + 原因
│   │   ├── jobs.xlsx      ← 旧版 Excel
│   │   ├── jobs.html      ← 旧版纯前端 HTML（已弃）
│   │   └── v5.html        ← 当前生产 SPA ⭐
│   ├── v4_output/         ← v4 中间产物
│   ├── v3_1_output/       ← v3.1 历史
│   ├── v3_output/         ← v3 历史
│   ├── v2_output/         ← v2 历史
│   └── junior_output/     ← 初级岗实验
│
├── 🌐 前端 SPA 生成器
│   ├── build_html_v5.py   ← 主生成器（4654 行，含完整 SPA）⭐
│   └── build_html.py      ← 旧版生成器（已弃）
│
├── 🔌 BFF / 代理服务
│   ├── training_bff_v2.py ← 当前 BFF（FastAPI）⭐
│   ├── training_bff.py    ← BFF v1（http.server，已被 v2 替代）
│   ├── maas_proxy.py      ← 早期 hpc-ai 代理（CORS workaround，被 BFF v2 取代）
│   └── asr_proxy.py       ← 早期 ASR 代理（被 BFF v2 取代）
│
├── 📋 配置 / 依赖
│   ├── config.py
│   ├── requirements.txt           ← 老的（仅 playwright）
│   └── requirements-bff.txt       ← BFF v2 需要的（fastapi/uvicorn/httpx/websockets）
│
├── 📚 设计文档
│   ├── ARCHITECTURE.md            ← 本文档 ⭐
│   ├── DESIGN.md                  ← 早期总体设计
│   ├── PRODUCT_REDESIGN.md        ← 第一性原理重构思考
│   ├── SCORING_V3.md              ← 评分模型 v3
│   ├── SEARCH_MODEL.md            ← 搜索模型 v1
│   └── SEARCH_MODEL_V2.md         ← 搜索模型 v2
│
├── 🗂 浏览器登录态（CDP）
│   ├── .auth/             ← 主要 Chrome user-data-dir
│   ├── .auth_v2/
│   └── .auth_stealth/
│
├── 🐛 调试中间产物
│   ├── debug_*.png                ← 截图
│   ├── full_output.log
│   ├── run_output.log
│   ├── inspect_output.log
│   └── enrich_output.log
│
├── 🔍 早期实验
│   ├── chrome-extension/          ← 实验性 Chrome 扩展
│   └── scraper.py                 ← 最早期 scraper
│
└── 📁 旧产物
    ├── jobs.csv / jobs.json / jobs_analysis.xlsx / jobs_enriched.json  ← 早期输出
    └── *.sh                       ← 早期启动脚本
```

**当前生产链路**（重构时只需要关心这条）：

```
v4.py → v4_1.py → v4_1_output/tiered.json
                ↓
        build_html_v5.py
                ↓
        v4_1_output/v5.html
                ↓
        training_bff_v2.py 启动 BFF
                ↓
        浏览器访问 http://127.0.0.1:8891/job-scraper/v4_1_output/v5.html
```

---

## 三、关键模块详解

### 3.1 `build_html_v5.py` —— 前端生成器（4654 行）

> 这是一个 **HTML 模板字符串** + Python 数据清洗器。所有前端逻辑（CSS/JS/HTML）都在 `HTML_TEMPLATE` 这个超长字符串里。

**Python 部分（~70 行）**：
- `clean_text()` / `clean_title()` / `clean_salary()` —— 清理 PUA 字符（BOSS 直聘字体反爬）
- `clean_job(j)` —— 清洗岗位数据 + 删除 `text/card_text/score/matched` 等冗余字段
- `main()` —— 读 `tiered.json` + `rejected.json`，把 JSON 字符串内嵌到 HTML 模板，输出 `v5.html`

**HTML 模板内的 JS 部分（~4500 行）**：

| 段落（按顺序） | 行号区间 | 职责 |
|--------------|---------|------|
| `// 数据模型 v3 - 正交化` | 1293-1424 | localStorage schema + storage migration（v2→v3） |
| `// 工具` | 1425-1490 | 通用 helpers (`escapeHtml` / `fmtDate` / etc.) |
| `// 视图：Today` | 1491-1626 | `renderToday()` —— 即将面试/需要跟进/待 triage |
| `// 视图：Discover (Inbox)` | 1627-1769 | `renderDiscover()` + `renderInboxRow()` —— 列表式 triage |
| `// 视图：Pipeline` | 1770-1852 | `renderPipeline()` + `renderKanbanCard()` —— Kanban 看板 |
| `// 详情 Modal` | 1853-1949 | 点击 Pipeline 卡片打开的详情弹窗 |
| `// 添加面试 Modal` | 1950-2006 | 添加面试时间/类型/结果 |
| `// 训练场 (Training Ground)` | 2007-3919 | **核心新模块**，详见 §3.4 |
| `// 复盘录入 Modal` | 3920-4508 | 面试复盘录题目（4 评分 + 标签） |
| `// 占位 + 主路由` | 4509-末尾 | `renderDecision()` / `render()` / 事件绑定 |

**视图 Tab**（5 个）：
- 🎯 Today
- 🔍 Discover
- 💼 Pipeline
- 🥋 训练场（**主战场**，占代码 1900+ 行）
- 📊 Decision（占位）

---

### 3.2 `training_bff_v2.py` —— BFF（FastAPI 单文件 ~340 行）

| Endpoint | Method | 用途 |
|----------|--------|------|
| `/` (mount) | GET | 静态文件，挂载 `--root` 指定的目录 |
| `/api/v1/diag/ping` | GET | 健康检查 |
| `/api/v1/config/runtime` | GET | 运行时 config（feature flags） |
| `/api/v1/chat` | POST | LLM 代理，body 含 `target.{base_url, model, api_key, extra_headers}` + `messages` |
| `/api/v1/asr/transcribe` | POST | 音频文件转写代理（multipart upload） |
| `/api/v1/asr/ws` | WebSocket | **桥接火山引擎实时 ASR**（关键，因为浏览器 native WS 加不了 `X-Api-*` header） |

**WebSocket 桥接细节**：
- 第一帧必须是 `{"type":"init", "config":{wsUrl, apiAppId, apiAccessKey, apiResourceId, apiAppKey, ...}}`
- BFF 用 `websockets.connect(extra_headers=...)` 携带 `X-Api-*` 连接火山
- 实现了火山的二进制协议：`_pack_header / _pack_frame / build_full_client_request / build_audio_frame / parse_server_text`
- 客户端发音频 bytes，BFF 包成火山协议帧；火山返回 partial，BFF 解包成 JSON `{type:"partial", text}` 推给浏览器

**跨域**：CORS 全开（`allow_origins=["*"]`），但实际生产用同源，不依赖 CORS。

---

### 3.3 数据 Schema

#### A. 离线 Pipeline 输出（`v4_1_output/tiered.json`）

```jsonc
{
  "P0": [
    {
      "title": "AI平台-算力调度",
      "company": "某互联网公司",
      "salary": "XX-XXK·XX薪",
      "area": "北京通州区...",
      "experience": "经验不限",
      "href": "https://www.zhipin.com/job_detail/xxx.html",
      "jd": "岗位职责...",
      "company_info": "公司基本信息...",
      "tags": "标签...",
      "source_keyword": "算力",
      "source_exp": "初级",
      "source": "BOSS直聘",
      "final_score": 119.0,
      "cluster_score": 95.0,
      "title_cluster_score": 60.0,
      "exp_bonus": 0,
      "company_bonus": 12,
      "negative_penalty": 0,
      "negative_reasons": [],
      "cluster_hits": [
        {"name": "platform_ai_infra", "display": "平台型 AI Infra（完美对口）", "score": 41, "opt_hits": 4}
      ],
      "tier": "P0"
    }
  ],
  "P1": [...], "P2": [...], "P3": [...]
}
```

#### B. 前端 localStorage Schema

**`job_tracker_v3`** —— 岗位用户状态
```jsonc
{
  "<jobId>": {
    "intent": "unknown" | "target" | "practice" | "backup" | "ignored",
    "pipelineCol": "todo" | "applied" | "contacting" | "interviewing" | "offer" | "closed",
    "outcome": null | "rejected_by_them" | "rejected_by_me" | "accepted" | "ghosted",
    "triagedAt": "ISO timestamp",
    "appliedAt": "ISO timestamp",
    "lastTouchAt": "ISO timestamp",
    "interviews": [
      {
        "type": "一面",
        "time": "ISO",
        "location": "腾讯会议",
        "result": "pass" | "fail" | "pending",
        "questions": [/* 同 training_v1.questions */],
        "reflection": "总体反思..."
      }
    ],
    "notes": ""
  }
}
```

> **迁移**：v3 schema 自动从 `job_tracker_v2`（旧 status enum）迁移而来，迁移函数在 `loadStore()` 内部。

**`training_v1`** —— 独立题库（训练场核心）
```jsonc
{
  "questions": [
    {
      "id": "q_xxx",
      "text": "K8s informer 的工作原理",
      "topics": ["K8s 架构", "Informer"],
      "rating": "good" | "ok" | "bad" | null,
      "reviewNote": "",
      "source": "manual" | "interview" | "derived",

      "createdAt": "ISO",
      "updatedAt": "ISO",

      // 间隔复习
      "reviewCount": 0,
      "lastReviewedAt": null,
      "nextReviewAt": null,

      // 笔记 / 行动
      "note": "",
      "actionItems": [],
      "nextQuestion": "",

      // 口述训练
      "speakingLogs": [
        {"startedAt": "ISO", "transcript": "...", "selfRating": "good", "feedback": "AI 自评..."}
      ],

      // AI 答案（三种模式）
      "answer": null,                // default 答案
      "bestPracticeAnswer": null,    // 最佳实践模式
      "followupAnswer": null,        // 模拟追问模式
      "lastAnswerMode": "default",

      // 题目拆解 / 关系图
      "decomposition": {
        "firstPrinciples": [...],
        "learningPath": [...],
        "subQuestions": [...]
      },
      "parentId": null,              // 母题 id
      "relationReason": "",          // 关系说明

      "conversation": []             // 多轮对话历史
    }
  ]
}
```

**`training_settings_v1`** —— LLM 配置
```jsonc
{
  "baseUrl": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "apiKey": "sk-xxx",
  "extraHeaders": "X-MaaS-Main-UID: xxx",
  "stream": true
}
```

**`training_asr_settings_v1`** —— ASR 配置
```jsonc
{
  "asr": {
    "transport": "websocket",
    "wsUrl": "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel",
    "apiAppId": "...",
    "apiAccessKey": "...",
    "apiResourceId": "volc.speech.dialog",
    "apiAppKey": "PlgvMymc7f3tQnJ6",
    "language": "zh"
  }
}
```

**`training_resume_drill_v1`** —— 简历拷打缓存
```jsonc
{
  "resumeText": "...",
  "drill": {
    "red_flags": [...],
    "dimensions": [{ "name": "...", "questions": [...] }]
  },
  "updatedAt": "ISO"
}
```

**其他 keys**：
- `training_answer_cache_v1` —— AI 答案外部缓存（防 quota）
- `training_ui_v1` —— UI 偏好（lite/full mode）

---

### 3.4 训练场（`build_html_v5.py` 内 1900+ 行的核心模块）

> 训练场是这次重构的灵魂。它把"做题"从"看 JSON"升级成了 **"采集 → 拆解 → 训练 → 复盘 → 行动"** 的完整闭环。

#### 子模块图

```
🥋 训练场
│
├── 🧭 训练 Hub（renderTrainingHub）
│   ├── 母题数 / 子题数 / 图谱覆盖率
│   ├── 今日待练 / 笔记题目 / 行动项
│   └── 智能"下一步建议"
│
├── ⚔ 简历拷打（renderResumeDrillSection）
│   ├── 粘贴简历
│   ├── AI 生成 red_flags + dimensions
│   └── 一键添加为题目
│
├── 🎤 口述训练
│   ├── startSpeakingDrill：录音 + WebSocket ASR 实时转写
│   ├── finishSpeakingDrill：AI 自评（结构/准确性/深度/表达 4 维 + 30 秒示例开场）
│   ├── 录音回放
│   └── 复盘历史 (renderSpeakingReviewSection)
│
├── 🎯 今日训练队列（getDueStandaloneQuestions）
│   ├── SM-2 简化版间隔复习
│   ├── bad → 1天后；ok → 3-5天；good → 3/7/21天 递增
│   └── 强制按 nextReviewAt 排序
│
├── 📚 自学题库（renderQuestionCard / renderQuestionCardLite）
│   ├── 三种 AI 回答模式
│   │   ├── default 标准答案
│   │   ├── 🧭 best_practice 最佳实践清单
│   │   └── 🥊 followup 模拟追问
│   ├── 评分（good/ok/bad → 影响下次复习时间）
│   ├── 笔记 / 行动项
│   ├── 题目拆解（decomposeQuestionByAI）→ 生成子题
│   └── 父子图谱（renderQuestionGraph）
│
├── 📝 面试复盘 (renderQuestionGraph + getAllReflections)
│   ├── 从 job_tracker_v3.interviews.questions 读取
│   └── 统一汇入热力图
│
├── 📊 技能熟练度热力图（aggregateTopics）
│   ├── 红/黄/绿三色按 score < 0.5 / 0.8 / ≥0.8 分类
│   └── 点击 topic 下钻
│
└── 📋 录入入口
    ├── + 单条添加（openAddQuestion）
    ├── 📋 批量粘贴（openBulkImport + inferTopics 自动打标）
    └── 📝 复盘录入（openReflectionModal，从 Pipeline 入口）
```

#### Lite vs Full 模式

- `trainingMode = 'lite' | 'full'`，存在 `training_ui_v1`
- **Lite 模式**：只显示今日训练队列 + 最简卡片，移动场景下用
- **Full 模式**：完整功能，桌面学习场景

切换函数：`toggleTrainingMode()`

---

## 四、当前痛点 / 重构目标

### 痛点 1：单文件 4654 行的 HTML 模板

**问题**：`build_html_v5.py` 把 CSS/JS/HTML/数据生成全塞在一个文件里，最大问题：
- 修任何 UI 都要在 4500+ 行的 raw string 里搜
- 没有类型检查、没有 lint、没有热重载
- JS 函数数量爆炸（90+ 个全局函数挂在 `window`）
- CSS 全局污染，没有模块隔离

**重构方向**：
- 前端独立成 Vite + 任意框架（React/Vue/Svelte）项目
- BFF 提供 RESTful API，前端通过 fetch 取数据，不再"编译时内嵌"
- HTML 模板 → 真正的 SPA

### 痛点 2：数据存储散乱

**问题**：5 个 localStorage key，schema 没集中定义：
- `job_tracker_v3` / `training_v1` / `training_settings_v1` / `training_asr_settings_v1` / `training_resume_drill_v1` / `training_answer_cache_v1` / `training_ui_v1`

迁移逻辑散落在 `loadStore()` / `loadTraining()` / `normalizeQuestion()` 里。

**重构方向**：
- 抽象出 storage layer：`AppStorage`（带版本号 + 迁移管线）
- TypeScript 定义 schema
- 考虑迁移到 IndexedDB（localStorage 5MB 上限会成为瓶颈，特别是录音/AI 答案缓存）

### 痛点 3：BFF 和爬虫职责模糊

**问题**：BFF 只做转发，但爬虫的输出 `tiered.json` 是静态文件嵌入 HTML 编译的，所以：
- 重新爬完要手动跑 `build_html_v5.py`
- 浏览器看到的"岗位列表"是冻结的快照
- 用户标记的 intent / 投递时间 在跨次爬取后**无法关联**到新岗位

**重构方向**：
- BFF 提供 `/api/v1/jobs` —— 直接读 `tiered.json` 返回，前端 fetch
- BFF 提供 `/api/v1/jobs/state` —— CRUD 用户状态，存到本地 SQLite
- 用户状态从 localStorage 迁移到服务端 SQLite（仍然本地，但允许跨浏览器/设备）

### 痛点 4：训练场和岗位联动弱

**问题**：训练场的题目和岗位完全分开（`training_v1` vs `job_tracker_v3`）。理论上：
- 投了某家公司 → 应该自动推荐"这家公司常考的题"
- 拿到面试 → 应该一键挂到训练场的"专项准备"
- 简历拷打的内容应该能 link 到实际投递的目标公司

但现在两边数据没关联。

**重构方向**：
- 让 question 支持 `linkedJobId` / `linkedCompany` 字段
- Pipeline 卡片增加"关联训练题"快捷入口
- 训练场增加"按公司 / 按岗位"维度

### 痛点 5：版本残留太多

**问题**：v2 / v3 / v3_1 / v4 / v4_1 同时存在，新人看到不知道用哪个；junior_output / 早期 jobs.csv 这些冗余产物没清理。

**重构方向**：
- 重构时只保留 v4_1 和 v5.html
- 其他归档到 `_legacy/` 目录
- README 只说明当前生产链路

### 痛点 6：BFF v2 和 v1 重复

`training_bff.py`（v1，纯 http.server）和 `training_bff_v2.py`（v2，FastAPI）并存。`maas_proxy.py` / `asr_proxy.py` 也已被 BFF v2 包含。

**重构方向**：
- 删 `training_bff.py` / `maas_proxy.py` / `asr_proxy.py`
- 只留 `training_bff_v2.py`，重命名为 `bff.py`

---

## 五、推荐的重构后目录结构

```
job-os/
│
├── server/                       ← 后端（Python 单包）
│   ├── pyproject.toml
│   ├── job_os/
│   │   ├── __init__.py
│   │   ├── bff/                  ← FastAPI app（取代 training_bff_v2.py）
│   │   │   ├── main.py
│   │   │   ├── routers/
│   │   │   │   ├── chat.py       ← LLM 代理
│   │   │   │   ├── asr.py        ← ASR 转写 + WebSocket 桥接
│   │   │   │   ├── jobs.py       ← 岗位 CRUD（读 tiered.json + 写 user state）
│   │   │   │   ├── questions.py  ← 题库 CRUD
│   │   │   │   └── diag.py       ← 健康检查 / 配置
│   │   │   └── deps.py
│   │   ├── scraper/              ← 爬虫包（取代 v4.py + v4_1.py 等）
│   │   │   ├── boss.py           ← BOSS 直聘 scraper
│   │   │   ├── pipeline.py       ← 评分 + 分层 + 输出
│   │   │   ├── scoring.py        ← 评分模型（簇匹配 v3.1）
│   │   │   └── cli.py            ← 命令行入口
│   │   ├── storage/              ← 数据访问层
│   │   │   ├── jobs_store.py     ← 静态 jobs 数据
│   │   │   ├── user_store.py     ← SQLite 用户状态
│   │   │   ├── questions_store.py← SQLite 题库
│   │   │   └── migrations/       ← schema 迁移
│   │   └── llm/
│   │       ├── client.py         ← OpenAI 兼容客户端
│   │       └── providers.py      ← 预设供应商
│   └── data/
│       ├── snapshot.json         ← 当前的 tiered.json
│       └── app.db                ← SQLite
│
├── web/                          ← 前端（Vite 单包）
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.ts
│       ├── App.tsx (or .vue)
│       ├── views/
│       │   ├── Today.tsx
│       │   ├── Discover.tsx
│       │   ├── Pipeline.tsx
│       │   ├── Training/
│       │   │   ├── Hub.tsx
│       │   │   ├── ResumeDrill.tsx
│       │   │   ├── SpeakingDrill.tsx
│       │   │   ├── DueQueue.tsx
│       │   │   └── Heatmap.tsx
│       │   └── Decision.tsx
│       ├── components/
│       │   ├── JobCard.tsx
│       │   ├── QuestionCard.tsx
│       │   ├── KanbanBoard.tsx
│       │   └── modals/
│       ├── stores/               ← 状态管理（Zustand / Pinia）
│       │   ├── jobs.ts
│       │   ├── questions.ts
│       │   └── settings.ts
│       ├── api/                  ← BFF 客户端
│       │   ├── chat.ts
│       │   ├── asr.ts
│       │   ├── jobs.ts
│       │   └── questions.ts
│       └── lib/
│           ├── spaced-repetition.ts
│           ├── topic-inference.ts
│           └── audio.ts
│
├── docs/
│   ├── ARCHITECTURE.md           ← 本文件
│   ├── DEVELOPMENT.md
│   └── DESIGN/                   ← 历史设计文档归档
│
├── scripts/
│   ├── start-dev.sh              ← 一键启动 BFF + Web dev
│   └── scrape.sh                 ← 跑爬虫
│
└── _legacy/                      ← 旧版归档（重构后保留以备查）
    └── job-scraper/              ← 整个旧目录扔这里
```

---

## 六、重构 Checklist（建议执行顺序）

### 阶段 1：清理（半天）
- [ ] 把 `v2.py / v3.py / v3_1.py / run.py / run_junior.py / scraper.py / inspect_dom.py` 等历史 Python 移到 `_legacy/`
- [ ] 删除 `v2_output / v3_output / v3_1_output / v4_output / junior_output / chrome-extension`
- [ ] 删除 `maas_proxy.py / asr_proxy.py / training_bff.py`（功能被 BFF v2 覆盖）
- [ ] 删除 `build_html.py`（被 v5 取代）
- [ ] 删除根目录散落的 `jobs.csv / jobs.json / *.xlsx / debug_*.png / *.log`

### 阶段 2：后端模块化（1-2 天）
- [ ] 把 `training_bff_v2.py` 拆成 `server/job_os/bff/` 包
- [ ] 抽出 routers/chat.py + routers/asr.py
- [ ] 增加 routers/jobs.py（取代 HTML 编译时数据嵌入）
- [ ] 增加 SQLite 持久层 `storage/` + 从 localStorage 迁移脚本
- [ ] 把 `v4.py / v4_1.py / v3_1.py` 重写到 `scraper/` 包

### 阶段 3：前端工程化（2-3 天）
- [ ] 用 Vite 起 SPA 工程（建议 React + TS，已知技能栈）
- [ ] 拆分 5 个 view 为独立组件
- [ ] 把 `build_html_v5.py` 内 90+ 个 JS 函数按职责拆分到 `lib/` `stores/` `views/`
- [ ] CSS 改用 CSS Modules / Tailwind / styled-components
- [ ] 状态管理（Zustand 推荐，schema TypeScript 化）

### 阶段 4：数据闭环（半天）
- [ ] 训练场题目支持 `linkedJobId`
- [ ] Pipeline 卡片增加"关联训练"入口
- [ ] 训练场新增"按公司"分组视图

### 阶段 5：可选增强
- [ ] 录音/AI 答案缓存迁移到 IndexedDB（localStorage 5MB 限制）
- [ ] 题库导入/导出（json + markdown）
- [ ] 知识点关联图可视化（D3 / Cytoscape）

---

## 七、关键依赖

### Python（BFF）
```
fastapi>=0.111.0
uvicorn>=0.30.0
httpx>=0.27.0
websockets>=12.0
python-multipart>=0.0.9
```

### Python（爬虫）
```
playwright>=1.40
beautifulsoup4
openpyxl
```

### 上游依赖
- **LLM**：任何 OpenAI 兼容接口（DeepSeek / hpc-ai dev MaaS / OpenAI / Kimi / GLM / 自定义）
- **ASR**：火山引擎实时语音识别（OpenSpeech 大模型协议）

---

## 八、当前可用的启动指令

```bash
# 1. 跑爬虫（按需）
cd $HOME/Projects/my-project/job-scraper
python3 v4.py        # 爬取 + 拉取
python3 v4_1.py      # 评分 + 分层

# 2. 生成 SPA
python3 build_html_v5.py

# 3. 启 BFF
pip3 install -r requirements-bff.txt
python3 training_bff_v2.py --port 8891 --root $HOME/Projects/my-project

# 4. 浏览器访问
open http://127.0.0.1:8891/job-scraper/v4_1_output/v5.html
```

---

## 九、术语表

| 术语 | 含义 |
|------|------|
| **BFF** | Backend for Frontend，前端的后端代理层 |
| **Tier** | 岗位匹配度分层 P0/P1/P2/P3，由 v4_1 评分模型决定 |
| **Cluster** | 评分中的"技能簇"，如 `platform_ai_infra` / `go_k8s_platform` / `gpu_cloud_platform` |
| **Intent** | 用户对岗位的意图：`unknown / target / practice / backup / ignored` |
| **Pipeline Col** | Kanban 阶段：`todo / applied / contacting / interviewing / offer / closed` |
| **CDP** | Chrome DevTools Protocol，Playwright 控制 Chrome 用 |
| **PUA 字符** | Unicode Private Use Area，BOSS 直聘字体反爬手段 |
| **复盘录入** | 面试结束后把题目结构化录入题库 |
| **拆解** | AI 把母题拆成第一性原理 + 学习路径 + 子题 |
| **拷打** | 简历拷打：粘贴简历让 AI 生成 red flags + 拷打维度 |
| **口述训练** | 录音 + 实时 ASR + AI 自评（4 维度） |
| **间隔复习** | SM-2 简化版，根据评分决定下次复习时间（1/3/7/21 天） |

---

> **下一步**：如果决定重构，建议先做"阶段 1 清理"和"阶段 5 数据闭环"中的"训练题与岗位联动"，**ROI 最高 + 风险最低**。前端工程化是大工程，建议有完整 1-2 周才动手。
