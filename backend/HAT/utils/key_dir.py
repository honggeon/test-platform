# -*- coding: utf-8 -*-
"""HAT key_dir 路径解析与合并（全局 + 用例级）"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from HAT.core.globalContext import g_context


def init_key_dirs_from_cli(key_dir_option: str | None) -> None:
    """从 pytest --keyDir 初始化 key_dirs（支持 os.pathsep 分隔的多路径）。"""
    key_dirs: list[str] = []
    if key_dir_option:
        for part in key_dir_option.split(os.pathsep):
            part = part.strip()
            if not part:
                continue
            resolved = Path(part).resolve()
            if resolved.is_dir():
                path_str = str(resolved)
                if path_str not in key_dirs:
                    key_dirs.append(path_str)
    g_context().set_dict("key_dirs", key_dirs)
    if key_dirs:
        g_context().set_dict("key_dir", key_dirs[0])


def merge_case_key_dir(suite_folder: str | Path, local_key_dir: str | None) -> None:
    """将 context.yaml 中的 key_dir 解析为用例目录下的绝对路径并合并。"""
    if not local_key_dir:
        return

    candidate = Path(local_key_dir)
    if not candidate.is_absolute():
        candidate = (Path(suite_folder) / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if not candidate.is_dir():
        return

    key_dirs = list(g_context().get_dict("key_dirs") or [])
    path_str = str(candidate)
    if path_str not in key_dirs:
        key_dirs.append(path_str)
    g_context().set_dict("key_dirs", key_dirs)


def get_key_dirs() -> list[str]:
    """返回当前生效的全部 key_dir 路径。"""
    dirs = g_context().get_dict("key_dirs")
    if dirs:
        return list(dirs)
    single = g_context().get_dict("key_dir")
    return [single] if single else []


def ensure_key_dirs_on_syspath() -> list[str]:
    """将 key_dirs 追加到 sys.path，返回已追加的路径列表。"""
    appended: list[str] = []
    for key_dir in get_key_dirs():
        if key_dir not in sys.path:
            sys.path.append(key_dir)
            appended.append(key_dir)
    return appended
