"""
BM25 索引

利用 rank_bm25 库构建内存 BM25 索引，用于代码搜索。
从 PostgreSQL 加载节点文本，按类型分组索引。
"""

from __future__ import annotations

from typing import Optional

from rank_bm25 import BM25Okapi

from app.kg.persistence import KGNode


class BM25Index:
    """BM25 内存索引

    封装 rank_bm25.BM25Okapi，为代码节点提供 BM25 评分。
    """

    def __init__(self, documents: list[str], node_ids: list[str]):
        """
        Args:
            documents: 文档文本列表（已预处理）
            node_ids:  对应的节点 ID 列表
        """
        self._node_ids = node_ids
        self._tokenized = [self._tokenize(d) for d in documents]
        self._bm25 = BM25Okapi(self._tokenized) if documents else None

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """简单分词：小写 + 按非字母数字分割"""
        return [t.lower() for t in text.split() if t]

    def search(self, query: str, top_k: int = 30) -> list[tuple[str, float]]:
        """BM25 搜索

        Returns:
            [(node_id, score), ...] 按分数降序
        """
        if not self._bm25:
            return []

        tokenized_query = self._tokenize(query)
        if not tokenized_query:
            return []

        scores = self._bm25.get_scores(tokenized_query)
        scored = [(self._node_ids[i], float(scores[i]))
                  for i in range(len(self._node_ids))]
        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]


class CodeBM25Index:
    """按类型分组的 BM25 索引"""

    def __init__(self):
        self._indexes: dict[str, BM25Index] = {}

    @classmethod
    def from_nodes(cls, nodes: list[KGNode]) -> CodeBM25Index:
        """从 KGNode 列表构建索引"""
        index = cls()

        # 按类型分组
        by_type: dict[str, list[tuple[str, str]]] = {}
        for node in nodes:
            doc = f"{node.name} {node.properties.get('doc', '')}"
            by_type.setdefault(node.type, []).append((node.node_id, doc))

        for node_type, items in by_type.items():
            ids = [i[0] for i in items]
            docs = [i[1] for i in items]
            index._indexes[node_type] = BM25Index(docs, ids)

        # 全局索引（所有类型）
        all_ids = [n.node_id for n in nodes]
        all_docs = [f"{n.name} {n.properties.get('doc', '')}" for n in nodes]
        index._indexes["__all__"] = BM25Index(all_docs, all_ids)

        return index

    def search(self, query: str, node_type: Optional[str] = None, top_k: int = 30) -> list[tuple[str, float]]:
        """搜索指定类型或全局"""
        key = node_type or "__all__"
        idx = self._indexes.get(key)
        if not idx:
            return []
        return idx.search(query, top_k)
