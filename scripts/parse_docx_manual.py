from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph
from pydantic import ValidationError

# 兼容直接执行：
# python scripts/parse_docx_manual.py --input ... --output ...
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.logging_utils import setup_logging  # noqa: E402
from app.models import KBChunk  # noqa: E402

logger = logging.getLogger(__name__)

WHITESPACE_RE = re.compile(r"\s+")
HEADING_NUM_RE = re.compile(
    r"^(第[一二三四五六七八九十百零\d]+[章节部分]|[一二三四五六七八九十]+、|\d+(\.\d+){0,3}\s+|\d+(\.\d+){0,3}[、.])"
)

CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("代发", ("代发", "工资发放", "批量发放", "代发工资")),
    ("查询", ("查询", "明细", "余额", "流水", "对账", "检索")),
    ("登录", ("登录", "登陆", "用户名", "密码", "验证码", "认证")),
    ("权限", ("权限", "授权", "复核", "审批", "操作员", "管理员")),
    ("账号权限", ("账号权限", "账户权限", "账号管理", "账户管理", "账户设置")),
    ("回单", ("回单", "回执", "电子回单", "回单下载", "回单打印")),
    ("转账", ("转账", "汇款", "付款", "支付", "单笔转账", "批量转账")),
    ("UKey", ("ukey", "u-key", "usbkey", "uk", "证书介质")),
    ("证书", ("证书", "ca", "签名证书", "证书更新", "证书下载", "证书过期")),
    ("控件", ("控件", "插件", "安全控件", "浏览器控件", "activex", "edge插件", "ie控件")),
]

# 当文档没有明确标题时，按自然段落切分的参考阈值
NATURAL_BREAK_MIN_CHARS = 180
TITLE_MAX_LEN = 36


class AppParseError(RuntimeError):
    """文档解析过程中的统一异常。"""


def normalize_text(value: Any) -> str:
    """
    统一文本清洗：
    1. None 安全处理
    2. 压缩连续空白
    3. 去除首尾空白
    """
    if value is None:
        return ""
    text = str(value).replace("\u3000", " ")
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


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


def relative_to_project(path: Path) -> str:
    """
    优先返回相对项目根目录的路径，便于后续前端或索引复用。
    """
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def ensure_dir(path: Path) -> None:
    """
    确保目录存在。
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AppParseError(f"创建目录失败：{path}") from exc


def find_powershell() -> str:
    """
    定位 PowerShell 可执行文件。
    仅在 .doc 自动转换时使用。
    """
    candidates = [
        shutil.which("powershell"),
        shutil.which("PowerShell"),
        shutil.which("pwsh"),
    ]
    for item in candidates:
        if item:
            return item
    raise AppParseError("未找到 PowerShell，无法执行 .doc 到 .docx 的自动转换。")


def convert_doc_to_docx(input_path: Path, converted_dir: Path) -> Path:
    """
    将 .doc 自动转换为 .docx。

    实现方式：
    - 仅在 Windows 上可用
    - 通过 PowerShell 调用 Word COM 完成转换
    - 需要本机安装 Microsoft Word

    若输入已经是 .docx，则直接返回原路径。
    """
    suffix = input_path.suffix.lower()
    if suffix == ".docx":
        return input_path

    if suffix != ".doc":
        raise AppParseError(f"不支持的文档类型：{input_path.suffix}")

    if os.name != "nt":
        raise AppParseError(".doc 自动转换仅支持 Windows 环境。")

    ensure_dir(converted_dir)

    output_path = converted_dir / f"{input_path.stem}.auto_converted.docx"
    powershell_exe = find_powershell()

    ps_script = r"""
param(
    [string]$InputPath,
    [string]$OutputPath
)

$wdFormatXMLDocument = 16
$word = $null
$doc = $null

try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $doc = $word.Documents.Open($InputPath, $false, $true)
    $doc.SaveAs([ref]$OutputPath, [ref]$wdFormatXMLDocument)
    $doc.Close()
    $doc = $null
    $word.Quit()
    $word = $null
    exit 0
}
catch {
    Write-Error $_
    exit 1
}
finally {
    if ($doc -ne $null) {
        try { $doc.Close() } catch {}
    }
    if ($word -ne $null) {
        try { $word.Quit() } catch {}
    }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}
""".strip()

    tmp_script_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".ps1",
                delete=False,
                encoding="utf-8",
        ) as f:
            f.write(ps_script)
            tmp_script_path = Path(f.name)

        logger.info("检测到 .doc 文件，开始自动转换为 .docx：%s", input_path)

        result = subprocess.run(
            [
                powershell_exe,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(tmp_script_path),
                str(input_path.resolve()),
                str(output_path.resolve()),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        if result.returncode != 0 or not output_path.exists():
            stderr = normalize_text(result.stderr)
            stdout = normalize_text(result.stdout)
            raise AppParseError(
                "Word COM 转换失败。请确认："
                "1) 当前系统为 Windows；"
                "2) 已安装 Microsoft Word；"
                "3) 文档未被占用；"
                f" stdout={stdout} stderr={stderr}"
            )

        logger.info("已完成 .doc -> .docx 转换：%s", output_path)
        return output_path

    except FileNotFoundError as exc:
        raise AppParseError("调用 PowerShell 失败，系统未找到对应可执行文件。") from exc
    except subprocess.SubprocessError as exc:
        raise AppParseError("执行 .doc 自动转换时出现子进程异常。") from exc
    finally:
        if tmp_script_path and tmp_script_path.exists():
            try:
                tmp_script_path.unlink()
            except OSError:
                pass


def load_document(input_path: Path) -> tuple[Document, Path]:
    """
    加载 doc/docx 文档。
    若为 .doc，会自动转换为 .docx 后再读取。
    """
    if not input_path.exists():
        raise AppParseError(f"输入文件不存在：{input_path}")
    if not input_path.is_file():
        raise AppParseError(f"输入路径不是文件：{input_path}")

    converted_dir = PROJECT_ROOT / "data" / "parsed" / "converted"
    docx_path = convert_doc_to_docx(input_path, converted_dir=converted_dir)

    try:
        doc = Document(str(docx_path))
    except Exception as exc:
        raise AppParseError(f"读取 DOCX 失败：{docx_path}") from exc

    return doc, docx_path


def iter_block_paragraphs(parent: DocxDocument | _Cell) -> Iterator[Paragraph]:
    """
    按文档中出现的顺序递归遍历段落。
    说明：
    - 支持正文段落
    - 支持表格单元格中的段落
    - 便于尽量保持手册中的原始顺序
    """
    if isinstance(parent, DocxDocument):
        parent_element = parent.element.body
    elif isinstance(parent, _Cell):
        parent_element = parent._tc
    else:
        raise TypeError(f"不支持的 parent 类型：{type(parent)!r}")

    for child in parent_element.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            table = Table(child, parent)
            for row in table.rows:
                for cell in row.cells:
                    yield from iter_block_paragraphs(cell)


def paragraph_has_picture(paragraph: Paragraph) -> bool:
    """
    判断段落是否包含内嵌图片。
    """
    for blip in paragraph._p.iter(qn("a:blip")):
        rel_id = blip.get(qn("r:embed"))
        if rel_id:
            return True
    return False


def save_paragraph_images(
        paragraph: Paragraph,
        *,
        doc: Document,
        image_dir: Path,
        source_stem: str,
        para_index: int,
        image_cache: dict[str, str],
) -> list[str]:
    """
    提取指定段落中的内嵌图片并保存到本地。
    返回该段落关联的图片路径列表。
    """
    image_paths: list[str] = []

    for blip in paragraph._p.iter(qn("a:blip")):
        rel_id = blip.get(qn("r:embed"))
        if not rel_id:
            continue

        if rel_id in image_cache:
            image_paths.append(image_cache[rel_id])
            continue

        image_part = doc.part.related_parts.get(rel_id)
        if image_part is None:
            continue

        ext = Path(str(image_part.partname)).suffix.lower() or ".png"
        output_path = image_dir / f"{source_stem}_{rel_id}{ext}"

        try:
            output_path.write_bytes(image_part.blob)
        except OSError as exc:
            logger.warning("保存图片失败：%s，err=%s", output_path, exc)
            continue

        relative_path = relative_to_project(output_path)
        image_cache[rel_id] = relative_path
        image_paths.append(relative_path)

    return unique_keep_order(image_paths)


def is_heading_paragraph(paragraph: Paragraph, text: str) -> bool:
    """
    判断段落是否可视为标题。

    判定依据：
    1. 样式名包含 Heading / 标题
    2. 明显的章节编号模式
    3. 文本较短、像章节标题而非叙述句
    """
    if not text:
        return False

    style_name = normalize_text(getattr(getattr(paragraph, "style", None), "name", ""))
    style_name_lower = style_name.casefold()

    if "heading" in style_name_lower or "标题" in style_name:
        return True

    if HEADING_NUM_RE.match(text) and len(text) <= 60:
        return True

    if len(text) <= 24 and not re.search(r"[。；;：:，,]", text):
        if not text.startswith("注：") and not text.startswith("说明："):
            return True

    return False


def infer_title(title_hint: str | None, paragraphs: list[str], chunk_no: int) -> str:
    """
    生成 chunk 标题。
    优先级：
    1. 标题段
    2. 首段主题句
    3. 兜底标题
    """
    if title_hint:
        title = normalize_text(title_hint)
        if title:
            return title[:TITLE_MAX_LEN]

    if paragraphs:
        first = normalize_text(paragraphs[0])
        if first:
            return first[:TITLE_MAX_LEN]

    return f"操作手册片段-{chunk_no}"


def infer_category(text: str) -> str | None:
    """
    基于规则粗分类。
    """
    content = normalize_text(text).casefold()
    if not content:
        return None

    for category, keywords in CATEGORY_RULES:
        for kw in keywords:
            if kw.casefold() in content:
                return category

    return None


def extract_keywords(category: str | None, title: str, paragraphs: list[str]) -> list[str]:
    """
    提取轻量关键词。
    这里不依赖分词库，采用规则法，保证脚本轻量稳定。
    """
    candidates: list[str] = []

    if category:
        candidates.append(category)

    for item in [title, *paragraphs[:2]]:
        text = normalize_text(item)
        if not text:
            continue
        parts = re.split(r"[，,。；;：:、/（）()\[\]【】《》\s]+", text)
        for part in parts:
            part = normalize_text(part)
            if 2 <= len(part) <= 20:
                candidates.append(part)

    return unique_keep_order(candidates)[:12]


def build_full_text(title: str, category: str | None, paragraphs: list[str], image_count: int) -> str:
    """
    构造适合 embedding 的自然语言文本。
    目标是把结构信息、主题和流程描述组织成完整语义串。
    """
    body = "。".join(p.strip("。") for p in paragraphs if normalize_text(p))
    parts: list[str] = [f"本节主题：{title}"]

    if category:
        parts.append(f"业务分类：{category}")

    if body:
        parts.append(f"操作说明：{body}")

    if image_count > 0:
        parts.append(f"本节包含 {image_count} 张配图，可辅助理解操作步骤")

    return "。".join(parts).strip("。") + "。"


def compute_chunk_hash(source_file: str, title: str, full_text: str) -> str:
    """
    为知识块生成稳定哈希。
    """
    raw = f"{source_file}||{title}||{full_text}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_chunk(
        *,
        source_file: str,
        chunk_no: int,
        title_hint: str | None,
        paragraphs: list[str],
        image_paths: list[str],
) -> KBChunk | None:
    """
    将一个手册片段构造为 KBChunk。
    当片段既无文本也无图片时，返回 None。
    """
    clean_paragraphs = [normalize_text(p) for p in paragraphs if normalize_text(p)]
    image_paths = unique_keep_order([p for p in image_paths if normalize_text(p)])

    if not clean_paragraphs and not image_paths and not normalize_text(title_hint):
        return None

    title = infer_title(title_hint=title_hint, paragraphs=clean_paragraphs, chunk_no=chunk_no)
    category = infer_category(" ".join([title, *clean_paragraphs]))
    full_text = build_full_text(
        title=title,
        category=category,
        paragraphs=clean_paragraphs,
        image_count=len(image_paths),
    )
    keywords = extract_keywords(category=category, title=title, paragraphs=clean_paragraphs)
    chunk_hash = compute_chunk_hash(source_file=source_file, title=title, full_text=full_text)

    return KBChunk(
        doc_id=f"{Path(source_file).stem}-chunk-{chunk_no:03d}",
        source_file=source_file,
        source_type="docx",
        title=title,
        category=category,
        question=None,
        answer=None,
        full_text=full_text,
        keywords=keywords,
        image_paths=image_paths,
        page_no=None,
        slide_no=None,
        priority=1.1,  # 高于 ppt 默认优先级
        chunk_hash=chunk_hash,
    )


def should_flush_on_blank(current_paragraphs: list[str], current_images: list[str]) -> bool:
    """
    在没有明确标题的情况下，遇到空段时是否应切分 chunk。
    规则：
    - 已累积足够正文长度时切分
    - 或当前片段有图片且已有一定文本时切分
    """
    total_chars = sum(len(p) for p in current_paragraphs)
    if total_chars >= NATURAL_BREAK_MIN_CHARS:
        return True
    if current_images and total_chars >= 60:
        return True
    return False


def parse_docx_manual(input_path: Path, image_dir: Path) -> list[KBChunk]:
    """
    解析企业网银操作手册 DOC/DOCX 并输出知识块列表。

    切分策略：
    1. 优先按标题切分
    2. 若标题不明显，则按空段和自然段落规模切分
    3. 每个 chunk 尽量对应“一节”或“一个流程说明”
    """
    ensure_dir(image_dir)

    doc, effective_docx_path = load_document(input_path)
    source_file = effective_docx_path.name
    source_stem = effective_docx_path.stem

    chunks: list[KBChunk] = []
    image_cache: dict[str, str] = {}

    current_title: str | None = None
    current_paragraphs: list[str] = []
    current_image_paths: list[str] = []
    chunk_no = 0
    para_index = 0

    logger.info("开始解析文档：source=%s", effective_docx_path)

    def flush_current() -> None:
        nonlocal chunk_no, current_title, current_paragraphs, current_image_paths

        chunk = build_chunk(
            source_file=source_file,
            chunk_no=chunk_no + 1,
            title_hint=current_title,
            paragraphs=current_paragraphs,
            image_paths=current_image_paths,
        )
        if chunk is None:
            current_title = None
            current_paragraphs = []
            current_image_paths = []
            return

        try:
            validated = KBChunk.model_validate(chunk.model_dump())
        except ValidationError as exc:
            logger.warning("chunk 校验失败，已跳过：title=%s err=%s", current_title, exc)
        else:
            chunks.append(validated)
            chunk_no += 1

        current_title = None
        current_paragraphs = []
        current_image_paths = []

    for paragraph in iter_block_paragraphs(doc):
        para_index += 1

        text = normalize_text(paragraph.text)
        para_images = save_paragraph_images(
            paragraph,
            doc=doc,
            image_dir=image_dir,
            source_stem=source_stem,
            para_index=para_index,
            image_cache=image_cache,
        )

        # 标题：先结束上一块，再开启新块
        if is_heading_paragraph(paragraph, text):
            if current_title or current_paragraphs or current_image_paths:
                flush_current()
            current_title = text
            current_image_paths.extend(para_images)
            continue

        # 空段：作为自然切分信号
        if not text and not para_images:
            if should_flush_on_blank(current_paragraphs, current_image_paths):
                flush_current()
            continue

        if text:
            current_paragraphs.append(text)

        if para_images:
            current_image_paths.extend(para_images)

        # 若当前没有标题，且正文很长，则在自然边界处切分，避免 chunk 过大
        total_chars = sum(len(p) for p in current_paragraphs)
        if total_chars >= 700:
            flush_current()

    # 收尾
    if current_title or current_paragraphs or current_image_paths:
        flush_current()

    logger.info(
        "文档解析完成：input=%s, effective_docx=%s, chunks=%s, extracted_images=%s",
        input_path,
        effective_docx_path,
        len(chunks),
        len(image_cache),
    )
    return chunks


def save_chunks_to_jsonl(chunks: list[KBChunk], output_path: Path) -> None:
    """
    保存为 JSONL，每行一个 KBChunk。
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
        raise AppParseError(f"写入 JSONL 失败：{output_path}") from exc

    logger.info("JSONL 已保存：%s（共 %s 条）", output_path, len(chunks))


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。
    """
    parser = argparse.ArgumentParser(
        description="解析企业网银操作手册 DOC/DOCX，输出结构化 KBChunk JSONL。"
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="输入文档路径，例如 data/raw/manual.docx 或 data/raw/manual.doc",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="输出 JSONL 路径，例如 data/parsed/manual_chunks.jsonl",
    )
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "parsed" / "images",
        help="图片输出目录，默认 data/parsed/images/",
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

    input_path = args.input.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    image_dir = args.image_dir.expanduser().resolve()

    logger.info("启动解析任务：input=%s output=%s image_dir=%s", input_path, output_path, image_dir)

    try:
        chunks = parse_docx_manual(input_path=input_path, image_dir=image_dir)
        save_chunks_to_jsonl(chunks=chunks, output_path=output_path)
        return 0
    except Exception as exc:
        logger.exception("执行失败：%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
