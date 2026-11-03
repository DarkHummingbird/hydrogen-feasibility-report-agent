"""资料上传、列表、删除（PRD F1）。

每份文件单独给结果：可用（切成 N 段）/ 无文字，检索不到 / 失败：原因。
单个文件失败不影响同批其它文件，失败原因按统一结构放在该条记录里。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.errors import AppError
from app.models import Document, Segment
from app.schemas.api import DocumentListOut, DocumentOut
from app.services import files as file_service
from app.services import parser
from app.services.chunker import split_chunks

router = APIRouter(prefix="/api", tags=["documents"])

_CHUNK_SIZE = 1024 * 1024


def _save_upload(upload: UploadFile, doc_id: str, ext: str, settings: Settings) -> tuple[Path, int]:
    target = file_service.store_path(settings.upload_dir, doc_id, ext)
    limit = settings.max_upload_mb * 1024 * 1024
    written = 0
    head = b""
    with target.open("wb") as fh:
        while True:
            block = upload.file.read(_CHUNK_SIZE)
            if not block:
                break
            if len(head) < 1024:
                head += block[: 1024 - len(head)]
            written += len(block)
            if written > limit:
                fh.close()
                target.unlink(missing_ok=True)
                raise AppError(
                    "FILE_TOO_LARGE",
                    f"上传失败，最大支持 {settings.max_upload_mb}M 文件",
                    status_code=413,
                )
            fh.write(block)
    file_service.check_size(written)
    file_service.check_real_type(head, ext)
    return target, written


@router.post("/documents", response_model=DocumentListOut)
def upload_documents(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not files:
        raise AppError("NO_FILES", "没有收到文件，请重新选择", status_code=400)

    items: list[DocumentOut] = []
    for upload in files:
        raw_name = upload.filename or "upload"
        safe_name = file_service.safe_filename(raw_name)
        doc_id = uuid.uuid4().hex
        try:
            ext = file_service.check_extension(safe_name)
            path, size = _save_upload(upload, doc_id, ext, settings)
            text, pages, no_text = parser.extract(path, ext)
        except AppError as exc:
            # 解析类失败不留下孤儿文件
            for candidate in Path(settings.upload_dir).glob(f"{doc_id}.*"):
                candidate.unlink(missing_ok=True)
            items.append(
                DocumentOut(
                    id=doc_id,
                    filename=safe_name,
                    status="failed",
                    segments_count=0,
                    size_bytes=0,
                    error=exc.message,
                    code=exc.code,
                    created_at=datetime.now(),
                )
            )
            continue

        if no_text or not text.strip():
            doc = Document(
                id=doc_id,
                filename=safe_name,
                stored_path=str(path),
                ext=ext,
                size_bytes=size,
                status="no_text",
                segments_count=0,
                error="无文字，检索不到（可能是扫描件），请上传文字版",
            )
            db.add(doc)
            db.commit()
            items.append(DocumentOut.model_validate(doc))
            continue

        pieces = split_chunks(text, settings.chunk_chars, settings.chunk_overlap)
        doc = Document(
            id=doc_id,
            filename=safe_name,
            stored_path=str(path),
            ext=ext,
            size_bytes=size,
            status="available",
            segments_count=len(pieces),
        )
        db.add(doc)
        for seq, piece in enumerate(pieces, start=1):
            db.add(Segment(document_id=doc_id, seq=seq, text=piece))
        db.commit()
        items.append(DocumentOut.model_validate(doc))

    return DocumentListOut(items=items)


@router.get("/documents", response_model=DocumentListOut)
def list_documents(db: Session = Depends(get_db)):
    rows = db.scalars(select(Document).order_by(Document.created_at.desc())).all()
    return DocumentListOut(items=[DocumentOut.model_validate(r) for r in rows])


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if doc is None:
        raise AppError("NOT_FOUND", "这份资料不存在或已删除", status_code=404)
    Path(doc.stored_path).unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
    return {"deleted": True}
