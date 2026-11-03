"""上传文件的安全处理：扩展名白名单、真实类型校验、安全文件名（底线条 6）。"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError

ALLOWED_EXT = {".pdf", ".docx", ".md", ".txt"}
# 真实类型的魔数（防止 .png 改名成 .pdf 混进来）
MAGIC = {
    ".pdf": [b"%PDF"],
    ".docx": [b"PK\x03\x04"],
}
_ILLEGAL = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")


def safe_filename(name: str, fallback: str = "upload") -> str:
    """去掉路径分隔符与控制字符，保留中文；限制长度。"""
    base = Path((name or "").replace("\\", "/")).name  # 反斜杠与 ../ 都当目录分隔处理
    base = unicodedata.normalize("NFC", base)
    base = _ILLEGAL.sub("_", base).strip(" .") or fallback
    if len(base) > 120:
        stem, suffix = Path(base).stem[:100], Path(base).suffix
        base = f"{stem}{suffix}"
    return base


def check_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise AppError(
            "UNSUPPORTED_FORMAT",
            "当前格式不支持，请上传 PDF、Word、Markdown 或 TXT",
            status_code=400,
        )
    return ext


def check_size(size_bytes: int) -> None:
    limit_mb = get_settings().max_upload_mb
    if size_bytes <= 0:
        raise AppError("EMPTY_FILE", "文件是空的，请换一个文件", status_code=400)
    if size_bytes > limit_mb * 1024 * 1024:
        raise AppError("FILE_TOO_LARGE", f"上传失败，最大支持 {limit_mb}M 文件", status_code=413)


def check_real_type(head: bytes, ext: str) -> None:
    """按魔数校验真实类型；.md/.txt 是纯文本，只拒明显二进制。"""
    if ext in MAGIC:
        if not any(head.startswith(m) for m in MAGIC[ext]):
            raise AppError(
                "UNSUPPORTED_FORMAT",
                "这个文件的内容和扩展名对不上（可能只是改了后缀），请上传真实格式的文件",
                status_code=400,
            )
    else:
        if b"\x00" in head[:1024]:
            raise AppError("UNSUPPORTED_FORMAT", "这不是文本文件，请上传 Markdown 或 TXT", status_code=400)


def store_path(root: str, doc_id: str, ext: str) -> Path:
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    return root_path / f"{doc_id}{ext}"
