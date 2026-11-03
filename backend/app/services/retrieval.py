"""BM25 关键词检索（替代向量库，见技术适配声明 §4 第 2 条）。

资料量级：10 份文件、切段后几十到几百段，关键词 + 同义词表足够。
召回不够时的升级条件写在技术适配声明里。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, Segment

# 领域同义词：把常见写法归一到同一批检索词（补关键词检索召回弱的问题）
SYNONYMS: dict[str, list[str]] = {
    "总投资": ["总投资", "投资估算", "建设投资", "项目总投资", "投资额"],
    "资本金": ["资本金", "自有资金", "股权资金", "资本金比例"],
    "技术路线": ["技术路线", "制氢工艺", "电解水制氢", "PEM", "碱性", "工艺方案"],
    "电解槽": ["电解槽", "制氢规模", "产氢量", "年产氢", "电解水"],
    "电耗": ["直流电耗", "电耗", "kWh", "度电", "耗电"],
    "压力": ["加注压力", "储氢压力", "出口压力", "MPa", "压力等级"],
    "站点": ["加氢站", "制氢加氢一体站", "加注能力", "站点", "站址"],
    "占地": ["占地面积", "用地", "㎡", "亩", "土地"],
    "工期": ["建设期", "工期", "开工", "投运", "进度"],
    "成本": ["制氢成本", "氢价", "电价", "成本"],
    "财务": ["内部收益率", "IRR", "投资回收期", "回收期", "收益率", "财务"],
}

_STOP = set("的 了 和 与 及 在 是 为 对 中 上 下 个 这 那 有 无 等 并 或 从 到 以 按 由 被 把".split())


@dataclass
class RetrievedChunk:
    text: str
    source: str
    score: float

    def as_dict(self) -> dict:
        return {"source": self.source, "text": self.text, "score": round(self.score, 3)}


def _tokens(text: str) -> list[str]:
    words = []
    for w in jieba.cut(text):
        w = w.strip()
        if not w or w in _STOP:
            continue
        if len(w) == 1 and not re.match(r"[\u4e00-\u9fff]", w):
            continue
        words.append(w.lower())
    return words


def expand_query(query: str) -> str:
    extra: list[str] = []
    for key, words in SYNONYMS.items():
        if key in query:
            extra.extend(words)
    return query + " " + " ".join(extra)


class Retriever:
    """在内存里建一次索引，检索 top-k 段。只检索 status=available 的资料。"""

    def __init__(self, db: Session):
        rows = db.execute(
            select(Segment.text, Document.filename)
            .join(Document, Document.id == Segment.document_id)
            .where(Document.status == "available")
            .order_by(Document.created_at, Segment.seq)
        ).all()
        self.texts = [r[0] for r in rows]
        self.sources = [r[1] for r in rows]
        self._bm25 = BM25Okapi([_tokens(t) for t in self.texts]) if self.texts else None

    def top(self, query: str, k: int = 6) -> list[RetrievedChunk]:
        if not self._bm25 or not self.texts:
            return []
        scores = self._bm25.get_scores(_tokens(expand_query(query)))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        picked = [i for i in order if scores[i] > 0][:k]
        return [
            RetrievedChunk(text=self.texts[i], source=self.sources[i], score=float(scores[i]))
            for i in picked
        ]


def format_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "（没有检索到相关资料）"
    return "\n\n".join(f"【来源：{c.source}】\n{c.text}" for c in chunks)


def dedupe_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[str] = set()
    out: list[RetrievedChunk] = []
    for c in chunks:
        key = c.text.strip()[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out
