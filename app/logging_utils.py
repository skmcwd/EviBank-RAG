from __future__ import annotations

import logging
import sys


_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """
    初始化应用全局日志配置。

    特性：
    - 使用标准库 logging
    - 输出到控制台
    - 避免重复添加处理器
    - 兼容 Windows / Python 3.12
    """
    level_name = (level or "INFO").upper()
    log_level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # 清理已有处理器，避免重复初始化时产生重复日志
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)

    # 可选：抑制部分第三方库过于冗长的日志
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)