"""接口的请求 / 响应结构（Pydantic）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ---------- 资料 ----------
class DocumentOut(BaseModel):
    id: str
    filename: str
    status: str            # available / no_text / failed
    segments_count: int
    size_bytes: int
    error: str | None = None
    code: str | None = None      # 失败时的稳定错误码（如 UNSUPPORTED_FORMAT）
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListOut(BaseModel):
    items: list[DocumentOut]


# ---------- 报告 ----------
class ReportCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    target_words: int = 12000
    extra_requirements: str = ""

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("标题不能为空")
        return v

    @field_validator("extra_requirements")
    @classmethod
    def _limit_requirements(cls, v: str) -> str:
        if len(v) > 2000:
            raise ValueError("补充要求最多 2,000 字")
        return v


class ChapterOut(BaseModel):
    id: int
    seq: int
    title: str
    key_points: list[str] = []
    data_needed: list[str] = []
    suggested_words: int
    status: str = "waiting"

    model_config = {"from_attributes": True}


class ReportOut(BaseModel):
    id: str
    title: str
    target_words: int
    extra_requirements: str
    status: str
    created_at: datetime
    updated_at: datetime
    chapters: list[ChapterOut] = []
    warnings: list[str] = []


class ReportSummaryOut(BaseModel):
    id: str
    title: str
    target_words: int
    status: str
    chapters_count: int
    words_total: int
    created_at: datetime


class ReportListOut(BaseModel):
    items: list[ReportSummaryOut]


# ---------- 大纲 ----------
class ChapterIn(BaseModel):
    seq: int | None = None
    title: str = Field(min_length=1, max_length=200)
    key_points: list[str] = []
    data_needed: list[str] = []
    suggested_words: int = Field(gt=0)


class OutlineSaveIn(BaseModel):
    chapters: list[ChapterIn] = Field(min_length=1)


class OutlineChapterModel(BaseModel):
    """模型输出的大纲一章（校验用）。"""

    chapter_id: int | None = None
    title: str = Field(min_length=1)
    key_points: list[str] = []
    data_needed: list[str] = []
    suggested_words: int = 0


class OutlinePayloadModel(BaseModel):
    """模型输出的大纲整体。"""

    full_outline: list[OutlineChapterModel] = Field(min_length=1)


# ---------- 写全文（2-2） ----------
class JobOut(BaseModel):
    id: str
    report_id: str
    status: str
    status_text: str = ""
    current_seq: int = 0
    total: int = 0
    message: str = ""
    error: str | None = None
    notices: list[str] = []


class ReportChapterProgress(BaseModel):
    seq: int
    title: str
    status: str
    status_text: str = ""
    words: int = 0
    rewrite_count: int = 0
    truncated: bool = False
    critical_count: int = 0
    warning_count: int = 0
    missing: list[str] = []


class ProgressSummary(BaseModel):
    done: int = 0
    manual: int = 0
    failed: int = 0
    words_total: int = 0


class ProgressOut(BaseModel):
    report_id: str
    report_status: str
    job: JobOut | None = None
    chapters: list[ReportChapterProgress] = []
    summary: ProgressSummary = ProgressSummary()
