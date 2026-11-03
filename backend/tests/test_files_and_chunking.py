"""文件安全与解析、切段的单元测试（底线条 6：格式、真实类型、大小、安全文件名）。"""

from __future__ import annotations

import io

import pytest

from app.core.config import get_settings
from app.services import parser
from app.services.chunker import split_chunks
from app.services.files import safe_filename


def test_safe_filename_strips_path_traversal():
    assert "/" not in safe_filename("../../evil.txt")
    assert safe_filename("../../evil.txt") == "evil.txt"
    assert safe_filename("..\\..\\x.txt") == "x.txt"
    assert safe_filename("氢能 项目 资料.docx") == "氢能 项目 资料.docx"
    assert safe_filename("   ") == "upload"


def test_split_chunks_overlap_and_size():
    text = "。".join(["这是第%d句用来测试切段的文本内容" % i for i in range(300)])
    chunks = split_chunks(text, chunk_chars=400, overlap=50)
    assert len(chunks) > 5
    assert all(len(c) <= 400 for c in chunks)


def test_split_chunks_keeps_all_text_when_short():
    text = "短文本。只有一句。"
    assert split_chunks(text, 800, 100) == ["短文本。只有一句。"]


def test_split_chunks_empty():
    assert split_chunks("   \n\n ", 800, 100) == []


def test_extract_txt_utf8_and_gbk():
    assert parser.extract_bytes("氢能项目资料".encode("utf-8"), ".txt")[0] == "氢能项目资料"
    assert parser.extract_bytes("氢能项目资料".encode("gb18030"), ".txt")[0] == "氢能项目资料"


def test_extract_docx():
    import docx

    document = docx.Document()
    document.add_paragraph("攀枝花制氢加氢一体化示范项目一期，总投资 25,000 万元。")
    buffer = io.BytesIO()
    document.save(buffer)
    text, _pages, no_text = parser.extract_bytes(buffer.getvalue(), ".docx")
    assert "25,000 万元" in text
    assert no_text is False


def test_scan_pdf_marks_no_text():
    """没有文字层的 PDF（这里用空白页模拟）应判为无文字，不能显示成功。"""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    text, pages, no_text = parser.extract_bytes(buffer.getvalue(), ".pdf")
    assert pages == 1
    assert text.strip() == ""
    assert no_text is True


def test_settings_limits():
    settings = get_settings()
    assert settings.target_words_max == 18000
    assert settings.outline_chapter_min == 8
    assert settings.outline_chapter_max == 13
    assert settings.model_max_retries == 3


def test_prompt_asks_no_numbers():
    from app.services.outline import load_template

    template = load_template()
    assert "第一章 概述" in template
    assert "第十章 研究结论及建议" in template


@pytest.mark.parametrize("name", ["a.doc", "a.exe", "a.png", "noext"])
def test_unsupported_extension(name):
    from app.core.errors import AppError
    from app.services.files import check_extension

    with pytest.raises(AppError) as exc:
        check_extension(name)
    assert exc.value.code == "UNSUPPORTED_FORMAT"
