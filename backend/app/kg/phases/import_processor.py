"""
Import 关系处理器

从 GitNexus gitnexus/src/core/ingestion/import-processor.ts 改写

分析文件间的 import/require 依赖关系，创建 IMPORTS 边。
支持 Python 和 JavaScript/TypeScript 的 import 解析。
"""

from __future__ import annotations

import os
import re
from typing import Optional

from app.kg.types import (
    GraphNode, GraphRelationship,
    REL_IMPORTS,
)


class ImportResolver:
    """Import 关系解析器

    将符号提取阶段收集的 import 信息解析为文件间的 IMPORTS 关系。
    处理相对路径解析（Python 和 JS/TS 的 import 路径语义）。
    """

    def __init__(self, repo_path: str, all_files: set[str]):
        """初始化

        Args:
            repo_path: 仓库根目录
            all_files: 仓库中所有文件的相对路径集合（用于路径匹配）
        """
        self.repo_path = os.path.abspath(repo_path)
        self.all_files = all_files
        # 缓存：模块名 → 文件路径
        self._module_cache: dict[str, str] = {}

    def resolve_imports(
        self, source_file: str, imports: list[tuple[str, str]],
    ) -> list[GraphRelationship]:
        """解析文件的 import 语句为 IMPORTS 关系

        Args:
            source_file: 源文件的相对路径
            imports: (module_name, alias) 列表

        Returns:
            IMPORTS 关系列表
        """
        relationships: list[GraphRelationship] = []
        source_id = f"file://{source_file.replace(os.sep, '/')}"

        for module_name, _alias in imports:
            target_file = self._resolve_module_to_file(source_file, module_name)
            if target_file:
                target_id = f"file://{target_file.replace(os.sep, '/')}"
                # 避免自引用
                if target_id == source_id:
                    continue

                rel_id = f"imports:{source_id}->{target_id}"
                relationships.append(GraphRelationship(
                    id=rel_id,
                    source_id=source_id,
                    target_id=target_id,
                    type=REL_IMPORTS,
                    properties={"module": module_name},
                ))

        return relationships

    def _resolve_module_to_file(
        self, source_file: str, module_name: str,
    ) -> Optional[str]:
        """将模块名解析为仓库内的文件路径

        处理：
        - 相对路径 (./foo, ../bar)
        - Python 包路径 (os.path, package.module)
        - JS 的目录索引 (import './components')
        """
        cache_key = f"{source_file}::{module_name}"
        if cache_key in self._module_cache:
            return self._module_cache[cache_key]

        result = self._do_resolve(source_file, module_name)
        self._module_cache[cache_key] = result  # type: ignore
        return result

    def _do_resolve(
        self, source_file: str, module_name: str,
    ) -> Optional[str]:
        entry_point = module_name

        # 去除 npm 包名中的 scope (@scope/package)
        if module_name.startswith("@"):
            # 这是一个 npm scope 包，不在本地仓库中
            return None

        # 标准库和第三方包（不在本地仓库中）
        if not module_name.startswith(".") and not module_name.startswith("/"):
            # Python 标准库或 pip 包 → 不在仓库中
            # JS 的 node_modules → 不在仓库中
            # 但如果是同一个仓库内的模块（如 from app.kg.types import X）
            # 需要尝试匹配
            return self._try_resolve_python_module(source_file, module_name)

        # 处理相对路径
        source_dir = os.path.dirname(source_file)
        if module_name.startswith("."):
            # 将 ./foo 或 ../bar 转换为相对于源文件的绝对路径
            resolved = os.path.normpath(os.path.join(source_dir, module_name))
            return self._find_file(resolved)

        # 处理绝对路径（以 / 开头）
        if module_name.startswith("/"):
            resolved = module_name.lstrip("/")
            return self._find_file(resolved)

        return None

    def _try_resolve_python_module(
        self, source_file: str, module_name: str,
    ) -> Optional[str]:
        """尝试将 Python 模块名解析为仓库内的文件"""
        # 将点号分隔的模块名转换为路径
        path_candidates = module_name.replace(".", "/")

        # 尝试不同的文件扩展名
        for ext in (".py",):
            candidate = f"{path_candidates}{ext}"
            candidate_file = self._find_file(candidate)
            if candidate_file:
                return candidate_file

        # 尝试作为包（__init__.py）
        for ext in ("/__init__.py",):
            candidate = f"{path_candidates}{ext}"
            candidate_file = self._find_file(candidate)
            if candidate_file:
                return candidate_file

        return None

    def _find_file(self, path_without_ext: str) -> Optional[str]:
        """尝试不同的扩展名和路径约定来找到文件"""
        if path_without_ext in self.all_files:
            return path_without_ext

        # 尝试加扩展名
        for ext in (".py", ".pyi", ".js", ".jsx", ".ts", ".tsx",
                    ".mjs", ".cjs", ".mts", ".cts"):
            candidate = f"{path_without_ext}{ext}"
            if candidate in self.all_files:
                return candidate

        # 尝试目录索引文件
        for index_file in (
            "/__init__.py", "/index.js", "/index.jsx",
            "/index.ts", "/index.tsx", "/index.mjs",
        ):
            candidate = f"{path_without_ext}{index_file}"
            if candidate in self.all_files:
                return candidate

        return None
