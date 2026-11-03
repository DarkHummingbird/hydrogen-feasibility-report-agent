"""写全文与进度（PRD F5）。

任务在后台线程跑，状态落库；本模块只负责发起、查询和继续。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_llm
from app.core.db import get_db
from app.core.errors import AppError
from app.models import Job, Report
from app.schemas.api import JobOut, ProgressOut, ProgressSummary, ReportChapterProgress
from app.services.llm import LLMService
from app.services.pipeline import WritingPipeline

router = APIRouter(prefix="/api", tags=["writing"])

STATUS_TEXT = {
    "pending": "排队中",
    "running": "写作中",
    "paused": "已暂停",
    "succeeded": "已完成",
    "failed": "失败",
}


def _job_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        report_id=job.report_id,
        status=job.status,
        status_text=STATUS_TEXT.get(job.status, job.status),
        current_seq=job.current_seq,
        total=job.total,
        message=job.message or "",
        error=job.error,
        notices=dedupe(job.notices or []),
    )


def dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for i in items:
        if i in seen:
            continue
        seen.add(i)
        out.append(i)
    return out


@router.post("/reports/{report_id}/write", response_model=JobOut)
def start_writing(
    report_id: str,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm),
):
    pipeline = WritingPipeline(llm=llm)
    job = pipeline.start(report_id)
    return _job_out(job)


@router.post("/reports/{report_id}/resume", response_model=JobOut)
def resume_writing(
    report_id: str,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm),
):
    pipeline = WritingPipeline(llm=llm)
    job = pipeline.resume(report_id)
    return _job_out(job)


@router.get("/reports/{report_id}/progress", response_model=ProgressOut)
def progress(report_id: str, db: Session = Depends(get_db)):
    report = db.get(Report, report_id)
    if report is None:
        raise AppError("NOT_FOUND", "这份报告不存在或已删除", 404)
    job = db.scalar(select(Job).where(Job.report_id == report_id).order_by(Job.created_at.desc()))

    chapters = sorted(report.chapters, key=lambda c: c.seq)
    chapters_out = [
        ReportChapterProgress(
            seq=ch.seq,
            title=ch.title,
            status=ch.status,
            status_text=CHAPTER_STATUS.get(ch.status, ch.status),
            words=ch.words or 0,
            rewrite_count=ch.rewrite_count or 0,
            truncated=bool(ch.truncated),
            critical_count=(ch.audit or {}).get("critical_count", 0),
            warning_count=(ch.audit or {}).get("warning_count", 0),
            missing=list(ch.missing or []),
        )
        for ch in chapters
    ]
    done = sum(1 for ch in chapters if ch.status in ("passed", "manual"))
    summary = ProgressSummary(
        done=done,
        manual=sum(1 for ch in chapters if ch.status == "manual"),
        failed=sum(1 for ch in chapters if ch.status == "failed"),
        words_total=sum(ch.words or 0 for ch in chapters),
    )
    return ProgressOut(
        report_id=report_id,
        report_status=report.status,
        job=_job_out(job) if job else None,
        chapters=chapters_out,
        summary=summary,
    )


CHAPTER_STATUS = {
    "waiting": "等待",
    "writing": "写作中",
    "compressing": "压缩中",
    "auditing": "审计中",
    "rewriting": "重写中",
    "passed": "通过",
    "manual": "待人工",
    "failed": "失败",
}
