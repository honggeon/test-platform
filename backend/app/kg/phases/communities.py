"""
社区检测器

从 GitNexus gitnexus/src/core/ingestion/pipeline-phases/communities.ts 改写

使用 networkx 的 greedy_modularity_communities（Louvain 贪心算法）
检测代码社区，创建 Community 节点 + MEMBER_OF 边。
"""

from __future__ import annotations

from typing import Callable, Optional, TYPE_CHECKING

import networkx as nx

from app.kg.types import (
    GraphNode, GraphRelationship,
    NODE_COMMUNITY, NODE_FILE, NODE_FOLDER,
    REL_CALLS, REL_IMPORTS, REL_MEMBER_OF,
    PhaseProgress,
)

if TYPE_CHECKING:
    from app.kg.pipeline import PipelineOutput


def communities_phase(
    output: PipelineOutput,
    repo_path: str,
    on_progress: Optional[Callable[[PhaseProgress], None]] = None,
) -> None:
    """Phase: 代码社区检测"""
    _report(on_progress, "communities", 0, "检测代码社区...")

    graph = output.graph

    # 收集非文件系统的符号节点
    symbol_nodes = {}
    for node in graph.iter_nodes():
        if node.type not in (NODE_FILE, NODE_FOLDER, NODE_COMMUNITY, NODE_FOLDER):
            symbol_nodes[node.id] = node

    if len(symbol_nodes) < 3:
        output.stats["communities"] = 0
        _report(on_progress, "communities", 100, "符号太少，跳过社区检测")
        return

    # 构建无向图（以符号为节点，CALLS + IMPORTS 为边）
    g = nx.Graph()
    for nid in symbol_nodes:
        g.add_node(nid)

    for rel in graph.iter_relationships():
        if rel.type in (REL_CALLS, REL_IMPORTS):
            if rel.source_id in symbol_nodes and rel.target_id in symbol_nodes:
                # 避免自环
                if rel.source_id != rel.target_id:
                    if g.has_edge(rel.source_id, rel.target_id):
                        g[rel.source_id][rel.target_id]["weight"] = g[rel.source_id][rel.target_id].get("weight", 1) + 1
                    else:
                        g.add_edge(rel.source_id, rel.target_id, weight=1)

    if g.number_of_edges() == 0:
        output.stats["communities"] = 0
        _report(on_progress, "communities", 100, "无边关系，跳过社区检测")
        return

    # 使用 greedy_modularity_communities
    try:
        communities = list(nx.algorithms.community.greedy_modularity_communities(g, weight="weight"))
    except Exception:
        output.stats["communities"] = 0
        _report(on_progress, "communities", 100, "社区检测失败")
        return

    # 过滤掉单节点社区（合并到 "misc" 社区）
    meaningful = [c for c in communities if len(c) >= 2]
    singletons = [c for c in communities if len(c) == 1]

    # 如果有大量单节点，创建一个 misc 社区容纳它们
    if singletons:
        misc_members = set()
        for s in singletons:
            misc_members.update(s)
        if len(misc_members) >= 2:
            meaningful.append(misc_members)

    communities = meaningful
    if not communities:
        output.stats["communities"] = 0
        _report(on_progress, "communities", 100, "未找到有意义社区")
        return

    # 为每个社区创建 Community 节点
    for idx, comm in enumerate(communities):
        comm_id = f"community://{idx}"
        member_ids = list(comm)

        # 启发式标签：取成员中最常见的文件路径前缀
        path_prefix = _heuristic_label(graph, member_ids)

        # 计算内聚度（社区内部边数 / 社区节点数）
        internal_edges = 0
        sub_g = g.subgraph(member_ids)
        if sub_g.number_of_nodes() > 0:
            cohesion = sub_g.number_of_edges() / sub_g.number_of_nodes()
        else:
            cohesion = 0.0

        output.graph.add_node(GraphNode(
            id=comm_id,
            type=NODE_COMMUNITY,
            name=f"Community {idx}",
            file_path="",
            properties={
                "heuristic_label": path_prefix,
                "symbol_count": len(member_ids),
                "cohesion": round(cohesion, 3),
            },
        ))

        for member_id in member_ids:
            rel_id = f"{member_id}_member_of_{comm_id}"
            output.graph.add_relationship(GraphRelationship(
                id=rel_id,
                source_id=member_id,
                target_id=comm_id,
                type=REL_MEMBER_OF,
                properties={},
            ))

    output.stats["communities"] = len(communities)
    output.stats["community_singletons"] = len(singletons)
    _report(on_progress, "communities", 100,
            f"社区: {len(communities)} 个")


def _heuristic_label(graph, member_ids: list[str]) -> str:
    """根据社区成员生成启发式标签"""
    from collections import Counter

    paths = []
    for mid in member_ids:
        node = graph.get_node(mid)
        if node and node.file_path:
            # 取目录部分
            dir_part = node.file_path.rsplit("/", 1)[0] if "/" in node.file_path else ""
            if dir_part:
                paths.append(dir_part)

    if not paths:
        return "misc"

    # 取最常见的路径前缀
    counter = Counter(paths)
    most_common = counter.most_common(1)[0][0]

    # 取最后一级目录名作为标签
    parts = most_common.split("/")
    return parts[-1] if parts else "misc"


def _report(callback, phase, percent, message=""):
    if callback:
        callback(PhaseProgress(phase=phase, percent=percent, message=message))
