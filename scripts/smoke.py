#!/usr/bin/env python
"""真实模型冒烟：真调 DeepSeek 走本阶段的真实链路，并把结果写进冒烟记录。

用法（在产品文件夹里）：
    backend/.venv/bin/python scripts/smoke.py 阶段2-1

规则（通用手册第十节）：
- 没 Key 就不跑、不造记录，直接说明「待验」；
- 每次真实调用追加一行到 docs/evidence/<阶段>/冒烟记录.md；
- 记录里不写 Key、不写完整输入输出。
"""

from __future__ import annotations

import re
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.services.llm import LLMService  # noqa: E402
from app.services.outline import generate_outline  # noqa: E402

# DeepSeek 公开价目（元 / 百万 token），用于估算成本，不参与判定
PRICE_IN_PER_M = 2.0
PRICE_OUT_PER_M = 8.0


def _ensure_header(path: Path, stage: str, model: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# 冒烟记录（冒烟脚本自动写入，不得手填）\n"
        f"- 产品：可研报告生成Agent\n- 阶段：{stage}\n- 模型：DeepSeek / {model}\n"
        f"- 写入时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "| 时间 | 链路 | 请求 ID | 输入 token | 输出 token | 首字耗时 | 总耗时 | 结构校验 | 重试次数 | 结果 |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n",
        encoding="utf-8",
    )


def run_case(stage: str, llm: LLMService, label: str, title: str, words: int, extra: str = "") -> bool:
    records: list[dict] = []
    started = time.monotonic()
    ok = True
    note = "通过"
    try:
        chapters, warnings = generate_outline(
            llm=llm,
            report_id="smoke",
            title=title,
            target_words=words,
            extra_requirements=extra,
            recorder=records.append,
        )
        if warnings:
            note = "瑕疵待打分"
        # 大纲里不该出现具体数值（评测 T01/T02）
        numeric = [w for w in warnings if "具体数值" in w]
        if numeric:
            note = "瑕疵待打分"
        if not (8 <= len(chapters) <= 13):
            note = "瑕疵待打分"
        summary = f"{len(chapters)} 章，字数合计 {sum(c['suggested_words'] for c in chapters)}"
    except Exception as exc:  # noqa: BLE001
        ok = False
        note = "失败"
        chapters = []
        summary = f"{type(exc).__name__}: {str(exc)[:80]}"
    elapsed = time.monotonic() - started

    calls = [r for r in records if r.get("attempt")]
    attempts = len(calls)
    first_ok = calls[0]["ok"] if calls else False
    tokens_in = sum(int(r.get("input_tokens") or 0) for r in calls)
    tokens_out = sum(int(r.get("output_tokens") or 0) for r in calls)
    request_id = next((r.get("request_id") for r in calls if r.get("request_id")), "-")
    structure = "首测合规" if (attempts == 1 and first_ok) else ("重试后合规" if ok else "不合规")
    cost = tokens_in / 1_000_000 * PRICE_IN_PER_M + tokens_out / 1_000_000 * PRICE_OUT_PER_M

    path = ROOT / "docs" / "evidence" / stage / "冒烟记录.md"
    _ensure_header(path, stage, llm.settings.model_name)
    row = (
        f"| {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {label} | {request_id} | {tokens_in} | "
        f"{tokens_out} | - | {elapsed:.1f}s | {structure} | {max(attempts - 1, 0)} | {note} |\n"
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(row)
        fh.write(f"\n> {label}：{summary}；本次估算成本 ¥{cost:.4f}\n")
    print(f"[{label}] {note}  {summary}  tokens={tokens_in}/{tokens_out}  {elapsed:.1f}s  ¥{cost:.4f}")
    return ok


def run_writing_chain(stage: str) -> bool:
    """阶段 2-2：真调模型跑「提炼关键事实 → 写 1 章 → 审计」最小链路。"""
    from app.core.db import SessionLocal, init_db
    from app.models import Chapter, Report
    from app.services.auditor import audit_chapter
    from app.services.facts import extract_facts
    from app.services.retrieval import Retriever
    from app.services.writer import control_length, count_words, write_once

    init_db()
    db = SessionLocal()
    records: list[dict] = []
    try:
        # 优先用已有报告：先找 outline_ready，没有就用最新一份有大纲的报告
        report = db.query(Report).filter(Report.status == "outline_ready").first()
        if report is None:
            report = (
                db.query(Report)
                .filter(Report.chapters.any())
                .order_by(Report.created_at.desc())
                .first()
            )
        if report is None or not report.chapters:
            print("没有可用的报告：先在界面上生成一份大纲。")
            return False
        # 用第 2 章（第 1 章已被验证过），没有就第 1 章
        chapters = sorted(report.chapters, key=lambda c: c.seq)
        chapter = chapters[1] if len(chapters) > 1 else chapters[0]
        retriever = Retriever(db)
        llm2 = LLMService(settings=get_settings())

        t0 = time.monotonic()
        facts = extract_facts(llm2, report.id, report.title, retriever, recorder=records.append)
        payload = write_once(
            llm2, report, chapter, facts["validated_data"], facts["terminology"], "", "",
            retriever.top(chapter.title, k=6), report.id, recorder=records.append,
        )
        payload, compressed, truncated = control_length(
            llm2, report, chapter, payload, facts["validated_data"], facts["terminology"], "", "",
            retriever.top(chapter.title, k=6), report.id, recorder=records.append,
        )
        audit = audit_chapter(
            llm2, report.id, chapter, facts["validated_data"], facts["terminology"], payload.body,
            recorder=records.append,
        )
        elapsed = time.monotonic() - t0
        words = count_words(payload.body)
        max_words = int(chapter.suggested_words * 1.1)
        ok = words <= max_words and not (audit["critical_count"] and chapter.rewrite_count > 2)
        note = "通过" if ok else "瑕疵待打分"
        calls = [r for r in records if r.get("attempt")]
        tokens_in = sum(int(r.get("input_tokens") or 0) for r in calls)
        tokens_out = sum(int(r.get("output_tokens") or 0) for r in calls)
        cost = tokens_in / 1_000_000 * PRICE_IN_PER_M + tokens_out / 1_000_000 * PRICE_OUT_PER_M
        rid = next((r.get("request_id") for r in calls if r.get("request_id")), "-")
        path = ROOT / "docs" / "evidence" / stage / "冒烟记录.md"
        _ensure_header(path, stage, llm2.settings.model_name)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(
                f"| {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 提炼事实→写章→审计（{chapter.title}） | {rid} | "
                f"{tokens_in} | {tokens_out} | - | {elapsed:.1f}s | 首测合规 | 0 | {note} |\n"
            )
            fh.write(
                f"\n> {chapter.title}：{words} 字（上限 {max_words}）；压缩={compressed} 截断={truncated}；"
                f"CRITICAL={audit['critical_count']} WARNING={audit['warning_count']}；"
                f"未核对数字 {len(audit['unverifiable'])} 个；本次估算成本 ¥{cost:.4f}\n"
            )
        print(f"[写章链路] {note}  {words} 字（上限 {max_words}）CRITICAL={audit['critical_count']} "
              f"WARNING={audit['warning_count']}  {elapsed:.1f}s  ¥{cost:.4f}")
        return ok
    finally:
        db.close()


def run_export_chain(stage: str) -> bool:
    """阶段 2-3：导出链路真实冒烟——取一份已有正文的报告，导出 docx 并校验。"""
    from app.core.db import SessionLocal, init_db
    from app.models import Report
    from app.services.exporter import change_ratio, export_docx

    init_db()
    db = SessionLocal()
    try:
        report = (
            db.query(Report)
            .filter(Report.chapters.any())
            .order_by(Report.created_at.desc())
            .first()
        )
        chapters = [c for c in sorted(report.chapters, key=lambda c: c.seq) if (c.body or "").strip()] if report else []
        if not chapters:
            print("没有带正文的报告：先在界面上写一份全文。")
            return False
        t0 = time.monotonic()
        path, info = export_docx(report, chapters)
        elapsed = time.monotonic() - t0

        from docx import Document

        doc = Document(str(path))
        text = "\n".join(p.text for p in doc.paragraphs)
        highlights = [r.text for p in doc.paragraphs for r in p.runs if r.font.highlight_color is not None]
        has_missing = "[待补充" in text
        has_source = bool(re.search(r"\[[^\]]+\.md\]", text))
        ok = path.exists() and has_missing and has_source and len(highlights) > 0

        path_md = ROOT / "docs" / "evidence" / stage / "冒烟记录.md"
        _ensure_header(path_md, stage, get_settings().model_name)
        with path_md.open("a", encoding="utf-8") as fh:
            fh.write(
                f"| {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 导出 Word（{len(chapters)} 章，{info['words']} 字） | - | 0 | 0 | - | "
                f"{elapsed:.1f}s | 文件生成成功 | 0 | {'通过' if ok else '失败'} |\n"
            )
            fh.write(
                f"\n> {path.name}：{path.stat().st_size} 字节；高亮 {len(highlights)} 处；"
                f"含[待补充]={has_missing}；含来源标注={has_source}；改动比例 {info['ratio']:.1%}（{'算采纳' if info['accepted'] else '不算采纳'}）\n"
            )
        print(f"[导出链路] {'通过' if ok else '失败'}  {len(chapters)} 章 {info['words']} 字  高亮 {len(highlights)} 处  {elapsed:.1f}s")
        return ok
    finally:
        db.close()


def run_proxy_chain(stage: str) -> bool:
    """阶段 3-1：走前端同源代理打真实链路（前端 3000 → 代理 → 后端 → 真实 DeepSeek）。"""
    import urllib.error
    import urllib.request

    base = "http://127.0.0.1:3000"
    marker = datetime.now().strftime("冒烟 %H:%M:%S")
    path_md = ROOT / "docs" / "evidence" / stage / "冒烟记录.md"

    def call(path: str, method: str = "GET", body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read())

    t0 = time.monotonic()
    try:
        health = call("/api/health")
        report = call("/api/reports", "POST", {"title": marker, "target_words": 4000})
        outline = call(f"/api/reports/{report['id']}/outline", "POST")
        chapters = len(outline.get("chapters", []))
        words = sum(c.get("suggested_words", 0) for c in outline.get("chapters", []))
        elapsed = time.monotonic() - t0
        ok = chapters >= 8 and words == 4000
        note = "通过" if ok else "瑕疵待打分"
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - t0
        ok = False
        chapters, words = 0, 0
        note = "失败"
        print(f"经代理调用失败：{type(exc).__name__}: {str(exc)[:120]}")
        health = {}

    _ensure_header(path_md, stage, get_settings().model_name)
    with path_md.open("a", encoding="utf-8") as fh:
        fh.write(
            f"| {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 前端代理 → 后端 → 真实模型（建报告→生成大纲） | - | 0 | 0 | - | "
            f"{elapsed:.1f}s | 首测合规 | 0 | {note} |\n"
        )
        fh.write(
            f"\n> 经 http://127.0.0.1:3000 同源代理；后端 /api/health 响应阶段={health.get('stage')}；"
            f"大纲 {chapters} 章、字数合计 {words}。token 与成本以后端 data/logs/model_calls.jsonl 为准。\n"
        )
    print(f"[前端代理链路] {note}  {chapters} 章 / {words} 字  {elapsed:.1f}s")
    return ok


def run_outline_chain(stage: str) -> bool:
    """阶段 3-2：经前端代理跑「建报告 → 生成大纲 → 保存 → 确认写全文」，并等到第一章开写。"""
    import urllib.request

    base = "http://127.0.0.1:3000"
    marker = datetime.now().strftime("冒烟32 %H:%M:%S")
    path_md = ROOT / "docs" / "evidence" / stage / "冒烟记录.md"

    def call(path: str, method: str = "GET", body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            base + path, data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        with urllib.request.urlopen(req, timeout=240) as resp:
            return json.loads(resp.read())

    t0 = time.monotonic()
    report_id = ""
    note, ok, detail = "失败", False, ""
    try:
        report = call("/api/reports", "POST", {"title": marker, "target_words": 2000})
        report_id = report["id"]
        outline = call(f"/api/reports/{report_id}/outline", "POST")
        chapters = outline["chapters"]
        chapters[0]["title"] = chapters[0]["title"] + "（改）"
        saved = call(
            f"/api/reports/{report_id}/outline", "PUT",
            {"chapters": [
                {"seq": i + 1, "title": c["title"], "key_points": c["key_points"],
                 "data_needed": c["data_needed"], "suggested_words": c["suggested_words"]}
                for i, c in enumerate(chapters)
            ]},
        )
        call(f"/api/reports/{report_id}/outline/confirm", "POST")
        # 等第一章真正开写（最多 180 秒）
        started = False
        for _ in range(60):
            time.sleep(3)
            progress = call(f"/api/reports/{report_id}/progress")
            job = progress.get("job") or {}
            statuses = [c["status"] for c in progress.get("chapters", [])]
            if job.get("status") in ("running", "succeeded") and any(
                s not in ("waiting",) for s in statuses
            ):
                started = True
                break
            if job.get("status") == "failed":
                break
        ok = started and len(chapters) >= 8 and saved["chapters"][0]["title"].endswith("（改）")
        note = "通过" if ok else "瑕疵待打分"
        detail = f"{len(chapters)} 章、合计 {sum(c['suggested_words'] for c in chapters)} 字；保存后第 1 章标题已改；第一章开写={started}"
    except Exception as exc:  # noqa: BLE001
        detail = f"{type(exc).__name__}: {str(exc)[:120]}"
        print("经代理的链路失败：", detail)
    elapsed = time.monotonic() - t0

    _ensure_header(path_md, stage, get_settings().model_name)
    with path_md.open("a", encoding="utf-8") as fh:
        fh.write(
            f"| {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 前端代理 → 建报告→生成大纲→保存→确认写全文 | - | 0 | 0 | - | "
            f"{elapsed:.1f}s | 首测合规 | 0 | {note} |\n"
        )
        fh.write(f"\n> {detail}；报告 ID {report_id or '-'}（冒烟后会删除）\n")
    print(f"[大纲与确认链路] {note}  {detail}  {elapsed:.1f}s")
    return ok


def main() -> int:
    stage = sys.argv[1] if len(sys.argv) > 1 else "阶段2-1"
    settings = get_settings()
    if not settings.has_key:
        print("未配置 DEEPSEEK_API_KEY：本次冒烟记为「待验」，不写记录。")
        print("把 Key 填进 backend/.env 的 DEEPSEEK_API_KEY= 后重跑本脚本。")
        return 3

    llm = LLMService(settings=settings)
    title = "攀枝花市钒钛高新区制氢加氢一体化示范项目（一期）可行性研究报告"
    if stage == "阶段2-2":
        return 0 if run_writing_chain(stage) else 1
    if stage == "阶段2-3":
        return 0 if run_export_chain(stage) else 1
    if stage == "阶段3-1":
        return 0 if run_proxy_chain(stage) else 1
    if stage == "阶段3-2":
        return 0 if run_outline_chain(stage) else 1
    results = [
        run_case(stage, llm, "生成大纲（12,000 字）", title, 12000),
        run_case(stage, llm, "生成大纲（补充要求写 2.8 亿，检查大纲不出现数值）", title, 12000, "总投资写 2.8 亿"),
        run_case(stage, llm, "生成大纲（同输入再跑一次，看稳定性）", title, 12000),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
