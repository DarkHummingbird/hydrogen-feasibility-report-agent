"""导出 Word（PRD F7）与改动比例（E3）。

规则：
- 报告标题 + 每章一个一级标题 + 正文段落；
- [待补充] 黄色高亮（拆成独立 run 保证高亮精确）；
- 句末 [文件名] 原样保留；
- 改动比例 = 1 − 导出稿与 AI 原稿的文本相似度，<15% 算采纳（PRD 北极星口径）。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from app.core.config import DATA_DIR
from app.services.highlights import MISSING_PATTERN

EXPORT_DIR = DATA_DIR / "exports"


def change_ratio(chapters) -> float:
    original = "\n".join((ch.original_body or ch.body or "") for ch in chapters)
    current = "\n".join((ch.body or "") for ch in chapters)
    if not original.strip():
        return 0.0
    similarity = SequenceMatcher(None, original, current).ratio()
    return round(max(0.0, 1 - similarity), 4)


def _add_paragraph(document, text: str):
    """把一段文本写进 docx，[待补充] 单独成 run 并标黄。"""
    paragraph = document.add_paragraph()
    cursor = 0
    for match in MISSING_PATTERN.finditer(text):
        if match.start() > cursor:
            paragraph.add_run(text[cursor : match.start()])
        run = paragraph.add_run(match.group(0))
        from docx.enum.text import WD_COLOR_INDEX

        run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        cursor = match.end()
    if cursor < len(text):
        paragraph.add_run(text[cursor:])
    return paragraph


def export_docx(report, chapters) -> tuple[Path, dict]:
    from docx import Document
    from docx.shared import Pt

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    document = Document()

    title = document.add_heading(report.title, level=0)
    for run in title.runs:
        run.font.size = Pt(20)

    for chapter in sorted(chapters, key=lambda c: c.seq):
        document.add_heading(chapter.title, level=1)
        blocks = [b.strip() for b in re.split(r"\n{1,}", chapter.body or "") if b.strip()]
        # 正文常以「第 N 章 ×××」开头，与一级标题重复，导出时去掉这一行
        if blocks and re.match(r"^第[一二三四五六七八九十0-9]+章", blocks[0]) and len(blocks[0]) <= 40:
            blocks = blocks[1:]
        for block in blocks:
            _add_paragraph(document, block)

    filename = f"{report.id}.docx"
    path = EXPORT_DIR / filename
    document.save(str(path))

    ratio = change_ratio(chapters)
    return path, {
        "ratio": ratio,
        "accepted": ratio < 0.15,
        "chapters": len(chapters),
        "words": sum(len(re.sub(r"\s", "", ch.body or "")) for ch in chapters),
    }


def seconds_since(report) -> float:
    """从创建到导出过了多少秒。created_at 是 naive UTC，这里统一按 UTC 比。"""
    try:
        created = report.created_at
        now = datetime.now(timezone.utc)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return round(max(0.0, (now - created).total_seconds()), 1)
    except Exception:
        return 0.0
