"""
知识图谱内存实现

从 GitNexus gitnexus/src/core/graph/graph.ts 改写

KnowledgeGraph 是代码知识图谱的内存表示，支持：
- 节点和关系的增删改查
- 按类型索引关系
- 按文件路径索引节点
- 节点关联关系的反向索引
"""

from __future__ import annotations

from typing import Iterable, Iterator, Optional

from app.kg.types import GraphNode, GraphRelationship


class KnowledgeGraph:
    """知识图谱

    对应 GitNexus 的 KnowledgeGraph 接口 (graph/types.ts + graph/graph.ts)
    使用 Map 实现 O(1) 的节点/关系查找，维护多种索引。
    """

    def __init__(self):
        # 主存储
        self._nodes: dict[str, GraphNode] = {}
        self._relationships: dict[str, GraphRelationship] = {}

        # 按类型索引关系: type → {rel_id → rel}
        self._rels_by_type: dict[str, dict[str, GraphRelationship]] = {}

        # 节点关联的反向索引: node_id → set(rel_id)
        # 用于快速删除和查询节点的所有关系
        self._edge_ids_by_node: dict[str, set[str]] = {}

        # 文件索引: file_path → set(node_id)
        # 用于按文件删除节点
        self._node_ids_by_file: dict[str, set[str]] = {}

    # ── 属性 ──────────────────────────────────────────────────────────────

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def relationship_count(self) -> int:
        return len(self._relationships)

    # ── 节点操作 ──────────────────────────────────────────────────────────

    def add_node(self, node: GraphNode) -> None:
        """添加节点。如果已存在则跳过。"""
        if node.id in self._nodes:
            return
        self._nodes[node.id] = node
        # 维护文件索引
        if node.file_path:
            self._add_to_bucket(self._node_ids_by_file, node.file_path, node.id)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self._nodes.get(node_id)

    def remove_node(self, node_id: str) -> bool:
        """删除节点及其所有关联关系。返回是否实际删除。"""
        node = self._nodes.pop(node_id, None)
        if node is None:
            return False

        # 清理文件索引
        if node.file_path:
            bucket = self._node_ids_by_file.get(node.file_path)
            if bucket:
                bucket.discard(node_id)
                if not bucket:
                    del self._node_ids_by_file[node.file_path]

        # 删除该节点关联的所有关系
        edge_ids = self._edge_ids_by_node.pop(node_id, set())
        for rel_id in edge_ids:
            rel = self._relationships.pop(rel_id, None)
            if rel:
                # 从类型索引中删除
                type_bucket = self._rels_by_type.get(rel.type)
                if type_bucket:
                    type_bucket.pop(rel_id, None)
                    if not type_bucket:
                        del self._rels_by_type[rel.type]

                # 从另一端节点的索引中删除
                other_id = rel.source_id if rel.target_id == node_id else rel.target_id
                other_bucket = self._edge_ids_by_node.get(other_id)
                if other_bucket:
                    other_bucket.discard(rel_id)
                    if not other_bucket:
                        del self._edge_ids_by_node[other_id]

        return True

    def remove_nodes_by_file(self, file_path: str) -> int:
        """删除属于某个文件的所有节点。返回删除的节点数。"""
        node_ids = self._node_ids_by_file.pop(file_path, set())
        count = 0
        for node_id in node_ids:
            if self.remove_node(node_id):
                count += 1
        return count

    def iter_nodes(self) -> Iterable[GraphNode]:
        return self._nodes.values()

    def for_each_node(self, fn):
        for node in self._nodes.values():
            fn(node)

    # ── 关系操作 ──────────────────────────────────────────────────────────

    def add_relationship(self, relationship: GraphRelationship) -> None:
        """添加关系。维护所有索引。"""
        rel = relationship
        self._relationships[rel.id] = rel

        # 按类型索引
        type_bucket = self._rels_by_type.setdefault(rel.type, {})
        type_bucket[rel.id] = rel

        # 源节点索引
        self._add_to_bucket(self._edge_ids_by_node, rel.source_id, rel.id)

        # 目标节点索引（自引用边只加一次）
        if rel.target_id != rel.source_id:
            self._add_to_bucket(self._edge_ids_by_node, rel.target_id, rel.id)

    def remove_relationship(self, rel_id: str) -> bool:
        """删除关系。返回是否实际删除。"""
        rel = self._relationships.pop(rel_id, None)
        if rel is None:
            return False

        # 从类型索引中删除
        type_bucket = self._rels_by_type.get(rel.type)
        if type_bucket:
            type_bucket.pop(rel_id, None)
            if not type_bucket:
                del self._rels_by_type[rel.type]

        # 从节点索引中删除
        self._remove_from_bucket(self._edge_ids_by_node, rel.source_id, rel_id)
        if rel.target_id != rel.source_id:
            self._remove_from_bucket(self._edge_ids_by_node, rel.target_id, rel_id)

        return True

    def iter_relationships(self) -> Iterable[GraphRelationship]:
        return self._relationships.values()

    def iter_relationships_by_type(self, rel_type: str) -> Iterable[GraphRelationship]:
        """按类型迭代关系。优先使用此方法而非 iter_relationships + 过滤。"""
        bucket = self._rels_by_type.get(rel_type)
        if bucket:
            return bucket.values()
        return []

    def for_each_relationship(self, fn):
        for rel in self._relationships.values():
            fn(rel)

    # ── 查询方法 ──────────────────────────────────────────────────────────

    def get_node_ids_by_file(self, file_path: str) -> set[str]:
        """获取属于某文件的所有节点 ID。"""
        return self._node_ids_by_file.get(file_path, set())

    def get_edge_ids_for_node(self, node_id: str) -> set[str]:
        """获取某节点关联的所有关系 ID。"""
        return self._edge_ids_by_node.get(node_id, set())

    def get_relationships_for_node(self, node_id: str) -> list[GraphRelationship]:
        """获取某节点关联的所有关系。"""
        return [
            self._relationships[rel_id]
            for rel_id in self._edge_ids_by_node.get(node_id, set())
            if rel_id in self._relationships
        ]

    def get_nodes_by_type(self, node_type: str) -> list[GraphNode]:
        """获取指定类型的所有节点。"""
        return [n for n in self._nodes.values() if n.type == node_type]

    def find_nodes_by_name(self, name: str, exact: bool = False) -> list[GraphNode]:
        """按名称查找节点。"""
        if exact:
            return [n for n in self._nodes.values() if n.name == name]
        return [n for n in self._nodes.values() if name.lower() in n.name.lower()]

    # ── 工具方法 ──────────────────────────────────────────────────────────

    @staticmethod
    def _add_to_bucket(map_: dict, key: str, value: str):
        bucket = map_.get(key)
        if bucket is None:
            bucket = set()
            map_[key] = bucket
        bucket.add(value)

    @staticmethod
    def _remove_from_bucket(map_: dict, key: str, value: str):
        bucket = map_.get(key)
        if bucket is None:
            return
        bucket.discard(value)
        if not bucket:
            del map_[key]
