"""接口测试：资料上传、报告创建、大纲生成/编辑/保存（全部用假模型）。"""

from __future__ import annotations

import io

from sqlalchemy import func, select

from app.models import Document, ModelCall, Segment
from app.services.llm import LLMService
from tests.conftest import OUTLINE_JSON, FakeLLM

TXT = "攀枝花市钒钛高新区制氢加氢一体化示范项目（一期）总投资 25,000 万元。".encode("utf-8")


def _upload(client, filename="资料.txt", content: bytes = TXT, mime="text/plain"):
    return client.post(
        "/api/documents",
        files=[("files", (filename, io.BytesIO(content), mime))],
    )


# ---------------- 资料 ----------------
def test_upload_txt_available(client, db):
    resp = _upload(client())
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["status"] == "available"
    assert item["segments_count"] == 1
    assert db.scalar(select(func.count()).select_from(Segment)) == 1


def test_upload_multiple_files(client, db):
    c = client()
    resp = c.post(
        "/api/documents",
        files=[
            ("files", ("一.txt", io.BytesIO(TXT), "text/plain")),
            ("files", ("二.md", io.BytesIO("# 标题\n\n正文内容".encode()), "text/markdown")),
        ],
    )
    items = resp.json()["items"]
    assert [i["status"] for i in items] == ["available", "available"]
    assert db.scalar(select(func.count()).select_from(Document)) == 2


def test_upload_unsupported_format_is_item_failure(client):
    resp = _upload(client(), filename="报告.doc")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["status"] == "failed"
    assert item["code"] == "UNSUPPORTED_FORMAT"
    assert "不支持" in item["error"]


def test_upload_fake_pdf_is_rejected(client):
    """把 PNG 改名成 .pdf，真实类型校验要拦住。"""
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    resp = _upload(client(), filename="假资料.pdf", content=png, mime="application/pdf")
    item = resp.json()["items"][0]
    assert item["status"] == "failed"
    assert item["code"] == "UNSUPPORTED_FORMAT"


def test_upload_empty_file(client):
    resp = _upload(client(), content=b"")
    item = resp.json()["items"][0]
    assert item["status"] == "failed"
    assert item["code"] == "EMPTY_FILE"


def test_upload_filename_sanitized(client, db):
    resp = _upload(client(), filename="../../evil.txt")
    item = resp.json()["items"][0]
    assert item["status"] == "available"
    assert item["filename"] == "evil.txt"
    stored = db.scalar(select(Document)).stored_path
    assert ".." not in stored


def test_upload_scan_pdf_marked_no_text(client):
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    resp = _upload(client(), filename="扫描件.pdf", content=buffer.getvalue(), mime="application/pdf")
    item = resp.json()["items"][0]
    assert item["status"] == "no_text"
    assert item["segments_count"] == 0


def test_delete_document_removes_segments(client, db):
    c = client()
    doc_id = _upload(c).json()["items"][0]["id"]
    assert db.scalar(select(func.count()).select_from(Segment)) == 1
    assert c.delete(f"/api/documents/{doc_id}").json() == {"deleted": True}
    assert db.scalar(select(func.count()).select_from(Segment)) == 0
    assert c.delete(f"/api/documents/{doc_id}").status_code == 404


# ---------------- 报告 ----------------
def test_create_report_defaults(client):
    resp = client().post("/api/reports", json={"title": "攀枝花氢能一期可研"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_words"] == 12000
    assert body["status"] == "draft"


def test_create_report_rejects_over_18000(client):
    resp = client().post("/api/reports", json={"title": "超限报告", "target_words": 19000})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_TARGET_WORDS"


def test_create_report_blank_title(client):
    resp = client().post("/api/reports", json={"title": "   "})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"


def test_create_report_requirements_too_long(client):
    resp = client().post("/api/reports", json={"title": "长要求", "extra_requirements": "字" * 2001})
    assert resp.status_code == 422


def test_report_list_shows_status(client):
    c = client()
    c.post("/api/reports", json={"title": "报告A"})
    items = c.get("/api/reports").json()["items"]
    assert items[0]["title"] == "报告A"
    assert items[0]["status"] == "draft"
    assert items[0]["chapters_count"] == 0


# ---------------- 大纲 ----------------
def _prepare(client, llm=None, title="攀枝花氢能一期", words=12000):
    c = client(llm)
    _upload(c)
    report_id = c.post("/api/reports", json={"title": title, "target_words": words}).json()["id"]
    return c, report_id


def test_generate_outline_success_and_words_balanced(client, db):
    c, report_id = _prepare(client)
    resp = c.post(f"/api/reports/{report_id}/outline")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["chapters"]) == 10
    assert sum(ch["suggested_words"] for ch in body["chapters"]) == 12000
    assert body["status"] == "outline_ready"
    assert [ch["seq"] for ch in body["chapters"]] == list(range(1, 11))

    calls = db.scalars(select(ModelCall)).all()
    assert len(calls) == 1
    assert calls[0].ok is True
    assert calls[0].step == "生成大纲"


def test_generate_outline_requires_documents(client):
    c = client()
    report_id = c.post("/api/reports", json={"title": "空资料库"}).json()["id"]
    resp = c.post(f"/api/reports/{report_id}/outline")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "NO_DOCUMENTS"


def test_generate_outline_retries_on_bad_json(client, db):
    fake = FakeLLM(["这不是 JSON", "还是不是", "依然不是"])
    c, report_id = _prepare(client, fake.service())
    resp = c.post(f"/api/reports/{report_id}/outline")
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "OUTLINE_INVALID"
    assert fake.calls == 3
    assert db.scalar(select(func.count()).select_from(ModelCall)) == 3


def test_generate_outline_recovers_after_retry(client):
    fake = FakeLLM(["bad", OUTLINE_JSON])
    c, report_id = _prepare(client, fake.service())
    resp = c.post(f"/api/reports/{report_id}/outline")
    assert resp.status_code == 200
    assert fake.calls == 2


def test_generate_outline_regenerates_when_chapter_count_invalid(client, db):
    from tests.conftest import OUTLINE_JSON as good

    short = '{"full_outline": [{"chapter_id":1,"title":"只有一章","key_points":["a"],"data_needed":["b"],"suggested_words":12000}]}'
    fake = FakeLLM([short, good])
    c, report_id = _prepare(client, fake.service())
    resp = c.post(f"/api/reports/{report_id}/outline")
    body = resp.json()
    assert fake.calls == 2
    assert len(body["chapters"]) == 10


def test_generate_outline_missing_fields_is_502(client):
    fake = FakeLLM(['{"full_outline": [{"title": ""}]}'])
    c, report_id = _prepare(client, fake.service())
    resp = c.post(f"/api/reports/{report_id}/outline")
    assert resp.status_code == 502


def test_outline_warns_when_numbers_in_points(client):
    with_numbers = OUTLINE_JSON.replace('"总投资"', '"总投资 2.5 亿元"')
    c, report_id = _prepare(client, FakeLLM([with_numbers]).service())
    body = c.post(f"/api/reports/{report_id}/outline").json()
    assert any("具体数值" in w for w in body["warnings"])


def test_save_outline_edits(client):
    c, report_id = _prepare(client)
    body = c.post(f"/api/reports/{report_id}/outline").json()
    chapters = body["chapters"]
    chapters[0]["title"] = "概述（改）"
    chapters.append(
        {"title": "新增一章：结论补充", "key_points": ["补充"], "data_needed": ["补充数据"], "suggested_words": 500}
    )
    resp = c.put(f"/api/reports/{report_id}/outline", json={"chapters": chapters})
    assert resp.status_code == 200
    saved = resp.json()["chapters"]
    assert saved[0]["title"] == "概述（改）"
    assert len(saved) == 11
    assert [ch["seq"] for ch in saved] == list(range(1, 12))


def test_save_outline_rejects_too_long(client):
    c, report_id = _prepare(client)
    body = c.post(f"/api/reports/{report_id}/outline").json()
    chapters = body["chapters"]
    chapters[0]["suggested_words"] = 18001
    resp = c.put(f"/api/reports/{report_id}/outline", json={"chapters": chapters})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OUTLINE_TOO_LONG"
    assert "2 万字" in resp.json()["error"]["message"]


def test_confirm_outline_starts_writing(client):
    """阶段 2-2 起「确认大纲并写全文」真正启动任务（阶段 2-1 时是 501）。"""
    c, report_id = _prepare(client)
    c.post(f"/api/reports/{report_id}/outline")
    resp = c.post(f"/api/reports/{report_id}/outline/confirm")
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_id"] == report_id
    assert body["status"] in ("pending", "running", "succeeded")


def test_progress_endpoint_shape(client):
    c, report_id = _prepare(client)
    c.post(f"/api/reports/{report_id}/outline")
    body = c.get(f"/api/reports/{report_id}/progress").json()
    assert body["report_id"] == report_id
    assert len(body["chapters"]) == 10
    assert set(body["summary"]) == {"done", "manual", "failed", "words_total"}


def test_write_requires_outline(client):
    c = client()
    rid = c.post("/api/reports", json={"title": "没大纲"}).json()["id"]
    resp = c.post(f"/api/reports/{rid}/write")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "NO_OUTLINE"


def test_health_reports_no_key_leak(client):
    body = client().get("/api/health").json()
    assert body["status"] == "ok"
    assert isinstance(body["has_key"], bool)
    assert set(body) == {"status", "model", "has_key", "stage"}
    assert "fake-for-test" not in str(body)


def test_llm_raises_when_no_key(monkeypatch):
    from app.core.config import Settings
    from app.core.errors import AppError

    settings = Settings(deepseek_api_key="", model_max_retries=1)
    service = LLMService(settings=settings, sleep_fn=lambda _s: None)
    try:
        service.call_json("生成大纲", [{"role": "user", "content": "hi"}], __import__("app.schemas.api", fromlist=["x"]).OutlinePayloadModel)
    except AppError as exc:
        assert exc.code == "MODEL_NOT_CONFIGURED"
    else:  # pragma: no cover
        raise AssertionError("没有 Key 时必须报 MODEL_NOT_CONFIGURED")
