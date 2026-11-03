"""切段：每段约 800 字，相邻重叠 100 字（PRD 第五节「参数默认值」）。

切点优先落在句末（。！？；\\n），避免把一句话拦腰截断。
"""

from __future__ import annotations

import re

_SENTENCE_END = re.compile(r"[。！？；!?;\n]")


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _cut_point(text: str, start: int, hard_end: int, min_end: int) -> int:
    """在 [min_end, hard_end] 里找最后一个句末标点之后的位置，找不到就硬切。"""
    window = text[min_end:hard_end]
    last = None
    for match in _SENTENCE_END.finditer(window):
        last = match
    if last is not None:
        return min_end + last.end()
    return hard_end


def split_chunks(text: str, chunk_chars: int = 800, overlap: int = 100) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    chunks: list[str] = []
    start = 0
    total = len(cleaned)
    while start < total:
        hard_end = min(start + chunk_chars, total)
        if hard_end >= total:
            piece = cleaned[start:total].strip()
            if piece:
                chunks.append(piece)
            break
        end = _cut_point(cleaned, start, hard_end, min(start + chunk_chars // 2, hard_end))
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        next_start = max(end - overlap, start + 1)
        start = next_start
    return chunks
