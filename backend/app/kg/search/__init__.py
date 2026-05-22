"""
代码搜索服务

利用 PostgreSQL FTS + BM25 + RRF 混合搜索进行代码搜索。
支持按类型过滤、按文件路径搜索、多模式搜索（fts / bm25 / hybrid）。
支持按 commit_hash 查询指定版本的图谱。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, func, text, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.kg.persistence import KGNode, KGRelationship, KGCommit


@dataclass
class SearchResult:
    """搜索结果"""
    node_id: str
    name: str
    type: str
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    score: float = 0.0
    match_context: str = ""
    properties: Optional[dict] = None


class CodeSearcher:
    """代码搜索器

    使用 PostgreSQL FTS + 名称模糊匹配进行代码搜索。
    支持多种搜索模式：
    - 全文搜索（FTS）：适合搜索代码中的自然语言概念
    - 名称搜索：精确或模糊搜索符号名
    - 类型过滤：只搜索特定类型的节点
    - 版本查询：按 commit_hash 查询指定版本的图谱
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    # ── commit hash 解析 ──────────────────────────────────────────────────

    async def _resolve_commit(self, repo_path: str, commit_hash: Optional[str]) -> Optional[str]:
        """解析 commit_hash：传了就用，没传取最新"""
        if commit_hash:
            return commit_hash
        # 从 kg_commits 取最新
        result = await self._session.execute(
            select(KGCommit.commit_hash)
            .where(KGCommit.repo_path == repo_path)
            .order_by(KGCommit.analyzed_at.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        if latest:
            return latest
        # 兼容旧数据：从 kg_nodes 中找一个 commit_hash
        result2 = await self._session.execute(
            select(KGNode.commit_hash)
            .where(KGNode.repo_path == repo_path)
            .limit(1)
        )
        return result2.scalar_one_or_none()

    # ── 主入口 ────────────────────────────────────────────────────────────

    async def search(
        self, repo_path: str, query: str,
        node_type: Optional[str] = None,
        limit: int = 30,
        mode: str = "hybrid",
        commit_hash: Optional[str] = None,
    ) -> list[SearchResult]:
        """搜索代码

        Args:
            repo_path: 代码仓库路径
            query: 搜索关键词
            node_type: 可选的节点类型过滤（class/function/file 等）
            limit: 最大结果数
            mode: 搜索模式 - "fts" | "bm25" | "hybrid"
            commit_hash: 可选，指定 commit 版本（不传则取最新）

        Returns:
            匹配的搜索结果列表
        """
        if mode == "fts":
            results = await self._fts_search(repo_path, query, node_type, limit, commit_hash)
            if len(results) < limit:
                name_results = await self._name_search(
                    repo_path, query, node_type, limit - len(results), commit_hash,
                )
                seen_ids = {r.node_id for r in results}
                for nr in name_results:
                    if nr.node_id not in seen_ids:
                        results.append(nr)
            results.sort(key=lambda r: -r.score)
            return results[:limit]

        if mode == "bm25":
            return await self._bm25_search(repo_path, query, node_type, limit, commit_hash)

        return await self._hybrid_search(repo_path, query, node_type, limit, commit_hash)

    # ── 子搜索方法 ────────────────────────────────────────────────────────

    async def _fts_search(
        self, repo_path: str, query: str,
        node_type: Optional[str], limit: int,
        commit_hash: Optional[str] = None,
    ) -> list[SearchResult]:
        """PostgreSQL FTS 全文搜索"""
        ch = await self._resolve_commit(repo_path, commit_hash)

        ts_query = " & ".join(
            word for word in query.replace("-", " ").split()
            if word.strip()
        )
        if not ts_query:
            return []

        stmt = select(
            KGNode.node_id, KGNode.name, KGNode.type,
            KGNode.file_path, KGNode.start_line, KGNode.end_line,
            KGNode.properties,
            func.ts_rank(
                func.to_tsvector('english',
                    KGNode.name + ' ' +
                    func.coalesce(KGNode.properties['doc'].astext, '')
                ),
                func.plainto_tsquery('english', query),
            ).label('rank'),
        ).where(
            KGNode.repo_path == repo_path,
        )

        if ch:
            stmt = stmt.where(KGNode.commit_hash == ch)

        stmt = stmt.where(
            func.to_tsvector('english',
                KGNode.name + ' ' +
                func.coalesce(KGNode.properties['doc'].astext, '')
            ).op('@@')(func.plainto_tsquery('english', query)),
        )

        if node_type:
            stmt = stmt.where(KGNode.type == node_type)

        stmt = stmt.order_by(text('rank DESC')).limit(limit)

        result = await self._session.execute(stmt)
        rows = result.all()

        return [
            SearchResult(
                node_id=row.node_id,
                name=row.name,
                type=row.type,
                file_path=row.file_path,
                start_line=row.start_line,
                end_line=row.end_line,
                score=float(row.rank or 0) * 100,
                match_context=f"FTS matched '{query}'",
                properties=row.properties,
            )
            for row in rows
        ]

    async def _name_search(
        self, repo_path: str, query: str,
        node_type: Optional[str], limit: int,
        commit_hash: Optional[str] = None,
    ) -> list[SearchResult]:
        """按名称模糊搜索"""
        ch = await self._resolve_commit(repo_path, commit_hash)

        stmt = select(
            KGNode.node_id, KGNode.name, KGNode.type,
            KGNode.file_path, KGNode.start_line, KGNode.end_line,
            KGNode.properties,
        ).where(
            KGNode.repo_path == repo_path,
            KGNode.name.ilike(f'%{query}%'),
        )

        if ch:
            stmt = stmt.where(KGNode.commit_hash == ch)

        if node_type:
            stmt = stmt.where(KGNode.type == node_type)

        stmt = stmt.order_by(KGNode.name).limit(limit)

        result = await self._session.execute(stmt)
        rows = result.all()

        return [
            SearchResult(
                node_id=row.node_id,
                name=row.name,
                type=row.type,
                file_path=row.file_path,
                start_line=row.start_line,
                end_line=row.end_line,
                score=50.0,
                match_context=f"name contains '{query}'",
                properties=row.properties,
            )
            for row in rows
        ]

    async def _bm25_search(
        self, repo_path: str, query: str,
        node_type: Optional[str], limit: int,
        commit_hash: Optional[str] = None,
    ) -> list[SearchResult]:
        """BM25 搜索"""
        from app.kg.search.bm25_index import CodeBM25Index

        ch = await self._resolve_commit(repo_path, commit_hash)

        stmt = select(KGNode).where(KGNode.repo_path == repo_path)
        if ch:
            stmt = stmt.where(KGNode.commit_hash == ch)
        if node_type:
            stmt = stmt.where(KGNode.type == node_type)
        result = await self._session.execute(stmt)
        nodes = result.scalars().all()

        if not nodes:
            return []

        index = CodeBM25Index.from_nodes(nodes)
        bm25_results = index.search(query, node_type, limit * 2)

        node_map = {n.node_id: n for n in nodes}

        results = []
        for node_id, score in bm25_results:
            node = node_map.get(node_id)
            if not node:
                continue
            results.append(SearchResult(
                node_id=node.node_id,
                name=node.name,
                type=node.type,
                file_path=node.file_path,
                start_line=node.start_line,
                end_line=node.end_line,
                score=score * 100,
                match_context="BM25 ranked",
                properties=node.properties,
            ))
        return results

    async def _hybrid_search(
        self, repo_path: str, query: str,
        node_type: Optional[str], limit: int,
        commit_hash: Optional[str] = None,
    ) -> list[SearchResult]:
        """混合搜索：FTS + BM25 + RRF"""
        from app.kg.search.bm25_index import CodeBM25Index
        from app.kg.search.hybrid_search import HybridSearch

        # FTS 结果
        fts_results = await self._fts_search(repo_path, query, node_type, limit * 3, commit_hash)
        fts_scored = [(r.node_id, r.score) for r in fts_results]

        # BM25 结果
        ch = await self._resolve_commit(repo_path, commit_hash)
        stmt = select(KGNode).where(KGNode.repo_path == repo_path)
        if ch:
            stmt = stmt.where(KGNode.commit_hash == ch)
        if node_type:
            stmt = stmt.where(KGNode.type == node_type)
        result = await self._session.execute(stmt)
        nodes = result.scalars().all()

        bm25_scored: list[tuple[str, float]] = []
        if nodes:
            index = CodeBM25Index.from_nodes(nodes)
            bm25_scored = index.search(query, node_type, limit * 3)

        # RRF 融合
        merged = HybridSearch().search(fts_scored, bm25_scored, limit=limit * 2)

        node_map = {n.node_id: n for n in nodes}
        for r in fts_results:
            if r.node_id not in node_map:
                node_map[r.node_id] = r  # type: ignore[assignment]

        results = []
        for node_id, rrf_score in merged:
            node = node_map.get(node_id)
            if not node:
                continue
            results.append(SearchResult(
                node_id=node.node_id,
                name=node.name,
                type=node.type,
                file_path=node.file_path,
                start_line=node.start_line,
                end_line=node.end_line,
                score=round(rrf_score * 100, 2),
                match_context="hybrid (FTS + BM25)",
                properties=node.properties,
            ))

        if len(results) < limit // 2:
            name_results = await self._name_search(repo_path, query, node_type, limit, commit_hash)
            seen = {r.node_id for r in results}
            for nr in name_results:
                if nr.node_id not in seen:
                    results.append(nr)
            results.sort(key=lambda r: -r.score)

        return results[:limit]

    async def search_by_type(
        self, repo_path: str, node_type: str, limit: int = 100,
        commit_hash: Optional[str] = None,
    ) -> list[SearchResult]:
        """按类型列出节点"""
        ch = await self._resolve_commit(repo_path, commit_hash)

        stmt = select(
            KGNode.node_id, KGNode.name, KGNode.type,
            KGNode.file_path, KGNode.start_line, KGNode.end_line,
            KGNode.properties,
        ).where(
            KGNode.repo_path == repo_path,
            KGNode.type == node_type,
        )
        if ch:
            stmt = stmt.where(KGNode.commit_hash == ch)

        stmt = stmt.order_by(KGNode.name).limit(limit)

        result = await self._session.execute(stmt)
        rows = result.all()

        return [
            SearchResult(
                node_id=row.node_id,
                name=row.name,
                type=row.type,
                file_path=row.file_path,
                start_line=row.start_line,
                end_line=row.end_line,
                score=1.0,
                properties=row.properties,
            )
            for row in rows
        ]

    async def get_node_context(
        self, repo_path: str, node_id: str,
        commit_hash: Optional[str] = None,
    ) -> Optional[dict]:
        """获取节点的详细信息，包括关联关系"""
        ch = await self._resolve_commit(repo_path, commit_hash)

        # 获取节点
        stmt = select(KGNode).where(
            KGNode.repo_path == repo_path,
            KGNode.node_id == node_id,
        )
        if ch:
            stmt = stmt.where(KGNode.commit_hash == ch)

        result = await self._session.execute(stmt)
        node = result.scalar_one_or_none()
        if not node:
            return None

        # 获取关联关系
        rel_stmt = select(KGRelationship).where(
            KGRelationship.repo_path == repo_path,
        )
        if ch:
            rel_stmt = rel_stmt.where(KGRelationship.commit_hash == ch)

        rel_stmt = rel_stmt.where(
            or_(
                KGRelationship.source_node_id == node_id,
                KGRelationship.target_node_id == node_id,
            ),
        ).limit(50)
        rel_result = await self._session.execute(rel_stmt)
        rels = rel_result.scalars().all()

        # 获取源代码片段（从当前磁盘文件读取）
        source_snippet = None
        if node.file_path and node.start_line:
            abs_path = f"{repo_path}/{node.file_path}"
            try:
                with open(abs_path, 'r') as f:
                    lines = f.readlines()
                end = node.end_line or node.start_line
                start = max(0, node.start_line - 2)
                snippet = ''.join(lines[start:end + 1])
                source_snippet = {
                    "start_line": start + 1,
                    "end_line": end,
                    "content": snippet,
                }
            except (IOError, OSError):
                pass

        return {
            "node": {
                "id": node.node_id,
                "name": node.name,
                "type": node.type,
                "file_path": node.file_path,
                "start_line": node.start_line,
                "end_line": node.end_line,
                "properties": node.properties,
            },
            "relationships": [
                {
                    "id": r.rel_id,
                    "type": r.type,
                    "source": r.source_node_id,
                    "target": r.target_node_id,
                }
                for r in rels
            ],
            "source": source_snippet,
        }
