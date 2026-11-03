"""写全文链路测试：假模型驱动，覆盖 PRD 评测方案的程序检查 C03–C10。"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Chapter, Job, Report, TruthBase
from app.services.llm import LLMService
from app.services.memory import dedupe_notices, last_sentence
from app.services.pipeline import WritingPipeline
from app.services.writer import count_words, max_words_for, truncate_at_sentence

FACTS = {
    "validated_data": {
        "total_investment": "总投资 25,000 万元",
        "capital_ratio": "资本金 7,500 万元，占 30%",
        "technology_route": "PEM 电解水制氢",
        "electrolyzer_config": "PEM 电解槽 10 台，年产氢 3,600 吨",
        "dc_power_consumption": "4.3 kWh/Nm³",
        "pressure_level": "加注压力 35 MPa",
        "project_scope": "A、B、C 三站",
        "site_area": None,
        "construction_period": "建设期 18 个月",
        "hydrogen_cost": None,
        "financial": "IRR 7.2%，回收期 11.6 年",
        "多出来的字段": "应被丢弃",
    },
    "sources": {"total_investment": "01-立项批复.md", "capital_ratio": "01-立项批复.md"},
    "global_terminology": ["PEM 电解槽", "制氢加氢一体站"],
}

BODY_OK = "本项目总投资 25,000 万元，采用 PEM 电解水制氢，建设期 18 个月。" * 1
NO_ISSUE = {"critical_count": 0, "warning_count": 0, "issues": [], "unverifiable": []}


def critical_audit(quote="总投资 30,000 万元"):
    return {
        "critical_count": 1,
        "warning_count": 0,
        "issues": [{"severity": "CRITICAL", "quote": quote, "expected": "25,000 万元", "basis": "total_investment"}],
        "unverifiable": [],
    }


def warning_audit():
    return {
        "critical_count": 0,
        "warning_count": 1,
        "issues": [{"severity": "WARNING", "quote": "电解槽", "expected": "PEM 电解槽", "basis": "术语表"}],
        "unverifiable": [],
    }


class ScriptedLLM:
    """按提示词内容分派：提炼事实 / 写章 / 审计，各自按顺序取脚本。"""

    def __init__(self, facts=None, writes=None, audits=None, facts_error=False):
        self.facts = facts or FACTS
        self.writes = list(writes or [{"body": BODY_OK, "summary": "本章介绍了总投资与工期。"}])
        self.audits = list(audits or [NO_ISSUE])
        self.facts_error = facts_error
        self.log: list[str] = []

    def chat_fn(self, messages, want_json):
        text = messages[-1]["content"]
        if "数据核对员" in text:
            self.log.append("facts")
            if self.facts_error:
                raise RuntimeError("模拟网络错误")
            return json.dumps(self.facts, ensure_ascii=False), {"input_tokens": 10, "output_tokens": 5}, "req_f"
        if "技术审计专家" in text:
            self.log.append("audit")
            item = self.audits.pop(0) if len(self.audits) > 1 else self.audits[0]
            return json.dumps(item, ensure_ascii=False), {"input_tokens": 10, "output_tokens": 5}, "req_a"
        self.log.append("write")
        item = self.writes.pop(0) if len(self.writes) > 1 else self.writes[0]
        return json.dumps(item, ensure_ascii=False), {"input_tokens": 10, "output_tokens": 5}, "req_w"


@pytest.fixture()
def scripted():
    def _make(**kwargs):
        fake = ScriptedLLM(**kwargs)
        return fake, LLMService(chat_fn=fake.chat_fn, sleep_fn=lambda _s: None)

    return _make


def make_report(db, chapters=3, words=100, target=300):
    report = Report(title="攀枝花氢能一期", target_words=target, status="outline_ready")
    db.add(report)
    db.flush()
    for i in range(1, chapters + 1):
        db.add(
            Chapter(
                report_id=report.id,
                seq=i,
                title=f"第{i}章 测试章节",
                key_points=["要点"],
                data_needed=["总投资"],
                suggested_words=words,
                status="waiting",
            )
        )
    db.commit()
    db.refresh(report)
    return report


# ---------------- 单元：字数与截断 ----------------
def test_count_words_ignores_whitespace():
    assert count_words("总投资 25,000\n万元") == len("总投资25,000万元")
    assert max_words_for(100) == 110


def test_truncate_at_sentence():
    text = "第一句。第二句。第三句。"
    clipped, ok = truncate_at_sentence(text, 8)
    assert ok is True
    assert count_words(clipped) <= 8
    assert clipped.endswith("。")


def test_last_sentence_from_body():
    assert last_sentence("第一段。第二段结束！") == "第二段结束！"


def test_dedupe_notices():
    assert dedupe_notices(["冲突 A", "冲突 A ", "", "冲突 B"]) == ["冲突 A", "冲突 B"]


# ---------------- 事实提炼 ----------------
def test_facts_normalized(db, scripted):
    fake, llm = scripted()
    report = make_report(db)
    pipeline = WritingPipeline(llm=llm)
    job = pipeline.start(report.id, run_sync=True)
    db.expire_all()
    truth = db.scalar(select(TruthBase).where(TruthBase.report_id == report.id))
    assert truth is not None
    assert "多出来的字段" not in truth.validated_data          # 多余字段丢弃
    assert truth.validated_data["site_area"] is None           # 缺失补 null
    assert truth.sources["capital_ratio"] == "01-立项批复.md"
    assert truth.validated_data["hydrogen_cost"] is None
    assert job.status == "succeeded"


def test_facts_source_defaults_to_unmarked(db, scripted):
    facts = json.loads(json.dumps(FACTS))
    facts["sources"] = {}
    fake, llm = scripted(facts=facts)
    report = make_report(db, chapters=1)
    WritingPipeline(llm=llm).start(report.id, run_sync=True)
    db.expire_all()
    truth = db.scalar(select(TruthBase).where(TruthBase.report_id == report.id))
    assert truth.sources["total_investment"] == "未标注"


# ---------------- 正常写完 ----------------
def test_writes_all_chapters_and_memory(db, scripted):
    fake, llm = scripted()
    report = make_report(db, chapters=3)
    job = WritingPipeline(llm=llm).start(report.id, run_sync=True)
    db.expire_all()
    chapters = sorted(db.get(Report, report.id).chapters, key=lambda c: c.seq)
    assert job.status == "succeeded"
    assert [c.status for c in chapters] == ["passed", "passed", "passed"]
    assert all(c.summary for c in chapters)
    assert all(count_words(c.body) <= max_words_for(c.suggested_words) for c in chapters)
    assert sum(c.words for c in chapters) < 20000
    # 第 2 章之后要带上第 1 章摘要（记忆由程序写）
    assert db.get(Report, report.id).status == "done"


def test_only_warning_does_not_rewrite(db, scripted):
    fake, llm = scripted(audits=[warning_audit()])
    report = make_report(db, chapters=1)
    WritingPipeline(llm=llm).start(report.id, run_sync=True)
    db.expire_all()
    chapter = db.get(Report, report.id).chapters[0]
    assert chapter.status == "passed"
    assert chapter.rewrite_count == 0
    assert chapter.audit["warning_count"] == 1
    assert fake.log.count("write") == 1          # 只写了一次，没有重写


def test_critical_triggers_rewrite_then_pass(db, scripted):
    fake, llm = scripted(audits=[critical_audit(), NO_ISSUE], writes=[{"body": BODY_OK}, {"body": BODY_OK + "已修正。"}])
    report = make_report(db, chapters=1)
    WritingPipeline(llm=llm).start(report.id, run_sync=True)
    db.expire_all()
    chapter = db.get(Report, report.id).chapters[0]
    assert chapter.status == "passed"
    assert chapter.rewrite_count == 1
    assert fake.log.count("audit") == 2


def test_rewrite_twice_still_critical_marks_manual(db, scripted):
    fake, llm = scripted(audits=[critical_audit()])
    report = make_report(db, chapters=1)
    WritingPipeline(llm=llm).start(report.id, run_sync=True)
    db.expire_all()
    chapter = db.get(Report, report.id).chapters[0]
    assert chapter.status == "manual"
    assert chapter.rewrite_count == 2
    assert chapter.audit["critical_count"] == 1


# ---------------- 控字数 ----------------
def test_over_length_compresses_once(db, scripted):
    long_body = "这是很长的正文。" * 40            # 远超 110 字
    short_body = "压缩后的正文。" * 10
    fake, llm = scripted(writes=[{"body": long_body}, {"body": short_body}])
    report = make_report(db, chapters=1, words=100)
    WritingPipeline(llm=llm).start(report.id, run_sync=True)
    db.expire_all()
    chapter = db.get(Report, report.id).chapters[0]
    assert chapter.truncated is False
    assert count_words(chapter.body) <= 110
    assert fake.log.count("write") == 2          # 写 + 压缩


def test_still_too_long_truncates(db, scripted):
    long_body = "这是很长的正文。" * 40
    still_long = "还是很长的正文。" * 40
    fake, llm = scripted(writes=[{"body": long_body}, {"body": still_long}])
    report = make_report(db, chapters=1, words=100)
    WritingPipeline(llm=llm).start(report.id, run_sync=True)
    db.expire_all()
    chapter = db.get(Report, report.id).chapters[0]
    assert chapter.truncated is True
    assert count_words(chapter.body) <= 110
    assert chapter.body.rstrip().endswith("。")


# ---------------- 失败与继续 ----------------
def test_model_failure_marks_chapter_failed_then_resume(db, scripted):
    fake, llm = scripted(facts_error=True)
    report = make_report(db, chapters=2)
    job = WritingPipeline(llm=llm).start(report.id, run_sync=True)
    assert job.status == "failed"
    db.expire_all()
    assert db.get(Report, report.id).status == "paused"

    fake2, llm2 = scripted()
    job2 = WritingPipeline(llm=llm2).resume(report.id, run_sync=True)
    assert job2.status == "succeeded"
    db.expire_all()
    assert [c.status for c in sorted(db.get(Report, report.id).chapters, key=lambda c: c.seq)] == [
        "passed",
        "passed",
    ]


def test_resume_does_not_refetch_facts_or_rewrite_done_chapters(db, scripted):
    fake, llm = scripted()
    report = make_report(db, chapters=3)
    WritingPipeline(llm=llm).start(report.id, run_sync=True)
    db.expire_all()
    # 手工模拟「第 3 章被标为失败」
    chapter3 = sorted(db.get(Report, report.id).chapters, key=lambda c: c.seq)[2]
    chapter3.status = "failed"
    job = db.scalar(select(Job).where(Job.report_id == report.id))
    job.status = "failed"
    job.current_seq = 3
    db.commit()

    fake2, llm2 = scripted()
    WritingPipeline(llm=llm2).resume(report.id, run_sync=True)
    assert "facts" not in fake2.log                      # 不重新提炼（C09）
    db.expire_all()
    chapters = sorted(db.get(Report, report.id).chapters, key=lambda c: c.seq)
    assert chapters[0].status == "passed" and chapters[1].status == "passed"
    assert chapters[2].status == "passed"


def test_recover_interrupted_marks_paused(db, scripted):
    report = make_report(db, chapters=1)
    job = Job(report_id=report.id, status="running", total=1, current_seq=1, message="正在写")
    report.status = "writing"
    db.add(job)
    db.commit()
    count = WritingPipeline.recover_interrupted(SessionLocal)
    assert count == 1
    db.expire_all()
    assert db.scalar(select(Job).where(Job.report_id == report.id)).status == "paused"
    assert db.get(Report, report.id).status == "paused"


# ---------------- 冲突提示 ----------------
def test_user_notice_deduped_at_end(db, scripted):
    notice = "你要求的 2.8 亿与项目资料里的 25,000 万元不一致，本章按项目资料撰写。"
    fake, llm = scripted(writes=[{"body": BODY_OK, "summary": "s", "user_notice": notice}])
    report = make_report(db, chapters=3)
    job = WritingPipeline(llm=llm).start(report.id, run_sync=True)
    db.expire_all()
    assert job.status == "succeeded"
    stored = db.scalar(select(Job).where(Job.report_id == report.id))
    assert stored.notices == [notice]        # 三章同一条提示，去重后只剩一条


# ---------------- 解析宽容度（真实模型踩过的坑） ----------------
def test_parse_json_repairs_unescaped_quotes():
    from app.services.llm import _parse_json

    broken = '{"body": "形成"光伏—制氢—加氢"闭环。", "summary": "s", "missing": [], "user_notice": ""}'
    parsed = _parse_json(broken)
    assert parsed["body"].startswith("形成")


def test_parse_json_fenced_block():
    from app.services.llm import _parse_json

    fenced = '```json\n{"body": "正文。", "summary": "s", "missing": [], "user_notice": ""}\n```'
    assert _parse_json(fenced)["body"] == "正文。"


def test_facts_accepts_numeric_values(db, scripted):
    facts = {
        "validated_data": {"total_investment": 25000, "capital_ratio": None},
        "sources": {"total_investment": "01-立项批复.md"},
        "global_terminology": [],
    }
    fake, llm = scripted(facts=facts)
    report = make_report(db, chapters=1)
    WritingPipeline(llm=llm).start(report.id, run_sync=True)
    db.expire_all()
    truth = db.scalar(select(TruthBase).where(TruthBase.report_id == report.id))
    assert truth.validated_data["total_investment"] == "25000"   # 数字转字符串，不丢值
    assert truth.validated_data["site_area"] is None


def test_audit_demotes_unverifiable_instead_of_critical(db, scripted):
    """PRD：全局事实里没有、没法核对的数不算错误（应进 unverifiable）。"""
    from app.services.auditor import AuditPayload
    from app.services.auditor import audit_chapter

    payload = AuditPayload(
        critical_count=1,
        warning_count=0,
        issues=[{
            "severity": "CRITICAL",
            "quote": "电解制氢系统投资 6,800 万元",
            "expected": "全局事实未给出该投资额，无法核对",
            "basis": "electrolyzer_config",
        }],
        unverifiable=[],
    )
    fake = ScriptedLLM()
    fake.chat_fn = lambda messages, want_json: (payload.model_dump_json(), {"input_tokens": 1, "output_tokens": 1}, "r")
    llm = LLMService(chat_fn=fake.chat_fn, sleep_fn=lambda _s: None)
    chapter = make_report(db, chapters=1).chapters[0]
    result = audit_chapter(llm, "r1", chapter, {"total_investment": "25,000 万元"}, [], "正文。")
    assert result["critical_count"] == 0
    assert result["has_critical"] is False
    assert any("6,800" in u for u in result["unverifiable"])


def test_audit_drops_equivalent_money_writing():
    """PRD：25,000 万元 = 2.5 亿元，等价值不算问题。"""
    from app.services.auditor import drop_equivalent

    truth = {"total_investment": "总投资 25,000 万元"}
    issues = [
        {"severity": "CRITICAL", "quote": "按 25,000 万元折合约 2.5 亿元", "expected": "25,000 万元", "basis": "total_investment"},
        {"severity": "CRITICAL", "quote": "项目总投资 30,000 万元", "expected": "25,000 万元", "basis": "total_investment"},
    ]
    kept = drop_equivalent(issues, truth)
    assert len(kept) == 1 and "30,000" in kept[0]["quote"]
