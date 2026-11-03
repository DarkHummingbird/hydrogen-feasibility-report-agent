"""FastAPI 入口：挂载 API、临时验收界面、统一错误处理。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from app.api import documents, health, reports, view, writing
from app.core.config import get_settings
from app.core.db import init_db
from app.core.errors import install_error_handlers


app = FastAPI(title="可研报告生成Agent", version="0.1.0-阶段2-1")
install_error_handlers(app)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(reports.router)
app.include_router(writing.router)
app.include_router(view.router)



@app.on_event("startup")
def _startup() -> None:
    get_settings()
    init_db()
    # 进程重启后，上次没跑完的任务不假装还在跑（底线第 2 条）
    from app.services.pipeline import WritingPipeline

    WritingPipeline.recover_interrupted()


@app.get("/")
def index():
    """阶段 3-1 起临时验收界面已废弃（前端在 frontend/，Next.js，端口 3000）。"""
    return {
        "status": "ok",
        "message": "这是后端 API。界面在 http://127.0.0.1:3000（阶段 3 正式前端）。",
        "docs": "/docs",
    }
