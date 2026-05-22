"""
执行流检测器

从 GitNexus gitnexus/src/core/ingestion/pipeline-phases/processes.ts 改写

从 Entry Points 开始做 BFS 追踪 CALLS 边，构建 Process 节点 + STEP_IN_PROCESS 边。
"""

from __future__ import annotations

from collections import deque
from typing import Callable, Optional, TYPE_CHECKING

from app.kg.types import (
    GraphNode, GraphRelationship,
    NODE_FUNCTION, NODE_METHOD, NODE_ROUTE, NODE_TOOL, NODE_PROCESS,
    REL_CALLS, REL_STEP_IN_PROCESS, REL_ENTRY_POINT_OF, REL_HANDLES_ROUTE,
    PhaseProgress,
)

if TYPE_CHECKING:
    from app.kg.pipeline import PipelineOutput


def process_extractor_phase(
    output: PipelineOutput,
    repo_path: str,
    on_progress: Optional[Callable[[PhaseProgress], None]] = None,
) -> None:
    """Phase: 执行流检测"""
    _report(on_progress, "processes", 0, "检测执行流...")

    graph = output.graph

    # 1. 识别 Entry Points
    entry_points = _find_entry_points(graph)

    if not entry_points:
        output.stats["processes"] = 0
        _report(on_progress, "processes", 100, "未找到执行入口")
        return

    # 2. 构建反向 CALLS 索引（用于快速查找被调用者）
    callee_to_callers: dict[str, list[str]] = {}
    caller_to_callees: dict[str, list[str]] = {}
    for rel in graph.iter_relationships():
        if rel.type == REL_CALLS:
            callee_to_callers.setdefault(rel.target_id, []).append(rel.source_id)
            caller_to_callees.setdefault(rel.source_id, []).append(rel.target_id)

    # 3. 从每个 Entry Point 做 BFS
    processes = []
    visited_global = set()
    min_steps = 3
    max_depth = 20

    for ep_id in entry_points:
        if ep_id in visited_global:
            continue

        # BFS
        queue = deque([(ep_id, 0)])
        visited = {ep_id}
        chain = [ep_id]

        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue

            for callee in caller_to_callees.get(current, []):
                if callee not in visited:
                    visited.add(callee)
                    chain.append(callee)
                    queue.append((callee, depth + 1))

        if len(chain) >= min_steps:
            processes.append({
                "entry_point": ep_id,
                "chain": chain,
            })
            visited_global.update(chain)

    # 4. 创建 Process 节点和 STEP_IN_PROCESS 边
    for idx, proc in enumerate(processes):
        proc_id = f"process://{idx}"
        entry_id = proc["entry_point"]
        chain = proc["chain"]

        # 确定 processType
        entry_node = graph.get_node(entry_id)
        process_type = "function"
        if entry_node:
            if entry_node.type in (NODE_FUNCTION, NODE_METHOD):
                # 检查该文件是否有 Route
                if entry_node.file_path:
                    file_id = f"file://{entry_node.file_path}"
                    for rel in graph.iter_relationships():
                        if rel.type == REL_HANDLES_ROUTE and rel.source_id == file_id:
                            process_type = "api_handler"
                            break

        # 收集跨越的社区
        communities = set()
        for node_id in chain:
            for rel in graph.iter_relationships():
                if rel.type == "MEMBER_OF" and rel.source_id == node_id:
                    communities.add(rel.target_id)

        output.graph.add_node(GraphNode(
            id=proc_id,
            type=NODE_PROCESS,
            name=f"Process {idx}",
            file_path=entry_node.file_path if entry_node else "",
            properties={
                "process_type": process_type,
                "step_count": len(chain),
                "entry_point_id": entry_id,
                "communities": list(communities),
            },
        ))

        for step_idx, node_id in enumerate(chain):
            rel_id = f"{node_id}_step_{step_idx}_{proc_id}"
            output.graph.add_relationship(GraphRelationship(
                id=rel_id,
                source_id=node_id,
                target_id=proc_id,
                type=REL_STEP_IN_PROCESS,
                properties={"step": step_idx},
            ))

        # ENTRY_POINT_OF: Route → Process
        if entry_node and entry_node.file_path:
            file_id = f"file://{entry_node.file_path}"
            for rel in graph.iter_relationships():
                if rel.type == REL_HANDLES_ROUTE and rel.source_id == file_id:
                    route_id = rel.target_id
                    rel_id = f"entry_point_of:{route_id}->{proc_id}"
                    output.graph.add_relationship(GraphRelationship(
                        id=rel_id,
                        source_id=route_id,
                        target_id=proc_id,
                        type=REL_ENTRY_POINT_OF,
                        properties={"reason": "route-handler-entry-point"},
                    ))

    output.stats["processes"] = len(processes)
    _report(on_progress, "processes", 100,
            f"执行流: {len(processes)} 个")


def _find_entry_points(graph) -> list[str]:
    """识别执行入口点"""
    entry_points = []

    # 1. 被 Route 处理的文件中的顶层函数
    route_files = set()
    for rel in graph.iter_relationships():
        if rel.type == REL_HANDLES_ROUTE:
            route_files.add(rel.source_id)

    for file_id in route_files:
        # 找到该文件中定义的函数
        for rel in graph.iter_relationships():
            if rel.type == "DEFINED_IN" and rel.target_id == file_id:
                node = graph.get_node(rel.source_id)
                if node and node.type in (NODE_FUNCTION, NODE_METHOD):
                    entry_points.append(node.id)

    # 2. main 函数
    for node in graph.iter_nodes():
        if node.type in (NODE_FUNCTION, NODE_METHOD) and node.name == "main":
            if node.id not in entry_points:
                entry_points.append(node.id)

    # 3. __init__.py 中的公开函数（简化：取模块下的第一个函数）
    # 暂不实现，避免入口过多

    return entry_points


def _report(callback, phase, percent, message=""):
    if callback:
        callback(PhaseProgress(phase=phase, percent=percent, message=message))
