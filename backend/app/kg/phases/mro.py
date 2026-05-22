"""
方法解析顺序 (MRO) 处理器

从 GitNexus gitnexus/src/core/ingestion/mro-processor.ts 改写

基于 EXTENDS / IMPLEMENTS 关系：
1. 计算每个类的 C3 线性化（或简化 DFS）得到 MRO 链
2. 匹配同名方法 → METHOD_OVERRIDES 边
3. 对接口方法匹配 → METHOD_IMPLEMENTS 边
"""

from __future__ import annotations

from typing import Callable, Optional, TYPE_CHECKING

import networkx as nx

from app.kg.types import (
    GraphRelationship,
    NODE_CLASS, NODE_INTERFACE, NODE_METHOD,
    REL_EXTENDS, REL_IMPLEMENTS,
    REL_METHOD_OVERRIDES, REL_METHOD_IMPLEMENTS,
    PhaseProgress,
)

if TYPE_CHECKING:
    from app.kg.pipeline import PipelineOutput


def mro_phase(
    output: PipelineOutput,
    repo_path: str,
    on_progress: Optional[Callable[[PhaseProgress], None]] = None,
) -> None:
    """Phase: 计算方法解析顺序"""
    _report(on_progress, "mro", 0, "计算方法解析顺序...")

    graph = output.graph

    # 构建继承图（有向）
    g = nx.DiGraph()

    # 收集所有 class 节点
    class_nodes = {}
    for node in graph.iter_nodes():
        if node.type == NODE_CLASS:
            class_nodes[node.id] = node
            g.add_node(node.id)

    # 添加 EXTENDS 边
    for rel in graph.iter_relationships():
        if rel.type == REL_EXTENDS:
            if rel.source_id in class_nodes and rel.target_id in class_nodes:
                g.add_edge(rel.source_id, rel.target_id)

    total_override = 0
    total_implements = 0
    ambiguity_count = 0

    # 对每个类计算 MRO
    for class_id, class_node in class_nodes.items():
        # 简化版 MRO：使用 DFS 拓扑序（Python 的 C3 在 networkx 中无内置，
        # 但 networkx 有 lexicographical_topological_sort）
        try:
            # 取该节点的所有祖先
            ancestors = list(nx.ancestors(g, class_id))
            if not ancestors:
                continue

            # 构建子图（class_id + 祖先）
            sub_g = g.subgraph([class_id] + ancestors)
            mro = list(nx.topological_sort(sub_g))
            # topological_sort 输出的是从源到汇的排序，需要反转
            # 实际上我们想要的是 method resolution order：从当前类开始，沿继承链向下
            # 简单处理：将 class_id 放第一，其余按拓扑序
            mro = [class_id] + [n for n in mro if n != class_id]
        except nx.NetworkXError:
            ambiguity_count += 1
            continue

        # 获取当前类的所有方法
        methods = _get_class_methods(graph, class_id)

        for method_name, method_id in methods.items():
            # METHOD_OVERRIDES: 沿 MRO 找父类同名方法
            for ancestor_id in mro[1:]:
                ancestor_methods = _get_class_methods(graph, ancestor_id)
                if method_name in ancestor_methods:
                    rel_id = f"method_overrides:{method_id}->{ancestor_methods[method_name]}"
                    graph.add_relationship(GraphRelationship(
                        id=rel_id,
                        source_id=method_id,
                        target_id=ancestor_methods[method_name],
                        type=REL_METHOD_OVERRIDES,
                        properties={"method_name": method_name},
                    ))
                    total_override += 1
                    break  # 只找最近的一个父类方法

    # METHOD_IMPLEMENTS: 对接口
    interface_methods = {}
    for node in graph.iter_nodes():
        if node.type == NODE_INTERFACE:
            interface_methods[node.id] = _get_interface_methods(graph, node.id)

    for rel in graph.iter_relationships():
        if rel.type == REL_IMPLEMENTS:
            class_id = rel.source_id
            iface_id = rel.target_id
            if iface_id not in interface_methods:
                continue
            class_methods = _get_class_methods(graph, class_id)
            for method_name, iface_method_id in interface_methods[iface_id].items():
                if method_name in class_methods:
                    rel_id = f"method_implements:{class_methods[method_name]}->{iface_method_id}"
                    graph.add_relationship(GraphRelationship(
                        id=rel_id,
                        source_id=class_methods[method_name],
                        target_id=iface_method_id,
                        type=REL_METHOD_IMPLEMENTS,
                        properties={"method_name": method_name},
                    ))
                    total_implements += 1

    output.stats["method_override_edges"] = total_override
    output.stats["method_implements_edges"] = total_implements
    output.stats["mro_ambiguities"] = ambiguity_count

    _report(on_progress, "mro", 100,
            f"MRO: {total_override} overrides, {total_implements} implements")


def _get_class_methods(graph, class_id: str) -> dict[str, str]:
    """获取类的所有方法 {method_name: method_node_id}"""
    methods = {}
    for rel in graph.iter_relationships():
        if rel.type == "DEFINED_IN" and rel.target_id == class_id:
            node = graph.get_node(rel.source_id)
            if node and node.type == NODE_METHOD:
                methods[node.name] = node.id
    return methods


def _get_interface_methods(graph, iface_id: str) -> dict[str, str]:
    """获取接口的所有方法签名 {method_name: method_node_id}"""
    methods = {}
    # interface 节点下可能没有 method 节点（因为 JS 正则提取的 interface 只有声明）
    # 这里用 DEFINED_IN 查找
    for rel in graph.iter_relationships():
        if rel.type == "DEFINED_IN" and rel.target_id == iface_id:
            node = graph.get_node(rel.source_id)
            if node and node.type in (NODE_METHOD, "function"):
                methods[node.name] = node.id
    # 如果 interface 下没有方法节点（常见），我们创建一个虚拟方法节点 ID
    # 但这会导致图中没有对应节点，所以暂时跳过
    return methods


def _report(callback, phase, percent, message=""):
    if callback:
        callback(PhaseProgress(phase=phase, percent=percent, message=message))
