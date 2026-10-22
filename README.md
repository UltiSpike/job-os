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
├── server/                # FastAPI BFF（23 个 router）
│   ├── main.py            # 入口（默认只监听 127.0.0.1，不注册 CORS）
│   ├── routers/           # jobs / questions / llm / llm_presets / asr / asr_config /
│   │                      # curriculum / resumes / profile / me / export / migration …
│   ├── storage/           # SQLite 数据访问层（db schema + 各 repo）
│   ├── services/          # asr_volc.py（火山引擎 ASR 二进制协议）、mastery_service
│   └── redact.py          # 响应/导出脱敏（密钥字段 → ***）
│
├── web/                   # 前端 SPA（原生 JS，无构建步骤）
│   ├── index.html
│   ├── api/ store/ views/ components/ lib/ styles/
│
├── scraper/               # 个人用的岗位抓取脚本（旧版生成器，仅供参考）
│   ├── scrape.py
│   ├── score.py
│   └── build_html.py
│
├── data/                  # 运行时数据（.gitignore，不入库）
│   ├── app.db             # SQLite（首次运行自动创建）
│   ├── snapshot.json      # 爬虫产物
│   └── curriculum/        # 手工维护的课程内容（入库）
│
├── docs/                  # 设计与重构文档
└── scripts/               # start.sh 等
```

## API 端点

```
GET  /api/v1/health                  健康检查

# 岗位（爬虫产出，SQLite）
GET  /api/v1/jobs?tier=P0            列出岗位
GET  /api/v1/jobs/{href}             单个岗位
POST /api/v1/jobs/reload             重新加载 snapshot

# 岗位状态 / 面试
GET    /api/v1/job-states            所有用户状态
GET    /api/v1/job-states/{href}     单个状态
PATCH  /api/v1/job-states/{href}     upsert
DELETE /api/v1/job-states/{href}
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

# LLM（预设存 SQLite；api_key 只回掩码）
GET    /api/v1/llm-presets
POST   /api/v1/llm-presets
PATCH  /api/v1/llm-presets/{name}
POST   /api/v1/llm-presets/{name}:activate
POST   /api/v1/llm-presets/{name}:test
POST   /api/v1/llm/test
POST   /api/v1/llm/chat              非流式
POST   /api/v1/llm/chat/stream       SSE 流式

# ASR（火山引擎；access key 只存服务端，不回前端）
GET  /api/v1/asr-config
PUT  /api/v1/asr-config
POST /api/v1/asr-config:test
POST /api/v1/asr/test
POST /api/v1/asr/transcribe          文件转写
WS   /api/v1/asr/ws                  实时桥接火山引擎

# 导出 / 迁移（导出会自动脱敏密钥字段）
GET  /api/v1/export
GET  /api/v1/migrate/export
POST /api/v1/migrate/from-localstorage
```

## 安全边界（重要）

本项目按**单用户、本机使用**设计：

- 默认只监听 `127.0.0.1:8891`，**不要用 `--host 0.0.0.0` 暴露到公网/局域网**；
- 全站**无登录鉴权**，且**不注册 CORS**（前端由本进程同源托管）——任何能访问该端口的进程都能读写数据；
- LLM `api_key`、火山 ASR `access_key` 只存在本地 `data/app.db`（SQLite 明文），
  API 只返回掩码，导出接口会对密钥字段脱敏（`***`）；
- `data/` 下的运行时数据与导出备份已在 `.gitignore` 中忽略，请勿提交。

如需在多用户/公网环境使用，请自行补充鉴权、TLS 与反向代理。

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

## 免责声明

`scraper/` 中的抓取脚本仅用于个人学习与研究，请自行遵守目标网站的 robots.txt、服务条款与当地法律，作者不对使用后果负责。仓库不包含任何抓取到的岗位数据（`data/` 已忽略）。

## License

本项目采用 **[PolyForm Noncommercial License 1.0.0](LICENSE)**：

- 允许个人学习、研究、非营利组织内部使用，以及修改和分发；
- **任何商业用途需另行获得授权**。

> 该协议不是 OSI 认可的开源协议，GitHub 会显示为 "Other"。

## 改动日志

### v3.1 (2026-10-22) — 安全加固
- ASR / LLM 凭据不再回传前端，导出接口对密钥字段脱敏
- 测试类接口禁止「复用已存密钥 + 调用方指定地址」
- 移除全开放的 CORS；ASR WebSocket 日志不再打印初始帧内容
- 清理历史提交中的身份与内部信息，补充非商用协议

### v3 (2026-04-08)
- 重构为模块化 BFF + SQLite 持久化
- 拆分 router（jobs / questions / llm / asr / migration）
- 用户状态从 localStorage → SQLite（保留迁移路径）
- 保留 web/index.html 作为前端（以后可换 React）
