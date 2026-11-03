"""正文标记计算（PRD F6）。

高亮区间全部由程序算，不信任模型返回的字符位置：
- `[待补充…]` 黄底：正则匹配全部出现位置；
- CRITICAL 点名的原句红底：用 quote 在正文里定位，找不到就记进 unlocated（页面上仍列出提示）。
"""

from __future__ import annotations

import re

MISSING_PATTERN = re.compile(r"\[待补充[^\]]*\]")


def resolve_source(basis: str, sources: dict | None = None) -> str:
    """把审计给的 basis（可能是字段名，也可能是一整句）映射到资料文件名。"""
    sources = sources or {}
    if not basis:
        return ""
    if basis in sources:
        return sources[basis]
    for field, filename in sources.items():
        if field and field in basis:
            return filename
    return ""


def build_marks(body: str, issues: list[dict], sources: dict | None = None) -> dict:
    """返回 {segments: [...], critical: [...], warnings: [...], unlocated: [...]}。"""
    body = body or ""
    sources = sources or {}
    spans: list[tuple[int, int, dict]] = []

    for m in MISSING_PATTERN.finditer(body):
        spans.append((m.start(), m.end(), {"type": "missing", "label": "待补充"}))

    critical, warnings, unlocated = [], [], []
    for issue in issues or []:
        severity = str(issue.get("severity", "")).upper()
        quote = (issue.get("quote") or "").strip()
        basis = issue.get("basis") or ""
        item = {
            "quote": quote,
            "expected": issue.get("expected", ""),
            "basis": basis,
            "source": resolve_source(basis, sources),
        }
        if severity == "CRITICAL":
            critical.append(item)
            pos = body.find(quote) if quote else -1
            if pos >= 0:
                tooltip = f"应为：{item['expected']}；依据：{item['source'] or '项目资料'}"
                spans.append(
                    (pos, pos + len(quote), {"type": "critical", "label": "CRITICAL", "tooltip": tooltip})
                )
            elif quote:
                unlocated.append(item)
        else:
            warnings.append(item)

    return {
        "segments": _render(body, spans),
        "critical": critical,
        "warnings": warnings,
        "unlocated": unlocated,
    }


def _render(text: str, spans: list[tuple[int, int, dict]]) -> list[dict]:
    """把区间套用成不重叠的分段（临界优先于待补充，重叠部分取先出现的）。"""
    if not spans:
        return [{"text": text, "marks": []}]

    order = {"critical": 0, "missing": 1}
    spans = sorted(spans, key=lambda s: (s[0], order.get(s[2]["type"], 9)))

    picked: list[tuple[int, int, dict]] = []
    for start, end, meta in spans:
        if start >= end:
            continue
        if picked and start < picked[-1][1]:
            continue  # 与已选区间重叠，跳过
        picked.append((start, end, meta))

    out, cursor = [], 0
    for start, end, meta in picked:
        if start > cursor:
            out.append({"text": text[cursor:start], "marks": []})
        out.append({"text": text[start:end], "marks": [meta]})
        cursor = end
    if cursor < len(text):
        out.append({"text": text[cursor:], "marks": []})
    return out


def collect_missing(chapters) -> list[dict]:
    """全文所有 [待补充]，按章聚合、同名去重（PRD F6 顶部汇总）。"""
    seen: dict[str, list[int]] = {}
    for ch in chapters:
        for name in ch.missing or []:
            key = str(name).strip()
            if not key:
                continue
            seen.setdefault(key, [])
            if ch.seq not in seen[key]:
                seen[key].append(ch.seq)
    return [{"name": k, "chapters": v} for k, v in seen.items()]
