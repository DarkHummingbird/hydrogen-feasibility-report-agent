"""SQLAlchemy 模型（阶段 2-1 需要的四张表 + 模型调用记录）。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return uuid.uuid4().hex


class Document(Base):
    """上传的资料。status: available / no_text / failed（PRD F1）。"""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    ext: Mapped[str] = mapped_column(String(10))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="failed")
    segments_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    owner: Mapped[str] = mapped_column(String(64), default="local")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    segments: Mapped[list["Segment"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Segment.seq"
    )


class Segment(Base):
    """切段结果：约 800 字，相邻重叠 100 字（PRD 第五节）。"""

    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)

    document: Mapped[Document] = relationship(back_populates="segments")


class Report(Base):
    """报告。status: draft / outline_ready / writing / paused / done。"""

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    title: Mapped[str] = mapped_column(String(200))
    target_words: Mapped[int] = mapped_column(Integer, default=12000)
    extra_requirements: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String(20), default="氢能")
    style: Mapped[str] = mapped_column(String(20), default="正式")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    owner: Mapped[str] = mapped_column(String(64), default="local")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="report", cascade="all, delete-orphan", order_by="Chapter.seq"
    )


class Chapter(Base):
    """章节：2-1 存大纲，2-2 填正文、审计与记忆。"""

    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    key_points: Mapped[list] = mapped_column(JSON, default=list)
    data_needed: Mapped[list] = mapped_column(JSON, default=list)
    suggested_words: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    # ---- 阶段 2-2 ----
    body: Mapped[str] = mapped_column(Text, default="")
    original_body: Mapped[str] = mapped_column(Text, default="")   # AI 原稿，用户改稿时不动
    summary: Mapped[str] = mapped_column(Text, default="")         # 本章摘要（≤100 字）
    audit: Mapped[dict] = mapped_column(JSON, default=dict)
    rewrite_count: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    retrieved: Mapped[list] = mapped_column(JSON, default=list)     # 本章检索到的段落与文件名
    missing: Mapped[list] = mapped_column(JSON, default=list)       # [待补充] 的数据名称
    notices: Mapped[list] = mapped_column(JSON, default=list)       # user_notice
    words: Mapped[int] = mapped_column(Integer, default=0)

    report: Mapped[Report] = relationship(back_populates="chapters")


class ModelCall(Base):
    """每次模型调用的元数据（不含输入输出正文；正文在 data/logs/model_calls.jsonl）。"""

    __tablename__ = "model_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    step: Mapped[str] = mapped_column(String(40))
    ok: Mapped[bool] = mapped_column(default=False)
    error_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class TruthBase(Base):
    """每份报告的关键事实，只提炼一次，不展示给用户（PRD 全局上下文管理）。"""

    __tablename__ = "truth_bases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), unique=True, index=True)
    validated_data: Mapped[dict] = mapped_column(JSON, default=dict)
    sources: Mapped[dict] = mapped_column(JSON, default=dict)
    terminology: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Job(Base):
    """写全文任务：持久化，进程重启后可「从第 N 章继续」（底线第 2 条）。"""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/paused/succeeded/failed
    current_seq: Mapped[int] = mapped_column(Integer, default=1)
    total: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(300), default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    notices: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Event(Base):
    """埋点（PRD 第四节 E1–E3），本地落库，不上报第三方。"""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(8), index=True)   # E1 / E2 / E3
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
