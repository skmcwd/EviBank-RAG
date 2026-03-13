from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class BaseDataModel(BaseModel):
    """
    统一的基础数据模型。

    说明：
    - extra="ignore"：忽略多余字段，提升兼容性
    - validate_assignment=True：赋值时继续校验，降低脏数据风险
    """

    model_config = ConfigDict(
        extra="ignore",
        validate_assignment=True,
        populate_by_name=True,
    )


class KBChunk(BaseDataModel):
    """
    知识库中的基础知识块。

    可用于承载从 Excel / PPT / DOCX 等文档切分后的 FAQ 条目或片段。
    所有字段均可直接进行 JSON 序列化。
    """

    doc_id: str = Field(default="", description="文档唯一标识")
    source_file: str = Field(default="", description="来源文件名或相对路径")
    source_type: str = Field(
        default="", description="来源类型，例如 excel / ppt / docx"
    )
    title: str = Field(default="", description="知识块标题")
    category: str | None = Field(default=None, description="业务分类，例如登录、UKey、转账")
    question: str | None = Field(default=None, description="标准问题或FAQ问题")
    answer: str | None = Field(default=None, description="标准答案或FAQ答案")
    full_text: str = Field(default="", description="完整文本内容，用于检索和展示")
    keywords: list[str] = Field(
        default_factory=list, description="关键词列表，用于召回增强或调试"
    )
    image_paths: list[str] = Field(
        default_factory=list, description="关联图片路径列表"
    )
    page_no: int | None = Field(default=None, description="若来源为文档，表示页码")
    slide_no: int | None = Field(default=None, description="若来源为PPT，表示页码/幻灯片号")
    priority: float = Field(default=1.0, description="来源优先级或业务优先级")
    chunk_hash: str = Field(default="", description="知识块内容哈希，用于去重和追踪")


class RetrievedChunk(KBChunk):
    """
    检索阶段返回的知识块。

    在 KBChunk 基础上增加检索与重排相关信息，便于调试、排序和前端展示。
    """

    retrieval_score: float = Field(default=0.0, description="最终综合检索分数")
    vector_score: float | None = Field(default=None, description="向量检索分数")
    bm25_score: float | None = Field(default=None, description="BM25 检索分数")
    rerank_reason: str | None = Field(
        default=None, description="重排原因或命中说明，用于调试和解释"
    )


class EvidenceItem(BaseDataModel):
    """
    前端展示的证据项。

    通常由 RetrievedChunk 映射而来，保留对用户可读且必要的信息。
    """

    doc_id: str = Field(default="", description="关联文档唯一标识")
    title: str = Field(default="", description="证据标题")
    source_file: str = Field(default="", description="来源文件名或路径")
    source_type: str = Field(default="", description="来源类型，例如 excel / ppt / docx")
    category: str | None = Field(default=None, description="证据所属业务分类")
    snippet: str = Field(default="", description="用于前端展示的证据摘要片段")
    quote: str | None = Field(default=None, description="高亮引用原文")
    page_no: int | None = Field(default=None, description="来源页码")
    slide_no: int | None = Field(default=None, description="来源幻灯片编号")
    score: float | None = Field(default=None, description="证据相关性分数")
    reason: str | None = Field(default=None, description="命中原因或排序说明")
    image_paths: list[str] = Field(
        default_factory=list, description="与该证据关联的图片路径"
    )


class ChatAnswer(BaseDataModel):
    """
    问答接口最终返回模型。

    answer_markdown:
        供前端主回答区直接渲染的 Markdown 文本。
    evidence_items:
        供前端证据区展示的证据列表。
    gallery_images:
        供前端图片画廊展示的图片列表，可来自多个证据项聚合。
    debug_info:
        调试信息，建议仅在开发环境返回。
    """

    answer_markdown: str = Field(default="", description="模型生成的 Markdown 答案")
    evidence_items: list[EvidenceItem] = Field(
        default_factory=list, description="证据列表"
    )
    gallery_images: list[str] = Field(
        default_factory=list, description="聚合后的图片路径列表"
    )
    debug_info: dict[str, Any] = Field(
        default_factory=dict, description="调试信息，如召回参数、耗时、分数明细等"
    )