"""查看与修改、顶部汇总、导出（PRD F6 / F7）。"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AppError
from app.models import Event, Report, TruthBase
from app.services import events as event_service
from app.services.exporter import change_ratio, export_docx, seconds_since
from app.services.highlights import build_marks, collect_missing

router = APIRouter(prefix="/api", tags=["view"])

STATUS_TEXT = {"passed": "通过", "manual": "待人工", "failed": "失败", "waiting": "等待"}


class BodyIn(BaseModel):
    body: str = Field(min_length=1)


def _report(db: Session, report_id: str) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise AppError("NOT_FOUND", "这份报告不存在或已删除", 404)
    if not report.chapters:
        raise AppError("NO_OUTLINE", "这份报告还没有大纲", 409)
    return report


def _sources(db: Session, report_id: str) -> dict:
    truth = db.scalar(select(TruthBase).where(TruthBase.report_id == report_id))
    return dict(truth.sources or {}) if truth else {}


def _chapter_payload(chapter, sources: dict) -> dict:
    marks = build_marks(chapter.body or "", (chapter.audit or {}).get("issues") or [], sources)
    return {
        "seq": chapter.seq,
        "title": chapter.title,
        "status": chapter.status,
        "status_text": STATUS_TEXT.get(chapter.status, chapter.status),
        "words": chapter.words or 0,
        "suggested_words": chapter.suggested_words,
        "body": chapter.body or "",
        "segments": marks["segments"],
        "critical": marks["critical"],
        "warnings": marks["warnings"],
        "unlocated": marks["unlocated"],
        "missing": list(chapter.missing or []),
        "notices": list(chapter.notices or []),
        "retrieved": list(chapter.retrieved or []),
        "truncated": bool(chapter.truncated),
        "rewrite_count": chapter.rewrite_count or 0,
        "audit": {
            "critical_count": (chapter.audit or {}).get("critical_count", 0),
            "warning_count": (chapter.audit or {}).get("warning_count", 0),
            "unverifiable": (chapter.audit or {}).get("unverifiable", []),
        },
        "changed": bool(chapter.original_body and chapter.body and chapter.body != chapter.original_body),
    }


@router.get("/reports/{report_id}/view")
def view(report_id: str, seq: int | None = None, db: Session = Depends(get_db)):
    report = _report(db, report_id)
    sources = _sources(db, report_id)
    chapters = sorted(report.chapters, key=lambda c: c.seq)
    target = next((c for c in chapters if c.seq == seq), None) or next(
        (c for c in chapters if c.status == "manual"), chapters[0]
    )
    return {
        "report": {
            "id": report.id,
            "title": report.title,
            "status": report.status,
            "target_words": report.target_words,
            "words_total": sum(c.words or 0 for c in chapters),
        },
        "directory": [
            {
                "seq": c.seq,
                "title": c.title,
                "status": c.status,
                "status_text": STATUS_TEXT.get(c.status, c.status),
                "words": c.words or 0,
                "truncated": bool(c.truncated),
                "critical_count": (c.audit or {}).get("critical_count", 0),
            }
            for c in chapters
        ],
        "summary": _summary(report, chapters),
        "chapter": _chapter_payload(target, sources),
    }


def _summary(report: Report, chapters) -> dict:
    manual = [{"seq": c.seq, "title": c.title} for c in chapters if c.status == "manual"]
    notices: list[str] = []
    seen = set()
    for c in chapters:
        for n in c.notices or []:
            key = re.sub(r"\s+", "", n)
            if key and key not in seen:
                seen.add(key)
                notices.append(n)
    return {
        "manual": manual,
        "missing": collect_missing(chapters),
        "missing_total": sum(len(c.missing or []) for c in chapters),
        "notices": notices,
        "change_ratio": change_ratio(chapters),
    }


@router.get("/reports/{report_id}/chapters/{seq}")
def chapter_detail(report_id: str, seq: int, db: Session = Depends(get_db)):
    report = _report(db, report_id)
    chapter = next((c for c in report.chapters if c.seq == seq), None)
    if chapter is None:
        raise AppError("NOT_FOUND", f"没有第 {seq} 章", 404)
    return _chapter_payload(chapter, _sources(db, report_id))


@router.get("/reports/{report_id}/summary")
def summary(report_id: str, db: Session = Depends(get_db)):
    report = _report(db, report_id)
    chapters = sorted(report.chapters, key=lambda c: c.seq)
    return _summary(report, chapters)


@router.put("/reports/{report_id}/chapters/{seq}/body")
def save_body(report_id: str, seq: int, payload: BodyIn, db: Session = Depends(get_db)):
    report = _report(db, report_id)
    chapter = next((c for c in report.chapters if c.seq == seq), None)
    if chapter is None:
        raise AppError("NOT_FOUND", f"没有第 {seq} 章", 404)
    body = payload.body.strip()
    if not body:
        raise AppError("EMPTY_BODY", "正文不能为空", 400)
    chapter.body = body
    chapter.words = len(re.sub(r"\s", "", body))
    if not chapter.original_body:
        chapter.original_body = body  # 极少见：AI 原稿缺失时以本次为原稿
    db.commit()
    db.refresh(chapter)
    chapters = sorted(report.chapters, key=lambda c: c.seq)
    return {
        "seq": chapter.seq,
        "words": chapter.words,
        "change_ratio": change_ratio(chapters),
        "chapter": _chapter_payload(chapter, _sources(db, report_id)),
    }


@router.post("/reports/{report_id}/export")
def export(report_id: str, db: Session = Depends(get_db)):
    report = _report(db, report_id)
    chapters = sorted(report.chapters, key=lambda c: c.seq)
    written = [c for c in chapters if (c.body or "").strip()]
    if not written:
        raise AppError("NO_CONTENT", "还没有正文，先写全文再导出", 409)
    path, info = export_docx(report, written)
    event_service.record(
        db,
        "E3",
        report_id,
        seconds_since_create=seconds_since(report),
        change_ratio=info["ratio"],
        accepted=info["accepted"],
        words=info["words"],
        chapters=info["chapters"],
    )
    return {
        "download": f"/api/reports/{report_id}/export.docx",
        "file": path.name,
        **info,
    }


@router.get("/reports/{report_id}/export.docx")
def download(report_id: str, db: Session = Depends(get_db)):
    report = _report(db, report_id)
    chapters = [c for c in sorted(report.chapters, key=lambda c: c.seq) if (c.body or "").strip()]
    if not chapters:
        raise AppError("NO_CONTENT", "还没有正文，先写全文再导出", 409)
    path, _info = export_docx(report, chapters)
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{report.title[:40]}.docx",
    )


@router.get("/reports/{report_id}/events")
def list_events(report_id: str, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Event).where(Event.report_id == report_id).order_by(Event.id)
    ).all()
    return {
        "items": [
            {"code": e.code, "payload": e.payload, "created_at": e.created_at.isoformat()} for e in rows
        ]
    }
