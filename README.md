# Job OS

> 求职流程管理 + AI 训练场，单用户本地工具

## 快速启动

```bash
# 一次性安装依赖
pip install --user -r requirements.txt
pip install --user eval_type_backport  # Python 3.9 需要

# 启动
./scripts/start.sh

# 或手动启动
python3 -m server.main --port 8891
```

打开浏览器：http://localhost:8891/

## 目录结构

```
job-os/
├── server/                # FastAPI BFF
│   ├── main.py           # 入口
│   ├── routers/          # API 路由
│   │   ├── jobs.py       # 岗位 + 状态 + 面试
│   │   ├── questions.py  # 题库 + 评分 + 复习
│   │   ├── llm.py        # LLM 代理（流式/非流式）
│   │   ├── asr.py        # ASR 转写 + WebSocket 桥接
│   │   └── migration.py  # localStorage → SQLite 迁移
│   ├── storage/          # 数据访问层
│   │   ├── db.py
│   │   ├── jobs_repo.py
│   │   ├── questions_repo.py
│   │   └── settings_repo.py
│   └── services/
│       └── asr_volc.py   # 火山引擎 ASR 二进制协议
│
├── web/                  # 前端（暂用 v5.html）
│   └── index.html
│
├── scraper/              # 爬虫（保持原样）
│   ├── scrape.py         # ← 原 v4.py
│   ├── score.py          # ← 原 v4_1.py
│   └── build_html.py     # ← 原 build_html_v5.py
│
├── data/                 # 运行时数据（gitignore）
│   ├── snapshot.json     # 爬虫产物
│   ├── rejected.json
│   └── app.db            # SQLite（首次运行自动创建）
│
├── docs/
└── scripts/
    └── start.sh
```

## API 端点

```
GET  /api/v1/health                  健康检查

# 岗位（read-only，from snapshot.json）
GET  /api/v1/jobs?tier=P0            列出岗位
GET  /api/v1/jobs/{href}             单个岗位
POST /api/v1/jobs/reload             重新加载 snapshot

# 岗位状态（SQLite）
GET    /api/v1/job-states            所有用户状态
GET    /api/v1/job-states/{href}     单个状态
PATCH  /api/v1/job-states/{href}     upsert
DELETE /api/v1/job-states/{href}

# 面试
GET    /api/v1/interviews?job_id=xxx
POST   /api/v1/jobs/{href}/interviews
PATCH  /api/v1/interviews/{id}
DELETE /api/v1/interviews/{id}

# 题库
GET    /api/v1/questions             支持 ?source=manual&topic=Go&rating=bad&due=true
POST   /api/v1/questions             单条创建
POST   /api/v1/questions/bulk        批量
PATCH  /api/v1/questions/{id}
DELETE /api/v1/questions/{id}
GET    /api/v1/questions/{id}
GET    /api/v1/questions/topics      技能点聚合（热力图数据）
GET    /api/v1/questions/due         今日待复习
POST   /api/v1/questions/{id}/review 提交评分（自动算下次复习时间）

# LLM
GET  /api/v1/llm/config
PUT  /api/v1/llm/config
POST /api/v1/llm/test
POST /api/v1/llm/chat                非流式
POST /api/v1/llm/chat/stream         SSE 流式

# ASR
POST /api/v1/asr/transcribe          文件转写
WS   /api/v1/asr/ws                  实时桥接火山引擎

# 迁移
POST /api/v1/migrate/from-localstorage
GET  /api/v1/migrate/export
```

## 数据迁移

从老版 v5.html 的 localStorage 迁移：

1. 在老 v5.html 里执行（控制台）：
   ```js
   const stores = {};
   ['job_tracker_v3', 'job_tracker_v2', 'training_v1', 'training_settings_v1', 'training_asr_settings_v1', 'training_resume_drill_v1', 'training_ui_v1'].forEach(k => {
     try { stores[k] = JSON.parse(localStorage.getItem(k) || 'null'); } catch(e) {}
   });
   const data = JSON.stringify({stores}, null, 2);
   const blob = new Blob([data], {type:'application/json'});
   const url = URL.createObjectURL(blob);
   const a = document.createElement('a');
   a.href = url;
   a.download = 'migration.json';
   a.click();
   ```

2. 把下载的 `migration.json` POST 到新 BFF：
   ```bash
   curl -X POST http://localhost:8891/api/v1/migrate/from-localstorage \
     -H "Content-Type: application/json" \
     -d @migration.json
   ```

## 改动日志

### v3 (2026-04-08)
- 重构为模块化 BFF + SQLite 持久化
- 拆分 router（jobs / questions / llm / asr / migration）
- 用户状态从 localStorage → SQLite（保留迁移路径）
- 保留 web/index.html 作为前端（以后可换 React）
```
