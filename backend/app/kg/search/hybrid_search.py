"""
RRF 混合搜索

从 GitNexus gitnexus/src/core/search/hybrid-search.ts 改写

融合多个搜索结果列表，使用 Reciprocal Rank Fusion (RRF) 排序。
"""

from __future__ import annotations

from typing import Optional


RRF_K = 60


def merge_with_rrf(
    *result_lists: list[tuple[str, float]],
    limit: int = 30,
) -> list[tuple[str, float]]:
    """RRF 融合多个结果列表

    Args:
        result_lists: 多个 (node_id, score) 列表，每个列表内部已按相关度排序
        limit: 返回最大结果数

    Returns:
        融合后的 (node_id, rrf_score) 列表，按分数降序
    """
    scores: dict[str, float] = {}

    for results in result_lists:
        for rank, (node_id, _) in enumerate(results):
            rrf_score = 1.0 / (RRF_K + rank + 1)
            scores[node_id] = scores.get(node_id, 0.0) + rrf_score

    merged = sorted(scores.items(), key=lambda x: -x[1])
    return merged[:limit]


class HybridSearch:
    """混合搜索器

    封装 RRF 融合逻辑，支持 FTS + BM25 + 其他来源。
    """

    def __init__(self):
        pass

    def search(
        self,
        fts_results: list[tuple[str, float]],
        bm25_results: list[tuple[str, float]],
        limit: int = 30,
    ) -> list[tuple[str, float]]:
        """融合 FTS 和 BM25 结果"""
        return merge_with_rrf(fts_results, bm25_results, limit=limit)
