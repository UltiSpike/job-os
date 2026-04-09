# Job OS 全量重构规划

> 撰写时间：2026-04-08
> 目标：从「单文件 4654 行的 HTML 模板 + 单脚本 BFF + 5 代散落数据」→ **工程化的全栈应用**
> 定位：**个人产品 + 简历项目 + 工程练手三合一**

---

## 一、重构的根本目的

不是为了「让代码看起来像样」，而是为了三件事：

| 目的 | 量化指标 |
|------|---------|
| **能持续迭代** | 加新 view / 改业务逻辑的成本从「半天」降到「半小时」 |
| **能作为简历项目** | 任何技术细节都经得起 P6/P7 面试官追问 |
| **能跨设备使用** | 手机/平板/笔记本随时打开都能用，数据实时同步 |

如果重构完成后这三件事没解决，那就是失败。

---

## 二、技术选型（带论证）

### 2.1 整体架构

```
┌─────────────────────────────────────────────┐
│  scraper/   (Python · 离线爬虫)              │
│      ↓ 输出 snapshot.json                    │
└─────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│  server/    (Go · BFF + 业务后端)            │
│      - REST API + WebSocket                  │
│      - SQLite 持久化                         │
│      - LLM/ASR 代理                          │
└─────────────────────────────────────────────┘
                  ▲
                  │ HTTP / WS
┌─────────────────────────────────────────────┐
│  web/       (React + TS + Vite · SPA)       │
│      - 5 视图                                │
│      - Zustand 状态                          │
│      - PWA 离线可用                          │
└─────────────────────────────────────────────┘
```

**核心决策：三服务三语言，各取所长**。

### 2.2 后端：为什么用 Go

| 选项 | Pros | Cons | 决策 |
|------|------|------|------|
| **Go** | 用户主语言；单二进制部署；强类型；性能；**简历价值最高** | LLM streaming/ASR WS 桥接需要现写 | ✅ **选这个** |
| Python (FastAPI) | 现有 BFF 直接用；ASR 协议已实现 | 不是用户主语言；类型系统弱；简历价值低 | ❌ |
| Node.js | 和前端共语言 | 用户不熟；JS 心智模型在后端反而拖累 | ❌ |

**关键论证**：你正在准备 Go + K8s 方向的面试，**这个项目就该是你的简历项目**。用 Go 写 BFF 意味着每一个面试技术点（goroutine、channel、context、标准库 net/http、SSE 流、WebSocket 升级、SQLite driver、错误处理、单元测试、go-zero 框架）都能在这个项目里实操出来。

ASR WebSocket 桥接和 SSE 流在 Go 里其实**比 Python 更优雅**（goroutine + channel 天然适合）。

**框架**：
- **net/http + chi** 或 **go-zero**
- 推荐 **go-zero**——和 internal-platform 同框架，你能复用经验，简历上还能写"基于 go-zero 微服务框架开发"

### 2.3 前端：为什么用 React + TS + Vite

| 选项 | Pros | Cons | 决策 |
|------|------|------|------|
| **React + TS** | 生态最大；面试官最熟；招聘最常见；可以写大型应用 | 心智模型相对复杂 | ✅ **选这个** |
| Vue 3 + TS | 心智模型清晰；学习曲线友好 | 后端岗简历价值不如 React | 🤷 备选 |
| SvelteKit | 最简洁；性能最好 | 生态小；国内招聘少 | ❌ |
| Solid | 反应式；性能好 | 太小众 | ❌ |

**关键论证**：你不需要花时间纠结，React 是后端工程师"懂前端"的标配。Vite 是 build 工具的事实标准。

**状态管理**：**Zustand**（不要 Redux，太重）

**UI 框架**：**Tailwind CSS + shadcn/ui**
- Tailwind = 无需写 CSS 文件，直接在 JSX 里写 class
- shadcn/ui = 不是组件库，是"复制粘贴的组件代码"，完全可控
- 这两个组合是 2026 年的事实标准，简历上写"Tailwind CSS"是加分项

### 2.4 数据存储

| 层 | 选型 | 理由 |
|----|------|------|
| **业务数据**（jobs/questions/interviews） | **SQLite** | 单用户 + 单文件 + 零运维；够用十年 |
| **大对象**（录音 blob / AI 答案缓存） | **文件系统 + SQLite 索引** | 录音是二进制，存 SQLite 不优雅 |
| **配置**（LLM endpoint / ASR token） | **SQLite settings 表** | 集中管理，方便导入导出 |

**ORM/Query Builder**：
- **sqlc**（推荐）：写 SQL → 生成类型安全的 Go 代码
- 或 **ent**（Facebook 出品的 ORM，internal-platform 在用）—— **简历加分，建议这个**

**Schema 迁移**：**atlas** 或 **goose**

### 2.5 爬虫：保持 Python

**不要重写**。Playwright 在 Python 生态里是一等公民，Go 的 Playwright 绑定不成熟。

scraper 作为**独立工具**，输出 JSON 到 `server/data/snapshot.json`，server 启动时读取。爬虫的代码组织也要工程化（包结构 + CLI + tests）。

### 2.6 通信协议

| 场景 | 协议 | 选型 |
|------|------|------|
| 一般 CRUD | REST | JSON |
| LLM 流式回答 | SSE (Server-Sent Events) | text/event-stream |
| 实时 ASR | WebSocket | 双向 |
| 类型契约 | OpenAPI 3.1 | 自动生成 TS client |

**关键决策：用 OpenAPI 自动生成前端 TypeScript 客户端**。
- Go 用 `swaggo` 或写 `*.api` 文件（go-zero 原生支持）
- 前端用 `openapi-typescript` 生成 type-safe 的 fetch client
- **这能彻底消除前后端 schema 不一致的问题**，是工程化的关键一步

---

## 三、领域模型（DDD 视角）

### 3.1 核心实体

```
┌────────────┐         ┌────────────┐         ┌────────────┐
│   Job      │ 1─────* │ Interview  │ 1─────* │ Question   │
│            │         │            │         │            │
│ id         │         │ jobId      │         │ id         │
│ title      │         │ type       │         │ text       │
│ company    │         │ time       │         │ topics[]   │
│ salary     │         │ result     │         │ rating     │
│ jd         │         │ ...        │         │ source     │
│ score      │         └────────────┘         │ ...        │
│ tier       │                                 │ jobId?     │ ← 可选关联
│ ...        │                                 │ parentId?  │ ← 题目图谱
└────────────┘                                 └────────────┘
      │                                              │
      │ hasState                                     │ hasReviews
      ▼                                              ▼
┌────────────┐                                 ┌────────────┐
│ JobState   │                                 │ Review     │
│            │                                 │            │
│ jobId      │                                 │ questionId │
│ intent     │                                 │ rating     │
│ pipelineCol│                                 │ reviewedAt │
│ outcome    │                                 │ nextDueAt  │
│ appliedAt  │                                 └────────────┘
│ notes      │
└────────────┘
```

**关键抽象**：
- **Job** 是不可变的（爬虫产出），**JobState** 是用户的状态（可变）—— 两者分离让爬虫和用户数据互不影响
- **Question** 可以独立于 Interview 存在（自学题）
- **Question.jobId** 可选，让训练场和岗位 Pipeline 联动（"快手投了→生成快手专项题库"）
- **Review** 是一次复习记录，间隔复习算法基于 review history 决定下次时间

### 3.2 边界上下文

```
┌─────────────────────┐    ┌─────────────────────┐
│  Job Discovery      │    │  Job Tracking       │
│                     │    │                     │
│  Job (read-only)    │    │  JobState           │
│  Cluster            │    │  Interview          │
│  Score              │    │  Application        │
└─────────────────────┘    └─────────────────────┘
            │                        │
            │   linkedJobId          │
            │                        │
            ▼                        ▼
┌─────────────────────────────────────────────┐
│         Training & Knowledge                 │
│                                              │
│  Question                                    │
│  Topic                                       │
│  Review (spaced repetition)                  │
│  Decomposition                               │
│  ResumeDrill                                 │
│  SpeakingDrill                               │
└─────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────┐
│         External Services                    │
│                                              │
│  LLM Provider (OpenAI compatible)            │
│  ASR Provider (Volc)                         │
└─────────────────────────────────────────────┘
```

四个边界上下文，对应到 Go 项目里就是四个 package：
- `discovery/`
- `tracking/`
- `training/`
- `external/`

---

## 四、API 设计

### 4.1 RESTful 端点

```
# 健康检查
GET    /api/v1/health

# 岗位 (read-only，from snapshot.json)
GET    /api/v1/jobs                    ← 列表 + 过滤 + 分页
GET    /api/v1/jobs/{id}               ← 单个详情
GET    /api/v1/jobs/stats              ← 统计（P0/P1 数量等）
POST   /api/v1/jobs/refresh            ← 触发重新加载 snapshot

# 岗位状态
GET    /api/v1/job-states              ← 当前用户所有 state
PATCH  /api/v1/job-states/{jobId}      ← 更新 intent / pipelineCol
DELETE /api/v1/job-states/{jobId}      ← 重置

# 面试
GET    /api/v1/interviews?jobId=xxx
POST   /api/v1/interviews              ← 创建
PATCH  /api/v1/interviews/{id}
DELETE /api/v1/interviews/{id}

# 题库
GET    /api/v1/questions               ← 列表 + 过滤（topic / source / due）
GET    /api/v1/questions/{id}
POST   /api/v1/questions               ← 单个或批量
PATCH  /api/v1/questions/{id}          ← 评分 / 笔记 / 答案
DELETE /api/v1/questions/{id}
POST   /api/v1/questions/import        ← 批量粘贴 + 自动打标
GET    /api/v1/questions/topics        ← 技能点聚合（热力图数据）
GET    /api/v1/questions/due           ← 今日待复习
POST   /api/v1/questions/{id}/review   ← 提交复习评分（更新间隔）

# 拆解 / 简历拷打
POST   /api/v1/questions/{id}/decompose ← AI 拆解
POST   /api/v1/resume-drill            ← 生成拷打题
GET    /api/v1/resume-drill/latest

# AI 代理
POST   /api/v1/llm/chat                ← 流式 SSE
POST   /api/v1/llm/test                ← 配置测试
GET    /api/v1/llm/config
PUT    /api/v1/llm/config

# ASR
POST   /api/v1/asr/transcribe          ← 文件转写
WS     /api/v1/asr/stream              ← 实时桥接（火山 OpenSpeech）
GET    /api/v1/asr/config
PUT    /api/v1/asr/config

# 数据迁移
POST   /api/v1/migrate/from-localstorage  ← 一次性导入老数据
GET    /api/v1/export                     ← 导出全部数据
POST   /api/v1/import                     ← 导入备份
```

### 4.2 OpenAPI 契约

用 **go-zero `.api` 文件**定义所有端点，自动生成：
1. Go 服务端 handler 骨架
2. TypeScript 前端 client（通过 `goctl` 或 `openapi-typescript`）

例：
```api
// server/api/jobs.api
type Job {
    Id          string   `json:"id"`
    Title       string   `json:"title"`
    Company     string   `json:"company"`
    Salary      string   `json:"salary,optional"`
    Tier        string   `json:"tier"`
    FinalScore  float64  `json:"final_score"`
    // ...
}

type ListJobsReq {
    Tier     string `form:"tier,optional"`
    Company  string `form:"company,optional"`
    Page     int    `form:"page,default=1"`
    PageSize int    `form:"page_size,default=20"`
}

type ListJobsResp {
    Items []Job `json:"items"`
    Total int64 `json:"total"`
}

@server (
    prefix: /api/v1
    group:  jobs
)
service job-os-api {
    @handler ListJobs
    get /jobs (ListJobsReq) returns (ListJobsResp)

    @handler GetJob
    get /jobs/:id returns (Job)
}
```

跑 `goctl api go -api jobs.api -dir .` → 自动生成 handler 骨架。

---

## 五、目录结构（最终态）

```
job-os/                              ← 项目根
│
├── README.md
├── ARCHITECTURE.md                   ← 已有
├── REFACTOR_PLAN.md                  ← 本文件
├── docker-compose.yml                ← 一键启动（dev + prod）
├── Makefile                          ← 常用命令封装
│
├── server/                           ← Go 后端
│   ├── go.mod
│   ├── go.sum
│   ├── main.go                       ← 入口，启动 HTTP + WS
│   ├── api/                          ← go-zero .api 文件
│   │   ├── jobs.api
│   │   ├── questions.api
│   │   ├── llm.api
│   │   ├── asr.api
│   │   └── all.api                   ← 聚合
│   ├── internal/
│   │   ├── config/                   ← 配置加载
│   │   ├── handler/                  ← HTTP handlers (生成)
│   │   ├── logic/                    ← 业务逻辑
│   │   │   ├── jobs/
│   │   │   ├── questions/
│   │   │   ├── interviews/
│   │   │   ├── llm/
│   │   │   └── asr/
│   │   ├── svc/                      ← Service Context (DI)
│   │   ├── types/                    ← 生成的 DTO
│   │   ├── ent/                      ← Ent ORM 生成的代码
│   │   │   └── schema/               ← Ent schema 定义
│   │   ├── llm/                      ← LLM client
│   │   │   ├── openai.go
│   │   │   ├── stream.go
│   │   │   └── providers.go
│   │   ├── asr/                      ← ASR client
│   │   │   ├── volc.go               ← 火山协议
│   │   │   ├── frame.go              ← 帧编解码
│   │   │   └── bridge.go             ← WebSocket 桥接
│   │   ├── snapshot/                 ← 读取爬虫产物
│   │   │   ├── loader.go
│   │   │   └── watcher.go            ← 文件变化自动 reload
│   │   ├── spaced/                   ← 间隔复习算法
│   │   │   └── sm2.go
│   │   └── topic/                    ← 技能点推断
│   │       └── inference.go
│   ├── pkg/                          ← 可复用的工具包
│   │   ├── errx/                     ← 业务错误
│   │   ├── logx/                     ← 日志封装
│   │   └── timex/                    ← 时间工具
│   ├── etc/                          ← 配置文件
│   │   ├── dev.yaml
│   │   └── prod.yaml
│   ├── data/                         ← 数据目录（gitignore）
│   │   ├── app.db                    ← SQLite
│   │   ├── snapshot.json             ← 爬虫产物
│   │   └── recordings/               ← 用户录音
│   ├── scripts/
│   │   └── migrate.sh
│   └── tests/                        ← 集成测试
│       ├── jobs_test.go
│       └── llm_test.go
│
├── web/                              ← React 前端
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── index.html
│   ├── public/
│   │   ├── icon.png
│   │   └── manifest.webmanifest      ← PWA
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── routes.tsx                ← React Router
│       ├── views/                    ← 页面级组件
│       │   ├── Today/
│       │   │   ├── index.tsx
│       │   │   ├── UpcomingInterviews.tsx
│       │   │   └── NeedFollowup.tsx
│       │   ├── Discover/
│       │   │   ├── index.tsx
│       │   │   ├── InboxRow.tsx
│       │   │   └── BulkActions.tsx
│       │   ├── Pipeline/
│       │   │   ├── index.tsx
│       │   │   ├── KanbanBoard.tsx
│       │   │   ├── KanbanColumn.tsx
│       │   │   └── KanbanCard.tsx
│       │   ├── Training/
│       │   │   ├── index.tsx
│       │   │   ├── Hub.tsx
│       │   │   ├── DueQueue.tsx
│       │   │   ├── Heatmap.tsx
│       │   │   ├── ResumeDrill.tsx
│       │   │   ├── SpeakingDrill.tsx
│       │   │   ├── QuestionCard.tsx
│       │   │   └── QuestionGraph.tsx
│       │   └── Decision/
│       │       └── index.tsx
│       ├── components/               ← 通用组件
│       │   ├── ui/                   ← shadcn/ui 组件
│       │   ├── modals/
│       │   │   ├── AddQuestionModal.tsx
│       │   │   ├── BulkImportModal.tsx
│       │   │   ├── InterviewModal.tsx
│       │   │   ├── ReflectionModal.tsx
│       │   │   └── SettingsModal.tsx
│       │   └── layout/
│       │       ├── TopNav.tsx
│       │       └── ViewTabs.tsx
│       ├── stores/                   ← Zustand 状态
│       │   ├── jobs.ts
│       │   ├── jobStates.ts
│       │   ├── questions.ts
│       │   ├── settings.ts
│       │   └── ui.ts
│       ├── api/                      ← BFF 客户端（type-safe）
│       │   ├── client.ts             ← fetch wrapper
│       │   ├── generated/            ← openapi-typescript 生成
│       │   │   └── schema.d.ts
│       │   ├── jobs.ts
│       │   ├── questions.ts
│       │   ├── llm.ts
│       │   └── asr.ts
│       ├── hooks/
│       │   ├── useChat.ts            ← LLM SSE 流
│       │   ├── useASR.ts             ← ASR WebSocket
│       │   ├── useDebounce.ts
│       │   └── useLocalStorage.ts
│       ├── lib/                      ← 纯函数工具
│       │   ├── spaced-repetition.ts  ← 间隔复习算法（同后端）
│       │   ├── topic-inference.ts
│       │   ├── format.ts
│       │   └── audio.ts
│       ├── styles/
│       │   └── globals.css           ← Tailwind base
│       └── tests/                    ← Vitest 单测
│
├── scraper/                          ← Python 爬虫（保留 + 工程化）
│   ├── pyproject.toml
│   ├── README.md
│   ├── job_scraper/
│   │   ├── __init__.py
│   │   ├── cli.py                    ← argparse 入口
│   │   ├── boss/
│   │   │   ├── browser.py            ← Playwright + CDP
│   │   │   ├── scraper.py            ← 列表抓取
│   │   │   ├── enricher.py           ← 详情补全
│   │   │   └── selectors.py          ← DOM 选择器集中管理
│   │   ├── cleaning/
│   │   │   ├── pua.py                ← PUA 字符清理
│   │   │   └── text.py
│   │   ├── scoring/
│   │   │   ├── clusters.py           ← 技能簇定义
│   │   │   ├── scorer.py             ← 评分模型 v3.1
│   │   │   └── tiering.py            ← P0/P1/P2/P3 分层
│   │   ├── storage/
│   │   │   └── snapshot.py           ← 输出 snapshot.json
│   │   └── tests/
│   └── output/                       ← gitignore
│       └── snapshot.json             ← 给 server 用
│
├── docs/                             ← 文档
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT.md                ← 本地开发指南
│   ├── DEPLOYMENT.md
│   ├── API.md                        ← 由 .api 文件生成
│   └── design/                       ← 设计文档归档
│       ├── search-model.md
│       ├── scoring-model.md
│       └── product-redesign.md
│
├── scripts/
│   ├── dev.sh                        ← 一键启动 dev 环境
│   ├── scrape.sh                     ← 跑爬虫
│   ├── migrate-from-localstorage.sh  ← 一次性数据迁移
│   └── backup.sh                     ← SQLite 备份
│
└── _legacy/                          ← 旧代码归档
    └── job-scraper/                  ← 整个老目录搬这里
```

---

## 六、数据迁移策略

### 6.1 用户现有数据（必须保留）

| Storage Key | 内容 | 行数 |
|-------------|------|------|
| `job_tracker_v3` | 岗位 state + interviews + questions（嵌套） | ~50-200 |
| `training_v1` | 自学题库 + 评分 + 答案 + 复习状态 | ~20-100 |
| `training_settings_v1` | LLM 配置 | 1 |
| `training_asr_settings_v1` | ASR 配置 | 1 |
| `training_resume_drill_v1` | 简历拷打缓存 | 1 |
| `training_answer_cache_v1` | AI 答案外部缓存 | ~10-50 |
| `training_ui_v1` | UI 偏好 | 1 |

### 6.2 迁移流程

**第一步**：在旧版 v5.html 里加一个「📤 导出全部数据」按钮，把 7 个 key 全部 dump 成一个 JSON 文件：

```json
{
  "version": "v5",
  "exportedAt": "2026-04-08T...",
  "stores": {
    "job_tracker_v3": {...},
    "training_v1": {...},
    ...
  }
}
```

**第二步**：新 server 提供 `POST /api/v1/migrate/from-localstorage` 端点，读 JSON → 写入 SQLite。

**第三步**：写映射逻辑：
```
v3 schema (localStorage)        ←→  SQLite tables
─────────────────────────           ─────────────────────
job_tracker_v3[jobId].intent    →   job_states.intent
job_tracker_v3[jobId].interviews →  interviews 表（多对一）
training_v1.questions           →   questions 表
training_v1.questions[i].answer →   answers 表（独立，因为大）
training_v1.questions[i].speakingLogs → speaking_logs 表
training_v1.questions[i].decomposition → decompositions 表
training_settings_v1            →   settings 表 (key: 'llm')
training_asr_settings_v1        →   settings 表 (key: 'asr')
training_resume_drill_v1        →   resume_drills 表
```

**第四步**：迁移完成后，旧 localStorage 标记 `migrated_at`，避免重复迁移。

---

## 七、SQLite Schema（用 Ent 定义）

```go
// server/internal/ent/schema/job_state.go
type JobState struct {
    ent.Schema
}

func (JobState) Fields() []ent.Field {
    return []ent.Field{
        field.String("id").Unique().Immutable(),
        field.String("job_id").Comment("引用 snapshot 中的 job"),
        field.Enum("intent").Values("unknown", "target", "practice", "backup", "ignored").Default("unknown"),
        field.Enum("pipeline_col").Values("todo", "applied", "contacting", "interviewing", "offer", "closed").Default("todo"),
        field.Enum("outcome").Values("pending", "rejected_by_them", "rejected_by_me", "accepted", "ghosted").Optional().Nillable(),
        field.Time("triaged_at").Optional().Nillable(),
        field.Time("applied_at").Optional().Nillable(),
        field.Time("last_touch_at"),
        field.String("notes").Default(""),
    }
}

func (JobState) Indexes() []ent.Index {
    return []ent.Index{
        index.Fields("job_id").Unique(),
        index.Fields("pipeline_col"),
        index.Fields("intent"),
    }
}
```

类似地定义：
- `Interview`
- `Question`（带 fts5 全文索引）
- `Answer`（独立表，因为内容大）
- `Review`
- `SpeakingLog`
- `Decomposition`
- `ResumeDrill`
- `Setting`

---

## 八、LLM 流式代理（Go 实现关键代码）

```go
// server/internal/llm/stream.go
func (c *Client) ChatStream(ctx context.Context, req ChatReq) (<-chan StreamChunk, error) {
    body, _ := json.Marshal(map[string]any{
        "model":    req.Model,
        "messages": req.Messages,
        "stream":   true,
    })

    httpReq, _ := http.NewRequestWithContext(ctx, "POST", c.baseURL+"/chat/completions", bytes.NewReader(body))
    httpReq.Header.Set("Authorization", "Bearer "+c.apiKey)
    httpReq.Header.Set("Content-Type", "application/json")

    resp, err := c.httpClient.Do(httpReq)
    if err != nil {
        return nil, err
    }

    out := make(chan StreamChunk, 16)
    go func() {
        defer resp.Body.Close()
        defer close(out)

        scanner := bufio.NewScanner(resp.Body)
        for scanner.Scan() {
            line := scanner.Text()
            if !strings.HasPrefix(line, "data: ") {
                continue
            }
            data := strings.TrimPrefix(line, "data: ")
            if data == "[DONE]" {
                return
            }
            var chunk StreamChunk
            if err := json.Unmarshal([]byte(data), &chunk); err == nil {
                select {
                case out <- chunk:
                case <-ctx.Done():
                    return
                }
            }
        }
    }()

    return out, nil
}
```

handler 把 channel 转成 SSE：

```go
func (h *LLMHandler) ChatStream(w http.ResponseWriter, r *http.Request) {
    w.Header().Set("Content-Type", "text/event-stream")
    w.Header().Set("Cache-Control", "no-cache")
    flusher := w.(http.Flusher)

    chunks, _ := h.client.ChatStream(r.Context(), req)
    for chunk := range chunks {
        data, _ := json.Marshal(chunk)
        fmt.Fprintf(w, "data: %s\n\n", data)
        flusher.Flush()
    }
}
```

**这段代码本身就能写进简历**：goroutine + channel + context + bufio + http.Flusher，5 个核心知识点一行没浪费。

---

## 九、ASR WebSocket 桥接（Go 实现思路）

```go
// server/internal/asr/bridge.go
func (b *Bridge) Handle(w http.ResponseWriter, r *http.Request) {
    clientWS, _ := upgrader.Upgrade(w, r, nil)
    defer clientWS.Close()

    // 1. 读 init 帧
    var init InitMessage
    if err := clientWS.ReadJSON(&init); err != nil {
        return
    }

    // 2. 连上游火山，带 X-Api-* header
    upstreamHeaders := http.Header{}
    upstreamHeaders.Set("X-Api-App-ID", init.Config.ApiAppID)
    upstreamHeaders.Set("X-Api-Access-Key", init.Config.ApiAccessKey)
    upstreamHeaders.Set("X-Api-Resource-Id", init.Config.ApiResourceID)
    upstreamHeaders.Set("X-Api-App-Key", init.Config.ApiAppKey)

    upstreamWS, _, err := websocket.DefaultDialer.Dial(init.Config.WsURL, upstreamHeaders)
    if err != nil {
        clientWS.WriteJSON(map[string]string{"type": "error", "message": err.Error()})
        return
    }
    defer upstreamWS.Close()

    // 3. 发 full client request
    upstreamWS.WriteMessage(websocket.BinaryMessage, buildFullClientRequest(init.Config))

    // 4. 双向桥接（goroutine + channel）
    ctx, cancel := context.WithCancel(r.Context())
    defer cancel()

    // upstream → client
    go func() {
        for {
            _, msg, err := upstreamWS.ReadMessage()
            if err != nil { cancel(); return }
            text := parseServerText(msg)
            clientWS.WriteJSON(map[string]string{"type": "partial", "text": text})
        }
    }()

    // client → upstream
    seq := int32(2)
    for {
        select {
        case <-ctx.Done(): return
        default:
            msgType, audio, err := clientWS.ReadMessage()
            if err != nil { return }
            if msgType == websocket.BinaryMessage {
                upstreamWS.WriteMessage(websocket.BinaryMessage, buildAudioFrame(audio, seq, false))
                seq++
            }
        }
    }
}
```

**面试加分点**：双向 channel 桥接 + context 取消传播 + WebSocket 升级 + 自定义二进制协议解析。

---

## 十、分阶段执行（按周）

### Week 1：清理 + 后端骨架

**目标**：把现有项目搬到新结构里，server 跑起来 hello world。

- [x] 创建 `job-os/` 目录结构
- [ ] 把现有 `job-scraper/` 整体搬到 `_legacy/`
- [ ] 在 `scraper/` 里搭起 Python 包结构（pyproject.toml + 拆出 boss/scoring/cleaning 包）
- [ ] 在 `server/` 里 init Go 项目（go-zero / chi 任选）
- [ ] 写 `etc/dev.yaml` 配置文件
- [ ] 实现最小 server：`/health` + 静态文件 mount + 启动日志
- [ ] 写 `Makefile`：`make dev` / `make scrape` / `make build`
- [ ] 写 `docker-compose.yml`（可选，但加分）

**交付物**：`make dev` 起 server，`curl localhost:8891/health` 返回 OK。

### Week 2：后端核心 API

**目标**：所有 REST 端点能用，前端拿 mock 数据测试。

- [ ] 用 Ent 定义 schema（job_state / interview / question / answer / review / setting）
- [ ] 跑 `ent generate`，生成 ORM 代码
- [ ] 用 atlas 跑首次迁移
- [ ] 写 `snapshot/loader.go` 读 `data/snapshot.json`
- [ ] 实现 `jobs/` logic：list / get / stats
- [ ] 实现 `job_states/` logic：CRUD
- [ ] 实现 `interviews/` logic：CRUD
- [ ] 实现 `questions/` logic：CRUD + bulk import + topic aggregation + due
- [ ] 实现 `spaced/sm2.go`：间隔复习算法
- [ ] 实现 `topic/inference.go`：关键词 → 技能点映射
- [ ] 单元测试（go test）覆盖 spaced + topic + 关键 logic

**交付物**：所有 REST API 用 curl 能跑通，单测覆盖率 > 60%。

### Week 3：LLM + ASR + 数据迁移

**目标**：AI 功能全部能用，老数据无损迁移。

- [ ] 实现 `llm/openai.go` + `llm/stream.go`（SSE 流式）
- [ ] 实现 `llm/providers.go`（DeepSeek / Kimi / GLM 预设）
- [ ] 实现 `/api/v1/llm/chat` SSE 端点
- [ ] 实现 `asr/volc.go`（火山协议二进制帧编解码）
- [ ] 实现 `asr/bridge.go`（WebSocket 桥接）
- [ ] 实现 `/api/v1/asr/stream` WebSocket 端点
- [ ] 实现 `migrate/from-localstorage.go`：解析旧 JSON → 写入 SQLite
- [ ] 在旧 v5.html 加「导出数据」按钮（一次性使用）
- [ ] 跑迁移，验证数据完整性

**交付物**：用旧账号导出数据 → 导入新 server → 所有岗位状态/题库/答案完整。

### Week 4：前端骨架

**目标**：React 工程跑起来，能看到 5 个 view（mock 数据）。

- [ ] 在 `web/` 里 init Vite + React + TS
- [ ] 装 Tailwind CSS
- [ ] 装 shadcn/ui，初始化几个基础组件（Button / Card / Input / Modal / Tabs）
- [ ] 装 Zustand
- [ ] 装 React Router
- [ ] 用 `openapi-typescript` 从 server 的 OpenAPI 生成 client
- [ ] 写 `api/client.ts` fetch wrapper（错误处理 / 流式解析）
- [ ] 实现 `<App>` 路由 + `<TopNav>` + `<ViewTabs>`
- [ ] 实现 5 个 view 的空骨架（占位）
- [ ] 配置 vite proxy 让 dev 直连 server

**交付物**：`pnpm dev` 起前端，五个 tab 能切换，TopNav 显示 BFF 健康状态。

### Week 5：前端核心 view（Today + Discover + Pipeline）

- [ ] 实现 `<Discover>` Inbox 列表 + 二元决策（关注 / 跳过）
- [ ] 实现 `<Pipeline>` Kanban 看板（拖拽用 dnd-kit）
- [ ] 实现 `<Today>` 仪表盘（即将面试 / 待跟进 / 待 triage）
- [ ] 实现 `<JobCard>` / `<KanbanCard>` / `<JobDetailModal>`
- [ ] 实现 `<InterviewModal>` 添加面试
- [ ] Zustand store 完成 jobs / jobStates / interviews 三个

**交付物**：Today / Discover / Pipeline 三个 view 完全能用，能投递、能拖卡、能加面试。

### Week 6：前端训练场

- [ ] 实现 `<Training>` 主页 + 5 个子 section（Hub / Heatmap / DueQueue / ResumeDrill / Speaking）
- [ ] 实现 `<QuestionCard>` + 三种 AI 答案模式
- [ ] 实现 `<BulkImportModal>` + 自动打标
- [ ] 实现 `<AddQuestionModal>`
- [ ] 实现 `<ReflectionModal>`（从 Pipeline 进入复盘）
- [ ] 实现 `useChat` hook（SSE 流接收）
- [ ] 实现 `useASR` hook（WebSocket 双向）
- [ ] 实现 `<SpeakingDrill>` 录音 + 实时转写 + AI 自评
- [ ] 实现 `<ResumeDrill>` 简历拷打
- [ ] 实现间隔复习的「今日训练队列」UI

**交付物**：训练场全部功能上线，AI 解答 / 拆解 / 拷打 / 口述 / 间隔复习 全部跑通。

### Week 7：打磨 + PWA + 测试

- [ ] PWA 配置（manifest + service worker），支持离线访问 + 添加到主屏幕
- [ ] 暗黑模式（Tailwind dark: 变体）
- [ ] 移动端适配（Pipeline 看板在手机上自动横向滚动）
- [ ] 单元测试 vitest（核心 lib + store）
- [ ] E2E 测试 playwright（关键流程：Discover → 投递 → 添加面试 → 复盘 → 训练场）
- [ ] 写 `docs/DEVELOPMENT.md` 本地开发指南
- [ ] 写 `docs/DEPLOYMENT.md` 部署指南
- [ ] 完善 `README.md`

**交付物**：完整可演示的 v1.0，能在手机上添加到主屏幕，能离线浏览数据。

### 总周期：7 周（每周 ~10-15 小时投入）

如果你**全职做**：3-4 周可完成。如果**业余做**：6-8 周可完成。

---

## 十一、风险 / 取舍

### 风险 1：Go 学习曲线

**说明**：你 Go 后端经验已经够，写应用层 web 服务问题不大；但 streaming、context 传播、WebSocket 升级这些细节可能没实战过。

**缓解**：
- Week 1 不动这些，先把骨架跑起来
- Week 3 写 LLM 流之前先看 1-2 篇 SSE 实现教程
- 大量参考 internal-platform 项目的 go-zero 代码模式

### 风险 2：前端工作量被低估

**说明**：4 周从零到 5 个完整 view + 训练场，对一个后端工程师来说不轻松。

**缓解**：
- 严格按 shadcn/ui 风格，不要造轮子
- 不追求像素级完美，先功能后美观
- 复杂组件（Kanban / Heatmap）可以直接抄第三方库的例子

### 风险 3：迁移失败导致数据丢失

**说明**：从 localStorage → SQLite 是一次性迁移，如果有 bug 可能丢数据。

**缓解**：
- 迁移前**强制导出 JSON 备份**到本地
- 迁移后数据完整性 check（行数对比 + 抽样验证）
- 旧 v5.html 保留至少 1 个月，作为 fallback

### 风险 4：过度工程化导致项目流产

**说明**：一开始野心太大可能写到一半放弃。

**缓解**：
- **Week 1-2 是 critical path**：能把后端骨架立起来，后面就有动力推进
- 不写 GraphQL、不上 Kubernetes、不做认证、不上 message queue
- 单用户、单进程、SQLite 一个文件解决所有问题

---

## 十二、ROI 总结

| 投入 | 产出 |
|------|------|
| **6-8 周业余时间** | 一个能放在简历最顶部的全栈项目 |
|  | 简历项目可以聊：Go BFF / Ent ORM / SSE 流 / WebSocket 桥接 / 火山实时 ASR / 间隔复习算法 / OpenAPI 契约 / React + Tailwind / PWA |
|  | 一个真正能每天用的求职 dashboard |
|  | 代码质量经得起 P6/P7 面试官 review |

**最关键的事**：这个项目在你简历上能写的远远不止「Job Scraper」。你可以这样写：

> **Job OS — 求职流程管理与训练系统**
> *Go (go-zero) / React (TS) / SQLite (Ent ORM) / Python (Playwright) / OpenAPI*
>
> 个人开发的求职 dashboard，覆盖岗位发现 → 决策 → 跟踪 → 面试准备 → 复盘训练 全链路。
>
> - 后端 Go (go-zero) 提供 RESTful + SSE + WebSocket API，Ent ORM + SQLite 持久化
> - 实现 LLM 流式代理与火山引擎实时 ASR WebSocket 桥接，封装二进制协议帧编解码
> - 基于 SM-2 简化版的间隔复习引擎，自动生成弱点复习队列
> - 评分模型用技能簇匹配（5 个簇 × 多维加权）+ Title/Company/Negative bonus
> - 前端 React + TS + Vite + Tailwind + shadcn/ui，5 个核心 view 全功能实现
> - OpenAPI 契约驱动开发，goctl 生成 Go handler + openapi-typescript 生成 TS client，前后端 schema 强一致
> - PWA 支持离线访问，单设备日均使用 50+ 次

这一段写在简历上，**至少能撑你聊 30 分钟的面试**。

---

## 十三、决策点（需要你拍板）

我需要你确认这些决策才能开始：

1. **后端语言：Go (go-zero) ?**
   - 推荐 Go，原因见 §2.2
   - 如果你想保险，也可以继续 Python (FastAPI)，但简历价值打折

2. **前端框架：React + TS + Vite + Tailwind + shadcn/ui ?**
   - 推荐这套，原因见 §2.3
   - 如果你想试 Vue 3 也行

3. **ORM：Ent ?**
   - 推荐 Ent，和 internal-platform 一致
   - 备选 sqlc / GORM

4. **要不要 PWA ?**
   - 推荐做，能装到手机上很爽
   - 但加 1-2 周工作量

5. **要不要做 OpenAPI 契约驱动 ?**
   - 推荐做，前后端 schema 强一致
   - 多 0.5 周工作量

6. **scraper 是否保持 Python ?**
   - 推荐保持
   - 如果想全 Go 化，需要重写整个爬虫，工作量翻倍

7. **执行节奏：全职 (3-4 周) / 业余 (6-8 周) ?**

确认后，我们就可以从 Week 1 开始执行，**第一步是建好新的目录结构 + Go 骨架 + Python 爬虫包化**。
