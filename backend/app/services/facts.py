"""关键事实提炼（PRD 第四节「关键事实提炼」）。

每份报告只提炼一次，程序校验字段后存库，之后写章与审计都读这一份（评测 C09）。
"""

from __future__ import annotations

from pathlib import Path

from typing import Any

from pydantic import BaseModel, Field

from app.services.llm import LLMService
from app.services.retrieval import Retriever, dedupe_chunks, format_context

PROMPT_PATH = Path(__file__).parent / "prompts" / "extract_facts.md"

# PRD 第四节的 11 个固定字段（字段名, 含义）—— 字段名不得增删改名
FIELD_SPECS: list[tuple[str, str]] = [
    ("total_investment", "总投资及构成（建设投资、建设期利息、流动资金）"),
    ("capital_ratio", "资本金比例和金额、贷款安排"),
    ("technology_route", "制氢技术路线、电源"),
    ("electrolyzer_config", "电解槽台数和单台规模、合计制氢规模、年产氢量"),
    ("dc_power_consumption", "直流电耗"),
    ("pressure_level", "加氢站加注压力等级、站内储氢压力（电解槽出口压力不算）"),
    ("project_scope", "站点构成、各站加注能力、氢气运输方式"),
    ("site_area", "各站占地面积"),
    ("construction_period", "建设期、开工和投运时间"),
    ("hydrogen_cost", "制氢成本及对应电价"),
    ("financial", "内部收益率、投资回收期"),
]
FIELD_NAMES = [f[0] for f in FIELD_SPECS]


class FactsPayload(BaseModel):
    validated_data: dict[str, Any] = Field(default_factory=dict)
    sources: dict[str, Any] = Field(default_factory=dict)
    global_terminology: list[str] = Field(default_factory=list)


def build_fields_prompt() -> str:
    return "\n".join(f"- {name}：{desc}" for name, desc in FIELD_SPECS)


def build_context(retriever: Retriever, per_field: int = 3) -> str:
    chunks = []
    for name, desc in FIELD_SPECS:
        chunks.extend(retriever.top(f"{desc} {name}", k=per_field))
    return format_context(dedupe_chunks(chunks))


def normalize_facts(payload: FactsPayload) -> dict:
    """程序校验：多出的字段丢掉、缺的补 null、值不是字符串按 null、有值没来源记「未标注」。"""
    data: dict[str, str | None] = {}
    sources: dict[str, str] = {}
    for name in FIELD_NAMES:
        value = payload.validated_data.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = str(value)
        if isinstance(value, str) and value.strip():
            data[name] = value.strip()
            raw = payload.sources.get(name)
            sources[name] = str(raw).strip() if raw else "未标注"
        else:
            data[name] = None
    terminology = [t.strip() for t in payload.global_terminology if isinstance(t, str) and t.strip()][:10]
    return {"validated_data": data, "sources": sources, "terminology": terminology}


def extract_facts(
    llm: LLMService,
    report_id: str,
    title: str,
    retriever: Retriever,
    per_field: int = 3,
    recorder=None,
) -> dict:
    prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
        title=title,
        fields=build_fields_prompt(),
        context=build_context(retriever, per_field),
    )
    messages = [
        {"role": "system", "content": "你是严格按格式输出的助手，只输出 JSON。"},
        {"role": "user", "content": prompt},
    ]
    payload = llm.call_json("提炼关键事实", messages, FactsPayload, report_id, recorder)
    return normalize_facts(payload)
