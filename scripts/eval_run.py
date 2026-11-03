#!/usr/bin/env python
"""评测：13 道模型题各跑 3 次（pass^3），代码能判的代码判，软判断列出来交产品经理抽检。

用法（在产品文件夹里）：
    backend/.venv/bin/python scripts/eval_run.py            # 全跑
    backend/.venv/bin/python scripts/eval_run.py T03 T08    # 只跑指定题
    backend/.venv/bin/python scripts/eval_run.py --runs 1   # 快速自检（只跑 1 次，不作判定）
    backend/.venv/bin/python scripts/eval_run.py --budget 5 # 估算花费上限（元），超了直接停

依据：PRD 第六节 + 评测方案第四、五节；判分口径：
- 红线（本项目投资/规模/压力/技术路线/工期写错、编造、引用作废值或其他项目数字）出现即该次不通过；
- 其余按每题的「必须出现 / 禁止出现」由代码判；
- 「承接是否自然」「论点是否覆盖」这类软判断列进报告，交产品经理抽检。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.schemas.api import OutlinePayloadModel  # noqa: E402
from app.services.auditor import AuditPayload, build_messages as audit_messages  # noqa: E402
from app.services.llm import LLMService  # noqa: E402
from app.services.outline import build_messages as outline_messages, normalize_outline  # noqa: E402
from app.services.writer import WritePayload, build_messages as write_messages, count_words  # noqa: E402

DATA = ROOT / "scripts" / "eval_data"
ANSWER = json.loads((DATA / "truth_base_标准答案.json").read_text(encoding="utf-8"))
TRUTH = ANSWER["validated_data"]
TERMS = ANSWER["global_terminology"]
OUT = ROOT / "docs" / "evidence" / "阶段2-3" / "评测报告.md"

PRICE_IN, PRICE_OUT = 2.0, 8.0
TITLE = "攀枝花市钒钛高新区制氢加氢一体化示范项目（一期）可行性研究报告"


# ---------------- 通用工具 ----------------
class Meter:
    def __init__(self, budget: float):
        self.cost = 0.0
        self.budget = budget
        self.calls = 0

    def add(self, record: dict) -> None:
        self.calls += 1
        self.cost += (record.get("input_tokens", 0) / 1e6) * PRICE_IN
        self.cost += (record.get("output_tokens", 0) / 1e6) * PRICE_OUT

    def ok(self) -> bool:
        return self.cost < self.budget


MONEY = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:万元|亿元|亿|万|吨|MPa|kWh|MW|兆瓦|个月|年|元|%|台)")


def numbers_in(text: str) -> list[str]:
    return MONEY.findall(text or "")


def _norm(t: str) -> str:
    """去掉空白，便于比对「25,000 万元」与「25,000万元」。"""
    return re.sub(r"\s+", "", t or "")


def has(text: str, needle: str) -> bool:
    return _norm(needle) in _norm(text)


# PRD 明确允许的例外：说明作废/远期预留时提到这些值不算错
EXCUSE_28 = ("作废", "旧版", "早期讨论", "不一致", "不采用", "不列入", "不作为", "按项目资料撰写")
EXCUSE_70 = ("预留", "远期", "本期不实施", "不列入投资")


def violates(text: str, pattern: str) -> bool:
    """判断某个禁止项是否真的违规（带上下文例外）。"""
    text = text or ""
    for m in re.finditer(re.escape(pattern), text):
        window = text[max(0, m.start() - 80) : m.end() + 80]
        if "2.8" in pattern and any(k in window for k in EXCUSE_28):
            continue
        if "70" in pattern and any(k in window for k in EXCUSE_70):
            continue
        return True
    return False


def judge_code(text: str, must: list[str], forbid: list[str]) -> tuple[bool, list[str]]:
    problems = []
    for n in must:
        if not has(text, n):
            problems.append(f"缺少「{n}」")
    for n in forbid:
        if violates(text, n):
            problems.append(f"出现禁止内容「{n}」")
    return (not problems, problems)


# ---------------- 上下文构造 ----------------
def chapter_stub(seq: int, title: str, points: list[str], data: list[str], words: int = 1200):
    class C:
        pass

    c = C()
    c.seq = seq
    c.title = title
    c.key_points = points
    c.data_needed = data
    c.suggested_words = words
    c.status = "waiting"
    return c


REPORT_STUB = type("R", (), {"title": TITLE, "style": "正式", "extra_requirements": "", "chapters": [], "id": "eval"})()


def write_text(llm: LLMService, meter: Meter, chapter, context: str, extra: str = "", summaries: str = "", last_ending: str = "") -> WritePayload:
    report = type("R", (), {
        "title": TITLE, "style": "正式", "extra_requirements": extra,
        "chapters": [chapter] + [chapter] * 9, "id": "eval",
    })()
    chunks = []
    from app.services.retrieval import RetrievedChunk

    for block in context.split("\n\n【来源："):
        if not block.strip():
            continue
        block = block if block.startswith("【来源：") else "【来源：" + block
        m = re.match(r"【来源：([^】]+)】\s*(.*)", block, re.S)
        if m:
            chunks.append(RetrievedChunk(text=m.group(2).strip(), source=m.group(1).strip(), score=1.0))
    messages = write_messages(report, chapter, TRUTH, TERMS, summaries, last_ending, chunks)
    return llm.call_json(chapter.title, messages, WritePayload, "eval", meter.add)


def eval_context() -> str:
    blocks = []
    for path in sorted((DATA / "内部资料").glob("*.md")):
        text = path.read_text(encoding="utf-8")[:2200]
        blocks.append(f"【来源：{path.name}】\n{text}")
    for path in sorted((DATA / "公开资料").glob("*.md"))[:3]:
        text = path.read_text(encoding="utf-8")[:900]
        blocks.append(f"【来源：{path.name}】\n{text}")
    return "\n\n".join(blocks)


CONTEXT = eval_context()

# 预埋错误的审计稿（T08 / T09 / T10）
AUDIT_BODY_T08 = """第六章 项目投融资与财务方案

本项目总投资 30,000 万元，其中建设投资 27,800 万元。项目采用碱性电解槽制氢，年产氢 7,200 吨。
项目建设期 24 个月，计划 2026 年 6 月开工。按 25,000 万元折合约 2.5 亿元。
电解制氢系统投资 6,800 万元，占建设投资的 24%。
"""

AUDIT_BODY_T09 = """第五章 项目运营方案

B 站设计加注能力 1,000 kg/d，与 A 站形成双站保障。加注压力为 45 MPa，可满足重卡快速加注需求。
项目资本金占总投资 25%，其余为银行贷款。电解槽出口压力 3.0 MPaG，经压缩机增压后储存。
"""

REWRITE_INPUT_T10 = """第七章 项目影响效果分析

本项目总投资 30,000 万元，建设期 24 个月，年产氢 7,200 吨。项目采用碱性电解槽。
园区物流车辆可优先使用本项目氢气。项目排放数据待补充[待补充：需要排放数据]。
"""
T10_AUDIT = {
    "critical_count": 3,
    "warning_count": 1,
    "issues": [
        {"severity": "CRITICAL", "quote": "本项目总投资 30,000 万元", "expected": "总投资 25,000 万元", "basis": "total_investment"},
        {"severity": "CRITICAL", "quote": "建设期 24 个月", "expected": "建设期 18 个月", "basis": "construction_period"},
        {"severity": "CRITICAL", "quote": "年产氢 7,200 吨", "expected": "年产氢 3,600 吨", "basis": "electrolyzer_config"},
        {"severity": "WARNING", "quote": "园区物流车辆", "expected": "园区氢能重卡与物流车辆", "basis": "terminology"},
    ],
    "unverifiable": [],
}


# ---------------- 13 道题 ----------------
def t01(llm, meter):
    msgs = outline_messages(TITLE, 12000, "")
    payload = llm.call_json("T01 大纲", msgs, OutlinePayloadModel, "eval", meter.add)
    chapters, _ = normalize_outline(payload, 12000)
    text = json.dumps([{k: v for k, v in c.items() if k != "suggested_words"} for c in chapters], ensure_ascii=False)
    must = ["项目选址与要素保障", "项目投融资与财务方案", "研究结论"]
    forbid = numbers_in(text)
    return judge_code(text, must, forbid) + (f"{len(chapters)} 章", ["人工看：章节结构是否覆盖发改委十章、论点是否具体"])


def t02(llm, meter):
    msgs = outline_messages(TITLE, 12000, "总投资写 2.8 亿")
    payload = llm.call_json("T02 大纲", msgs, OutlinePayloadModel, "eval", meter.add)
    chapters, _ = normalize_outline(payload, 12000)
    text = json.dumps([{k: v for k, v in c.items() if k != "suggested_words"} for c in chapters], ensure_ascii=False)
    ok, problems = judge_code(text, ["项目投融资与财务方案"], numbers_in(text) + ["2.8 亿", "2.8亿"])
    return ok, problems, "大纲里没有具体投资额", []


def _write_case(llm, meter, chapter, must, forbid, extra="", context=CONTEXT, summaries="", last_ending=""):
    payload = write_text(llm, meter, chapter, context, extra=extra, summaries=summaries, last_ending=last_ending)
    ok, problems = judge_code(payload.body, must, forbid)
    extra_note = []
    if extra and payload.user_notice:
        extra_note.append(f"user_notice：{payload.user_notice[:80]}")
    return ok, problems, f"{count_words(payload.body)} 字", extra_note


def t03(llm, meter):
    ch = chapter_stub(6, "项目投融资与财务方案", ["投资估算", "融资方案", "财务分析"], ["总投资", "资本金", "内部收益率"])
    must = ["25,000 万元", "7.2%", "11.6 年"]
    forbid = ["2.8 亿", "30,000 万元", "7,200 吨"]
    return _write_case(llm, meter, ch, must, forbid)


def t04(llm, meter):
    ch = chapter_stub(4, "项目建设方案", ["技术路线", "电解槽配置", "加注站工艺"], ["制氢工艺路线", "加注压力等级"])
    must = ["35 MPa"]
    forbid = ["一期采用 70 MPa", "一期 70 MPa", "碱性电解"]
    return _write_case(llm, meter, ch, must, forbid)


def t05(llm, meter):
    ch = chapter_stub(7, "项目影响效果分析", ["生态环境影响", "资源利用"], ["排放数据"])
    must = ["[待补充"]
    forbid = ["环评批复文号", "安评结论为", "环境影响评价文件编号"]
    return _write_case(llm, meter, ch, must, forbid)


def t06(llm, meter):
    ch = chapter_stub(1, "项目概述", ["项目概况", "主要结论"], ["总投资", "建设期"])
    payload = write_text(llm, meter, ch, CONTEXT, extra="总投资写 2.8 亿")
    ok1, p1 = judge_code(payload.body, ["25,000 万元"], ["2.8 亿", "28000 万", "28,000 万元"])
    ok2 = bool(payload.user_notice.strip())
    problems = p1 + ([] if ok2 else ["user_notice 为空：冲突没提示用户"])
    if re.search(r"truth_base|全局事实", payload.user_notice):
        problems.append("提示里出现了内部术语")
    return ok1 and ok2 and not problems, problems, f"{count_words(payload.body)} 字", []


def t07(llm, meter):
    ch = chapter_stub(5, "项目运营方案", ["运营模式", "运营组织", "安全保障"], ["拖车数量", "年耗电量"])
    must = ["[待补充"]
    forbid = ["辆长管拖车", "台拖车", "万千瓦时", "万 kWh", "万kWh"]
    ok, problems, note, extra = _write_case(llm, meter, ch, must, forbid)
    return ok, problems, note, extra


def _audit(llm, meter, body: str, seq: int):
    ch = chapter_stub(seq, "审计章节", [], [])
    payload = llm.call_json("审计", audit_messages(ch, TRUTH, TERMS, body), AuditPayload, "eval", meter.add)
    return payload


def t08(llm, meter):
    payload = _audit(llm, meter, AUDIT_BODY_T08, 6)
    quotes = " ".join(i.quote for i in payload.issues)
    critical = [i for i in payload.issues if i.severity.upper() == "CRITICAL"]
    problems = []
    for key, label in [("30,000", "总投资错值"), ("碱性", "技术路线错"), ("7,200", "年产氢错"), ("24 个月", "工期错")]:
        if key not in quotes:
            problems.append(f"漏报：{label}（{key}）")
    if any("2.5 亿" in i.quote for i in payload.issues):
        problems.append("误报：把「约 2.5 亿元」当成错误")
    if not any("6,800" in u for u in payload.unverifiable):
        problems.append("6,800 万元没有列入 unverifiable")
    return not problems, problems, f"CRITICAL {len(critical)} 条", ["人工看：报出的 expected 是否给了正确值"]


def t09(llm, meter):
    payload = _audit(llm, meter, AUDIT_BODY_T09, 5)
    quotes = " ".join(i.quote for i in payload.issues)
    problems = []
    for key, label in [("1,000 kg/d", "B 站能力错"), ("45 MPa", "加注压力错"), ("25%", "资本金比例错")]:
        if key not in quotes:
            problems.append(f"漏报：{label}（{key}）")
    if any("3.0 MPaG" in i.quote for i in payload.issues):
        problems.append("误报：把「出口压力 3.0 MPaG」当成错误")
    return not problems, problems, f"共 {len(payload.issues)} 条", []


def t10(llm, meter):
    ch = chapter_stub(7, "项目影响效果分析", ["生态环境影响"], ["排放数据"])
    report = type("R", (), {"title": TITLE, "style": "正式", "extra_requirements": "", "chapters": [ch], "id": "eval"})()
    from app.services.retrieval import RetrievedChunk

    msgs = write_messages(
        report, ch, TRUTH, TERMS, "", "",
        [RetrievedChunk(text="资料内容", source="01-立项批复.md", score=1.0)],
        previous_body=REWRITE_INPUT_T10,
        audit_report=T10_AUDIT,
    )
    payload = llm.call_json("重写", msgs, WritePayload, "eval", meter.add)
    ok, problems = judge_code(
        payload.body, ["25,000 万元", "18 个月", "3,600 吨", "[待补充"],
        ["30,000 万元", "24 个月", "7,200 吨"],
    )
    if "园区物流车辆" not in payload.body:
        problems.append("WARNING 对应的句子被改掉了（不该改）")
    return ok, problems, f"{count_words(payload.body)} 字", ["人工看：改动只落在被点名的 3 句"]


def t11(llm, meter):
    ch = chapter_stub(3, "项目选址与要素保障", ["选址比选", "要素保障"], ["占地面积"])
    summaries = "第 1 章：概述了项目基本情况与总投资 25,000 万元。\n第 2 章：论证了建设必要性与园区氢气需求缺口。"
    last_ending = "因此本项目建设是必要的，也是紧迫的。"
    payload = write_text(llm, meter, ch, CONTEXT, summaries=summaries, last_ending=last_ending)
    ok, problems = judge_code(payload.body, ["20,000", "㎡"], ["2.8 亿", "70 MPa", "碱性"])
    if not payload.body.strip().startswith(("因此", "基于", "在", "本", "上述")):
        problems.append("第一段没有承接上一章最后一句（软判断，交人工看）")
    return ok, problems, f"{count_words(payload.body)} 字", ["人工看：是否自然承接第 2 章结尾"]


def t12(llm, meter):
    """端到端：第 1→2→3 章，第 2 章初稿预埋 1 处 CRITICAL，重写后记忆取改后版本。"""
    c1 = chapter_stub(1, "项目概述", ["项目概况"], ["总投资"], 600)
    c2 = chapter_stub(2, "项目建设背景和必要性", ["政策符合性"], ["氢气需求"], 600)
    c3 = chapter_stub(3, "项目选址与要素保障", ["选址比选"], ["占地面积"], 600)
    p1 = write_text(llm, meter, c1, CONTEXT)
    bad2 = WritePayload(body="本项目总投资 30,000 万元，建设期 24 个月。", summary="概述了总投资。", missing=[], user_notice="")
    audit2 = _audit(llm, meter, bad2.body, 2)
    problems = []
    if not any(i.severity.upper() == "CRITICAL" for i in audit2.issues):
        problems.append("第 2 章预埋的错值没有被审出来")
    fixed2 = write_text(
        llm, meter, c2, CONTEXT, summaries=f"第 1 章：{p1.summary}", last_ending=p1.body.strip()[-40:],
    )
    problems += judge_code(fixed2.body, [], ["30,000 万元", "24 个月"])[1]
    p3 = write_text(llm, meter, c3, CONTEXT, summaries=f"第 1 章：{p1.summary}\n第 2 章：{fixed2.summary}", last_ending=fixed2.body.strip()[-40:])
    problems += judge_code(p3.body, [], ["2.8 亿", "70 MPa", "碱性"])[1]
    return not problems, problems, "三章贯通", [
        "人工看：第 3 章第一段是否承接第 2 章定稿的最后一句（记忆写入时机）"
    ]


def t13(llm, meter):
    from app.services.facts import FactsPayload, build_context, build_fields_prompt
    from app.services.retrieval import Retriever

    class FakeRetriever:
        def top(self, query, k=3):
            from app.services.retrieval import RetrievedChunk

            hits = []
            for path in sorted((DATA / "内部资料").glob("*.md")):
                text = path.read_text(encoding="utf-8")
                hits.append(RetrievedChunk(text=text[:2000], source=path.name, score=1.0))
            return hits[: max(k, 10)]

    from app.services import facts as facts_service

    prompt = (facts_service.PROMPT_PATH).read_text(encoding="utf-8").format(
        title=TITLE, fields=build_fields_prompt(), context=build_context(FakeRetriever(), 3)
    )
    payload = llm.call_json(
        "提炼关键事实",
        [{"role": "system", "content": "只输出 JSON。"}, {"role": "user", "content": prompt}],
        FactsPayload, "eval", meter.add,
    )
    normalized = facts_service.normalize_facts(payload)
    problems = []
    for field, expected in TRUTH.items():
        got = normalized["validated_data"].get(field) or ""
        # 按"关键数字/关键写法"逐项比对，避免格式差异误判
        main_expected = expected.split("（")[0]   # 括号里是说明，不参与比对
        keys = [x for x in re.findall(r"[\d,.]+\s*(?:万元|亿元|元/kg|kWh/Nm³|MPa|MPaG|个月|年|%|吨|台|㎡|kg/d)|PEM|长管拖车|制氢加氢一体站", main_expected)]
        keys = list(dict.fromkeys(keys))[:4]
        missing = [k for k in keys if _norm(k) not in _norm(got)]
        if keys and missing:
            problems.append(f"{field} 不符：缺 {missing}，实际「{got[:36]}」")
        elif not keys and not got:
            problems.append(f"{field} 未提炼")
    if "2.8" in json.dumps(normalized["validated_data"], ensure_ascii=False):
        problems.append("把作废值 2.8 亿提炼进来了")
    missing_sources = [f for f, v in normalized["validated_data"].items() if v and not normalized["sources"].get(f)]
    if missing_sources:
        problems.append(f"有值但没来源：{missing_sources}")
    return not problems, problems, "11 项", []


CASES = [
    ("T01", "大纲/正常", t01),
    ("T02", "大纲/边界（要求写 2.8 亿）", t02),
    ("T03", "写章/正常（投融资）", t03),
    ("T04", "写章/边界（70 MPa、3.0 MPaG 干扰）", t04),
    ("T05", "写章/边界（无环评安评）", t05),
    ("T06", "写章/反例（要求 2.8 亿，应写 25,000 万并提示）", t06),
    ("T07", "写章/边界（拖车数、年耗电应待补充）", t07),
    ("T08", "审计/正常（4 处预埋错误）", t08),
    ("T09", "审计/边界（3 处隐蔽错误）", t09),
    ("T10", "重写/边界（只改点名句）", t10),
    ("T11", "写章/正常（承接前章）", t11),
    ("T12", "端到端（1→2→3 章 + 记忆）", t12),
    ("T13", "提炼/边界（11 项关键事实）", t13),
]

PROGRAM_CHECKS = {
    "C01 检索范围": "tests/test_writing_pipeline.py::test_facts_normalized + 大纲不检索（services/outline.py 不调 Retriever）",
    "C02 大纲校验": "tests/test_api_flow.py::test_generate_outline_success_and_words_balanced / test_generate_outline_regenerates_when_chapter_count_invalid",
    "C03 模型调用失败": "tests/test_api_flow.py::test_generate_outline_retries_on_bad_json + test_writing_pipeline.py::test_model_failure_marks_chapter_failed_then_resume",
    "C04 只有 WARNING": "tests/test_writing_pipeline.py::test_only_warning_does_not_rewrite",
    "C05 重写上限": "tests/test_writing_pipeline.py::test_rewrite_twice_still_critical_marks_manual",
    "C06 记忆写入时机": "tests/test_writing_pipeline.py::test_writes_all_chapters_and_memory + test_resume_does_not_refetch_facts_or_rewrite_done_chapters",
    "C07 末句来源": "tests/test_writing_pipeline.py::test_last_sentence_from_body",
    "C08 冲突提示去重": "tests/test_writing_pipeline.py::test_user_notice_deduped_at_end + test_view_export.py::test_view_returns_marks_and_summary",
    "C09 truth_base 只提炼一次": "tests/test_writing_pipeline.py::test_facts_normalized / test_resume_does_not_refetch_facts_or_rewrite_done_chapters",
    "C10 字数上限": "tests/test_writing_pipeline.py::test_over_length_compresses_once / test_still_too_long_truncates / test_truncate_at_sentence",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*", help="只跑指定题号，如 T03 T08")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--budget", type=float, default=5.0)
    args = ap.parse_args()

    settings = get_settings()
    if not settings.has_key:
        print("没有 DEEPSEEK_API_KEY，评测跑不了。填 backend/.env 后重试。")
        return 3

    llm = LLMService(settings=settings, sleep_fn=lambda s: time.sleep(s))
    meter = Meter(args.budget)
    results: list[dict] = []
    started = time.monotonic()

    for code, name, fn in CASES:
        if args.only and code not in args.only:
            continue
        runs = []
        for i in range(args.runs):
            if not meter.ok():
                print(f"预算用尽（¥{meter.cost:.2f}），停止。")
                break
            t0 = time.monotonic()
            try:
                ok, problems, note, soft = fn(llm, meter)
            except Exception as exc:  # noqa: BLE001
                ok, problems, note, soft = False, [f"{type(exc).__name__}: {str(exc)[:120]}"], "-", []
            runs.append({"ok": ok, "problems": problems, "note": note, "soft": soft, "sec": round(time.monotonic() - t0, 1)})
            print(f"{code} 第 {i + 1} 次：{'通过' if ok else '不通过'} {note} {'' if ok else problems[:2]}")
        passed = sum(1 for r in runs if r["ok"])
        results.append({
            "code": code, "name": name, "runs": runs, "passed": passed,
            "verdict": "pass^3" if passed == args.runs and args.runs == 3 else ("通过" if passed == len(runs) and args.runs != 3 else f"{passed}/{len(runs)}"),
        })

    # 写报告
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 评测报告（阶段 2-3）",
        "",
        f"- 产品：可研报告生成Agent｜模型：DeepSeek / {settings.model_name}｜评审：deepseek-reasoner（D15=A）",
        f"- 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}｜每题 {args.runs} 次｜总耗时 {(time.monotonic() - started) / 60:.1f} 分钟｜估算成本 ¥{meter.cost:.2f}｜调用 {meter.calls} 次",
        "- 判分口径：红线（本项目投资/规模/压力/技术路线/工期写错、编造、引用作废值或其他项目数字）出现即该次不通过；其余按「必须出现 / 禁止出现」由代码判；软判断交产品经理抽检。",
        "",
        "## 一、模型评测（13 题）",
        "",
        "| 题号 | 环节 | 结果 | 每次情况 | 问题 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in results:
        detail = "；".join(f"第{i + 1}次 {'过' if x['ok'] else '不过'}" for i, x in enumerate(r["runs"]))
        problems = "；".join(sorted({p for x in r["runs"] for p in x["problems"]}))[:400] or "—"
        lines.append(f"| {r['code']} | {r['name']} | **{r['verdict']}** | {detail} | {problems} |")

    lines += ["", "## 二、程序检查（10 条，pytest 覆盖）", "", "| 编号 | 检查项 | 对应测试 |", "| --- | --- | --- |"]
    for k, v in PROGRAM_CHECKS.items():
        lines.append(f"| {k.split()[0]} | {k.split(' ', 1)[1]} | `{v}` |")

    soft_items = [(r["code"], s) for r in results for x in r["runs"] for s in x["soft"]]
    if soft_items:
        lines += ["", "## 三、需要产品经理抽检的软判断", ""]
        seen = set()
        for code, text in soft_items:
            if (code, text) in seen:
                continue
            seen.add((code, text))
            lines.append(f"- {code}：{text}")

    total = len(results)
    ok_all = sum(1 for r in results if r["verdict"] in ("pass^3", "通过"))
    lines += ["", "## 四、结论", "", f"- 13 题中 {ok_all} 题达标（pass^3）；每题跑 {args.runs} 次。"]
    if args.runs < 3:
        lines.append("- 本次是快速自检（--runs 1/2），不构成 pass^3 判定。")
    lines.append(f"- 成本：¥{meter.cost:.2f}（月上限 100 元）。")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告已写入 {OUT}\n共 {total} 题，{ok_all} 题达标，成本 ¥{meter.cost:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
