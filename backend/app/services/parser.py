"""文本抽取与「无文字」判定（PRD F1：平均每页不到 50 字算扫描件）。"""

from __future__ import annotations

import io
from pathlib import Path

from app.core.errors import AppError

MIN_CHARS_PER_PAGE = 50


def _decode_text(raw: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def extract_pdf(path: Path) -> tuple[str, int, bool]:
    """返回 (文本, 页数, 是否无文字)。"""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = len(reader.pages)
    texts = []
    for page in reader.pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception:  # 单页解析失败不影响其它页
            texts.append("")
    text = "\n".join(texts)
    no_text = bool(pages) and len(text.strip()) / max(pages, 1) < MIN_CHARS_PER_PAGE
    return text, pages, no_text


def extract_docx(path: Path) -> tuple[str, int, bool]:
    import docx

    document = docx.Document(str(path))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    text = "\n".join(p for p in parts if p is not None)
    # 50 字/页 是判断扫描件 PDF 的规则；docx 只要有文字就算可用
    no_text = len(text.strip()) == 0
    return text, 1, no_text


def extract(path: Path, ext: str) -> tuple[str, int, bool]:
    if ext == ".pdf":
        try:
            return extract_pdf(path)
        except AppError:
            raise
        except Exception as exc:  # 损坏的 PDF
            raise AppError("PARSE_FAILED", f"PDF 解析失败：{type(exc).__name__}", status_code=400) from exc
    if ext == ".docx":
        try:
            return extract_docx(path)
        except Exception as exc:
            raise AppError("PARSE_FAILED", f"Word 解析失败：{type(exc).__name__}", status_code=400) from exc
    text = _decode_text(path.read_bytes())
    return text, 1, len(text.strip()) == 0


def extract_bytes(raw: bytes, ext: str) -> tuple[str, int, bool]:
    """测试用：从内存内容抽取（与 extract 等价）。"""
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        pages = len(reader.pages)
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        no_text = bool(pages) and len(text.strip()) / max(pages, 1) < MIN_CHARS_PER_PAGE
        return text, pages, no_text
    if ext == ".docx":
        import docx

        document = docx.Document(io.BytesIO(raw))
        text = "\n".join(p.text for p in document.paragraphs)
        return text, 1, len(text.strip()) == 0
    text = _decode_text(raw)
    return text, 1, len(text.strip()) == 0
