"""报告与大纲（PRD F2 / F3 / F4）。

本阶段只做到「大纲可生成、可编辑、可保存」；「确认大纲并写全文」返回 501，
不假装完成（写全文在阶段 2-2）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_llm
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.errors import AppError
from app.models import Chapter, Document, ModelCall, Report
from app.schemas.api import (
    ChapterOut,
    OutlineSaveIn,
    ReportCreateIn,
    ReportListOut,
    ReportOut,
    ReportSummaryOut,
)
from app.services.llm import LLMService
from app.services.events import record as record_event
from app.services.outline import generate_outline

router = APIRouter(prefix="/api", tags=["reports"])


def _chapter_out(ch: Chapter) -> ChapterOut:
    return ChapterOut(
        id=ch.id,
        seq=ch.seq,
        title=ch.title,
        key_points=list(ch.key_points or []),
        data_needed=list(ch.data_needed or []),
        suggested_words=ch.suggested_words,
        status=ch.status,
    )


def _report_out(report: Report, warnings: list[str] | None = None) -> ReportOut:
    return ReportOut(
        id=report.id,
        title=report.title,
        target_words=report.target_words,
        extra_requirements=report.extra_requirements or "",
        status=report.status,
        created_at=report.created_at,
        updated_at=report.updated_at,
        chapters=[_chapter_out(ch) for ch in report.chapters],
        warnings=warnings or [],
    )


def _get_report(db: Session, report_id: str) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise AppError("NOT_FOUND", "这份报告不存在或已删除", status_code=404)
    return report


@router.post("/reports", response_model=ReportOut)
def create_report(
    payload: ReportCreateIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not (settings.target_words_min <= payload.target_words <= settings.target_words_max):
        raise AppError(
            "INVALID_TARGET_WORDS",
            f"全文不能超过 2 万字，目标字数只能填 {settings.target_words_min} 到 "
            f"{settings.target_words_max}，超过不能提交",
            status_code=400,
        )
    report = Report(
        title=payload.title,
        target_words=payload.target_words,
        extra_requirements=payload.extra_requirements,
        owner=settings.owner_id,
        status="draft",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _report_out(report)


@router.get("/reports", response_model=ReportListOut)
def list_reports(db: Session = Depends(get_db)):
    rows = db.scalars(select(Report).order_by(Report.created_at.desc())).all()
    items = []
    for report in rows:
        chapters = report.chapters
        items.append(
            ReportSummaryOut(
                id=report.id,
                title=report.title,
                target_words=report.target_words,
                status=report.status,
                chapters_count=len(chapters),
                words_total=sum(ch.suggested_words for ch in chapters),
                created_at=report.created_at,
            )
        )
    return ReportListOut(items=items)


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: str, db: Session = Depends(get_db)):
    return _report_out(_get_report(db, report_id))


@router.delete("/reports/{report_id}")
def delete_report(report_id: str, db: Session = Depends(get_db)):
    report = _get_report(db, report_id)
    db.delete(report)
    db.commit()
    return {"deleted": True}


@router.post("/reports/{report_id}/outline", response_model=ReportOut)
def make_outline(
    report_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    llm: LLMService = Depends(get_llm),
):
    report = _get_report(db, report_id)

    usable = db.scalars(select(Document).where(Document.status == "available")).all()
    if not usable:
        raise AppError(
            "NO_DOCUMENTS",
            "资料库还是空的（或只有无法检索的文件），先去上传资料再生成大纲",
            status_code=409,
        )

    def recorder(record: dict) -> None:
        # 只在这里落元数据；完整输入输出在 data/logs/model_calls.jsonl
        if record.get("event") == "retry_chapter_count":
            return
        db.add(
            ModelCall(
                report_id=report_id,
                step=str(record.get("step", ""))[:40],
                ok=bool(record.get("ok")),
                error_type=(record.get("error_type") or None),
                request_id=(record.get("request_id") or None),
                input_tokens=int(record.get("input_tokens") or 0),
                output_tokens=int(record.get("output_tokens") or 0),
                latency_ms=int(record.get("latency_ms") or 0),
            )
        )
        db.commit()

    chapters, warnings = generate_outline(
        llm=llm,
        report_id=report_id,
        title=report.title,
        target_words=report.target_words,
        extra_requirements=report.extra_requirements or "",
        domain=report.domain,
        style=report.style,
        recorder=recorder,
        settings=settings,
    )

    for old in list(report.chapters):
        db.delete(old)
    db.flush()
    for ch in chapters:
        db.add(
            Chapter(
                report_id=report_id,
                seq=ch["seq"],
                title=ch["title"],
                key_points=ch["key_points"],
                data_needed=ch["data_needed"],
                suggested_words=ch["suggested_words"],
                status="waiting",
            )
        )
    report.status = "outline_ready"
    db.commit()
    db.refresh(report)
    record_event(
        db,
        "E1",
        report_id,
        chapters=len(report.chapters),
        words_total=sum(ch.suggested_words for ch in report.chapters),
        warnings=len(warnings or []),
    )
    return _report_out(report, warnings)


@router.put("/reports/{report_id}/outline", response_model=ReportOut)
def save_outline(
    report_id: str,
    payload: OutlineSaveIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    report = _get_report(db, report_id)
    if not payload.chapters:
        raise AppError("NO_CHAPTERS", "大纲至少要有一章", status_code=400)

    total = sum(ch.suggested_words for ch in payload.chapters)
    if total > settings.target_words_max:
        raise AppError(
            "OUTLINE_TOO_LONG",
            f"字数合计 {total} 超过上限 {settings.target_words_max}，全文不能超过 2 万字，请先删减",
            status_code=400,
        )

    warnings: list[str] = []
    if total != report.target_words:
        warnings.append(f"字数合计 {total} 与目标字数 {report.target_words} 不一致，写全文时会按上限控制")

    for old in list(report.chapters):
        db.delete(old)
    db.flush()

    for idx, item in enumerate(payload.chapters, start=1):
        db.add(
            Chapter(
                report_id=report_id,
                seq=idx,
                title=item.title.strip()[:200],
                key_points=[str(k).strip() for k in item.key_points if str(k).strip()][:6],
                data_needed=[str(d).strip() for d in item.data_needed if str(d).strip()][:8],
                suggested_words=item.suggested_words,
                status="waiting",
            )
        )
    report.status = "outline_ready"
    db.commit()
    db.refresh(report)
    record_event(
        db,
        "E1",
        report_id,
        chapters=len(report.chapters),
        words_total=sum(ch.suggested_words for ch in report.chapters),
        warnings=len(warnings or []),
    )
    return _report_out(report, warnings)


@router.post("/reports/{report_id}/outline/confirm")
def confirm_outline(
    report_id: str,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm),
):
    """确认大纲并写全文（PRD F4 → F5）。"""
    report = _get_report(db, report_id)
    if not report.chapters:
        raise AppError("NO_CHAPTERS", "还没有大纲，先生成大纲", status_code=409)
    total = sum(ch.suggested_words for ch in report.chapters)
    if total > 18000:
        raise AppError(
            "OUTLINE_TOO_LONG",
            f"大纲字数合计 {total} 超过 18,000，全文不能超过 2 万字，请先删减",
            status_code=400,
        )
    from app.api.writing import _job_out
    from app.services.pipeline import WritingPipeline

    job = WritingPipeline(llm=llm).start(report_id)
    return _job_out(job)
