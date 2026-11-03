"""写全文的任务主循环（PRD F5）。

关键约束：
- 任务状态落库（jobs 表），进程重启后把 running 改成 paused，用户可「从第 N 章继续」；
- truth_base 每份报告只提炼一次，「继续」不重新提炼（评测 C09）；
- 已定稿（passed/manual）的章节不重写；
- 每章结束就提交一次，崩在哪一章都能看清楚。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import AppError
from app.models import Chapter, Job, Report, TruthBase
from app.services.auditor import audit_chapter
from app.services.facts import extract_facts
from app.services.llm import LLMService
from app.services.memory import clip_summary, collect_notices, dedupe_notices
from app.services.retrieval import Retriever
from app.services.writer import control_length, count_words, write_once

logger = logging.getLogger("app.pipeline")

DONE_STATUSES = {"passed", "manual"}


def _now():
    return datetime.now(timezone.utc)


def chapter_query(ch: Chapter) -> str:
    return " ".join([ch.title, *[str(k) for k in (ch.key_points or [])], *[str(d) for d in (ch.data_needed or [])]])


def previous_context(chapters: list[Chapter], seq: int) -> tuple[str, str]:
    """前面各章的摘要 + 上一章最后一句（只看已定稿的章）。"""
    lines, last = [], ""
    for ch in chapters:
        if ch.seq >= seq:
            break
        if ch.summary:
            lines.append(f"第 {ch.seq} 章：{ch.summary}")
        if ch.body:
            from app.services.memory import last_sentence

            last = last_sentence(ch.body)
    return "\n".join(lines), last


class WritingPipeline:
    def __init__(self, llm: LLMService | None = None, session_factory=SessionLocal):
        self.llm_factory = llm
        self.session_factory = session_factory

    # ---------- 对外 ----------
    def start(self, report_id: str, run_sync: bool = False) -> Job:
        db = self.session_factory()
        try:
            report = db.get(Report, report_id)
            if report is None:
                raise AppError("NOT_FOUND", "这份报告不存在或已删除", 404)
            if not report.chapters:
                raise AppError("NO_OUTLINE", "还没有大纲，先生成并确认大纲再写全文", 409)
            running = db.scalar(
                select(Job).where(Job.report_id == report_id, Job.status.in_(["pending", "running"]))
            )
            if running is not None:
                raise AppError("JOB_RUNNING", "这份报告正在写，等它跑完或等它失败后再继续", 409)

            job = Job(
                report_id=report_id,
                status="pending",
                total=len(report.chapters),
                current_seq=min((ch.seq for ch in report.chapters), default=1),
                message="准备开始",
            )
            db.add(job)
            report.status = "writing"
            db.commit()
            db.refresh(job)
            job_id = job.id
        finally:
            db.close()

        if run_sync:
            self.run(job_id)
        else:
            threading.Thread(target=self.run, args=(job_id,), daemon=True, name=f"write-{job_id[:6]}").start()

        db = self.session_factory()
        try:
            return db.get(Job, job_id)
        finally:
            db.close()

    def resume(self, report_id: str, run_sync: bool = False) -> Job:
        db = self.session_factory()
        try:
            report = db.get(Report, report_id)
            if report is None:
                raise AppError("NOT_FOUND", "这份报告不存在或已删除", 404)
            job = db.scalar(
                select(Job).where(Job.report_id == report_id).order_by(Job.created_at.desc())
            )
            if job is None:
                raise AppError("NO_JOB", "这份报告还没开始写过，先点「确认大纲并写全文」", 409)
            if job.status in ("pending", "running"):
                raise AppError("JOB_RUNNING", "任务还在跑，不用继续", 409)
            if job.status == "succeeded":
                raise AppError("JOB_DONE", "这份报告已经写完了", 409)

            chapters = sorted(report.chapters, key=lambda c: c.seq)
            pending = [c for c in chapters if c.status not in DONE_STATUSES]
            job.status = "pending"
            job.error = None
            job.current_seq = pending[0].seq if pending else len(chapters)
            job.message = f"从第 {job.current_seq} 章继续"
            report.status = "writing"
            db.commit()
            job_id = job.id
        finally:
            db.close()

        if run_sync:
            self.run(job_id)
        else:
            threading.Thread(target=self.run, args=(job_id,), daemon=True, name=f"resume-{job_id[:6]}").start()

        db = self.session_factory()
        try:
            return db.get(Job, job_id)
        finally:
            db.close()

    @staticmethod
    def recover_interrupted(session_factory=SessionLocal) -> int:
        """进程启动时调用：把上次没跑完的 running 任务改为 paused（不假装还在跑）。"""
        db = session_factory()
        try:
            jobs = db.scalars(select(Job).where(Job.status.in_(["running", "pending"]))).all()
            for job in jobs:
                job.status = "paused"
                job.message = "服务重启，任务已暂停，可点「从第 N 章继续」"
                report = db.get(Report, job.report_id)
                if report is not None and report.status == "writing":
                    report.status = "paused"
            db.commit()
            return len(jobs)
        finally:
            db.close()

    # ---------- 主循环 ----------
    def run(self, job_id: str) -> None:
        db = self.session_factory()
        try:
            job = db.get(Job, job_id)
            if job is None:
                return
            report = db.get(Report, job.report_id)
            if report is None:
                job.status = "failed"
                job.error = "报告不存在"
                db.commit()
                return

            settings = get_settings()
            llm = self.llm_factory or LLMService(settings=settings)
            retriever = Retriever(db)

            job.status = "running"
            job.message = "正在读取资料…"
            db.commit()

            truth = self._get_or_extract_truth(db, report, llm, retriever, job, settings)

            chapters = sorted(report.chapters, key=lambda c: c.seq)
            pending = [c for c in chapters if c.status not in DONE_STATUSES and c.seq >= job.current_seq]
            for chapter in pending:
                self._write_one(db, report, chapters, chapter, truth, llm, retriever, job, settings)
                db.commit()

            job.status = "succeeded"
            job.current_seq = len(chapters)
            job.message = "全文完成"
            job.notices = collect_notices(chapters)
            job.finished_at = _now()
            report.status = "done"
            db.commit()
            from app.services.events import record as record_event

            record_event(
                db,
                "E2",
                report.id,
                chapters=len(chapters),
                words_total=sum(c.words or 0 for c in chapters),
                manual=sum(1 for c in chapters if c.status == "manual"),
                rewrites=sum(c.rewrite_count or 0 for c in chapters),
                truncated=sum(1 for c in chapters if c.truncated),
                missing=sum(len(c.missing or []) for c in chapters),
                notices=len(job.notices or []),
            )
        except AppError as exc:
            self._fail(db, job_id, exc.message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("写全文失败: %s", type(exc).__name__)
            self._fail(db, job_id, f"{type(exc).__name__}：{str(exc)[:200]}")
        finally:
            db.close()

    def _fail(self, db: Session, job_id: str, message: str) -> None:
        db.rollback()
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status = "failed"
        job.error = message
        job.message = f"第 {job.current_seq} 章失败：{message[:80]}"
        report = db.get(Report, job.report_id)
        if report is not None:
            report.status = "paused"
            ch = next((c for c in report.chapters if c.seq == job.current_seq), None)
            if ch is not None and ch.status not in DONE_STATUSES:
                ch.status = "failed"
        db.commit()

    # ---------- 内部 ----------
    def _get_or_extract_truth(self, db, report, llm, retriever, job, settings) -> dict:
        row = db.scalar(select(TruthBase).where(TruthBase.report_id == report.id))
        if row is None:
            job.message = "正在读取资料…"
            db.commit()
            facts = extract_facts(
                llm, report.id, report.title, retriever,
                per_field=settings.retrieve_fact_segments,
                recorder=None,
            )
            row = TruthBase(
                report_id=report.id,
                validated_data=facts["validated_data"],
                sources=facts["sources"],
                terminology=facts["terminology"],
            )
            db.add(row)
            db.commit()
        return {"data": row.validated_data, "sources": row.sources, "terminology": row.terminology}

    def _write_one(self, db, report, chapters, chapter, truth, llm, retriever, job, settings) -> None:
        total = len(chapters)
        job.message = f"正在写第 {chapter.seq} / {total} 章：{chapter.title}"
        job.current_seq = chapter.seq
        chapter.status = "writing"
        db.commit()

        chunks = retriever.top(chapter_query(chapter), k=settings.retrieve_chapter_segments)
        chapter.retrieved = [c.as_dict() for c in chunks]

        summaries, last_ending = previous_context(chapters, chapter.seq)
        payload = write_once(
            llm, report, chapter, truth["data"], truth["terminology"], summaries, last_ending,
            chunks, report.id,
        )

        chapter.status = "compressing"
        db.commit()
        payload, compressed, truncated = control_length(
            llm, report, chapter, payload, truth["data"], truth["terminology"], summaries, last_ending,
            chunks, report.id, ratio=settings.chapter_words_ratio,
        )

        chapter.status = "auditing"
        db.commit()
        audit = audit_chapter(llm, report.id, chapter, truth["data"], truth["terminology"], payload.body)
        rewrites = 0
        while audit["has_critical"] and rewrites < settings.rewrite_max:
            rewrites += 1
            chapter.rewrite_count = rewrites
            chapter.status = "rewriting"
            job.message = f"正在写第 {chapter.seq} / {total} 章：{chapter.title}（第 {rewrites} 次重写）"
            db.commit()
            payload = write_once(
                llm, report, chapter, truth["data"], truth["terminology"], summaries, last_ending,
                chunks, report.id, step="重写",
                previous_body=payload.body, audit_report=audit,
            )
            payload, compressed, truncated = control_length(
                llm, report, chapter, payload, truth["data"], truth["terminology"], summaries, last_ending,
                chunks, report.id, ratio=settings.chapter_words_ratio,
            )
            audit = audit_chapter(llm, report.id, chapter, truth["data"], truth["terminology"], payload.body)

        # 定稿：只有这一版才写记忆
        chapter.body = payload.body
        chapter.original_body = payload.body
        chapter.summary = clip_summary(payload.summary, payload.body)
        chapter.missing = [m for m in payload.missing if m]
        chapter.notices = dedupe_notices([payload.user_notice] if payload.user_notice else [])
        chapter.audit = audit
        chapter.words = count_words(payload.body)
        chapter.truncated = truncated
        chapter.status = "manual" if audit["has_critical"] else "passed"
        job.message = f"第 {chapter.seq} / {total} 章完成：{chapter.title}"
        db.commit()
