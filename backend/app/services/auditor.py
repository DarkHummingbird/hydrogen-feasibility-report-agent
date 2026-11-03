"""审计（PRD 第四节「审计」）：只对照 truth_base 与术语表挑错，不改稿。

程序侧规则：CRITICAL 触发重写；WARNING 只记录；truth_base 里没有的数字记 unverifiable，不判错。
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from app.services.llm import LLMService

PROMPT_PATH = Path(__file__).parent / "prompts" / "audit.md"


class AuditIssue(BaseModel):
    severity: str = "WARNING"
    quote: str = ""
    expected: str = ""
    basis: str = ""


class AuditPayload(BaseModel):
    critical_count: int = 0
    warning_count: int = 0
    issues: list[AuditIssue] = Field(default_factory=list)
    unverifiable: list[str] = Field(default_factory=list)


def build_messages(chapter, truth: dict, terminology: list[str], body: str) -> list[dict]:
    truth_text = "\n".join(f"- {k}：{v}" for k, v in truth.items() if v) or "（没有提炼到关键事实）"
    prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
        truth_base=truth_text,
        terminology="、".join(terminology) or "（无）",
        n=chapter.seq,
        body=body,
    )
    return [
        {"role": "system", "content": "你是严格按格式输出的助手，只输出 JSON。"},
        {"role": "user", "content": prompt},
    ]


# PRD 审计规则：「全局事实里没有、没法核对的数，不算错误，放进 unverifiable」。
# 模型偶尔会把这类判成 CRITICAL，程序按判决书自己的措辞再兜一层（确定性兜底）。
UNVERIFIABLE_HINTS = ("无法核对", "不能核对", "无法比对", "未给出", "未提供", "不能对应", "无对应", "无法验证")


# PRD 审计规则：「同一个数的不同写法（25,000 万元 = 2.5 亿元）不算问题」。
# 模型偶尔仍会把等价值报成问题，程序按「这句话里的数字是否都等于核定值」做确定性过滤。
_MONEY = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(亿元|亿|万元|万|元)")


def _money_values(text: str) -> set[float]:
    """把金额统一换算成「元」，便于比较 2.5 亿元 与 25,000 万元。"""
    values = set()
    for num, unit in _MONEY.findall(text or ""):
        try:
            n = float(num.replace(",", ""))
        except ValueError:
            continue
        factor = {"亿元": 1e8, "亿": 1e8, "万元": 1e4, "万": 1e4, "元": 1}[unit]
        values.add(round(n * factor, 2))
    return values


def drop_equivalent(issues: list[dict], truth: dict) -> list[dict]:
    """报错句里的金额全都等于核定值，说明是等价写法，不算问题。"""
    truth_values: set[float] = set()
    for value in (truth or {}).values():
        if value:
            truth_values |= _money_values(str(value))
    if not truth_values:
        return issues
    kept = []
    for issue in issues:
        quote_values = _money_values(issue.get("quote", ""))
        if quote_values and quote_values.issubset(truth_values):
            continue
        kept.append(issue)
    return kept


def demote_unverifiable(critical: list[dict], unverifiable: list[str]) -> tuple[list[dict], list[str]]:
    keep, moved = [], list(unverifiable)
    for issue in critical:
        text = f"{issue.get('expected', '')}{issue.get('basis', '')}"
        if any(hint in text for hint in UNVERIFIABLE_HINTS):
            quote = (issue.get("quote") or "").strip()
            if quote and quote not in moved:
                moved.append(quote)
            continue
        keep.append(issue)
    return keep, moved


def audit_chapter(llm: LLMService, report_id: str, chapter, truth: dict, terminology: list[str], body: str, recorder=None) -> dict:
    payload = llm.call_json("审计", build_messages(chapter, truth, terminology, body), AuditPayload, report_id, recorder)
    issues = [i.model_dump() for i in payload.issues]
    issues = drop_equivalent(issues, truth)
    # 程序再兜一层：以 issues 里的 severity 为准统计，避免模型前后数字对不上
    critical = [i for i in issues if str(i.get("severity", "")).upper() == "CRITICAL"]
    warning = [i for i in issues if str(i.get("severity", "")).upper() == "WARNING"]
    critical, unverifiable = demote_unverifiable(critical, payload.unverifiable)
    kept_quotes = {id(i) for i in critical}
    final_issues = [i for i in issues if str(i.get("severity", "")).upper() != "CRITICAL" or id(i) in kept_quotes]
    return {
        "critical_count": len(critical),
        "warning_count": len(warning),
        "issues": final_issues,
        "unverifiable": unverifiable,
        "has_critical": len(critical) > 0,
    }
