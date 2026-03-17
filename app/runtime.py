from __future__ import annotations

import sys
from pathlib import Path


def get_runtime_root() -> Path:
    """
    返回程序运行根目录。
    - 开发环境：项目根目录
    - PyInstaller 打包后：exe 所在目录
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent