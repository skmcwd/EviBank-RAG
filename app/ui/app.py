from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any, Generator

import gradio as gr
import pandas as pd

from app.config import get_settings
from app.logging_utils import setup_logging
from app.models import ChatAnswer, EvidenceItem
from app.services.chat_service import ChatService

setup_logging("INFO")
logger = logging.getLogger(__name__)

# PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
from app.runtime import get_runtime_root
PROJECT_ROOT = get_runtime_root()

# GitHub 仓库配置
GITHUB_REPO_URL = "https://github.com/skmcwd/EviBank-RAG"
GITHUB_REPO_NAME = "evibank-rag"
PROJECT_BRAND_NAME = "EviBank-RAG"

EXECUTOR = ThreadPoolExecutor(max_workers=4)

CUSTOM_CSS = r"""
/* =========================================
   1. Theme Variables (Modern & Unified)
   ========================================= */
:root,
.light,
[data-theme="light"] {
  --ebank-primary: #005bac;
  --ebank-primary-hover: #004b8e;
  --ebank-accent: #003f7a;
  --ebank-bg: #f4f7fa;
  --ebank-bg-soft: #f0f4f8;
  --ebank-card: #ffffff;
  --ebank-card-2: #fcfdfe;
  --ebank-border: #e2e8f0;
  --ebank-border-strong: #cbd5e1;
  --ebank-text: #1e293b;
  --ebank-text-soft: #475569;
  --ebank-text-faint: #94a3b8;
  --ebank-shadow: 0 10px 25px rgba(0, 40, 100, 0.06);
  --ebank-shadow-soft: 0 4px 12px rgba(0, 40, 100, 0.04);
  
  --ebank-user-bubble-bg: var(--ebank-primary);
  --ebank-user-bubble-text: #ffffff;
  --ebank-bot-bubble-bg: #f8fafc;
  --ebank-bot-bubble-border: #e2e8f0;

  --ebank-radius-xl: 20px;
  --ebank-radius-lg: 16px;
  --ebank-radius-md: 12px;
  --ebank-radius-sm: 8px;
}

.dark,
body.dark,
[data-theme="dark"],
.gradio-container.dark {
  --ebank-primary: #3b82f6; 
  --ebank-primary-hover: #60a5fa;
  --ebank-accent: #93c5fd;
  --ebank-bg: #0f172a;
  --ebank-bg-soft: #1e293b;
  --ebank-card: #1e293b;
  --ebank-card-2: #243147;
  --ebank-border: #334155;
  --ebank-border-strong: #475569;
  --ebank-text: #f8fafc;
  --ebank-text-soft: #cbd5e1;
  --ebank-text-faint: #94a3b8;
  --ebank-shadow: 0 12px 28px rgba(0, 0, 0, 0.4);
  --ebank-shadow-soft: 0 6px 16px rgba(0, 0, 0, 0.3);

  --ebank-user-bubble-bg: #2563eb;
  --ebank-user-bubble-text: #ffffff;
  --ebank-bot-bubble-bg: #152033;
  --ebank-bot-bubble-border: #334155;
}

/* =========================================
   2. Global Typography & Spacing
   ========================================= */
html, body {
  background: var(--ebank-bg) !important;
  color: var(--ebank-text) !important;
}

.gradio-container {
  max-width: 1560px !important;
  margin: 0 auto !important;
  padding: 24px 32px !important;
  background: var(--ebank-bg) !important;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif !important;
}

#evibank-main-row {
  gap: 24px;
  align-items: stretch;
}

#evibank-bottom-row {
  margin-top: 24px;
}

.evibank-column {
  gap: 24px !important;
}

/* =========================================
   3. Header
   ========================================= */
#evibank-header {
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg, var(--ebank-primary) 0%, #003a70 100%);
  border-radius: var(--ebank-radius-xl);
  padding: 36px 40px;
  box-shadow: var(--ebank-shadow);
  margin-bottom: 24px;
}

#evibank-header::after {
  content: "";
  position: absolute;
  right: -50px;
  bottom: -50px;
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 60%);
  pointer-events: none;
}

#evibank-header h1 {
  margin: 0;
  color: #ffffff;
  font-size: 32px;
  font-weight: 800;
  letter-spacing: 0.5px;
}

#evibank-header p {
  margin: 10px 0 0 0;
  color: rgba(255, 255, 255, 0.85);
  font-size: 15px;
  line-height: 1.6;
}

#evibank-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 20px;
}

.evibank-badge {
  display: inline-flex;
  align-items: center;
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(4px);
  color: #ffffff;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 600;
}

/* =========================================
   4. Panels & Cards 
   ========================================= */
.evibank-panel {
  position: relative;
  background: var(--ebank-card) !important;
  border: 1px solid var(--ebank-border) !important;
  border-radius: var(--ebank-radius-xl) !important;
  padding: 24px !important;
  box-shadow: var(--ebank-shadow-soft) !important;
  display: flex;
  flex-direction: column;
  height: auto; /* 修复大片留白：不再强制拉伸高度 */
  flex-grow: 0;
}

#chat-panel {
  height: 100%; /* 仅保留左侧主对话框的自适应拉伸 */
}

/* --- 修复 Issue 3: 消除 HTML/Markdown 组件的奇怪局布滚动条 --- */
.evibank-panel .prose,
.evibank-panel-title,
.evibank-panel-title h3,
.evibank-panel-title p {
  overflow: hidden !important; 
  white-space: normal !important;
}

.evibank-panel-title {
  margin-bottom: 16px;
}

.evibank-panel-title h3 {
  margin: 0 0 6px 0;
  color: var(--ebank-text);
  font-size: 18px;
  font-weight: 700;
}

.evibank-panel-title p {
  margin: 0;
  color: var(--ebank-text-soft);
  font-size: 13px;
  line-height: 1.5;
}

.evibank-divider {
  height: 1px;
  background: var(--ebank-border);
  margin: 16px 0;
}

/* =========================================
   5. Chatbox & Input
   ========================================= */
#chatbot-box {
  border: 1px solid var(--ebank-border) !important;
  border-radius: var(--ebank-radius-lg) !important;
  background: var(--ebank-bg-soft) !important;
  flex-grow: 1;
  min-height: 480px;
}

#chatbot-box .message-content {
  border-radius: 14px !important;
  line-height: 1.7 !important;
  font-size: 14px !important;
  padding: 14px 20px !important;
}

/* --- 修复 Issue 1: 强制覆盖用户气泡内深层标签的字体颜色 --- */
#chatbot-box .message.user .message-content,
#chatbot-box .message.user .message-content *,
#chatbot-box .message[data-testid="chatbot-message-user"] .message-content,
#chatbot-box .message[data-testid="chatbot-message-user"] .message-content * {
  background: var(--ebank-user-bubble-bg) !important;
  color: var(--ebank-user-bubble-text) !important;
  border: none !important;
}

#chatbot-box .message.bot .message-content,
#chatbot-box .message.bot .message-content *,
#chatbot-box .message[data-testid="chatbot-message-bot"] .message-content,
#chatbot-box .message[data-testid="chatbot-message-bot"] .message-content * {
  background: var(--ebank-card) !important;
  color: var(--ebank-text) !important;
  border-color: var(--ebank-bot-bubble-border) !important;
}

#query-box textarea,
#query-box input {
  background: var(--ebank-card) !important;
  border: 1px solid var(--ebank-border-strong) !important;
  border-radius: var(--ebank-radius-md) !important;
  padding: 14px 16px !important;
}

#query-box textarea:focus {
  border-color: var(--ebank-primary) !important;
  box-shadow: 0 0 0 3px rgba(0, 91, 172, 0.15) !important;
}

#send-btn button {
  background: var(--ebank-primary) !important;
  color: white !important;
  border-radius: var(--ebank-radius-md) !important;
  font-weight: 600 !important;
  transition: all 0.2s ease !important;
}

#send-btn button:hover {
  background: var(--ebank-primary-hover) !important;
}

/* =========================================
   6. Examples Grid
   ========================================= */
.examples-grid {
  display: grid !important;
  grid-template-columns: repeat(2, 1fr) !important;
  gap: 12px !important;
  width: 100% !important;
}

.examples-grid .example-chip button {
  width: 100% !important;
  height: 100% !important;
  min-height: 56px !important;
  background: var(--ebank-card) !important;
  color: var(--ebank-text-soft) !important;
  border: 1px solid var(--ebank-border) !important;
  border-radius: var(--ebank-radius-md) !important;
  text-align: left !important;
  padding: 12px 16px !important;
  white-space: normal !important;
  transition: all 0.2s ease !important;
}

.examples-grid .example-chip button:hover {
  border-color: var(--ebank-primary) !important;
  color: var(--ebank-primary) !important;
  background: var(--ebank-bg-soft) !important;
}

.evibank-footnote {
  color: var(--ebank-text-faint);
  font-size: 12px;
  line-height: 1.6;
  margin-top: 12px;
  padding-left: 4px;
}

/* =========================================
   7. Right Column Elements
   ========================================= */
#summary-box {
  background: var(--ebank-bg-soft) !important;
  border: 1px solid var(--ebank-border) !important;
  border-radius: var(--ebank-radius-md) !important;
  padding: 16px 20px !important;
  overflow: hidden !important; /* 隐藏内部滚动条 */
}

#summary-box .prose,
#summary-box .markdown-body {
  color: var(--ebank-text) !important;
  line-height: 1.7 !important;
}

#gallery-box .gallery-item {
  border-radius: var(--ebank-radius-md) !important;
  border: 1px solid var(--ebank-border) !important;
}

/* --- 修复 Issue 4: JSON 组件的双滚动条 --- */
#debug-box > div.wrap,
#debug-box > div > div.wrap {
  overflow: hidden !important; 
}

/* =========================================
   8. Evidence Table 
   ========================================= */
#evidence-table-wrap {
  border: 1px solid var(--ebank-border) !important;
  border-radius: var(--ebank-radius-md) !important;
  background: var(--ebank-card) !important;
  overflow: hidden !important;
}

#evidence-table-wrap table {
  margin: 0 !important;
}

#evidence-table-wrap th, 
#evidence-table-wrap td {
  padding: 14px 16px !important;
  border-color: var(--ebank-border) !important;
  font-size: 13px !important;
  color: var(--ebank-text) !important;
  background: var(--ebank-card) !important;
}

#evidence-table-wrap th {
  background: var(--ebank-bg-soft) !important;
  color: var(--ebank-text-soft) !important;
  font-weight: 600 !important;
}

/* =========================================
   9. Footer
   ========================================= */
#evibank-footer {
  margin-top: 24px;
  padding: 20px 24px;
  border-radius: var(--ebank-radius-lg);
  background: var(--ebank-card);
  border: 1px solid var(--ebank-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--ebank-text-soft);
  font-size: 13px;
}

#evibank-footer a {
  color: var(--ebank-primary);
  text-decoration: none;
  font-weight: 600;
}

#evibank-footer a:hover {
  text-decoration: underline;
}

footer.svelte-1rjryqp {
  display: none !important;
}
"""

EVIDENCE_TABLE_COLUMNS = [
    "doc_id",
    "标题",
    "来源文件",
    "来源类型",
    "分类",
    "位置",
    "分数",
    "命中原因",
]

DEFAULT_EVIDENCE_SUMMARY = """### 来源依据
当前尚未产生回答。发送问题后，这里将显示本次回答的证据摘要、命中逻辑与关联截图。"""

DEFAULT_DEBUG_INFO = {
    "status": "idle",
    "message": "等待用户提问。",
}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\u3000", " ").strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _empty_evidence_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=EVIDENCE_TABLE_COLUMNS)


def _resolve_media_path(path_str: str) -> str | None:
    clean = _normalize_text(path_str)
    if not clean:
        return None

    path = Path(clean)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()

    if not path.exists() or not path.is_file():
        return None

    return str(path)


def _format_location(item: EvidenceItem) -> str:
    if item.slide_no is not None:
        return f"第 {item.slide_no} 页/张"
    if item.page_no is not None:
        return f"第 {item.page_no} 页"
    return "-"


def _build_evidence_summary(answer: ChatAnswer) -> str:
    evidence_items = answer.evidence_items or []
    if not evidence_items:
        return "### 来源依据\n未检索到可展示的证据。"

    lines: list[str] = [
        "### 来源依据",
        f"本次回答共参考 **{len(evidence_items)}** 条证据，以下为优先级最高的命中结果：",
        "",
    ]

    for idx, item in enumerate(evidence_items[:5], start=1):
        title = _normalize_text(item.title) or "未命名资料"
        source_file = _normalize_text(item.source_file) or "未知文件"
        source_type = _normalize_text(item.source_type) or "未知类型"
        category = _normalize_text(item.category) or "未分类"
        location = _format_location(item)
        score = _safe_float(item.score, 0.0)
        reason = _normalize_text(item.reason) or "无"

        lines.extend(
            [
                f"**证据 {idx}：{title}**",
                f"- 来源：`{source_file}` · `{source_type}` · 分类：`{category}` · 位置：`{location}`",
                f"- 分数：`{score:.4f}`",
                f"- 命中原因：{reason}",
                "",
            ]
        )

    return "\n".join(lines).strip()


def _build_evidence_dataframe(answer: ChatAnswer) -> pd.DataFrame:
    rows: list[list[Any]] = []

    for item in answer.evidence_items or []:
        rows.append(
            [
                _normalize_text(item.doc_id),
                _normalize_text(item.title),
                _normalize_text(item.source_file),
                _normalize_text(item.source_type),
                _normalize_text(item.category) or "未分类",
                _format_location(item),
                round(_safe_float(item.score, 6)),
                _normalize_text(item.reason),
            ]
        )

    if not rows:
        return _empty_evidence_dataframe()

    return pd.DataFrame(rows, columns=EVIDENCE_TABLE_COLUMNS)


def _build_gallery_items(answer: ChatAnswer) -> list[tuple[str, str | None]]:
    items: list[tuple[str, str | None]] = []
    for idx, path_str in enumerate(answer.gallery_images or [], start=1):
        resolved = _resolve_media_path(path_str)
        if not resolved:
            continue
        items.append((resolved, f"相关截图 {idx}"))
    return items


def _build_source_basis_lines(evidence_items: list[EvidenceItem]) -> list[str]:
    if not evidence_items:
        return ["### 来源依据", "- 当前未检索到可展示的证据。"]

    lines: list[str] = ["### 来源依据"]
    for idx, item in enumerate(evidence_items[:4], start=1):
        title = _normalize_text(item.title) or "未命名资料"
        source_file = _normalize_text(item.source_file) or "未知文件"
        source_type = _normalize_text(item.source_type) or "未知类型"
        category = _normalize_text(item.category) or "未分类"
        location = _format_location(item)
        score = _safe_float(item.score, 0.0)
        lines.append(
            f"- [{idx}] {title}（{source_file} / {source_type} / {category} / {location} / score={score:.4f}）"
        )
    return lines


def _build_chatbot_answer(answer: ChatAnswer) -> str:
    answer_markdown = _normalize_text(answer.answer_markdown)
    source_lines = _build_source_basis_lines(answer.evidence_items or [])

    if answer_markdown:
        return f"{answer_markdown}\n\n" + "\n".join(source_lines)

    return "\n".join(source_lines)


def _debug_payload(answer: ChatAnswer) -> dict[str, Any]:
    debug_info = answer.debug_info if isinstance(answer.debug_info, dict) else {}
    return debug_info or {"status": "ok", "message": "无额外调试信息。"}


def _panel_title_html(title: str, subtitle: str = "") -> str:
    title_text = escape(_normalize_text(title))
    subtitle_text = escape(_normalize_text(subtitle))

    if subtitle_text:
        return f"""
        <div class="evibank-panel-title">
          <h3>{title_text}</h3>
          <p>{subtitle_text}</p>
        </div>
        """
    return f"""
    <div class="evibank-panel-title">
      <h3>{title_text}</h3>
    </div>
    """


def _iter_markdown_frames(text: str) -> list[str]:
    full_text = _normalize_text(text)
    if not full_text:
        return [""]

    blocks = re.split(r"\n\s*\n", full_text)
    frames: list[str] = []
    collected: list[str] = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        if len(block) <= 120:
            collected.append(block)
            frames.append("\n\n".join(collected))
            continue

        sentences = re.split(r"(?<=[。！？!?])", block)
        current = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            current += sentence
            if len(current) >= 70:
                temp_collected = [*collected, current]
                frames.append("\n\n".join(temp_collected))
        if current:
            collected.append(current)
            frames.append("\n\n".join(collected))

    if not frames or frames[-1] != full_text:
        frames.append(full_text)

    deduped: list[str] = []
    prev = None
    for frame in frames:
        if frame != prev:
            deduped.append(frame)
        prev = frame

    return deduped


@lru_cache(maxsize=1)
def _get_chat_service() -> ChatService:
    return ChatService()


def _safe_ui_settings() -> tuple[str, str, list[str]]:
    try:
        settings = get_settings()
        title = _normalize_text(settings.ui.app_title) or "企业网银 FAQ RAG Demo"
        subtitle = _normalize_text(settings.ui.app_subtitle) or "基于阿里云百炼 OpenAI 兼容接口的企业网银智能问答演示"
        examples = [
            _normalize_text(q)
            for q in settings.ui.example_questions
            if _normalize_text(q)
        ]
        if not examples:
            examples = [
                "企业网银登录时提示控件未安装怎么办？",
                "UKey 插入后无法识别如何处理？",
                "客户证书过期了怎么更新？",
                "企业网银代发工资查询",
                "为什么每次登录都需要重新下载控件？",
                "回单在哪里查看和下载？",
            ]
        return title, subtitle, examples
    except Exception as exc:
        logger.warning("读取 UI 配置失败，使用默认值：err=%s", exc)
        return (
            "企业网银 FAQ RAG Demo",
            "基于阿里云百炼 OpenAI 兼容接口的企业网银智能问答演示",
            [
                "企业网银登录时提示控件未安装怎么办？",
                "UKey 插入后无法识别如何处理？",
                "客户证书过期了怎么更新？",
                "企业网银代发工资查询",
                "为什么每次登录都需要重新下载控件？",
                "回单在哪里查看和下载？",
            ],
        )


def _register_static_paths() -> None:
    try:
        settings = get_settings()
        image_dir = settings.paths.parsed_images_dir
        if image_dir.exists() and image_dir.is_dir():
            gr.set_static_paths(paths=[image_dir])
            logger.info("已注册 Gradio 静态目录：%s", image_dir)
    except Exception as exc:
        logger.warning("注册静态目录失败，将继续运行：err=%s", exc)


def _fill_example(example_text: str) -> str:
    return _normalize_text(example_text)


def _handle_chat_stream(
        query: str,
        chat_state: list[dict[str, str]] | None,
) -> Generator[
    tuple[
        list[dict[str, str]],
        list[dict[str, str]],
        str,
        str,
        pd.DataFrame,
        list[tuple[str, str | None]],
        dict[str, Any],
    ],
    None,
    None,
]:
    history = list(chat_state or [])
    clean_query = _normalize_text(query)

    if not clean_query:
        gr.Warning("请输入问题后再发送。")
        yield (
            history,
            history,
            "",
            DEFAULT_EVIDENCE_SUMMARY,
            _empty_evidence_dataframe(),
            [],
            {"status": "warning", "message": "empty_query"},
        )
        return

    user_message = {"role": "user", "content": clean_query}
    pending_assistant = {
        "role": "assistant",
        "content": "正在检索知识并生成回答，请稍候…",
    }
    pending_history = [*history, user_message, pending_assistant]

    service = _get_chat_service()
    start_time = time.perf_counter()
    future = EXECUTOR.submit(service.chat, clean_query, history)

    while not future.done():
        elapsed = time.perf_counter() - start_time
        yield (
            pending_history,
            pending_history,
            "",
            "### 来源依据\n正在检索候选证据并组织回答，请稍候…",
            _empty_evidence_dataframe(),
            [],
            {
                "status": "running",
                "message": "retrieving_and_generating",
                "query": clean_query,
                "elapsed_seconds": round(elapsed, 2),
            },
        )
        time.sleep(0.12)

    try:
        answer = future.result()
        final_answer_markdown = _build_chatbot_answer(answer)
        evidence_summary = _build_evidence_summary(answer)
        evidence_df = _build_evidence_dataframe(answer)
        gallery_items = _build_gallery_items(answer)
        debug_info = _debug_payload(answer)

        elapsed = round(time.perf_counter() - start_time, 4)
        if isinstance(debug_info, dict):
            debug_info = {**debug_info, "ui_elapsed_seconds": elapsed}

        frames = _iter_markdown_frames(final_answer_markdown)

        for idx, frame in enumerate(frames):
            streamed_history = [
                *history,
                user_message,
                {"role": "assistant", "content": frame},
            ]

            yield (
                streamed_history,
                streamed_history,
                "",
                evidence_summary,
                evidence_df,
                gallery_items,
                debug_info,
            )

            if idx < len(frames) - 1:
                time.sleep(0.03)

    except Exception as exc:
        logger.exception("UI 对话处理失败：%s", exc)
        gr.Warning("本次请求处理失败，请查看调试信息或稍后重试。")

        error_text = (
            "一、结论\n"
            "根据当前知识库无法确认。\n\n"
            "二、操作步骤\n"
            "请稍后重试，或补充更具体的报错原文、截图、菜单路径或错误码。\n\n"
            "三、补充说明\n"
            "当前请求在服务执行过程中发生异常，未生成可信答案。\n\n"
            "### 来源依据\n"
            "- 本次请求因系统异常未完成证据整理。"
        )

        new_history = [
            *history,
            user_message,
            {"role": "assistant", "content": error_text},
        ]

        debug_info = {
            "status": "error",
            "message": str(exc),
        }

        yield (
            new_history,
            new_history,
            "",
            "### 来源依据\n当前请求处理失败，未生成有效证据摘要。",
            _empty_evidence_dataframe(),
            [],
            debug_info,
        )


def _clear_all() -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    str,
    str,
    pd.DataFrame,
    list[tuple[str, str | None]],
    dict[str, Any],
]:
    empty_history: list[dict[str, str]] = []
    return (
        empty_history,
        empty_history,
        "",
        DEFAULT_EVIDENCE_SUMMARY,
        _empty_evidence_dataframe(),
        [],
        DEFAULT_DEBUG_INFO,
    )


def build_demo() -> gr.Blocks:
    _register_static_paths()
    app_title, app_subtitle, example_questions = _safe_ui_settings()

    theme = gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="slate",
        neutral_hue="slate",
    ).set(
        body_background_fill="transparent",
        background_fill_primary="transparent",
        background_fill_secondary="transparent",
        block_background_fill="transparent",
        block_border_width="0px",
    )

    header_badges = [
        "企业网银 FAQ",
        "多源知识库",
        "混合检索",
        "图文证据展示",
        "Qwen3.5-Flash",
    ]
    badges_html = "".join(
        f'<span class="evibank-badge">{escape(text)}</span>' for text in header_badges
    )

    footer_html = f"""
    <div id="evibank-footer">
      <div>
        <span>⭐ <strong>{escape(PROJECT_BRAND_NAME)}</strong> · 企业网银 FAQ 证据增强问答演示</span>
      </div>
      <div>
        <a href="{escape(GITHUB_REPO_URL)}" target="_blank" rel="noopener noreferrer">
          GitHub · {escape(GITHUB_REPO_NAME)}
        </a>
      </div>
    </div>
    """

    with gr.Blocks(
            title=app_title,
            theme=theme,
            css=CUSTOM_CSS,
            fill_height=False,
            elem_id="evibank-root",
    ) as demo:
        chat_state = gr.State(value=[])

        gr.HTML(
            f"""
            <div id="evibank-header">
              <h1>{escape(app_title)}</h1>
              <p>{escape(app_subtitle)}</p>
              <div id="evibank-badges">{badges_html}</div>
            </div>
            """
        )

        with gr.Row(equal_height=False, elem_id="evibank-main-row"):
            with gr.Column(scale=7, min_width=600, elem_classes=["evibank-column"]):
                with gr.Group(elem_classes=["evibank-panel"], elem_id="chat-panel"):
                    gr.HTML(
                        _panel_title_html(
                            "智能问答",
                            "输入企业网银相关问题。系统将检索本地知识库后生成答案，并在右侧同步展示证据与截图。",
                        )
                    )

                    chatbot = gr.Chatbot(
                        value=[],
                        type="messages",
                        show_copy_button=False,
                        bubble_full_width=False,
                        placeholder="请输入企业网银相关问题，例如登录、UKey、证书、回单、转账、代发、权限等。",
                        show_label=False,
                        elem_id="chatbot-box",
                    )

                    gr.HTML('<div class="evibank-divider"></div>')

                    query_box = gr.Textbox(
                        value="",
                        show_label=False,
                        placeholder="例如：企业网银登录时提示安全控件异常怎么办？",
                        lines=3,
                        max_lines=6,
                        autofocus=True,
                        elem_id="query-box",
                    )

                    with gr.Row():
                        send_btn = gr.Button("发送", variant="primary", size="lg", elem_id="send-btn")
                        clear_btn = gr.Button("清空历史", variant="secondary", size="lg")

                    gr.HTML(
                        _panel_title_html(
                            "示例问题",
                            "点击下方问题卡片快速填充输入框，便于会议演示与功能验证。",
                        )
                    )

                    with gr.Column(elem_classes=["examples-grid"]):
                        for example in example_questions:
                            example_btn = gr.Button(
                                value=example,
                                variant="secondary",
                                elem_classes=["example-chip"],
                            )
                            example_btn.click(
                                fn=_fill_example,
                                inputs=gr.State(example),
                                outputs=query_box,
                            )

                    gr.Markdown(
                        "提示：答案正文下方会显式补充“来源依据”；右侧展示图文辅助信息，底部证据表汇总命中结果与分数，适合会议演示时快速核对。",
                        elem_classes=["evibank-footnote"],
                    )

            # 解耦了右侧结构，废除了无意义的外层全局嵌套 Panel，解决底部巨幅留白问题
            with gr.Column(scale=5, min_width=480, elem_classes=["evibank-column"]):
                with gr.Group(elem_classes=["evibank-panel"], elem_id="gallery-box"):
                    gr.HTML(
                        _panel_title_html(
                            "相关截图",
                            "若命中的知识条目包含图文说明，将优先在此展示辅助截图。",
                        )
                    )
                    # 去除了固定 height 约束，以实现内容高度自适应
                    gallery = gr.Gallery(
                        value=[],
                        show_label=False,
                        columns=2,
                        preview=True,
                        object_fit="contain",
                    )

                with gr.Group(elem_classes=["evibank-panel"]):
                    gr.HTML(
                        _panel_title_html(
                            "证据摘要",
                            "展示当前回答最重要的命中依据、来源与得分。",
                        )
                    )
                    evidence_summary = gr.Markdown(
                        value=DEFAULT_EVIDENCE_SUMMARY,
                        show_label=False,
                        elem_id="summary-box",
                    )

                with gr.Accordion("调试信息", open=False, elem_id="debug-box"):
                    debug_json = gr.JSON(
                        value=DEFAULT_DEBUG_INFO,
                        show_label=False,
                    )

        with gr.Row(equal_height=False, elem_id="evibank-bottom-row"):
            with gr.Column(scale=1):
                with gr.Group(elem_classes=["evibank-panel"]):
                    gr.HTML(
                        _panel_title_html(
                            "命中证据表",
                            "横跨全宽展示本次检索结果，便于比对标题、来源、分类、位置与分数。",
                        )
                    )
                    evidence_table = gr.Dataframe(
                        value=_empty_evidence_dataframe(),
                        headers=EVIDENCE_TABLE_COLUMNS,
                        datatype=["str", "str", "str", "str", "str", "str", "number", "str"],
                        interactive=False,
                        wrap=True,
                        max_height=320,
                        show_label=False,
                        elem_id="evidence-table-wrap",
                    )

        gr.HTML(footer_html)

        send_outputs = [
            chat_state,
            chatbot,
            query_box,
            evidence_summary,
            evidence_table,
            gallery,
            debug_json,
        ]

        send_btn.click(
            fn=_handle_chat_stream,
            inputs=[query_box, chat_state],
            outputs=send_outputs,
        )

        query_box.submit(
            fn=_handle_chat_stream,
            inputs=[query_box, chat_state],
            outputs=send_outputs,
        )

        clear_btn.click(
            fn=_clear_all,
            inputs=None,
            outputs=send_outputs,
        )

    demo.queue(default_concurrency_limit=8)
    return demo


demo = build_demo()

if __name__ == "__main__":
    demo.launch()
