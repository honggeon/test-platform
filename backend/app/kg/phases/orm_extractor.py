"""
ORM 查询提取器

从 GitNexus gitnexus/src/core/ingestion/pipeline-phases/orm.ts 改写

提取 ORM 查询并创建 CodeElement 节点 + QUERIES 边。
支持 SQLAlchemy、Django ORM、Prisma、Supabase。
"""

from __future__ import annotations

import os
import re
from typing import Callable, Optional, TYPE_CHECKING

from app.kg.types import (
    GraphNode, GraphRelationship,
    NODE_CODE_ELEMENT, REL_QUERIES,
    PhaseProgress,
)

if TYPE_CHECKING:
    from app.kg.pipeline import PipelineOutput


# ── ORM 检测模式 ──────────────────────────────────────────────────────────


class ORMExtractor:
    """ORM 查询提取器"""

    # Django: ModelName.objects.filter(...)
    _DJANGO_PATTERN = re.compile(
        r'(\w+)\.objects\.(get|filter|create|update|delete|all|first|last)',
        re.MULTILINE,
    )

    # SQLAlchemy: session.query(ModelName)
    _SQLALCHEMY_PATTERN = re.compile(
        r'(?:session|db)\.query\((\w+)\)',
        re.IGNORECASE | re.MULTILINE,
    )

    # Prisma: prisma.modelName.findMany(...)
    _PRISMA_PATTERN = re.compile(
        r'prisma\.(\w+)\.(findMany|findUnique|findFirst|create|update|delete|upsert)',
        re.IGNORECASE | re.MULTILINE,
    )

    # Supabase: supabase.from('table_name')
    _SUPABASE_PATTERN = re.compile(
        r"supabase\.from\(['\"]([^'\"]+)['\"]\)",
        re.IGNORECASE | re.MULTILINE,
    )

    def extract(self, file_path: str, source: str) -> list[tuple[str, str, str]]:
        """提取 ORM 查询

        Returns: list of (model_name, orm_type, method)
        """
        queries = []

        for match in self._DJANGO_PATTERN.finditer(source):
            queries.append((match.group(1), "django", match.group(2)))

        for match in self._SQLALCHEMY_PATTERN.finditer(source):
            queries.append((match.group(1), "sqlalchemy", "query"))

        for match in self._PRISMA_PATTERN.finditer(source):
            queries.append((match.group(1), "prisma", match.group(2)))

        for match in self._SUPABASE_PATTERN.finditer(source):
            queries.append((match.group(1), "supabase", "from"))

        return queries


# ── Pipeline Phase ────────────────────────────────────────────────────────


def orm_phase(
    output: PipelineOutput,
    repo_path: str,
    on_progress: Optional[Callable[[PhaseProgress], None]] = None,
) -> None:
    """Phase: 提取 ORM 查询"""
    _report(on_progress, "orm", 0, "提取 ORM 查询...")

    extractor = ORMExtractor()
    model_nodes: dict[str, str] = {}  # model_key -> node_id
    seen_edges: set[str] = set()
    total_queries = 0
    total_files = len(output.scan_results)

    for idx, scan_result in enumerate(output.scan_results):
        ext = scan_result.extension
        if ext not in (".py", ".pyi", ".js", ".jsx", ".ts", ".tsx"):
            continue

        try:
            with open(scan_result.absolute_path, "r",
                      encoding="utf-8", errors="replace") as f:
                source = f.read()
        except (IOError, OSError):
            continue

        queries = extractor.extract(scan_result.file_path, source)
        for model_name, orm_type, method in queries:
            model_key = f"{orm_type}:{model_name}"

            # 获取或创建 model 节点
            if model_key not in model_nodes:
                # 尝试查找图中已有的 class/interface 节点
                candidate_ids = [
                    f"class://{scan_result.file_path}::{model_name}",
                    f"interface://{scan_result.file_path}::{model_name}",
                ]
                existing = None
                for cid in candidate_ids:
                    if output.graph.get_node(cid):
                        existing = cid
                        break

                if existing:
                    model_nodes[model_key] = existing
                else:
                    node_id = f"code_element://{orm_type}:{model_name}"
                    output.graph.add_node(GraphNode(
                        id=node_id,
                        type=NODE_CODE_ELEMENT,
                        name=model_name,
                        file_path="",
                        properties={
                            "orm_type": orm_type,
                            "description": f"{orm_type} model/table: {model_name}",
                        },
                    ))
                    model_nodes[model_key] = node_id

            model_node_id = model_nodes[model_key]
            file_node_id = f"file://{scan_result.file_path}"

            edge_key = f"{file_node_id}->{model_node_id}:{method}"
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            if output.graph.get_node(file_node_id):
                rel_id = f"queries:{file_node_id}->{model_node_id}"
                output.graph.add_relationship(GraphRelationship(
                    id=rel_id,
                    source_id=file_node_id,
                    target_id=model_node_id,
                    type=REL_QUERIES,
                    properties={"method": method, "orm_type": orm_type},
                ))
                total_queries += 1

        if (idx + 1) % max(1, total_files // 10) == 0:
            pct = int((idx + 1) / total_files * 100)
            _report(on_progress, "orm", pct,
                    f"ORM 提取: {idx + 1}/{total_files} 文件")

    output.stats["orm_queries"] = total_queries
    output.stats["orm_models"] = len(model_nodes)
    _report(on_progress, "orm", 100,
            f"ORM: {len(model_nodes)} models, {total_queries} queries")


def _report(callback, phase, percent, message=""):
    if callback:
        callback(PhaseProgress(phase=phase, percent=percent, message=message))
