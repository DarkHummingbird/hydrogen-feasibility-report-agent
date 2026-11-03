"""查看修改、导出、埋点（PRD F6/F7、E1–E3）。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Chapter, Event, Report, TruthBase
from app.services.exporter import change_ratio
from app.services.highlights import build_marks, collect_missing

BODY = "本项目总投资 25,000 万元，采用 PEM 电解水制氢[01-立项批复.md]。年耗电量[待补充：需要年耗电量数据]。"
CRITICAL_ISSUE = {
    "severity": "CRITICAL",
    "quote": "本项目总投资 25,000 万元",
    "expected": "总投资 30,000 万元",
    "basis": "total_investment",
}
WARNING_ISSUE = {"severity": "WARNING", "quote": "电解水", "expected": "PEM 电解槽", "basis": "terminology"}


@pytest.fixture()
def report_with_content(db):
    report = Report(title="攀枝花氢能一期", target_words=1200, status="done")
    db.add(report)
    db.flush()
    db.add(
        TruthBase(
            report_id=report.id,
            validated_data={"total_investment": "总投资 25,000 万元"},
            sources={"total_investment": "01-立项批复.md"},
            terminology=["PEM 电解槽"],
        )
    )
    db.add(
        Chapter(
            report_id=report.id,
            seq=1,
            title="项目概述",
            key_points=["概况"],
            data_needed=["总投资"],
            suggested_words=600,
            status="manual",
            body=BODY,
            original_body=BODY,
            summary="概述",
            audit={"critical_count": 1, "warning_count": 1, "issues": [CRITICAL_ISSUE, WARNING_ISSUE], "unverifiable": []},
            missing=["年耗电量"],
            notices=["你要求的 2.8 亿与资料不一致"],
            retrieved=[{"source": "01-立项批复.md", "text": "总投资 25,000 万元", "score": 1.0}],
            truncated=False,
            words=len(BODY.replace("\n", "")),
        )
    )
    db.add(
        Chapter(
            report_id=report.id,
            seq=2,
            title="建设方案",
            key_points=["方案"],
            data_needed=["压力"],
            suggested_words=600,
            status="passed",
            body="加注压力 35 MPa。",
            original_body="加注压力 35 MPa。",
            summary="方案",
            audit={"critical_count": 0, "warning_count": 0, "issues": [], "unverifiable": []},
            missing=["年耗电量", "运距"],
            notices=["你要求的 2.8 亿与资料不一致"],
            retrieved=[],
            truncated=True,
            words=12,
        )
    )
    db.commit()
    db.refresh(report)
    return report


# ---------------- 高亮计算 ----------------
def test_missing_and_critical_marks():
    marks = build_marks(BODY, [CRITICAL_ISSUE], {"total_investment": "01-立项批复.md"})
    types = [m["type"] for seg in marks["segments"] for m in seg["marks"]]
    assert "missing" in types and "critical" in types
    critical = next(s for s in marks["segments"] if any(m["type"] == "critical" for m in s["marks"]))
    assert "01-立项批复.md" in critical["marks"][0]["tooltip"]
    assert "30,000" in critical["marks"][0]["tooltip"]


def test_quote_not_found_goes_to_unlocated():
    issue = dict(CRITICAL_ISSUE, quote="这句话正文里没有")
    marks = build_marks(BODY, [issue], {})
    assert marks["critical"] and marks["unlocated"]
    assert not any(m["type"] == "critical" for seg in marks["segments"] for m in seg["marks"])


def test_reconstructs_original_text():
    marks = build_marks(BODY, [CRITICAL_ISSUE], {})
    assert "".join(seg["text"] for seg in marks["segments"]) == BODY


def test_warning_listed_separately():
    marks = build_marks(BODY, [WARNING_ISSUE], {})
    assert len(marks["warnings"]) == 1
    assert not marks["critical"]


def test_collect_missing_dedupes(db, report_with_content):
    rows = collect_missing(sorted(report_with_content.chapters, key=lambda c: c.seq))
    by_name = {r["name"]: r["chapters"] for r in rows}
    assert by_name["年耗电量"] == [1, 2]
    assert by_name["运距"] == [2]


# ---------------- 接口 ----------------
def test_view_returns_marks_and_summary(client, report_with_content):
    body = client().get(f"/api/reports/{report_with_content.id}/view").json()
    assert body["report"]["words_total"] == 12 + len(BODY.replace("\n", ""))
    assert body["directory"][0]["status_text"] == "待人工"
    assert body["summary"]["manual"][0]["seq"] == 1
    assert len(body["summary"]["notices"]) == 1          # 两章同一条提示，去重后一条
    chapter = body["chapter"]
    assert chapter["seq"] == 1                            # 默认打开待人工章
    assert chapter["critical"] and chapter["warnings"]
    assert chapter["retrieved"][0]["source"] == "01-立项批复.md"
    assert chapter["truncated"] is False


def test_view_second_chapter_and_truncated_flag(client, report_with_content):
    body = client().get(f"/api/reports/{report_with_content.id}/view?seq=2").json()
    assert body["chapter"]["seq"] == 2
    assert body["chapter"]["truncated"] is True


def test_save_body_updates_words_and_ratio(client, db, report_with_content):
    new_body = BODY.replace("[待补充：需要年耗电量数据]", "年耗电量 3,600 万千瓦时[待补充：需核定]")
    resp = client().put(
        f"/api/reports/{report_with_content.id}/chapters/1/body", json={"body": new_body}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["change_ratio"] > 0
    db.expire_all()
    chapter = db.scalar(select(Chapter).where(Chapter.report_id == report_with_content.id, Chapter.seq == 1))
    assert chapter.body == new_body
    assert chapter.original_body == BODY                  # AI 原稿不动
    assert chapter.words == len(re.sub(r"\s", "", new_body))


def test_save_body_rejects_empty(client, report_with_content):
    resp = client().put(f"/api/reports/{report_with_content.id}/chapters/1/body", json={"body": "   "})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "EMPTY_BODY"


def test_export_docx_writes_file_and_event(client, db, report_with_content):
    resp = client().post(f"/api/reports/{report_with_content.id}/export")
    assert resp.status_code == 200
    info = resp.json()
    assert info["chapters"] == 2
    assert 0 <= info["ratio"] < 0.15
    assert info["accepted"] is True

    from app.services.exporter import EXPORT_DIR

    path = EXPORT_DIR / info["file"]
    assert path.exists() and path.stat().st_size > 0

    from docx import Document

    document = Document(str(path))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "攀枝花氢能一期" in text
    assert "项目概述" in text and "建设方案" in text
    assert "[01-立项批复.md]" in text                      # 句末来源原样保留
    assert "[待补充：需要年耗电量数据]" in text
    highlighted = [
        run.text
        for p in document.paragraphs
        for run in p.runs
        if run.font.highlight_color is not None
    ]
    assert any(t.startswith("[待补充") for t in highlighted)

    events = db.scalars(select(Event).where(Event.code == "E3")).all()
    assert len(events) == 1
    assert events[0].payload["accepted"] is True
    assert events[0].payload["seconds_since_create"] >= 0


def test_export_requires_content(client, db):
    report = Report(title="空报告", target_words=12000, status="outline_ready")
    db.add(report)
    db.flush()
    db.add(
        Chapter(
            report_id=report.id, seq=1, title="空章", key_points=[], data_needed=[],
            suggested_words=600, status="waiting", body="",
        )
    )
    db.commit()
    resp = client().post(f"/api/reports/{report.id}/export")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "NO_CONTENT"


def test_download_endpoint_returns_docx(client, report_with_content):
    resp = client().get(f"/api/reports/{report_with_content.id}/export.docx")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml"
    )


def test_change_ratio_grows_with_edit(report_with_content):
    chapters = sorted(report_with_content.chapters, key=lambda c: c.seq)
    assert change_ratio(chapters) == 0
    chapters[0].body = chapters[0].body + "追加一段完全不同的内容，用来测试比例变化。"
    assert change_ratio(chapters) > 0


def test_events_endpoint_lists_codes(client, db, report_with_content):
    from app.services.events import record

    record(db, "E1", report_with_content.id, chapters=2)
    record(db, "E2", report_with_content.id, chapters=2, manual=1)
    items = client().get(f"/api/reports/{report_with_content.id}/events").json()["items"]
    assert [i["code"] for i in items] == ["E1", "E2"]
    assert json.dumps(items, ensure_ascii=False).count("E2") == 1


def test_resolve_source_from_long_basis():
    from app.services.highlights import resolve_source

    sources = {"electrolyzer_config": "01-立项批复.md"}
    assert resolve_source("electrolyzer_config", sources) == "01-立项批复.md"
    assert (
        resolve_source("electrolyzer_config：合计制氢规模 10,000 Nm³/h；年产氢 3,600 吨", sources)
        == "01-立项批复.md"
    )
    assert resolve_source("没有的字段", sources) == ""
