"""
管道编排器

从 GitNexus gitnexus/src/core/ingestion/pipeline.ts 改写

DAG（有向无环图）管道，按依赖顺序执行各个分析阶段。
每个阶段接收上一个阶段的输出，渐进式丰富知识图谱。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.kg.graph import KnowledgeGraph
from app.kg.types import PhaseProgress, ScanResult
from app.kg.phases.scan import FilesystemWalker
from app.kg.phases.structure import StructureBuilder
from app.kg.phases.symbols import symbols_and_imports_phase
from app.kg.phases.calls import calls_phase
from app.kg.phases.heritage_processor import heritage_phase
from app.kg.phases.mro import mro_phase
from app.kg.phases.route_extractor import routes_phase
from app.kg.phases.tool_extractor import tools_phase
from app.kg.phases.orm_extractor import orm_phase
from app.kg.phases.communities import communities_phase
from app.kg.phases.process_extractor import process_extractor_phase as processes_phase
from app.kg.phases.markdown import markdown_phase


# ── 阶段定义 ──────────────────────────────────────────────────────────────


@dataclass
class PipelineOutput:
    """管道执行输出"""
    graph: KnowledgeGraph
    scan_results: list[ScanResult] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


PhaseHandler = Callable[[PipelineOutput, str, Optional[Callable]], None]


@dataclass
class PipelinePhase:
    """管道阶段定义"""
    name: str
    handler: PhaseHandler
    deps: list[str] = field(default_factory=list)
    description: str = ""


# ── 阶段实现 ──────────────────────────────────────────────────────────────


def _scan_phase(
    output: PipelineOutput,
    repo_path: str,
    on_progress: Optional[Callable[[PhaseProgress], None]] = None,
) -> None:
    """Phase 1: 扫描文件系统"""
    _report(on_progress, "scan", 0, "扫描文件...")
    walker = FilesystemWalker()
    start = time.time()
    results = walker.walk(repo_path)
    elapsed = time.time() - start

    output.scan_results = results
    output.stats["files_found"] = len(results)
    output.stats["scan_time"] = elapsed

    _report(on_progress, "scan", 100, f"找到 {len(results)} 个文件 ({elapsed:.1f}s)")


def _structure_phase(
    output: PipelineOutput,
    repo_path: str,
    on_progress: Optional[Callable[[PhaseProgress], None]] = None,
) -> None:
    """Phase 2: 构建文件/目录结构"""
    _report(on_progress, "structure", 0, "构建文件目录结构...")
    builder = StructureBuilder()
    start = time.time()
    struct_graph = builder.build(output.scan_results, repo_path)
    elapsed = time.time() - start

    # 合并到主图
    for node in struct_graph.iter_nodes():
        output.graph.add_node(node)
    for rel in struct_graph.iter_relationships():
        output.graph.add_relationship(rel)

    output.stats["files"] = sum(1 for n in struct_graph.iter_nodes()
                                if n.type == "file")
    output.stats["folders"] = sum(1 for n in struct_graph.iter_nodes()
                                  if n.type == "folder")
    output.stats["structure_time"] = elapsed

    _report(on_progress, "structure", 100,
            f"结构: {output.stats['folders']} 目录, "
            f"{output.stats['files']} 文件 ({elapsed:.1f}s)")


# ── 管道定义（完整 DAG）───────────────────────────────────────────────────


ALL_PHASES: list[PipelinePhase] = [
    PipelinePhase(
        name="scan",
        handler=_scan_phase,
        deps=[],
        description="扫描文件系统，收集文件元信息",
    ),
    PipelinePhase(
        name="structure",
        handler=_structure_phase,
        deps=["scan"],
        description="构建文件/目录树结构",
    ),
    PipelinePhase(
        name="markdown",
        handler=markdown_phase,
        deps=["structure"],
        description="提取 Markdown 结构",
    ),
    PipelinePhase(
        name="symbols",
        handler=symbols_and_imports_phase,
        deps=["structure"],
        description="提取符号（类/函数/变量）并解析 Import 关系",
    ),
    PipelinePhase(
        name="calls",
        handler=calls_phase,
        deps=["symbols"],
        description="分析函数调用关系",
    ),
    PipelinePhase(
        name="heritage",
        handler=heritage_phase,
        deps=["symbols"],
        description="提取继承/实现关系",
    ),
    PipelinePhase(
        name="mro",
        handler=mro_phase,
        deps=["heritage"],
        description="计算方法解析顺序",
    ),
    PipelinePhase(
        name="routes",
        handler=routes_phase,
        deps=["structure"],
        description="提取 API 路由",
    ),
    PipelinePhase(
        name="tools",
        handler=tools_phase,
        deps=["symbols"],
        description="检测 Tool 定义",
    ),
    PipelinePhase(
        name="orm",
        handler=orm_phase,
        deps=["symbols"],
        description="提取 ORM 查询",
    ),
    PipelinePhase(
        name="communities",
        handler=communities_phase,
        deps=["calls", "mro"],
        description="代码社区检测",
    ),
    PipelinePhase(
        name="processes",
        handler=processes_phase,
        deps=["calls", "routes", "communities"],
        description="执行流检测",
    ),
]


# ── 辅助方法 ──────────────────────────────────────────────────────────────


def _report(
    callback: Optional[Callable[[PhaseProgress], None]],
    phase: str,
    percent: int,
    message: str = "",
):
    if callback:
        callback(PhaseProgress(phase=phase, percent=percent, message=message))


# ── 管道执行 ──────────────────────────────────────────────────────────────


def run_pipeline_from_repo(
    repo_path: str,
    on_progress: Optional[Callable[[PhaseProgress], None]] = None,
    skip_phases: Optional[list[str]] = None,
) -> PipelineOutput:
    """执行完整的分析管道

    从 GitNexus runPipelineFromRepo (pipeline.ts) 改写

    Args:
        repo_path: 代码仓库的绝对路径
        on_progress: 进度回调函数
        skip_phases: 要跳过的阶段名称列表

    Returns:
        管道执行输出（含知识图谱和统计信息）
    """
    repo_path = os.path.abspath(repo_path)
    skip_set = set(skip_phases or [])

    # 构建 DAG 执行顺序（基于依赖关系）
    phases_by_name = {p.name: p for p in ALL_PHASES}
    executed: set[str] = set()
    output = PipelineOutput(graph=KnowledgeGraph())

    def _execute(phase: PipelinePhase):
        if phase.name in executed:
            return
        if phase.name in skip_set:
            executed.add(phase.name)
            return

        # 先执行依赖阶段
        for dep in phase.deps:
            if dep in phases_by_name:
                _execute(phases_by_name[dep])

        # 执行当前阶段
        _report(on_progress, phase.name, 0, phase.description)
        phase.handler(output, repo_path, on_progress)
        executed.add(phase.name)

    # 按定义顺序执行
    for phase in ALL_PHASES:
        _execute(phase)

    output.stats["phases_executed"] = list(executed - skip_set)
    output.stats["total_nodes"] = output.graph.node_count
    output.stats["total_relationships"] = output.graph.relationship_count

    return output
