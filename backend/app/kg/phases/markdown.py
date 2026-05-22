"""
Markdown 处理器

从 GitNexus gitnexus/src/core/ingestion/pipeline-phases/markdown.ts 改写

提取 Markdown/MDX 标题和交叉链接，创建 MarkdownSection 节点 + LINKS_TO 边。
"""

from __future__ import annotations

import re
from typing import Callable, Optional, TYPE_CHECKING

from app.kg.types import (
    GraphNode, GraphRelationship,
    NODE_MARKDOWN_SECTION, REL_CONTAINS, REL_LINKS_TO,
    PhaseProgress,
)

if TYPE_CHECKING:
    from app.kg.pipeline import PipelineOutput


# ── Markdown 提取 ─────────────────────────────────────────────────────────


class MarkdownExtractor:
    """Markdown 轻量提取器"""

    _HEADING_PATTERN = re.compile(r'^(#{1,4})\s+(.+)$', re.MULTILINE)
    _LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

    def extract(self, file_path: str, source: str) -> tuple[list[GraphNode], list[GraphRelationship]]:
        nodes = []
        rels = []

        lines = source.splitlines()
        for match in self._HEADING_PATTERN.finditer(source):
            level = len(match.group(1))
            title = match.group(2).strip()
            line_no = source[:match.start()].count('\n') + 1

            section_id = f"md_section://{file_path}::{title}"
            nodes.append(GraphNode(
                id=section_id,
                type=NODE_MARKDOWN_SECTION,
                name=title,
                file_path=file_path,
                start_line=line_no,
                end_line=line_no,
                properties={"level": level},
            ))

            # CONTAINS: File → Section
            file_id = f"file://{file_path}"
            rels.append(GraphRelationship(
                id=f"contains:{file_id}->{section_id}",
                source_id=file_id,
                target_id=section_id,
                type=REL_CONTAINS,
                properties={},
            ))

        return nodes, rels

    def extract_links(self, file_path: str, source: str) -> list[tuple[str, str]]:
        """提取交叉链接 (source_section_id, target_path)"""
        links = []
        for match in self._LINK_PATTERN.finditer(source):
            target = match.group(2)
            # 只保留相对路径链接
            if target.startswith("http") or target.startswith("#"):
                continue
            # 找到链接所在的 section（简化：用最近的上一个标题）
            line_no = source[:match.start()].count('\n') + 1
            section_title = self._find_nearest_heading(source, line_no)
            if section_title:
                source_id = f"md_section://{file_path}::{section_title}"
                links.append((source_id, target))
        return links

    @staticmethod
    def _find_nearest_heading(source: str, line_no: int) -> Optional[str]:
        """找到某行之前最近的标题"""
        lines = source.splitlines()
        for i in range(line_no - 1, -1, -1):
            if i >= len(lines):
                continue
            m = re.match(r'^(#{1,4})\s+(.+)$', lines[i])
            if m:
                return m.group(2).strip()
        return None


# ── Pipeline Phase ────────────────────────────────────────────────────────


def markdown_phase(
    output: PipelineOutput,
    repo_path: str,
    on_progress: Optional[Callable[[PhaseProgress], None]] = None,
) -> None:
    """Phase: 提取 Markdown 结构"""
    _report(on_progress, "markdown", 0, "提取 Markdown...")

    extractor = MarkdownExtractor()
    total_sections = 0
    total_links = 0
    md_files = 0

    for scan_result in output.scan_results:
        if not scan_result.file_path.endswith((".md", ".mdx")):
            continue

        md_files += 1
        try:
            with open(scan_result.absolute_path, "r",
                      encoding="utf-8", errors="replace") as f:
                source = f.read()
        except (IOError, OSError):
            continue

        nodes, rels = extractor.extract(scan_result.file_path, source)
        for node in nodes:
            output.graph.add_node(node)
        for rel in rels:
            output.graph.add_relationship(rel)
        total_sections += len(nodes)

        # 交叉链接（简化：链接到文件路径，不创建具体 section 节点）
        links = extractor.extract_links(scan_result.file_path, source)
        for source_id, target_path in links:
            target_id = f"file://{target_path}"
            if output.graph.get_node(target_id):
                rel_id = f"links_to:{source_id}->{target_id}"
                output.graph.add_relationship(GraphRelationship(
                    id=rel_id,
                    source_id=source_id,
                    target_id=target_id,
                    type=REL_LINKS_TO,
                    properties={},
                ))
                total_links += 1

    output.stats["markdown_sections"] = total_sections
    output.stats["markdown_links"] = total_links
    _report(on_progress, "markdown", 100,
            f"Markdown: {total_sections} sections, {total_links} links ({md_files} files)")


def _report(callback, phase, percent, message=""):
    if callback:
        callback(PhaseProgress(phase=phase, percent=percent, message=message))
