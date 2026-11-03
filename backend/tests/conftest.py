"""测试基座：临时数据库 + 假模型（不花一分钱、离线可跑）。"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

TMP_DIR = Path(tempfile.mkdtemp(prefix="kyan-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{TMP_DIR / 'test.db'}"
os.environ["UPLOAD_DIR"] = str(TMP_DIR / "uploads")
os.environ["DEEPSEEK_API_KEY"] = "fake-for-test"          # 短字符串，避免被密钥扫描误判
os.environ["MODEL_MAX_RETRIES"] = "3"
os.environ["MAX_UPLOAD_MB"] = "100"
(TMP_DIR / "uploads").mkdir(parents=True, exist_ok=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_llm  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.llm import LLMService  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    for item in (TMP_DIR / "uploads").glob("*"):
        item.unlink()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class FakeLLM:
    """按脚本返回内容的假模型：responses 里每个元素可以是字符串或异常。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def chat_fn(self, messages, want_json):
        self.calls += 1
        item = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item, {"input_tokens": 100, "output_tokens": 50}, "req_fake"

    def service(self) -> LLMService:
        return LLMService(chat_fn=self.chat_fn, sleep_fn=lambda _s: None)


@pytest.fixture()
def client(db):
    def _client(llm: LLMService | None = None) -> TestClient:
        app.dependency_overrides[get_llm] = lambda: (llm or FakeLLM([OUTLINE_JSON]).service())
        return TestClient(app)

    yield _client
    app.dependency_overrides.clear()


OUTLINE_JSON = """
{"full_outline": [
 {"chapter_id": 1, "title": "概述", "key_points": ["项目概况", "主要结论"], "data_needed": ["总投资", "建设期"], "suggested_words": 1000},
 {"chapter_id": 2, "title": "项目建设背景和必要性", "key_points": ["政策符合性", "必要性"], "data_needed": ["氢气需求"], "suggested_words": 900},
 {"chapter_id": 3, "title": "项目需求分析和产出方案", "key_points": ["需求分析", "产出方案"], "data_needed": ["年产氢量"], "suggested_words": 900},
 {"chapter_id": 4, "title": "项目选址与要素保障", "key_points": ["选址比选", "要素保障"], "data_needed": ["占地面积"], "suggested_words": 1200},
 {"chapter_id": 5, "title": "项目建设方案", "key_points": ["技术路线", "设备配置"], "data_needed": ["电解槽配置", "加注压力等级"], "suggested_words": 1500},
 {"chapter_id": 6, "title": "项目运营方案", "key_points": ["运营模式", "安全保障"], "data_needed": ["氢气运输方式"], "suggested_words": 1200},
 {"chapter_id": 7, "title": "项目投融资与财务方案", "key_points": ["投资估算", "财务分析"], "data_needed": ["内部收益率", "投资回收期"], "suggested_words": 1500},
 {"chapter_id": 8, "title": "项目影响效果分析", "key_points": ["经济影响", "环境影响"], "data_needed": ["碳排放"], "suggested_words": 1200},
 {"chapter_id": 9, "title": "项目风险管控方案", "key_points": ["风险识别", "管控措施"], "data_needed": ["风险等级"], "suggested_words": 900},
 {"chapter_id": 10, "title": "研究结论及建议", "key_points": ["结论", "建议"], "data_needed": ["主要结论"], "suggested_words": 800}
]}
"""


def pytest_sessionfinish(session, exitstatus):  # pragma: no cover - 清理临时目录
    shutil.rmtree(TMP_DIR, ignore_errors=True)
