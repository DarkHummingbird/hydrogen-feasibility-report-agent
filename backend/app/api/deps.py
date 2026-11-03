"""依赖注入：方便测试覆盖假模型。"""

from __future__ import annotations

from app.services.llm import LLMService


def get_llm() -> LLMService:
    return LLMService()
