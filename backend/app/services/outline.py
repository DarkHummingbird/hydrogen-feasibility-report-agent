"""大纲生成与程序校验（PRD F4、评测 C02）。

程序负责：章数校验与自动重生成一次、字数按比例调平、章节编号重排、
大纲里是否混进具体数字的提示。模型只负责"写什么"，"对不对"由这里判。
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.schemas.api import OutlinePayloadModel
from app.services.llm import LLMService

PROMPT_PATH = Path(__file__).parent / "prompts" / "outline.md"
TEMPLATE_PATH = Path(__file__).parent / "templates" / "mofcom_2023.md"

_NUMBER = re.compile(r"\d+(?:\.\d+)?\s*(?:万元|亿元|亿|万|吨|MPa|兆瓦|MW|台|个月|年|元|%|％)")


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def build_messages(
    title: str,
    target_words: int,
    extra_requirements: str,
    domain: str = "氢能",
    style: str = "正式",
) -> list[dict]:
    prompt = _load_prompt().format(
        title=title,
        domain=domain,
        style=style,
        target_words=target_words,
        user_requirements=extra_requirements or "无",
        template=load_template(),
    )
    return [
        {"role": "system", "content": "你是严格按格式输出的助手，只输出 JSON。"},
        {"role": "user", "content": prompt},
    ]


def rebalance_words(words: list[int], target: int) -> list[int]:
    """按比例调平，保证合计精确等于 target，每章至少 200 字。"""
    count = len(words)
    if count == 0:
        return []
    floor = 200
    if target < floor * count:
        # 目标太小：平均分（极端情况，正常不会出现）
        base = target // count
        result = [base] * count
        result[-1] += target - base * count
        return result

    weights = [max(w, 1) for w in words]
    total_weight = sum(weights)
    raw = [target * w / total_weight for w in weights]
    result = [max(floor, int(x)) for x in raw]

    # 用最大余数法补齐差额，保证合计 == target
    diff = target - sum(result)
    remainders = sorted(range(count), key=lambda i: (raw[i] - int(raw[i])), reverse=True)
    idx = 0
    while diff != 0 and idx < count * 4:
        i = remainders[idx % count]
        step = 1 if diff > 0 else -1
        if result[i] + step >= floor:
            result[i] += step
            diff -= step
        idx += 1
    if diff != 0:
        result[0] += diff
    return result


def detect_numbers(item: dict) -> list[str]:
    """返回大纲里出现的具体数值片段（用于提示，不阻断）。"""
    hits: list[str] = []
    for text in [item.get("title", "")] + list(item.get("key_points") or []) + list(item.get("data_needed") or []):
        hits.extend(_NUMBER.findall(str(text)))
    return hits


def normalize_outline(payload: OutlinePayloadModel, target_words: int, settings: Settings | None = None) -> tuple[list[dict], list[str]]:
    settings = settings or get_settings()
    warnings: list[str] = []
    items = payload.full_outline

    chapter_min, chapter_max = settings.outline_chapter_min, settings.outline_chapter_max
    if not (chapter_min <= len(items) <= chapter_max):
        warnings.append(
            f"章数不在 {chapter_min}–{chapter_max}，请手动增删（当前 {len(items)} 章）"
        )

    if items and items[0].key_points and len(items[0].key_points) > 6:
        warnings.append("第一章论点条数偏多，建议人工精简")

    hits: list[str] = []
    for item in items:
        hits.extend(detect_numbers(item.model_dump()))
    if hits:
        warnings.append(f"大纲里出现了具体数值（{', '.join(sorted(set(hits))[:5])}），PRD 要求论点只写数据名称")

    suggested = [item.suggested_words or 0 for item in items]
    balanced = rebalance_words(suggested, target_words)

    chapters: list[dict] = []
    for idx, item in enumerate(items, start=1):
        chapters.append(
            {
                "seq": idx,
                "title": item.title.strip()[:200],
                "key_points": [str(k).strip() for k in (item.key_points or []) if str(k).strip()][:6],
                "data_needed": [str(d).strip() for d in (item.data_needed or []) if str(d).strip()][:8],
                "suggested_words": balanced[idx - 1],
            }
        )
    return chapters, warnings


def generate_outline(
    llm: LLMService,
    report_id: str,
    title: str,
    target_words: int,
    extra_requirements: str = "",
    domain: str = "氢能",
    style: str = "正式",
    recorder=None,
    settings: Settings | None = None,
    max_chapter_retries: int = 1,
) -> tuple[list[dict], list[str]]:
    """生成大纲。章数不在 8–13 时自动重新生成一次（PRD F4、评测 C02）。"""
    settings = settings or get_settings()
    lo, hi = settings.outline_chapter_min, settings.outline_chapter_max
    messages = build_messages(title, target_words, extra_requirements, domain, style)

    chapters: list[dict] = []
    warnings: list[str] = []
    for attempt in range(max_chapter_retries + 1):
        try:
            payload = llm.call_json("生成大纲", messages, OutlinePayloadModel, report_id, recorder)
        except AppError as exc:
            if exc.code == "MODEL_FAILED":
                raise AppError(
                    "OUTLINE_INVALID", "大纲生成失败：模型没有返回可用的结构，请重试", 502
                ) from exc
            raise
        chapters, warnings = normalize_outline(payload, target_words, settings)
        if lo <= len(chapters) <= hi:
            return chapters, warnings
        if attempt < max_chapter_retries and recorder is not None:
            recorder(
                {
                    "step": "生成大纲",
                    "event": "retry_chapter_count",
                    "count": len(chapters),
                    "attempt": attempt + 1,
                }
            )
    return chapters, warnings
