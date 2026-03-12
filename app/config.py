from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfigError(RuntimeError):
    """应用配置加载异常。"""


class EnvSettings(BaseSettings):
    """
    从 .env / 环境变量读取的配置。
    这些配置主要用于 API 鉴权、模型选择和运行环境标识。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    dashscope_api_key: str = Field(..., alias="DASHSCOPE_API_KEY")
    dashscope_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        alias="DASHSCOPE_BASE_URL",
    )
    llm_model: str = Field(default="qwen3.5-flash", alias="LLM_MODEL")
    embed_model: str = Field(default="text-embedding-v4", alias="EMBED_MODEL")
    app_env: str = Field(default="development", alias="APP_ENV")


class RetrievalConfig(BaseModel):
    """检索相关参数。"""

    vector_top_k: int = Field(default=8, ge=1)
    bm25_top_k: int = Field(default=8, ge=1)
    final_context_k: int = Field(default=6, ge=1)


class RerankConfig(BaseModel):
    """重排相关参数。"""

    vector_weight: float = Field(default=0.55, ge=0.0)
    bm25_weight: float = Field(default=0.45, ge=0.0)
    exact_match_boost: float = Field(default=0.2, ge=0.0)
    category_boost: float = Field(default=0.15, ge=0.0)
    priority_boost: float = Field(default=0.1, ge=0.0)


class UIConfig(BaseModel):
    """前端展示相关配置。"""

    app_title: str = "企业网银 FAQ RAG Demo"
    app_subtitle: str = "基于阿里云百炼 OpenAI 兼容接口的企业网银智能问答演示"
    example_questions: list[str] = Field(default_factory=list)


class SourcePriorityConfig(BaseModel):
    """不同来源文档的优先级。"""

    excel: float = 1.0
    ppt: float = 0.95
    docx: float = 1.1


class PathConfig(BaseModel):
    """
    项目路径配置。
    使用 pathlib.Path，兼容 Windows / Linux / macOS。
    """

    project_root: Path
    app_dir: Path
    config_dir: Path
    data_dir: Path
    raw_data_dir: Path
    processed_data_dir: Path
    vector_store_dir: Path
    cache_dir: Path
    logs_dir: Path
    settings_file: Path
    env_file: Path


class APIConfig(BaseModel):
    """API 调用配置。"""

    api_key: str
    base_url: str


class ModelConfig(BaseModel):
    """模型名称配置。"""

    llm_model: str
    embed_model: str


class Settings(BaseModel):
    """
    应用总配置：
    - API 配置
    - 模型名
    - 路径配置
    - 检索/重排参数
    - UI 配置
    - 其他业务辅助配置
    """

    app_env: str
    api: APIConfig
    models: ModelConfig
    paths: PathConfig
    retrieval: RetrievalConfig
    rerank: RerankConfig
    ui: UIConfig
    source_priority: SourcePriorityConfig
    categories: list[str] = Field(default_factory=list)

    @property
    def openai_api_key(self) -> str:
        """为 OpenAI 兼容客户端保留的便捷访问属性。"""
        return self.api.api_key

    @property
    def openai_base_url(self) -> str:
        """为 OpenAI 兼容客户端保留的便捷访问属性。"""
        return self.api.base_url


def _build_paths(project_root: Path) -> PathConfig:
    """构建项目内常用路径。"""
    app_dir = project_root / "app"
    config_dir = project_root / "config"
    data_dir = project_root / "data"

    return PathConfig(
        project_root=project_root,
        app_dir=app_dir,
        config_dir=config_dir,
        data_dir=data_dir,
        raw_data_dir=data_dir / "raw",
        processed_data_dir=data_dir / "processed",
        vector_store_dir=data_dir / "vector_store",
        cache_dir=project_root / ".cache",
        logs_dir=project_root / "logs",
        settings_file=config_dir / "settings.yaml",
        env_file=project_root / ".env",
    )


def _load_yaml_config(settings_file: Path) -> dict[str, Any]:
    """
    读取 YAML 配置文件。
    返回 dict，若文件缺失或格式非法则抛出 AppConfigError。
    """
    if not settings_file.exists():
        raise AppConfigError(
            f"未找到 YAML 配置文件: {settings_file}. "
            f"请确认 config/settings.yaml 已创建。"
        )

    try:
        content = settings_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise AppConfigError(f"读取配置文件失败: {settings_file}") from exc

    try:
        data = yaml.safe_load(content) or {}
    except yaml.YAMLError as exc:
        raise AppConfigError(f"YAML 解析失败: {settings_file}") from exc

    if not isinstance(data, dict):
        raise AppConfigError(
            f"YAML 顶层结构必须为对象映射(dict)，实际类型为: {type(data).__name__}"
        )

    return data


def _ensure_directories(paths: PathConfig) -> None:
    """
    创建运行时必要目录。
    不强制创建 raw_data_dir，因为有些场景希望由用户自行管理原始资料目录。
    """
    required_dirs = [
        paths.config_dir,
        paths.data_dir,
        paths.processed_data_dir,
        paths.vector_store_dir,
        paths.cache_dir,
        paths.logs_dir,
    ]

    for directory in required_dirs:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AppConfigError(f"创建目录失败: {directory}") from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    单例方式加载配置，避免重复读取 .env 与 YAML 文件。
    适合在整个应用生命周期中反复调用。
    """
    project_root = Path(__file__).resolve().parent.parent
    paths = _build_paths(project_root)

    try:
        env = EnvSettings()
    except ValidationError as exc:
        raise AppConfigError(
            "环境变量加载失败，请检查 .env 文件或系统环境变量。"
        ) from exc

    yaml_data = _load_yaml_config(paths.settings_file)

    try:
        retrieval = RetrievalConfig.model_validate(yaml_data.get("retrieval", {}))
        rerank = RerankConfig.model_validate(yaml_data.get("rerank", {}))
        ui = UIConfig.model_validate(yaml_data.get("ui", {}))
        source_priority = SourcePriorityConfig.model_validate(
            yaml_data.get("source_priority", {})
        )
    except ValidationError as exc:
        raise AppConfigError("settings.yaml 字段校验失败，请检查配置项类型和值范围。") from exc

    categories = yaml_data.get("categories", [])
    if categories is None:
        categories = []
    if not isinstance(categories, list) or not all(
            isinstance(item, str) for item in categories
    ):
        raise AppConfigError("settings.yaml 中的 categories 必须是字符串列表。")

    _ensure_directories(paths)

    return Settings(
        app_env=env.app_env,
        api=APIConfig(
            api_key=env.dashscope_api_key,
            base_url=env.dashscope_base_url,
        ),
        models=ModelConfig(
            llm_model=env.llm_model,
            embed_model=env.embed_model,
        ),
        paths=paths,
        retrieval=retrieval,
        rerank=rerank,
        ui=ui,
        source_priority=source_priority,
        categories=categories,
    )
