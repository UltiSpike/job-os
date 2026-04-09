"""Job OS BFF 主入口

启动:
    cd job-os
    pip install -r requirements.txt
    python -m server.main --port 8891

或:
    uvicorn server.main:app --port 8891 --reload
"""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.exceptions import ConfigError, JobOsError, NotFoundError, UpstreamError, ValidationError
from server.logging_setup import configure_logging, get_logger, set_request_id
from server.routers import (
    analyses, answers, asr, asr_config, chat, concepts, curriculum, export,
    interviews, job_state_events, jobs, llm, llm_presets, me, migration,
    profile, prompts, questions, resume_profiles, resumes,
    settings as settings_router, study_plans, topics,
)
from server.storage.db import get_conn, init_db

ROOT = Path(__file__).parents[1]
logger = get_logger("server.main")


def _validate_environment() -> None:
    """启动时 fail-fast 校验 — 比运行时第一次失败友好得多"""
    db_dir = ROOT / "data"
    if not db_dir.exists():
        try:
            db_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise ConfigError(f"data dir not creatable: {db_dir}") from e

    # DB 必须能 ping 通
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as e:
        raise ConfigError(f"sqlite unreachable at {db_dir / 'app.db'}: {e}") from e

    # snapshot 是可选 — 警告但不阻断
    snap = ROOT / "data" / "snapshot.json"
    if not snap.exists():
        logger.warning("snapshot.json missing — jobs API will return empty until scraper runs", extra={"path": str(snap)})

    logger.info("environment validated", extra={"db": str(db_dir / 'app.db')})


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("job-os starting", extra={"version": "3.0"})
    _validate_environment()
    init_db()
    logger.info("job-os ready")
    yield
    logger.info("job-os shutting down")


def create_app() -> FastAPI:
    app = FastAPI(title="Job OS", version="3.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # request id 中间件 — 每个请求生成一个，写入 contextvar 供 logger 用
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("x-request-id") or set_request_id()
        if not request.headers.get("x-request-id"):
            set_request_id(rid)
        else:
            set_request_id(rid)
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    # 全局领域异常 → HTTP 翻译
    from fastapi.responses import JSONResponse

    @app.exception_handler(NotFoundError)
    async def _nf(_req: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"error": str(exc)})

    @app.exception_handler(ValidationError)
    async def _ve(_req: Request, exc: ValidationError):
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(UpstreamError)
    async def _ue(_req: Request, exc: UpstreamError):
        return JSONResponse(status_code=502, content={"error": str(exc), "upstream_status": exc.status})

    @app.exception_handler(JobOsError)
    async def _je(_req: Request, exc: JobOsError):
        logger.error("unhandled domain error", exc_info=exc)
        return JSONResponse(status_code=500, content={"error": str(exc)})

    # API
    # Core
    app.include_router(jobs.router)
    app.include_router(interviews.router)
    app.include_router(job_state_events.router)
    app.include_router(questions.router)
    app.include_router(answers.router)
    app.include_router(analyses.router)
    app.include_router(topics.router)
    app.include_router(topics.question_router)  # /questions/{id}/topics
    app.include_router(chat.session_router)
    app.include_router(chat.message_router)
    # AI
    app.include_router(llm.router)
    app.include_router(llm_presets.router)
    app.include_router(asr.router)
    app.include_router(asr_config.router)
    # Resources
    app.include_router(resumes.router)
    app.include_router(resume_profiles.router)
    app.include_router(prompts.router)
    # Curriculum
    app.include_router(curriculum.router)
    app.include_router(study_plans.router)
    # Concept + Me (核心抽象)
    app.include_router(concepts.router)
    app.include_router(me.router)
    # Settings / Profile
    app.include_router(settings_router.router)
    app.include_router(profile.router)
    # Ops
    app.include_router(migration.router)
    app.include_router(export.router)

    # 健康检查 — 真实校验依赖
    @app.get("/api/v1/health")
    def health():
        checks: dict[str, object] = {"service": "job-os", "version": "3.0"}
        try:
            with get_conn() as conn:
                conn.execute("SELECT 1").fetchone()
            checks["db"] = "ok"
        except Exception as e:
            checks["db"] = f"fail: {e}"
            checks["ok"] = False
            return checks
        snap = ROOT / "data" / "snapshot.json"
        checks["snapshot"] = "ok" if snap.exists() else "missing"
        checks["ok"] = True
        return checks

    # 静态文件挂载（前端 web/ 目录）
    web_dir = ROOT / "web"
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app


app = create_app()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8891)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    print(f"\n🚀 Job OS BFF starting on http://{args.host}:{args.port}")
    print(f"   Health: http://{args.host}:{args.port}/api/v1/health")
    print(f"   API docs: http://{args.host}:{args.port}/docs")
    print(f"   Web UI: http://{args.host}:{args.port}/  (after building web/)\n")

    uvicorn.run(
        "server.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
