"""DeepSeek 调用封装：OpenAI 兼容接口 + JSON 模式 + 有限重试 + 结构校验 + 调用日志。

底线要求（AGENTS.md 第 2 节第 3、4 条）：
- 模型输出必须结构校验（Pydantic），失败按调用失败处理、有限重试；
- 超时 / 报错 / SDK 初始化失败都要兜底，转成统一错误结构；
- 日志不记密钥；完整输入输出只落本地 data/logs（data/ 已 gitignore）。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.config import LOG_DIR, Settings, get_settings
from app.core.errors import AppError

logger = logging.getLogger("app.llm")

ChatFn = Callable[[list[dict], bool], tuple[str, dict, str | None]]


class LLMService:
    """一次调用最多重试 MODEL_MAX_RETRIES 次（默认 3），间隔 2s / 4s / 8s 递增。"""

    def __init__(
        self,
        settings: Settings | None = None,
        chat_fn: ChatFn | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings or get_settings()
        self._chat_fn = chat_fn
        self._sleep = sleep_fn
        self._client = None

    # ---------- 底层：构造客户端（这里可能失败：无 Key / 网络不可达） ----------
    def _client_or_error(self):
        if self._client is not None:
            return self._client
        if not self.settings.has_key:
            raise AppError(
                "MODEL_NOT_CONFIGURED",
                "还没有配置 DeepSeek API Key：把它填进 backend/.env 的 DEEPSEEK_API_KEY 后重启服务",
                status_code=502,
            )
        try:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
                timeout=self.settings.model_timeout_seconds,
                max_retries=0,  # 重试由本类统一控制，避免双重放大
            )
        except Exception as exc:  # SDK 初始化失败
            raise AppError(
                "MODEL_INIT_FAILED",
                "模型客户端初始化失败，请检查网络或稍后重试",
                status_code=502,
            ) from exc
        return self._client

    def _default_chat(self, messages: list[dict], want_json: bool) -> tuple[str, dict, str | None]:
        client = self._client_or_error()
        kwargs: dict[str, Any] = {
            "model": self.settings.model_name,
            "messages": messages,
            "temperature": 0.3,
        }
        if want_json:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        usage = {
            "input_tokens": getattr(resp.usage, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(resp.usage, "completion_tokens", 0) or 0,
        }
        return choice.message.content or "", usage, getattr(resp, "id", None)

    # ---------- 日志 ----------
    def _write_jsonl(self, record: dict) -> None:
        import os

        if os.environ.get("PYTEST_CURRENT_TEST"):
            return
        try:
            path = Path(LOG_DIR) / "model_calls.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:  # 日志失败不影响主流程
            logger.warning("写模型调用日志失败", exc_info=True)

    # ---------- 对外：结构化调用 ----------
    def call_json(
        self,
        step: str,
        messages: list[dict],
        model_cls: type[BaseModel],
        report_id: str | None = None,
        recorder: Callable[[dict], None] | None = None,
    ) -> BaseModel:
        chat = self._chat_fn or self._default_chat
        attempts = max(1, self.settings.model_max_retries)
        last_error: str = ""

        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            content = ""
            usage: dict = {}
            request_id: str | None = None
            ok = False
            error_type: str | None = None
            parsed: Any = None
            try:
                content, usage, request_id = chat(messages, True)
                parsed = _parse_json(content)
                validated = model_cls.model_validate(parsed)
                ok = True
            except AppError:
                raise
            except ValidationError as exc:
                error_type = "SCHEMA_INVALID"
                last_error = f"字段不符合要求：{exc.errors()[0].get('msg', '')}"
            except json.JSONDecodeError:
                error_type = "JSON_INVALID"
                last_error = "模型返回的不是合法 JSON"
            except Exception as exc:  # 网络、超时、限流……
                error_type = type(exc).__name__
                last_error = f"{type(exc).__name__}：{str(exc)[:200]}"
            latency_ms = int((time.monotonic() - started) * 1000)

            record = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "step": step,
                "report_id": report_id,
                "attempt": attempt,
                "ok": ok,
                "error_type": error_type,
                "request_id": request_id,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "latency_ms": latency_ms,
                "messages": messages,
                "raw_output": content,
            }
            self._write_jsonl(record)
            if recorder is not None:
                try:
                    recorder(record)
                except Exception:
                    logger.warning("记录模型调用元数据失败", exc_info=True)

            if ok:
                return validated  # type: ignore[return-value]

            logger.warning("模型调用失败 step=%s attempt=%s err=%s", step, attempt, error_type)
            if attempt < attempts:
                self._sleep(min(2 ** attempt, 8))

        raise AppError(
            "MODEL_FAILED",
            f"模型调用失败（已重试 {attempts} 次）：{last_error}",
            status_code=502,
        )


def _parse_json(content: str) -> Any:
    """宽容解析：直接 loads → 剥 ```json 代码块 → 取第一个 {...} → json-repair 修复。

    实测 DeepSeek 偶尔会在正文里写未转义的英文引号（如 "光伏—制氢—加氢"），
    直接 loads 失败。这类属于格式瑕疵，用确定性修复比"重试 3 次烧钱"更划算
    （通用手册第九节之 3「解析器要宽容」）。
    """
    text = (content or "").strip()
    if not text:
        raise json.JSONDecodeError("empty", text, 0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if "```" in text:
        block = text.split("```")[1]
        block = block[4:] if block.lower().startswith("json") else block
        return json.loads(block.strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    try:
        from json_repair import repair_json

        repaired = repair_json(text, return_objects=True)
        if isinstance(repaired, dict):
            return repaired
    except Exception:  # 修复失败就按原样报错
        pass
    raise json.JSONDecodeError("no json object", text, 0)
