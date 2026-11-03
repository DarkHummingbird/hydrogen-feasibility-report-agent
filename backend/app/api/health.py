"""健康检查：确认服务活着、模型有没有配 Key（不泄露 Key 本身）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "model": settings.model_name,
        "has_key": settings.has_key,
        "stage": "3-1",
    }
