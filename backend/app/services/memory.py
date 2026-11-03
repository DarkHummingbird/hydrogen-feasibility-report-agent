"""章节记忆与冲突提示（PRD「全局上下文管理」）。

三条硬规则：
1. 只有定稿版本才写 chapter_summaries / last_ending；
2. 重写只覆盖本章；
3. 各章 user_notice 去重后，全部写完统一提示一次。
"""

from __future__ import annotations

import re

_MAX_SUMMARY = 100


def last_sentence(body: str) -> str:
    """从正文里截最后一句（评测 C07：不能从 summary 或 user_notice 里截）。"""
    text = re.sub(r"\s+", "", body or "")
    if not text:
        return ""
    parts = re.split(r"(?<=[。！？])", text)
    for part in reversed(parts):
        if part.strip():
            return part.strip()[:120]
    return text[-120:]


def clip_summary(summary: str, body: str) -> str:
    text = (summary or "").strip()
    if not text:
        text = last_sentence(body)
    return text[:_MAX_SUMMARY]


def format_summaries(chapters) -> str:
    lines = []
    for ch in chapters:
        if ch.summary and ch.seq < getattr(ch, "_writing_seq", 10**6):
            lines.append(f"第 {ch.seq} 章：{ch.summary}")
    return "\n".join(lines)


def dedupe_notices(notices: list[str]) -> list[str]:
    seen, out = set(), []
    for n in notices:
        key = re.sub(r"\s+", "", n or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(n.strip())
    return out


def collect_notices(chapters) -> list[str]:
    raw: list[str] = []
    for ch in chapters:
        raw.extend(ch.notices or [])
    return dedupe_notices(raw)
