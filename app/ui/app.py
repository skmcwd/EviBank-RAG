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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 你发布到 GitHub 后，把下面 URL 改成真实仓库地址即可
GITHUB_REPO_URL = "https://github.com/skmcwd/EviBank-RAG"
GITHUB_REPO_NAME = "evibank-rag"
PROJECT_BRAND_NAME = "EviBank-RAG"

# 用于后台执行 ChatService.chat，使前端可以持续刷新“处理中动画 + 计时器”
EXECUTOR = ThreadPoolExecutor(max_workers=4)

CUSTOM_CSS = r"""
/* =========================================
   1. Theme Variables
   ========================================= */
:root,
.light,
[data-theme="light"] {
  --ebank-primary: #1f5eff;
  --ebank-primary-2: #5b8cff;
  --ebank-accent: #103f82;
  --ebank-bg: #f3f7fc;
  --ebank-bg-soft: #edf3fb;
  --ebank-card: #ffffff;
  --ebank-card-2: #f9fbff;
  --ebank-border: #d7e1ee;
  --ebank-border-strong: #c5d3e5;
  --ebank-text: #17324d;
  --ebank-text-soft: #5c6f86;
  --ebank-text-faint: #7b8ca3;
  --ebank-shadow: 0 14px 36px rgba(18, 48, 84, 0.08);
  --ebank-shadow-soft: 0 8px 22px rgba(18, 48, 84, 0.05);
  --ebank-success: #10b981;
  --ebank-warning: #f59e0b;

  --ebank-user-bubble-bg: linear-gradient(135deg, #2d6dff, #7ea6ff);
  --ebank-user-bubble-text: #ffffff;
  --ebank-bot-bubble-bg: #f7faff;
  --ebank-bot-bubble-border: #dbe6f3;

  --ebank-radius-xl: 24px;
  --ebank-radius-lg: 18px;
  --ebank-radius-md: 14px;
  --ebank-radius-sm: 10px;
}

.dark,
body.dark,
[data-theme="dark"],
.gradio-container.dark {
  --ebank-primary: #7ca6ff;
  --ebank-primary-2: #9ab8ff;
  --ebank-accent: #b9d1ff;
  --ebank-bg: #0c1118;
  --ebank-bg-soft: #101722;
  --ebank-card: #141c27;
  --ebank-card-2: #182230;
  --ebank-border: #243345;
  --ebank-border-strong: #31445a;
  --ebank-text: #e6edf7;
  --ebank-text-soft: #b6c5d9;
  --ebank-text-faint: #8fa3b9;
  --ebank-shadow: 0 20px 46px rgba(0, 0, 0, 0.28);
  --ebank-shadow-soft: 0 10px 30px rgba(0, 0, 0, 0.22);
  --ebank-success: #34d399;
  --ebank-warning: #fbbf24;

  --ebank-user-bubble-bg: linear-gradient(135deg, #27468a, #3861ba);
  --ebank-user-bubble-text: #eef5ff;
  --ebank-bot-bubble-bg: #111926;
  --ebank-bot-bubble-border: #243345;
}

/* =========================================
   2. Global
   ========================================= */
html, body {
  background: var(--ebank-bg) !important;
  color: var(--ebank-text) !important;
}

body {
  overflow-x: hidden;
}

.gradio-container {
  max-width: 1560px !important;
  margin: 0 auto !important;
  padding: 20px 22px 18px 22px !important;
  background:
    radial-gradient(circle at top left, rgba(91, 140, 255, 0.08), transparent 26%),
    linear-gradient(180deg, var(--ebank-bg) 0%, var(--ebank-bg-soft) 100%) !important;
  color: var(--ebank-text) !important;
  font-family:
    "Segoe UI", "PingFang SC", "Microsoft YaHei", "Helvetica Neue",
    Arial, sans-serif !important;
}

#evibank-root {
  color: var(--ebank-text);
}

#evibank-main-row {
  gap: 18px;
  align-items: stretch;
}

#evibank-bottom-row {
  margin-top: 18px;
}

.evibank-column {
  gap: 18px !important;
}

/* =========================================
   3. Header
   ========================================= */
#evibank-header {
  position: relative;
  overflow: hidden;
  background:
    linear-gradient(135deg, rgba(20, 64, 148, 0.32), rgba(12, 30, 67, 0.12)),
    linear-gradient(90deg, rgba(16, 54, 120, 0.78), rgba(10, 26, 54, 0.92));
  border: 1px solid rgba(92, 138, 224, 0.16);
  border-radius: 32px;
  padding: 28px 30px 24px 30px;
  box-shadow: 0 18px 54px rgba(3, 13, 30, 0.28);
  margin-bottom: 18px;
}

#evibank-header::before {
  content: "";
  position: absolute;
  right: -30px;
  top: -30px;
  width: 220px;
  height: 220px;
  background: radial-gradient(circle, rgba(106, 153, 255, 0.20) 0%, transparent 70%);
  pointer-events: none;
}

#evibank-header h1 {
  margin: 0;
  color: #b8d1ff;
  font-size: 34px;
  font-weight: 900;
  letter-spacing: 0.2px;
}

#evibank-header p {
  margin: 12px 0 0 0;
  color: rgba(232, 241, 255, 0.90);
  font-size: 15px;
  line-height: 1.72;
  max-width: 980px;
}

#evibank-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 16px;
}

.evibank-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(33, 91, 210, 0.16);
  color: #cfe0ff;
  border: 1px solid rgba(122, 165, 255, 0.18);
  border-radius: 999px;
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 700;
}

/* =========================================
   4. Panel / Card
   ========================================= */
.evibank-panel {
  position: relative;
  background: linear-gradient(180deg, var(--ebank-card) 0%, var(--ebank-card-2) 100%) !important;
  border: 1px solid var(--ebank-border) !important;
  border-radius: var(--ebank-radius-xl) !important;
  padding: 18px !important;
  box-shadow: var(--ebank-shadow-soft) !important;
  overflow: hidden;
}

.evibank-panel-title {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.evibank-panel-title h3 {
  margin: 0;
  color: var(--ebank-text);
  font-size: 18px;
  font-weight: 800;
  letter-spacing: 0.1px;
}

.evibank-panel-title p {
  margin: 0;
  color: var(--ebank-text-soft);
  font-size: 13px;
  line-height: 1.6;
}

.evibank-divider {
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--ebank-border), transparent);
  margin: 8px 0 6px 0;
}

/* =========================================
   5. Chat Panel
   ========================================= */
#chat-panel {
  min-height: 760px;
}

#chatbot-box {
  border: 1px solid var(--ebank-border) !important;
  border-radius: 20px !important;
  overflow: hidden !important;
  background: var(--ebank-card) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
}

#chatbot-box > .wrap,
#chatbot-box .wrap,
#chatbot-box .panel-wrap {
  padding: 14px !important;
  background: transparent !important;
}

#chatbot-box .message,
#chatbot-box .message-wrap,
#chatbot-box .message-row {
  background: transparent !important;
}

#chatbot-box .message-content {
  border-radius: 18px !important;
  line-height: 1.78 !important;
  font-size: 14px !important;
  padding: 16px 18px !important;
  animation: evibankFadeUp 0.22s ease both;
  box-sizing: border-box !important;
}

#chatbot-box .message.user .message-content,
#chatbot-box .message[data-testid="chatbot-message-user"] .message-content {
  background: var(--ebank-user-bubble-bg) !important;
  color: var(--ebank-user-bubble-text) !important;
  border: none !important;
  box-shadow: 0 10px 22px rgba(31, 94, 255, 0.16);
}

#chatbot-box .message.bot .message-content,
#chatbot-box .message.assistant .message-content,
#chatbot-box .message[data-testid="chatbot-message-bot"] .message-content,
#chatbot-box .message[data-testid="chatbot-message-assistant"] .message-content {
  background: var(--ebank-bot-bubble-bg) !important;
  color: var(--ebank-text) !important;
  border: 1px solid var(--ebank-bot-bubble-border) !important;
  box-shadow: none !important;
}

#chatbot-box button[aria-label*="copy"],
#chatbot-box button[title*="copy"],
#chatbot-box button[aria-label*="复制"],
#chatbot-box button[title*="复制"] {
  opacity: 0.72;
}

#query-box textarea,
#query-box input,
#query-box .wrap textarea,
#query-box .wrap input {
  background: var(--ebank-card) !important;
  color: var(--ebank-text) !important;
  border: 1px solid var(--ebank-border-strong) !important;
  border-radius: 18px !important;
  box-shadow: none !important;
  font-size: 14px !important;
  padding: 12px 14px !important;
}

#query-box textarea:focus,
#query-box input:focus {
  border-color: rgba(31, 94, 255, 0.55) !important;
  box-shadow: 0 0 0 4px rgba(31, 94, 255, 0.10) !important;
}

#send-btn button,
#clear-btn button,
.example-chip button {
  border-radius: 14px !important;
  font-weight: 700 !important;
  transition:
    transform 0.16s ease,
    box-shadow 0.18s ease,
    border-color 0.18s ease !important;
}

#send-btn button:hover,
#clear-btn button:hover,
.example-chip button:hover {
  transform: translateY(-1px);
}

#send-btn button {
  background: linear-gradient(135deg, var(--ebank-primary), var(--ebank-primary-2)) !important;
  color: white !important;
  border: none !important;
  box-shadow: 0 10px 24px rgba(31, 94, 255, 0.22) !important;
}

#clear-btn button {
  background: transparent !important;
  color: var(--ebank-text) !important;
  border: 1px solid var(--ebank-border-strong) !important;
}

#examples-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 2px;
}

.example-chip button {
  width: 100% !important;
  min-height: 54px !important;
  background: var(--ebank-card) !important;
  color: var(--ebank-text) !important;
  border: 1px solid var(--ebank-border) !important;
  box-shadow: none !important;
  text-align: left !important;
  line-height: 1.48 !important;
  padding: 10px 14px !important;
  white-space: normal !important;
}

.example-chip button:hover {
  border-color: rgba(31, 94, 255, 0.42) !important;
  box-shadow: 0 8px 16px rgba(31, 94, 255, 0.08) !important;
}

.evibank-footnote {
  color: var(--ebank-text-faint);
  font-size: 12px;
  line-height: 1.62;
  margin-top: 4px;
}

/* =========================================
   6. Right Stack / Summary / Gallery
   ========================================= */
#right-stack {
  position: relative;
  min-height: 760px;
}

#gallery-box {
  min-height: 330px;
}

#gallery-box .thumbnail-item,
#gallery-box .gallery-item,
#gallery-box [data-testid="gallery"] button {
  border-radius: 14px !important;
}

#gallery-box .wrap {
  padding: 6px 2px 0 2px !important;
}

#gallery-box img {
  border-radius: 14px !important;
  background: var(--ebank-card) !important;
}

#summary-box .prose,
#summary-box .markdown,
#summary-box {
  line-height: 1.78 !important;
  color: var(--ebank-text) !important;
}

#summary-box p,
#summary-box li,
#summary-box strong,
#summary-box h1,
#summary-box h2,
#summary-box h3,
#summary-box h4 {
  color: var(--ebank-text) !important;
}

#summary-box .prose,
#summary-box .markdown-body,
#summary-box .wrap {
  padding: 2px 4px 2px 2px !important;
}

/* =========================================
   7. Evidence Table (Full Width)
   ========================================= */
#evidence-table-wrap .wrap {
  border: 1px solid var(--ebank-border) !important;
  border-radius: 18px !important;
  overflow: hidden !important;
  background: var(--ebank-card) !important;
}

#evidence-table-wrap table,
#evidence-table-wrap thead,
#evidence-table-wrap tbody,
#evidence-table-wrap tr,
#evidence-table-wrap th,
#evidence-table-wrap td {
  background: var(--ebank-card) !important;
  color: var(--ebank-text) !important;
  border-color: var(--ebank-border) !important;
  font-size: 13px !important;
}

#evidence-table-wrap th {
  background: var(--ebank-bg-soft) !important;
  font-weight: 700 !important;
}

#evidence-table-wrap td,
#evidence-table-wrap th {
  padding: 10px 12px !important;
}

/* =========================================
   8. Processing Overlay
   ========================================= */
#processing-left,
#processing-right {
  position: absolute;
  inset: 0;
  z-index: 15;
  pointer-events: none;
}

.evibank-processing-overlay {
  position: absolute;
  inset: 0;
  border-radius: 24px;
  background:
    linear-gradient(90deg, rgba(31, 94, 255, 0.00), rgba(31, 94, 255, 0.08), rgba(31, 94, 255, 0.00)),
    rgba(17, 27, 42, 0.08);
  overflow: hidden;
  animation: evibankOverlayFade 0.16s ease both;
}

.dark .evibank-processing-overlay,
body.dark .evibank-processing-overlay,
[data-theme="dark"] .evibank-processing-overlay {
  background:
    linear-gradient(90deg, rgba(122, 166, 255, 0.00), rgba(122, 166, 255, 0.10), rgba(122, 166, 255, 0.00)),
    rgba(5, 10, 18, 0.18);
}

.evibank-processing-overlay::before {
  content: "";
  position: absolute;
  left: -36%;
  top: 0;
  width: 36%;
  height: 100%;
  background: linear-gradient(
    90deg,
    rgba(255,255,255,0.0) 0%,
    rgba(255,255,255,0.18) 50%,
    rgba(255,255,255,0.0) 100%
  );
  animation: evibankShimmer 1.4s linear infinite;
}

.evibank-processing-chip {
  position: absolute;
  right: 14px;
  bottom: 14px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  background: rgba(13, 22, 34, 0.84);
  color: #ecf4ff;
  border: 1px solid rgba(121, 158, 255, 0.18);
  border-radius: 999px;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 700;
  box-shadow: 0 8px 24px rgba(0,0,0,0.24);
}

.evibank-processing-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #81adff;
  box-shadow: 0 0 0 0 rgba(129, 173, 255, 0.72);
  animation: evibankPulse 1.35s ease infinite;
}

.evibank-processing-text {
  color: #eef5ff;
}

.evibank-processing-elapsed {
  color: #bcd3ff;
  font-variant-numeric: tabular-nums;
}

/* =========================================
   9. Footer
   ========================================= */
#evibank-footer {
  margin-top: 20px;
  border: 1px solid var(--ebank-border);
  border-radius: 18px;
  background: linear-gradient(180deg, var(--ebank-card) 0%, var(--ebank-card-2) 100%);
  box-shadow: var(--ebank-shadow-soft);
  padding: 14px 18px;
}

#evibank-footer-inner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

#evibank-footer-left {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--ebank-text-soft);
  font-size: 13px;
}

#evibank-footer-left strong {
  color: var(--ebank-text);
}

#evibank-footer a {
  color: var(--ebank-primary);
  text-decoration: none;
  font-weight: 700;
}

#evibank-footer a:hover {
  text-decoration: underline;
}

/* =========================================
   10. Gradio Footer / Settings
   ========================================= */
footer,
.gradio-container footer {
  display: flex !important;
  opacity: 0.92;
  padding-top: 8px !important;
}

footer a,
footer button {
  color: var(--ebank-text-soft) !important;
}

/* =========================================
   11. Animations
   ========================================= */
@keyframes evibankShimmer {
  0% { left: -36%; }
  100% { left: 136%; }
}

@keyframes evibankPulse {
  0% { box-shadow: 0 0 0 0 rgba(129, 173, 255, 0.72); }
  70% { box-shadow: 0 0 0 8px rgba(129, 173, 255, 0.0); }
  100% { box-shadow: 0 0 0 0 rgba(129, 173, 255, 0.0); }
}

@keyframes evibankFadeUp {
  from {
    opacity: 0.0;
    transform: translateY(4px);
  }
  to {
    opacity: 1.0;
    transform: translateY(0);
  }
}

@keyframes evibankOverlayFade {
  from {
    opacity: 0.0;
  }
  to {
    opacity: 1.0;
  }
}

/* =========================================
   12. Responsive
   ========================================= */
@media (max-width: 1280px) {
  .gradio-container {
    padding: 16px !important;
  }

  #evibank-header h1 {
    font-size: 30px;
  }
}

@media (max-width: 980px) {
  #evibank-header {
    padding: 22px 18px 18px 18px;
  }

  #evibank-header h1 {
    font-size: 24px;
  }

  #chat-panel,
  #right-stack {
    min-height: auto;
  }

  .evibank-panel {
    padding: 15px !important;
  }
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
                round(_safe_float(item.score, 0.0), 6),
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
    """
    尽量平滑地分段输出答案：
    1. 先按空行分块
    2. 再对较长段落做细切
    """
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


def _processing_overlay_html(scope_text: str, elapsed_seconds: float) -> str:
    return f"""
    <div class="evibank-processing-overlay">
      <div class="evibank-processing-chip">
        <span class="evibank-processing-dot"></span>
        <span class="evibank-processing-text">{escape(scope_text)}</span>
        <span class="evibank-processing-elapsed">{elapsed_seconds:.1f}s</span>
      </div>
    </div>
    """


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
        str,
        str,
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
            {
                "status": "warning",
                "message": "empty_query",
            },
            "",
            "",
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

    # 在后台执行 chat() 时，持续刷新处理中遮罩与计时器
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
            _processing_overlay_html("正在检索与生成", elapsed),
            _processing_overlay_html("正在整理证据与图示", elapsed),
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

        # 开始逐段展示答案。此阶段也保留轻量遮罩，直到最后一帧再去掉。
        for idx, frame in enumerate(frames):
            streamed_history = [
                *history,
                user_message,
                {"role": "assistant", "content": frame},
            ]

            keep_overlay = idx < len(frames) - 1
            current_elapsed = time.perf_counter() - start_time

            yield (
                streamed_history,
                streamed_history,
                "",
                evidence_summary,
                evidence_df,
                gallery_items,
                debug_info,
                _processing_overlay_html("正在渲染回答", current_elapsed) if keep_overlay else "",
                _processing_overlay_html("正在同步证据", current_elapsed) if keep_overlay else "",
            )

            if keep_overlay:
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
            "",
            "",
        )


def _clear_all() -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    str,
    str,
    pd.DataFrame,
    list[tuple[str, str | None]],
    dict[str, Any],
    str,
    str,
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
        "",
        "",
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
      <div id="evibank-footer-inner">
        <div id="evibank-footer-left">
          <span style="font-size:16px;">⭐</span>
          <span><strong>{escape(PROJECT_BRAND_NAME)}</strong> · 企业网银 FAQ 证据增强问答演示</span>
        </div>
        <div id="evibank-footer-right">
          <a href="{escape(GITHUB_REPO_URL)}" target="_blank" rel="noopener noreferrer">
            GitHub · {escape(GITHUB_REPO_NAME)}
          </a>
        </div>
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
            with gr.Column(scale=7, min_width=760, elem_classes=["evibank-column"]):
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
                        height=560,
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
                        send_btn = gr.Button(
                            "发送",
                            variant="primary",
                            size="lg",
                            elem_id="send-btn",
                        )
                        clear_btn = gr.Button(
                            "清空历史",
                            variant="secondary",
                            size="lg",
                            elem_id="clear-btn",
                        )

                    gr.HTML(
                        _panel_title_html(
                            "示例问题",
                            "点击下方问题卡片快速填充输入框，便于会议演示与功能验证。",
                        )
                    )

                    with gr.Column(elem_id="examples-wrap"):
                        row_size = 2 if len(example_questions) <= 4 else 3
                        for i in range(0, len(example_questions), row_size):
                            with gr.Row():
                                for example in example_questions[i : i + row_size]:
                                    example_btn = gr.Button(
                                        value=example,
                                        variant="secondary",
                                        size="sm",
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

                    processing_left = gr.HTML("", elem_id="processing-left")

            with gr.Column(scale=5, min_width=520, elem_classes=["evibank-column"]):
                with gr.Group(elem_classes=["evibank-panel"], elem_id="right-stack"):
                    with gr.Group(elem_classes=["evibank-panel"], elem_id="gallery-box"):
                        gr.HTML(
                            _panel_title_html(
                                "相关截图",
                                "若命中的知识条目包含图文说明，将优先在此展示辅助截图。",
                            )
                        )
                        gallery = gr.Gallery(
                            value=[],
                            show_label=False,
                            columns=2,
                            height=300,
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

                    processing_right = gr.HTML("", elem_id="processing-right")

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
            processing_left,
            processing_right,
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