from __future__ import annotations

import sys
from pathlib import Path


def _looks_like_runtime_root(path: Path) -> bool:
    """
    判断某个目录是否像“项目运行根目录”：
    只要存在 config / data / .env 中任意一种，就认为是候选运行根目录。
    """
    return (
            (path / "config").exists()
            or (path / "data").exists()
            or (path / ".env").exists()
    )


def get_runtime_root() -> Path:
    """
    返回程序运行根目录。

    开发环境：
        项目根目录

    打包后：
        优先尝试 exe 所在目录；
        若 exe 所在目录的上一级更像项目根目录（例如 app/ 或 rebuild/ 子目录结构），
        则返回上一级目录。
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent

        # 先看 exe 同级目录
        if _looks_like_runtime_root(exe_dir):
            return exe_dir

        # 再看 exe 上一级目录（适配 app/、rebuild/ 子目录）
        parent_dir = exe_dir.parent
        if _looks_like_runtime_root(parent_dir):
            return parent_dir

        # 最后兜底
        return exe_dir

    return Path(__file__).resolve().parent.parent