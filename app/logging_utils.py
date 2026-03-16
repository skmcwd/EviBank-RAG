from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
_ROOT_CONFIGURED = False

"""
第一步：分析多文件日志记录的潜在冲突（逻辑推理）
在 Python 的 logging 模块中，日志器（Logger）是树状的层级结构。
如果直接沿用之前的逻辑，在每个文件里都调用 setup_logging()：
文件夹分散问题：由于每个文件执行到 datetime.now() 的时间有微小差异（毫秒或秒级），会导致同一次运行生成多个不同的时间戳文件夹。
处理器（Handler）互相覆盖问题：第一版中包含 root_logger.removeHandler(handler)。如果 main.py 调用了配置，随后它导入的 model.py 也调用了配置，model.py 会把 main.py 绑定的文件句柄清空。这会导致所有日志最终都只流向最后一个被实例化的文件中。

第二步：架构重构与解决方案
全局唯一运行时间戳（Run ID）：在 logging_utils.py 模块被首次导入时，立刻生成一个时间戳变量。同一次运行中，所有后续导入该模块的文件都将共享这一个时间戳，确保它们写入同一个文件夹。
状态锁（State Flag）：引入一个全局变量 _ROOT_CONFIGURED。根日志器（负责控制台输出和旧 Handler 清理）只在第一次调用时初始化，避免重复清理导致的文件句柄丢失。
独立的分发机制：通过新增一个可选参数 module_name，让每个代码文件可以获取专属的文件日志器，互不干扰，但同时将信息向上传递给根日志器以在控制台显示。
"""


def setup_logging(
        level: str = "INFO",
        project_root: Optional[Path | str] = None,
        module_name: Optional[str] = None
) -> Path:
    """
    初始化项目级日志系统。

    功能特性：
    1. 每次运行在 logs/ 下创建独立的日期时间文件夹。
    2. 支持多文件独立落盘，自动识别主程序物理文件名与子模块名。
    3. 自动清理与冗余抑制，防止文件句柄泄露。
    """
    global _ROOT_CONFIGURED

    level_name = (level or "INFO").upper()
    log_level = getattr(logging, level_name, logging.INFO)

    # 1. 创建本次运行的专属日志文件夹
    if project_root:
        root_path = Path(project_root)
    else:
        # 核心修复：基于当前 logging_utils.py 的绝对物理路径，动态向上寻找项目根目录
        current_file_dir = Path(__file__).resolve().parent
        root_path = current_file_dir

        # 向上遍历目录树，通过项目特征文件（锚点）来准确定位根目录
        # 你的项目包含 scripts 和 data 文件夹，将其作为根目录的判断依据
        for parent in [current_file_dir, *current_file_dir.parents]:
            if (parent / "scripts").exists() or (parent / "requirements.txt").exists():
                root_path = parent
                break

    run_logs_dir = root_path / "logs" / _RUN_TIMESTAMP
    run_logs_dir.mkdir(parents=True, exist_ok=True)

    # 2. 确定当前日志文件的命名前缀 (已修复 __main__ 覆盖真实文件名的问题)
    if module_name and module_name != "__main__":
        # 如果是被其他文件 import 的子模块 (如 src.models)，取最后一部分
        file_prefix = module_name.split('.')[-1]
    else:
        # 如果是直接运行的主脚本 (module_name == "__main__") 或未传入 module_name
        # 强制从 sys.argv[0] 解析真实的物理文件路径
        if sys.argv and sys.argv[0]:
            file_prefix = Path(sys.argv[0]).stem
        else:
            file_prefix = "app"

        # 防止交互式环境解析出异常名称
        if file_prefix in ("-c", "", "__main__"):
            file_prefix = "interactive"

    # 3. 生成该文件的独立日志路径
    current_time = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = run_logs_dir / f"{file_prefix}-{current_time}.log"

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # 4. 初始化根日志器 (Root Logger) - 仅执行一次
    root_logger = logging.getLogger()
    if not _ROOT_CONFIGURED:
        root_logger.setLevel(log_level)

        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            try:
                handler.flush()
                handler.close()
            except Exception:
                pass

        console_handler = logging.StreamHandler(stream=sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

        _ROOT_CONFIGURED = True

    # 5. 配置文件专属的日志器
    target_logger = logging.getLogger(module_name) if module_name else root_logger

    if target_logger.level == logging.NOTSET or target_logger.level > log_level:
        target_logger.setLevel(log_level)

    has_target_file_handler = any(
        isinstance(h, logging.FileHandler) and Path(h.baseFilename) == log_path
        for h in target_logger.handlers
    )

    if not has_target_file_handler:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        target_logger.addHandler(file_handler)

        if target_logger is not root_logger:
            target_logger.propagate = True

    # 日志内容本身也做优化：显式打印出实际的文件前缀，便于核对
    target_logger.info("模块 [%s] 日志已挂载 -> %s", file_prefix, log_path)

    return log_path
