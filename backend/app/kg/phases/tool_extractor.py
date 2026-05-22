"""
Tool 定义提取器

从 GitNexus gitnexus/src/core/ingestion/pipeline-phases/tools.ts 改写

检测 MCP / RPC / AI Tool 定义，创建 Tool 节点 + HANDLES_TOOL 边。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, Optional, TYPE_CHECKING

from app.kg.types import (
    GraphNode, GraphRelationship,
    NODE_TOOL, REL_HANDLES_ROUTE,
    PhaseProgress,
)

if TYPE_CHECKING:
    from app.kg.pipeline import PipelineOutput


@dataclass
class ToolDef:
    name: str
    file_path: str
    description: str = ""
    handler_node_id: Optional[str] = None


# ── 检测模式 ──────────────────────────────────────────────────────────────


class ToolExtractor:
    """Tool 定义提取器"""

    # MCP / LangChain tool 定义模式
    _TOOL_PATTERNS = [
        # name: 'xxx', description: 'xxx'
        re.compile(
            r"name\s*:\s*['\"](\w+)['\"]\s*,\s*\n?\s*description\s*:\s*['\"`]([\s\S]*?)['\"`]",
            re.MULTILINE,
        ),
        # @tool decorator
        re.compile(
            r"@tool\s*(?:\(\s*['\"]([^'\"]+)['\"]\s*\))?\s*\n?\s*def\s+(\w+)",
            re.MULTILINE,
        ),
        # class XTool(BaseTool)
        re.compile(
            r"class\s+(\w+Tool)\s*\(\s*\w*Tool\s*\)",
            re.MULTILINE,
        ),
    ]

    def extract(self, file_path: str, source: str) -> list[ToolDef]:
        tools: list[ToolDef] = []
        seen = set()

        for pattern in self._TOOL_PATTERNS:
            for match in pattern.finditer(source):
                if pattern == self._TOOL_PATTERNS[0]:
                    name = match.group(1)
                    desc = match.group(2).replace("\\n", " ").replace("\n", " ").strip()[:200]
                elif pattern == self._TOOL_PATTERNS[1]:
                    name = match.group(1) or match.group(2)
                    desc = ""
                else:
                    name = match.group(1)
                    desc = ""

                if not name or name in seen:
                    continue
                seen.add(name)
                tools.append(ToolDef(name=name, file_path=file_path, description=desc))

        return tools


# ── Pipeline Phase ────────────────────────────────────────────────────────


def tools_phase(
    output: PipelineOutput,
    repo_path: str,
    on_progress: Optional[Callable[[PhaseProgress], None]] = None,
) -> None:
    """Phase: 检测 Tool 定义"""
    _report(on_progress, "tools", 0, "检测 Tool 定义...")

    extractor = ToolExtractor()
    tool_defs: list[ToolDef] = []
    total_files = len(output.scan_results)

    for idx, scan_result in enumerate(output.scan_results):
        ext = scan_result.extension
        if ext not in (".py", ".pyi", ".js", ".jsx", ".ts", ".tsx"):
            continue

        # 优先检查文件名是否包含 tool
        basename = os.path.basename(scan_result.file_path).lower()
        if "tool" not in basename and "mcp" not in basename:
            # 如果文件名不包含 tool，也尝试读取内容检查是否有 inputSchema / @tool
            pass  # 仍然尝试，因为 tool 定义可能在任意文件中

        try:
            with open(scan_result.absolute_path, "r",
                      encoding="utf-8", errors="replace") as f:
                source = f.read()
        except (IOError, OSError):
            continue

        # 快速排除：不包含 tool 相关关键字的文件直接跳过
        if "inputSchema" not in source and "@tool" not in source and "description" not in source:
            continue

        tools = extractor.extract(scan_result.file_path, source)
        tool_defs.extend(tools)

        if (idx + 1) % max(1, total_files // 10) == 0:
            pct = int((idx + 1) / total_files * 100)
            _report(on_progress, "tools", pct,
                    f"Tool 检测: {idx + 1}/{total_files} 文件")

    # 去重并创建节点
    seen_names = set()
    for td in tool_defs:
        if td.name in seen_names:
            continue
        seen_names.add(td.name)

        tool_node_id = f"tool://{td.name}"
        output.graph.add_node(GraphNode(
            id=tool_node_id,
            type=NODE_TOOL,
            name=td.name,
            file_path=td.file_path,
            properties={"description": td.description},
        ))

    output.stats["tools_found"] = len(seen_names)
    _report(on_progress, "tools", 100,
            f"Tool: {len(seen_names)} 个")


def _report(callback, phase, percent, message=""):
    if callback:
        callback(PhaseProgress(phase=phase, percent=percent, message=message))
