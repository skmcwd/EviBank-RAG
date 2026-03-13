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
    """检索参数配置。"""

    vector_top_k: int = Field(default=8, ge=1, description="向量召回候选数")
    bm25_top_k: int = Field(default=8, ge=1, description="BM25 召回候选数")
    final_context_k: int = Field(default=6, ge=1, description="最终送入上下文的条数")


class RerankConfig(BaseModel):
    """重排参数配置。"""

    vector_weight: float = Field(default=0.55, ge=0.0, description="向量分数权重")
    bm25_weight: float = Field(default=0.45, ge=0.0, description="BM25 分数权重")
    exact_match_boost: float = Field(default=0.2, ge=0.0, description="精确匹配加权")
    category_boost: float = Field(default=0.15, ge=0.0, description="类别命中加权")
    priority_boost: float = Field(default=0.1, ge=0.0, description="来源优先级加权")


class UIConfig(BaseModel):
    """前端展示配置。"""

    app_title: str = Field(default="企业网银 FAQ RAG Demo", description="应用标题")
    app_subtitle: str = Field(
        default="基于阿里云百炼 OpenAI 兼容接口的企业网银智能问答演示",
        description="应用副标题",
    )
    example_questions: list[str] = Field(
        default_factory=list,
        description="示例问题列表",
    )


class SourcePriorityConfig(BaseModel):
    """不同来源类型的默认优先级。"""

    excel: float = Field(default=1.0, ge=0.0)
    ppt: float = Field(default=0.95, ge=0.0)
    docx: float = Field(default=1.1, ge=0.0)


class APIConfig(BaseModel):
    """外部 API 配置。"""

    api_key: str = Field(..., description="阿里云百炼 API Key")
    base_url: str = Field(..., description="阿里云百炼 OpenAI 兼容接口 Base URL")


class ModelConfig(BaseModel):
    """模型配置。"""

    llm_model: str = Field(default="qwen3.5-flash", description="问答模型名称")
    embed_model: str = Field(default="text-embedding-v4", description="Embedding 模型名称")


class PathConfig(BaseModel):
    """
    项目路径配置。
    所有路径统一使用 pathlib.Path，兼容 Windows。
    """

    project_root: Path
    app_dir: Path
    clients_dir: Path
    retrieval_dir: Path
    services_dir: Path
    ui_dir: Path
    scripts_dir: Path

    config_dir: Path
    settings_file: Path
    synonyms_file: Path
    env_file: Path

    data_dir: Path
    raw_dir: Path
    parsed_dir: Path
    parsed_images_dir: Path
    manifests_dir: Path

    index_dir: Path
    chroma_db_dir: Path
    bm25_dir: Path

    cache_dir: Path
    logs_dir: Path


class Settings(BaseModel):
    """
    应用总配置。
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
        """OpenAI 兼容客户端访问 API Key 的便捷属性。"""
        return self.api.api_key

    @property
    def openai_base_url(self) -> str:
        """OpenAI 兼容客户端访问 Base URL 的便捷属性。"""
        return self.api.base_url


def _project_root() -> Path:
    """
    获取项目根目录：
    ebank_rag_demo/
    └─ app/
       └─ config.py
    """
    return Path(__file__).resolve().parent.parent


def _build_paths(project_root: Path) -> PathConfig:
    """
    构建项目路径对象。
    """
    app_dir = project_root / "app"
    config_dir = project_root / "config"
    data_dir = project_root / "data"

    parsed_dir = data_dir / "parsed"
    index_dir = data_dir / "index"

    return PathConfig(
        project_root=project_root,
        app_dir=app_dir,
        clients_dir=app_dir / "clients",
        retrieval_dir=app_dir / "retrieval",
        services_dir=app_dir / "services",
        ui_dir=app_dir / "ui",
        scripts_dir=project_root / "scripts",
        config_dir=config_dir,
        settings_file=config_dir / "settings.yaml",
        synonyms_file=config_dir / "synonyms.json",
        env_file=project_root / ".env",
        data_dir=data_dir,
        raw_dir=data_dir / "raw",
        parsed_dir=parsed_dir,
        parsed_images_dir=parsed_dir / "images",
        manifests_dir=parsed_dir / "manifests",
        index_dir=index_dir,
        chroma_db_dir=index_dir / "chroma_db",
        bm25_dir=index_dir / "bm25",
        cache_dir=project_root / ".cache",
        logs_dir=project_root / "logs",
    )


def _ensure_directories(paths: PathConfig) -> None:
    """
    创建运行期必要目录。
    不会创建具体文件，只保证目录结构存在。
    """
    required_dirs = [
        paths.config_dir,
        paths.data_dir,
        paths.raw_dir,
        paths.parsed_dir,
        paths.parsed_images_dir,
        paths.manifests_dir,
        paths.index_dir,
        paths.chroma_db_dir,
        paths.bm25_dir,
        paths.cache_dir,
        paths.logs_dir,
    ]

    for directory in required_dirs:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AppConfigError(f"创建目录失败：{directory}") from exc


def _load_yaml_config(settings_file: Path) -> dict[str, Any]:
    """
    读取 YAML 配置文件。
    """
    if not settings_file.exists():
        raise AppConfigError(
            f"未找到配置文件：{settings_file}。请确认 config/settings.yaml 已创建。"
        )
    if not settings_file.is_file():
        raise AppConfigError(f"配置路径不是文件：{settings_file}")

    try:
        content = settings_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise AppConfigError(f"读取配置文件失败：{settings_file}") from exc

    try:
        data = yaml.safe_load(content) or {}
    except yaml.YAMLError as exc:
        raise AppConfigError(f"YAML 解析失败：{settings_file}") from exc

    if not isinstance(data, dict):
        raise AppConfigError(
            f"YAML 顶层结构必须是对象映射(dict)，实际为：{type(data).__name__}"
        )

    return data


def _validate_categories(value: Any) -> list[str]:
    """
    校验并清洗分类列表。
    """
    if value is None:
        return []

    if not isinstance(value, list):
        raise AppConfigError("settings.yaml 中的 categories 必须是字符串列表。")

    categories: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise AppConfigError("settings.yaml 中的 categories 必须全部为字符串。")
        text = " ".join(item.replace("\u3000", " ").split()).strip()
        if text:
            categories.append(text)

    return categories


def _load_env_settings(paths: PathConfig) -> EnvSettings:
    """
    加载 .env / 环境变量配置。
    """
    try:
        return EnvSettings(
            _env_file=paths.env_file,
            _env_file_encoding="utf-8",
        )
    except ValidationError as exc:
        raise AppConfigError(
            "环境变量加载失败，请检查 .env 中是否已配置 "
            "DASHSCOPE_API_KEY、DASHSCOPE_BASE_URL、LLM_MODEL、EMBED_MODEL、APP_ENV。"
        ) from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    单例方式加载应用配置，避免重复读取 .env 与 YAML。

    返回：
        Settings: 已完成校验的配置对象
    """
    project_root = _project_root()
    paths = _build_paths(project_root)

    _ensure_directories(paths)

    env = _load_env_settings(paths)
    yaml_data = _load_yaml_config(paths.settings_file)

    try:
        retrieval = RetrievalConfig.model_validate(yaml_data.get("retrieval", {}))
        rerank = RerankConfig.model_validate(yaml_data.get("rerank", {}))
        ui = UIConfig.model_validate(yaml_data.get("ui", {}))
        source_priority = SourcePriorityConfig.model_validate(
            yaml_data.get("source_priority", {})
        )
    except ValidationError as exc:
        raise AppConfigError(
            "settings.yaml 字段校验失败，请检查 retrieval / rerank / ui / source_priority 配置。"
        ) from exc

    categories = _validate_categories(yaml_data.get("categories", []))

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