"""配置：全部从环境变量 / backend/.env 读取，代码不硬编码模型名与密钥。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]          # .../backend
PRODUCT_DIR = BACKEND_DIR.parent                            # .../可研报告生成Agent
DATA_DIR = PRODUCT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
LOG_DIR = DATA_DIR / "logs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # 模型（D4/D7：只接 DeepSeek，OpenAI 兼容接口）
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    model_name: str = "deepseek-chat"
    model_timeout_seconds: int = 120
    model_max_retries: int = 3

    # 存储
    database_url: str = f"sqlite:///{DATA_DIR / 'app.db'}"
    upload_dir: str = str(UPLOAD_DIR)
    max_upload_mb: int = 100

    # 产品参数（PRD 第五节「参数默认值」）
    target_words_default: int = 12000
    target_words_min: int = 1000
    target_words_max: int = 18000
    outline_chapter_min: int = 8
    outline_chapter_max: int = 13
    chunk_chars: int = 800
    chunk_overlap: int = 100
    # 阶段 2-2：检索、重写、字数
    retrieve_chapter_segments: int = 6
    retrieve_fact_segments: int = 3
    rewrite_max: int = 2
    chapter_words_ratio: float = 1.1

    # 本版不做登录（D5）：全部数据固定归属
    owner_id: str = "local"

    port: int = 8010

    @property
    def has_key(self) -> bool:
        return bool(self.deepseek_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return settings
