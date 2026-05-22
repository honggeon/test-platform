"""
继承关系提取器

从 GitNexus gitnexus/src/core/ingestion/heritage-processor.ts 改写

提取 EXTENDS / IMPLEMENTS 关系：
- Python: ast 遍历 ClassDef.bases
- JS/TS: 正则匹配 class X extends Y implements Z
"""

from __future__ import annotations

import ast
import os
import re
from typing import Callable, Optional, TYPE_CHECKING

from app.kg.types import (
    GraphRelationship,
    NODE_CLASS, NODE_INTERFACE,
    REL_EXTENDS, REL_IMPLEMENTS,
    PhaseProgress,
)

if TYPE_CHECKING:
    from app.kg.pipeline import PipelineOutput


# ── Python 继承提取 ───────────────────────────────────────────────────────


class PythonHeritageExtractor:
    """Python 继承关系提取器"""

    def extract(self, file_path: str, source: str) -> list[GraphRelationship]:
        relationships: list[GraphRelationship] = []
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError:
            return relationships

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            class_id = f"class://{file_path}::{node.name}"
            for base in node.bases:
                parent_name = self._get_base_name(base)
                if not parent_name:
                    continue
                rel = self._resolve_relationship(
                    file_path, class_id, node.name, parent_name,
                )
                if rel:
                    relationships.append(rel)
        return relationships

    @staticmethod
    def _get_base_name(node: ast.expr) -> Optional[str]:
        """从 ast.expr 提取类名"""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            # module.Class → 取 Class 名简化处理
            parts = []
            current: ast.expr = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return parts[0] if parts else None
        return None

    def _resolve_relationship(
        self, file_path: str, class_id: str, class_name: str,
        parent_name: str,
    ) -> Optional[GraphRelationship]:
        """解析继承关系类型"""
        if parent_name in ("object", "type", "Exception", "BaseException"):
            # 跳过内置基类，减少噪声
            return None

        # 启发式：如果父名以 I 开头且第二个字母大写，倾向于 IMPLEMENTS
        # 但 Python 中这不够可靠，我们默认 EXTENDS，除非明确知道是接口
        rel_type = REL_EXTENDS

        # Python 没有原生 interface，但可用 typing.Protocol / abc.ABC 等
        # 这里简化处理，后续可通过 graph 中的节点类型二次修正

        parent_id = f"class://{file_path}::{parent_name}"
        rel_id = f"{rel_type.lower()}:{class_id}->{parent_id}"

        return GraphRelationship(
            id=rel_id,
            source_id=class_id,
            target_id=parent_id,
            type=rel_type,
            properties={"parent_name": parent_name, "file_path": file_path},
        )


# ── JS/TS 继承提取 ────────────────────────────────────────────────────────


class JSHeritageExtractor:
    """JavaScript/TypeScript 继承关系提取器（基于正则）"""

    # class X extends Y
    _EXTENDS_PATTERN = re.compile(
        r'(?:export\s+)?(?:abstract\s+)?class\s+(\w+)'
        r'(?:\s+extends\s+(\w+))?',
        re.MULTILINE,
    )
    # class X implements Y1, Y2
    _IMPLEMENTS_PATTERN = re.compile(
        r'(?:export\s+)?(?:abstract\s+)?class\s+(\w+)'
        r'(?:\s+extends\s+\w+)?\s+implements\s+([\w,\s<>]+)',
        re.MULTILINE,
    )

    def extract(self, file_path: str, source: str) -> list[GraphRelationship]:
        relationships: list[GraphRelationship] = []

        # extends
        for match in self._EXTENDS_PATTERN.finditer(source):
            class_name = match.group(1)
            parent_name = match.group(2)
            if not parent_name:
                continue
            class_id = f"class://{file_path}::{class_name}"
            parent_id = f"class://{file_path}::{parent_name}"
            rel_id = f"extends:{class_id}->{parent_id}"
            relationships.append(GraphRelationship(
                id=rel_id,
                source_id=class_id,
                target_id=parent_id,
                type=REL_EXTENDS,
                properties={"parent_name": parent_name},
            ))

        # implements
        for match in self._IMPLEMENTS_PATTERN.finditer(source):
            class_name = match.group(1)
            interfaces_str = match.group(2)
            class_id = f"class://{file_path}::{class_name}"
            for iface in interfaces_str.split(','):
                iface_name = iface.strip()
                if not iface_name:
                    continue
                iface_id = f"interface://{file_path}::{iface_name}"
                # 如果 interface 不存在，fallback 到 class
                rel_id = f"implements:{class_id}->{iface_id}"
                relationships.append(GraphRelationship(
                    id=rel_id,
                    source_id=class_id,
                    target_id=iface_id,
                    type=REL_IMPLEMENTS,
                    properties={"interface_name": iface_name},
                ))

        return relationships


# ── 统一调度 ──────────────────────────────────────────────────────────────


class HeritageExtractor:
    """统一继承关系提取器"""

    def __init__(self):
        self._py = PythonHeritageExtractor()
        self._js = JSHeritageExtractor()

    def extract(self, file_path: str, source: str) -> list[GraphRelationship]:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".py", ".pyi", ".pyx"):
            return self._py.extract(file_path, source)
        elif ext in (".js", ".jsx", ".ts", ".tsx", ".mts", ".cts"):
            return self._js.extract(file_path, source)
        return []


# ── Pipeline Phase ────────────────────────────────────────────────────────


def heritage_phase(
    output: PipelineOutput,
    repo_path: str,
    on_progress: Optional[Callable[[PhaseProgress], None]] = None,
) -> None:
    """Phase: 提取继承/实现关系"""
    _report(on_progress, "heritage", 0, "提取继承关系...")

    extractor = HeritageExtractor()
    total_rels = 0
    total_files = len(output.scan_results)

    for idx, scan_result in enumerate(output.scan_results):
        ext = scan_result.extension
        if ext not in (".py", ".pyi", ".pyx", ".js", ".jsx", ".ts", ".tsx", ".mts", ".cts"):
            continue

        try:
            with open(scan_result.absolute_path, "r",
                      encoding="utf-8", errors="replace") as f:
                source = f.read()
        except (IOError, OSError):
            continue

        rels = extractor.extract(scan_result.file_path, source)
        for rel in rels:
            # 只添加目标节点已在图中的关系（避免悬空边）
            if output.graph.get_node(rel.target_id) is not None:
                output.graph.add_relationship(rel)
                total_rels += 1

        if (idx + 1) % max(1, total_files // 10) == 0:
            pct = int((idx + 1) / total_files * 100)
            _report(on_progress, "heritage", pct,
                    f"继承提取: {idx + 1}/{total_files} 文件")

    output.stats["heritage_relations"] = total_rels
    _report(on_progress, "heritage", 100,
            f"继承关系: {total_rels} 条")


def _report(callback, phase, percent, message=""):
    if callback:
        callback(PhaseProgress(phase=phase, percent=percent, message=message))
