"""写章：正文生成、压缩、截断、重写（PRD F5 与第四节写章提示词）。

字数规则（PRD 第五节）：正文去掉空格和换行后的字符数；[待补充] 与句末 [文件名] 也算。
每章上限 = 建议字数 × 1.1；超了先压缩一次，仍超就在上限内最后一个句号处截断。
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from app.services.llm import LLMService
from app.services.retrieval import RetrievedChunk, format_context

PROMPT_PATH = Path(__file__).parent / "prompts" / "write_chapter.md"
_WS = re.compile(r"\s+")


class WritePayload(BaseModel):
    body: str = Field(min_length=1)
    summary: str = ""
    missing: list[str] = Field(default_factory=list)
    user_notice: str = ""


def count_words(text: str) -> int:
    return len(_WS.sub("", text or ""))


def max_words_for(suggested_words: int, ratio: float = 1.1) -> int:
    return int(suggested_words * ratio)


def truncate_at_sentence(text: str, limit: int) -> tuple[str, bool]:
    """超过 limit 时，在上限内最后一个句号处截断；没有句号就硬切。"""
    if count_words(text) <= limit:
        return text, False
    out, count = [], 0
    for ch in text:
        if not ch.isspace():
            count += 1
        if count > limit:
            break
        out.append(ch)
    clipped = "".join(out)
    cut = max(clipped.rfind("。"), clipped.rfind("！"), clipped.rfind("？"))
    if cut > 0:
        clipped = clipped[: cut + 1]
    return clipped, True


def build_chapter_task(chapter) -> str:
    points = "；".join(chapter.key_points or [])
    data = "、".join(chapter.data_needed or [])
    return (
        f"标题：{chapter.title}\n"
        f"关键论点：{points or '（无）'}\n"
        f"所需数据：{data or '（无）'}\n"
        f"建议字数：{chapter.suggested_words}"
    )


def build_messages(
    report,
    chapter,
    truth: dict,
    terminology: list[str],
    summaries: str,
    last_ending: str,
    chunks: list[RetrievedChunk],
    previous_body: str | None = None,
    audit_report: dict | None = None,
    shorten: dict | None = None,
) -> list[dict]:
    prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
        title=report.title,
        style=report.style,
        user_requirements=report.extra_requirements or "无",
        n=chapter.seq,
        total=len(report.chapters),
        chapter=build_chapter_task(chapter),
        max_words=max_words_for(chapter.suggested_words),
        truth_base=_format_truth(truth),
        terminology="、".join(terminology) or "（无）",
        chapter_summaries=summaries or "（本章是第一章）",
        last_ending=last_ending or "（无）",
        context=format_context(chunks),
    )
    if previous_body is not None and audit_report is not None:
        prompt += (
            "\n\n上一版正文：" + previous_body
            + "\n\n审计结果：" + _format_audit(audit_report)
            + "\n\n# Rewrite Rules\n"
            "- 逐条修改审计结果里 CRITICAL 点名的句子，改成审计给出的正确值。\n"
            "- 没被点名的句子原样保留；其他数字和 [待补充] 一个字不动。\n"
            "- 输出格式不变，summary 按改后的正文重写。\n"
        )
    if previous_body is not None and shorten is not None:
        prompt += (
            "\n\n上一版正文：" + previous_body
            + f"\n上一版字数：{shorten['words']}，超过了本章上限 {shorten['max_words']}。"
            + "\n\n# Shorten Rules\n"
            f"- 硬约束：压缩后正文（去掉空格换行）不得超过 {shorten['max_words']} 字，目标 {shorten['target']} 字；超过会被程序直接截断。\n"
            "- 删重复和铺陈的句子，不加新内容。\n"
            f"- 必须删掉约 {max(10, int((1 - shorten['target'] / max(shorten['words'], 1)) * 100))}% 的字数；"
            "该删就删整段铺垫、背景罗列和重复表述，保留关键论点、所有数字、[待补充] 与句末 [文件名]。\n"
            "- 所有数字、[待补充] 和句末 [文件名] 原样保留。\n"
            "- 输出格式不变，summary 按改后的正文重写。\n"
        )
    return [
        {"role": "system", "content": "你是严格按格式输出的助手，只输出 JSON。"},
        {"role": "user", "content": prompt},
    ]


def _format_truth(truth: dict) -> str:
    lines = [f"- {k}：{v}" for k, v in truth.items() if v]
    return "\n".join(lines) or "（没有提炼到关键事实）"


def _format_audit(audit: dict) -> str:
    issues = audit.get("issues") or []
    lines = []
    for item in issues:
        if item.get("severity") != "CRITICAL":
            continue
        lines.append(
            f"- 原句：{item.get('quote', '')} → 应为：{item.get('expected', '')}（依据：{item.get('basis', '')}）"
        )
    return "\n".join(lines) or "（无 CRITICAL）"


def write_once(
    llm: LLMService,
    report,
    chapter,
    truth: dict,
    terminology: list[str],
    summaries: str,
    last_ending: str,
    chunks: list[RetrievedChunk],
    report_id: str,
    recorder=None,
    step: str = "写章",
    previous_body: str | None = None,
    audit_report: dict | None = None,
    shorten: dict | None = None,
) -> WritePayload:
    messages = build_messages(
        report, chapter, truth, terminology, summaries, last_ending, chunks,
        previous_body=previous_body, audit_report=audit_report, shorten=shorten,
    )
    return llm.call_json(step, messages, WritePayload, report_id, recorder)


def control_length(
    llm: LLMService,
    report,
    chapter,
    payload: WritePayload,
    truth: dict,
    terminology: list[str],
    summaries: str,
    last_ending: str,
    chunks: list[RetrievedChunk],
    report_id: str,
    recorder=None,
    ratio: float = 1.1,
) -> tuple[WritePayload, bool, bool]:
    """控字数：超上限压缩一次，仍超就截断。

    返回 (最终 payload, 是否压缩过, 是否截断过)。
    """
    max_words = max_words_for(chapter.suggested_words, ratio)
    if count_words(payload.body) <= max_words:
        return payload, False, False

    compressed = write_once(
        llm, report, chapter, truth, terminology, summaries, last_ending, chunks,
        report_id, recorder,
        step="压缩",
        previous_body=payload.body,
        shorten={
            "words": count_words(payload.body),
            "max_words": max_words,
            # 实测 DeepSeek 对字数约束遵守度差（压缩一轮只减 2%），
            # 目标定在上限的 80% 并明确"删掉约 X%"，仍超则按 PRD 截断
            "target": int(max_words * 0.8),
        },
    )
    if count_words(compressed.body) <= max_words:
        return compressed, True, False

    body, truncated = truncate_at_sentence(compressed.body, max_words)
    return (
        WritePayload(
            body=body,
            summary=compressed.summary,
            missing=compressed.missing,
            user_notice=compressed.user_notice,
        ),
        True,
        truncated,
    )
