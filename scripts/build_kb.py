from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from markdown_it.rules_core.normalize import NULL_RE
from pydantic import ValidationError

# 兼容直接执行：
# python scripts/build_kb.py --input a.jsonl b.jsonl --output data/parsed/kb.jsonl
# PROJECT_ROOT = Path(__file__).resolve().parent.parent
from app.runtime import get_runtime_root

PROJECT_ROOT = get_runtime_root()

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.logging_utils import setup_logging  # noqa: E402
from app.models import KBChunk  # noqa: E402

logger = logging.getLogger(__name__)

WHITESPACE_RE = re.compile(r"\s+")
SPLIT_RE = re.compile(r"[，,。；;：:、/\\|（）()\[\]【】《》<>\-—_\s]+")
DEFAULT_PRIORITY_BY_SOURCE_TYPE: dict[str, float] = {
    "docx": 1.1,
    "excel": 1.0,
    "ppt": 0.95,
}


class KBBuildError(RuntimeError):
    """知识库构建阶段的统一异常。"""


def normalize_text(value: Any) -> str:
    """
    文本归一化：
    1. None 安全处理
    2. 全角空格转半角空格
    3. 连续空白折叠
    4. 去除首尾空白
    """
    if value is None:
        return ""
    text = str(value).replace("\u3000", " ")
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def normalize_optional_text(value: Any) -> str | None:
    """
    将文本标准化为可选字符串。
    空值或空白字符串统一转为 None。
    """
    text = normalize_text(value)
    return text or None


def ensure_dir(path: Path) -> None:
    """
    确保目录存在。
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise KBBuildError(f"创建目录失败：{path}") from exc


def stable_chunk_hash(source_file: str, title: str, full_text: str) -> str:
    """
    生成稳定哈希，用于统一去重。

    设计原则：
    - 仅基于稳定语义字段
    - 不依赖运行时顺序
    - 适合后续增量更新与重复构建
    """
    payload = "||".join(
        [
            normalize_text(source_file).casefold(),
            normalize_text(title),
            normalize_text(full_text),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def infer_source_type(source_type: Any, source_file: str, input_file: Path) -> str:
    """
    推断 source_type。
    优先级：
    1. 记录内已有 source_type
    2. 根据 source_file 后缀推断
    3. 根据输入 jsonl 文件名推断
    """
    text = normalize_text(source_type).lower()
    if text in {"excel", "ppt", "docx"}:
        return text

    candidates = [
        Path(source_file).suffix.lower(),
        input_file.stem.lower(),
        input_file.name.lower(),
    ]

    for item in candidates:
        if item in {".xlsx", ".xls", ".xlsm"} or "excel" in item:
            return "excel"
        if item in {".ppt", ".pptx", ".pptm"} or "ppt" in item:
            return "ppt"
        if item in {".doc", ".docx"} or "docx" in item or "manual" in item:
            return "docx"

    return "excel"


def default_priority_for_source_type(source_type: str) -> float:
    """
    返回 source_type 的默认优先级。
    """
    return DEFAULT_PRIORITY_BY_SOURCE_TYPE.get(source_type, 1.0)


def coerce_str_list(value: Any) -> list[str]:
    """
    将输入转换为字符串列表。
    兼容：
    - None
    - 单个字符串
    - 普通列表
    """
    if value is None:
        return []

    if isinstance(value, list):
        result = [normalize_text(item) for item in value]
        return [item for item in result if item]

    if isinstance(value, str):
        text = normalize_text(value)
        if not text:
            return []
        return [text]

    text = normalize_text(value)
    return [text] if text else []


def unique_keep_order(items: list[str]) -> list[str]:
    """
    保持原顺序去重。
    """
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def derive_title(
        *,
        title: str | None,
        question: str | None,
        full_text: str,
        source_file: str,
) -> str:
    """
    自动补全标题。
    优先级：
    1. 原 title
    2. question
    3. full_text 首句
    4. 来源文件名
    """
    if title:
        return title

    if question:
        return question[:40]

    text = normalize_text(full_text)
    if text:
        first = re.split(r"[。；;！？!?]", text, maxsplit=1)[0].strip()
        if first:
            return first[:40]

    return Path(source_file).stem[:40] or "未命名知识块"


def build_full_text(
        *,
        full_text: str | None,
        category: str | None,
        title: str,
        question: str | None,
        answer: str | None,
) -> str:
    """
    自动补全 full_text。
    目标是形成适合 embedding 的自然语言文本。
    """
    if full_text and normalize_text(full_text):
        text = normalize_text(full_text)
        return text if text.endswith("。") else f"{text}。"

    parts: list[str] = [f"主题：{title}"]
    if category:
        parts.append(f"分类：{category}")
    if question:
        parts.append(f"问题：{question}")
    if answer:
        parts.append(f"解答：{answer}")

    result = "。".join(part.strip("。") for part in parts if normalize_text(part)).strip("。")
    return f"{result}。" if result else ""


def derive_keywords(
        *,
        category: str | None,
        title: str,
        question: str | None,
        source_type: str,
        max_keywords: int = 12,
) -> list[str]:
    """
    自动补全 keywords。
    使用轻量规则法，不依赖分词框架。
    """
    candidates: list[str] = []

    if category:
        candidates.append(category)

    candidates.append(title)

    if question:
        candidates.append(question)

    candidates.append(source_type)

    parts: list[str] = []
    for item in candidates:
        text = normalize_text(item)
        if not text:
            continue
        parts.extend(SPLIT_RE.split(text))
        alpha_num_tokens = re.findall(r"[A-Za-z][A-Za-z0-9._-]*|\d+[A-Za-z0-9._-]*", text)
        parts.extend(alpha_num_tokens)

    result: list[str] = []
    seen: set[str] = set()

    for item in parts:
        token = normalize_text(item)
        if not token:
            continue
        if len(token) < 2 or len(token) > 24:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(token)
        if len(result) >= max_keywords:
            break

    return result


def safe_int(value: Any) -> int | None:
    """
    尝试将值转为 int；失败则返回 None。
    """
    if value is None:
        return None
    text = normalize_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def safe_float(value: Any) -> float | None:
    """
    尝试将值转为 float；失败则返回 None。
    """
    if value is None:
        return None
    text = normalize_text(value)
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def make_doc_id(source_file: str, chunk_hash: str, raw_doc_id: Any) -> str:
    """
    自动补全 doc_id。
    """
    doc_id = normalize_text(raw_doc_id)
    if doc_id:
        return doc_id
    stem = Path(source_file).stem or "chunk"
    return f"{stem}-{chunk_hash[:12]}"


def canonicalize_record(raw: dict[str, Any], input_file: Path) -> KBChunk:
    """
    将原始 JSON 记录标准化并校验为 KBChunk。

    处理内容：
    - 统一文本清洗
    - 自动补全缺失字段
    - 统一重算 chunk_hash
    - 统一补全 priority / keywords / image_paths
    """
    source_file = normalize_text(raw.get("source_file")) or input_file.name
    source_type = infer_source_type(raw.get("source_type"), source_file, input_file)

    category = normalize_optional_text(raw.get("category"))
    question = normalize_optional_text(raw.get("question"))
    answer = normalize_optional_text(raw.get("answer"))
    title = normalize_optional_text(raw.get("title"))
    full_text_raw = normalize_optional_text(raw.get("full_text"))

    title_final = derive_title(
        title=title,
        question=question,
        full_text=full_text_raw or "",
        source_file=source_file,
    )
    full_text_final = build_full_text(
        full_text=full_text_raw,
        category=category,
        title=title_final,
        question=question,
        answer=answer,
    )

    chunk_hash = stable_chunk_hash(
        source_file=source_file,
        title=title_final,
        full_text=full_text_final,
    )

    image_paths = unique_keep_order(coerce_str_list(raw.get("image_paths")))

    raw_priority = safe_float(raw.get("priority"))
    priority = (
        raw_priority
        if raw_priority is not None and raw_priority > 0
        else default_priority_for_source_type(source_type)
    )

    raw_keywords = unique_keep_order(coerce_str_list(raw.get("keywords")))
    keywords = raw_keywords or derive_keywords(
        category=category,
        title=title_final,
        question=question,
        source_type=source_type,
    )

    page_no = safe_int(raw.get("page_no"))
    slide_no = safe_int(raw.get("slide_no"))

    doc_id = make_doc_id(source_file=source_file, chunk_hash=chunk_hash, raw_doc_id=raw.get("doc_id"))

    normalized_payload: dict[str, Any] = {
        "doc_id": doc_id,
        "source_file": source_file,
        "source_type": source_type,
        "title": title_final,
        "category": category,
        "question": question,
        "answer": answer,
        "full_text": full_text_final,
        "keywords": keywords,
        "image_paths": image_paths,
        "page_no": page_no,
        "slide_no": slide_no,
        "priority": priority,
        "chunk_hash": chunk_hash,
    }

    try:
        return KBChunk.model_validate(normalized_payload)
    except ValidationError as exc:
        raise KBBuildError(f"KBChunk 校验失败：source_file={source_file}, title={title_final}") from exc


def iter_jsonl_records(file_path: Path) -> list[dict[str, Any]]:
    """
    读取单个 JSONL 文件中的全部记录。
    """
    if not file_path.exists():
        raise KBBuildError(f"输入文件不存在：{file_path}")
    if not file_path.is_file():
        raise KBBuildError(f"输入路径不是文件：{file_path}")
    if file_path.suffix.lower() != ".jsonl":
        raise KBBuildError(f"输入文件不是 .jsonl：{file_path}")

    records: list[dict[str, Any]] = []

    try:
        with file_path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise KBBuildError(
                        f"JSONL 解析失败：file={file_path}, line={line_no}"
                    ) from exc

                if not isinstance(obj, dict):
                    raise KBBuildError(
                        f"JSONL 行必须是对象：file={file_path}, line={line_no}"
                    )

                records.append(obj)
    except OSError as exc:
        raise KBBuildError(f"读取 JSONL 失败：{file_path}") from exc

    return records


def merge_kb_chunks(input_files: list[Path]) -> tuple[list[KBChunk], dict[str, Any]]:
    """
    合并多个解析结果文件，输出去重后的 KBChunk 列表与统计信息。
    """
    unique_chunks: dict[str, KBChunk] = {}
    total_input_records = 0
    invalid_record_count = 0
    duplicate_removed_count = 0
    replaced_by_higher_priority_count = 0

    for input_file in input_files:
        logger.info("开始处理输入文件：%s", input_file)
        raw_records = iter_jsonl_records(input_file)

        for idx, raw in enumerate(raw_records, start=1):
            total_input_records += 1
            try:
                chunk = canonicalize_record(raw=raw, input_file=input_file)
            except Exception as exc:
                invalid_record_count += 1
                logger.warning(
                    "跳过无效记录：file=%s, record_index=%s, err=%s",
                    input_file,
                    idx,
                    exc,
                )
                continue

            existing = unique_chunks.get(chunk.chunk_hash)
            if existing is None:
                unique_chunks[chunk.chunk_hash] = chunk
                continue

            duplicate_removed_count += 1

            # 去重时保留优先级更高的版本；若优先级相同则保留先出现者
            if chunk.priority > existing.priority:
                unique_chunks[chunk.chunk_hash] = chunk
                replaced_by_higher_priority_count += 1
                logger.debug(
                    "重复 chunk 用更高优先级版本替换：hash=%s old=%s/%s new=%s/%s",
                    chunk.chunk_hash,
                    existing.source_type,
                    existing.priority,
                    chunk.source_type,
                    chunk.priority,
                )

    merged = sorted(
        unique_chunks.values(),
        key=lambda item: (
            item.source_type,
            item.source_file,
            item.title,
            item.doc_id,
            item.chunk_hash,
        ),
    )

    source_type_counter = Counter(chunk.source_type or "unknown" for chunk in merged)
    category_counter = Counter(chunk.category or "未分类" for chunk in merged)

    stats: dict[str, Any] = {
        "total_input_files": len(input_files),
        "input_files": [str(path) for path in input_files],
        "total_input_records": total_input_records,
        "invalid_record_count": invalid_record_count,
        "duplicate_removed_count": duplicate_removed_count,
        "replaced_by_higher_priority_count": replaced_by_higher_priority_count,
        "total_unique_chunks": len(merged),
        "by_source_type": dict(sorted(source_type_counter.items())),
        "by_category": dict(sorted(category_counter.items())),
    }

    return merged, stats


def write_kb_jsonl(chunks: list[KBChunk], output_path: Path) -> None:
    """
    写出最终合并后的 kb.jsonl。
    """
    ensure_dir(output_path.parent)

    try:
        with output_path.open("w", encoding="utf-8") as f:
            for chunk in chunks:
                line = json.dumps(
                    chunk.model_dump(mode="json", exclude_none=False),
                    ensure_ascii=False,
                )
                f.write(line + "\n")
    except OSError as exc:
        raise KBBuildError(f"写入 kb.jsonl 失败：{output_path}") from exc

    logger.info("已写出知识库文件：%s，条数=%s", output_path, len(chunks))


def write_stats_json(stats: dict[str, Any], stats_path: Path) -> None:
    """
    写出统计文件。
    """
    ensure_dir(stats_path.parent)

    try:
        with stats_path.open("w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        raise KBBuildError(f"写入统计文件失败：{stats_path}") from exc

    logger.info("已写出统计文件：%s", stats_path)


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。
    """
    parser = argparse.ArgumentParser(
        description="合并 Excel/PPT/DOCX 解析结果为统一知识库 kb.jsonl。"
    )
    parser.add_argument(
        "--input", "--inputs",  # 兼容两种输入
        nargs="+",
        required=True,
        type=Path,
        help="一个或多个输入 jsonl 文件路径",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="输出 kb.jsonl 路径，例如 data/parsed/kb.jsonl",
    )
    parser.add_argument(
        "--stats-output",
        type=Path,
        default=None,
        help="统计文件输出路径；默认与 kb.jsonl 同目录，文件名为 kb_stats.json",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="日志级别，例如 DEBUG / INFO / WARNING / ERROR",
    )
    return parser.parse_args()


def main() -> int:
    """
    命令行主入口。
    """
    args = parse_args()
    setup_logging(args.log_level, module_name=__name__)
    # 这里直接读取 args.input 即可，无需 if/else 判定
    input_files = [path.expanduser().resolve() for path in args.input]

    output_path = args.output.expanduser().resolve()
    stats_output = (
        args.stats_output.expanduser().resolve()
        if args.stats_output is not None
        else output_path.parent / "kb_stats.json"
    )

    logger.info(
        "开始构建统一知识库：inputs=%s, output=%s, stats_output=%s",
        input_files,
        output_path,
        stats_output,
    )

    try:
        merged_chunks, stats = merge_kb_chunks(input_files=input_files)
        write_kb_jsonl(chunks=merged_chunks, output_path=output_path)
        write_stats_json(stats=stats, stats_path=stats_output)
        return 0
    except Exception as exc:
        logger.exception("构建知识库失败：%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
