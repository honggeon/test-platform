"""
PostgreSQL 知识图谱持久化

替代 GitNexus 的 LadybugDB (KuzuDB) 持久化层。

将 KnowledgeGraph 中的节点和关系写入 PostgreSQL 的 kg_nodes / kg_relationships 表。
支持多版本共存（按 commit_hash 区分）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import Column, Integer, Text, DateTime, text, delete, select, func, or_
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import Base
from app.kg.graph import KnowledgeGraph
from app.kg.types import GraphNode, GraphRelationship


# ── SQLAlchemy ORM 模型 ──────────────────────────────────────────────────


class KGNode(Base):
    """知识图谱节点表（多版本）"""
    __tablename__ = "kg_nodes"
    __table_args__ = {"comment": "代码知识图谱节点表（按 commit_hash 区分版本）"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    repo_path = Column(Text, nullable=False, comment="代码仓库路径")
    commit_hash = Column(Text, nullable=False, default="UNKNOWN", comment="Git commit hash")
    node_id = Column(Text, nullable=False, comment="图中唯一 ID")
    type = Column(Text, nullable=False, comment="节点类型")
    name = Column(Text, nullable=False, comment="节点名称")
    file_path = Column(Text, nullable=True, comment="源文件路径")
    start_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    properties = Column(JSONB, default=dict, comment="扩展属性")
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))


class KGRelationship(Base):
    """知识图谱关系表（多版本）"""
    __tablename__ = "kg_relationships"
    __table_args__ = {"comment": "代码知识图谱关系表（按 commit_hash 区分版本）"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    repo_path = Column(Text, nullable=False, comment="代码仓库路径")
    commit_hash = Column(Text, nullable=False, default="UNKNOWN", comment="Git commit hash")
    rel_id = Column(Text, nullable=False, comment="图中唯一 ID")
    type = Column(Text, nullable=False, comment="关系类型")
    source_node_id = Column(Text, nullable=False, comment="源节点 ID")
    target_node_id = Column(Text, nullable=False, comment="目标节点 ID")
    properties = Column(JSONB, default=dict, comment="扩展属性")
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))


class KGCommit(Base):
    """已分析的 commit 版本元信息"""
    __tablename__ = "kg_commits"
    __table_args__ = {"comment": "已分析的 commit 版本元信息"}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    repo_path = Column(Text, nullable=False)
    commit_hash = Column(Text, nullable=False)
    commit_message = Column(Text, nullable=True)
    commit_author = Column(Text, nullable=True)
    commit_timestamp = Column(DateTime(timezone=True), nullable=True)
    node_count = Column(Integer, default=0)
    rel_count = Column(Integer, default=0)
    analyzed_at = Column(DateTime(timezone=True), server_default=text("NOW()"))


@dataclass
class CommitInfo:
    """Commit 元信息"""
    commit_hash: str
    commit_message: str | None
    commit_author: str | None
    commit_timestamp: str | None
    node_count: int
    rel_count: int
    analyzed_at: str


# ── 数据库索引 ────────────────────────────────────────────────────────────


_INDEX_STMTS = [
    # 节点表索引
    "CREATE INDEX IF NOT EXISTS idx_kg_nodes_repo_commit_type ON kg_nodes(repo_path, commit_hash, type)",
    "CREATE INDEX IF NOT EXISTS idx_kg_nodes_name ON kg_nodes USING gin(name gin_trgm_ops)",
    """
    CREATE INDEX IF NOT EXISTS idx_kg_nodes_fts ON kg_nodes
    USING gin(to_tsvector('english', name || ' ' || COALESCE(properties->>'doc', '')))
    """,
    "CREATE INDEX IF NOT EXISTS idx_kg_nodes_file_path ON kg_nodes(repo_path, commit_hash, file_path)",
    # 关系表索引
    "CREATE INDEX IF NOT EXISTS idx_kg_rels_repo_commit_type ON kg_relationships(repo_path, commit_hash, type)",
    "CREATE INDEX IF NOT EXISTS idx_kg_rels_source ON kg_relationships(source_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_kg_rels_target ON kg_relationships(target_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_kg_rels_repo_commit_source ON kg_relationships(repo_path, commit_hash, source_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_kg_rels_repo_commit_target ON kg_relationships(repo_path, commit_hash, target_node_id)",
    # commit 元信息表索引
    "CREATE INDEX IF NOT EXISTS idx_kg_commits_repo ON kg_commits(repo_path, analyzed_at DESC)",
]


async def ensure_indexes(session):
    """确保数据库索引存在"""
    # pg_trgm 扩展是 gin_trgm_ops 索引的前置依赖
    await session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    for stmt in _INDEX_STMTS:
        await session.execute(text(stmt))
    await session.commit()


# ── 持久化服务 ────────────────────────────────────────────────────────────


class GraphPersistence:
    """知识图谱持久化（多版本）

    将 KnowledgeGraph 保存到 PostgreSQL（替代 LadybugDB）。
    支持按 commit_hash 存储多个版本，自动清理旧版本。
    """

    # 每个仓库最多保留的 commit 版本数
    MAX_VERSIONS = 10

    def __init__(self, session: AsyncSession):
        self._session = session

    # ── 写操作 ────────────────────────────────────────────────────────────

    async def save_graph(
        self, repo_path: str, commit_hash: str, graph: KnowledgeGraph,
        commit_message: str | None = None,
        commit_author: str | None = None,
        commit_timestamp: str | None = None,
    ) -> dict:
        """将知识图谱写入 PostgreSQL（指定 commit 版本）

        先清空该 repo + commit 的旧数据（幂等），再批量写入新数据。
        不删除其他 commit 版本的数据。

        Args:
            repo_path: 代码仓库路径
            commit_hash: Git commit hash
            graph: 要持久化的知识图谱
            commit_message: 提交信息
            commit_author: 提交作者
            commit_timestamp: 提交时间（ISO 格式字符串）

        Returns:
            写入统计信息
        """
        # 1. 清空该 repo + commit 的旧数据
        await self._clear_commit_data(repo_path, commit_hash)

        # 2. 批量写入节点
        nodes_written = 0
        for node in graph.iter_nodes():
            self._session.add(KGNode(
                repo_path=repo_path,
                commit_hash=commit_hash,
                node_id=node.id,
                type=node.type,
                name=node.name,
                file_path=node.file_path,
                start_line=node.start_line,
                end_line=node.end_line,
                properties=node.properties or {},
            ))
            nodes_written += 1

        # 3. 批量写入关系
        rels_written = 0
        for rel in graph.iter_relationships():
            self._session.add(KGRelationship(
                repo_path=repo_path,
                commit_hash=commit_hash,
                rel_id=rel.id,
                type=rel.type,
                source_node_id=rel.source_id,
                target_node_id=rel.target_id,
                properties=rel.properties or {},
            ))
            rels_written += 1

        # 4. 更新/插入 commit 元信息
        await self._upsert_commit_meta(
            repo_path, commit_hash,
            node_count=nodes_written,
            rel_count=rels_written,
            commit_message=commit_message,
            commit_author=commit_author,
            commit_timestamp=commit_timestamp,
        )

        await self._session.commit()

        # 5. 清理旧版本
        await self._cleanup_old_versions(repo_path)

        return {
            "commit_hash": commit_hash,
            "nodes_written": nodes_written,
            "relationships_written": rels_written,
        }

    async def _clear_commit_data(self, repo_path: str, commit_hash: str) -> None:
        """清空某个仓库指定 commit 的所有数据"""
        await self._session.execute(
            delete(KGNode).where(
                KGNode.repo_path == repo_path,
                KGNode.commit_hash == commit_hash,
            )
        )
        await self._session.execute(
            delete(KGRelationship).where(
                KGRelationship.repo_path == repo_path,
                KGRelationship.commit_hash == commit_hash,
            )
        )
        await self._session.flush()

    async def _upsert_commit_meta(
        self, repo_path: str, commit_hash: str,
        node_count: int, rel_count: int,
        commit_message: str | None = None,
        commit_author: str | None = None,
        commit_timestamp: str | None = None,
    ) -> None:
        """更新或插入 commit 元信息"""
        # 先删除旧记录
        await self._session.execute(
            delete(KGCommit).where(
                KGCommit.repo_path == repo_path,
                KGCommit.commit_hash == commit_hash,
            )
        )
        # 插入新记录
        from datetime import datetime
        ts = None
        if commit_timestamp:
            try:
                ts = datetime.fromisoformat(commit_timestamp.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        self._session.add(KGCommit(
            repo_path=repo_path,
            commit_hash=commit_hash,
            commit_message=commit_message,
            commit_author=commit_author,
            commit_timestamp=ts,
            node_count=node_count,
            rel_count=rel_count,
        ))
        await self._session.flush()

    async def _cleanup_old_versions(self, repo_path: str, keep: int | None = None) -> None:
        """只保留最近 N 个 commit 的图谱数据"""
        keep = keep or self.MAX_VERSIONS

        # 查询该 repo 的所有 commit（按分析时间倒序）
        result = await self._session.execute(
            select(KGCommit.commit_hash)
            .where(KGCommit.repo_path == repo_path)
            .order_by(KGCommit.analyzed_at.desc())
        )
        all_commits = [row[0] for row in result.all()]

        if len(all_commits) <= keep:
            return

        # 删除旧的 commit 数据
        to_delete = all_commits[keep:]
        for ch in to_delete:
            await self._session.execute(
                delete(KGNode).where(
                    KGNode.repo_path == repo_path,
                    KGNode.commit_hash == ch,
                )
            )
            await self._session.execute(
                delete(KGRelationship).where(
                    KGRelationship.repo_path == repo_path,
                    KGRelationship.commit_hash == ch,
                )
            )
            await self._session.execute(
                delete(KGCommit).where(
                    KGCommit.repo_path == repo_path,
                    KGCommit.commit_hash == ch,
                )
            )
        await self._session.commit()

    # ── Commit 管理 ───────────────────────────────────────────────────────

    async def get_latest_commit(self, repo_path: str) -> str | None:
        """获取该 repo 最新分析的 commit hash"""
        result = await self._session.execute(
            select(KGCommit.commit_hash)
            .where(KGCommit.repo_path == repo_path)
            .order_by(KGCommit.analyzed_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row

    async def list_commits(self, repo_path: str, limit: int = 20) -> list[CommitInfo]:
        """列出该 repo 已分析的所有 commit（按时间倒序）

        兼容旧数据：如果 kg_commits 为空但 kg_nodes 有数据，
        返回一个虚拟的 UNKNOWN commit。
        """
        result = await self._session.execute(
            select(KGCommit)
            .where(KGCommit.repo_path == repo_path)
            .order_by(KGCommit.analyzed_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()

        if rows:
            return [
                CommitInfo(
                    commit_hash=r.commit_hash,
                    commit_message=r.commit_message,
                    commit_author=r.commit_author,
                    commit_timestamp=r.commit_timestamp.isoformat() if r.commit_timestamp else None,
                    node_count=r.node_count or 0,
                    rel_count=r.rel_count or 0,
                    analyzed_at=r.analyzed_at.isoformat() if r.analyzed_at else "",
                )
                for r in rows
            ]

        # 兼容旧数据：检查是否有 UNKNOWN commit 的数据
        unknown_count = await self._session.execute(
            select(func.count(KGNode.id))
            .where(KGNode.repo_path == repo_path)
            .where(KGNode.commit_hash == "UNKNOWN")
        )
        count = unknown_count.scalar() or 0
        if count > 0:
            rel_count_result = await self._session.execute(
                select(func.count(KGRelationship.id))
                .where(KGRelationship.repo_path == repo_path)
                .where(KGRelationship.commit_hash == "UNKNOWN")
            )
            rel_count = rel_count_result.scalar() or 0
            return [
                CommitInfo(
                    commit_hash="UNKNOWN",
                    commit_message="历史数据（迁移前分析）",
                    commit_author=None,
                    commit_timestamp=None,
                    node_count=count,
                    rel_count=rel_count,
                    analyzed_at="",
                )
            ]

        return []

    # ── 查询方法（所有方法支持可选 commit_hash，不传则取最新） ────────────

    async def _resolve_commit(self, repo_path: str, commit_hash: str | None) -> str:
        """解析 commit_hash：传了就用，没传取最新"""
        if commit_hash:
            return commit_hash
        latest = await self.get_latest_commit(repo_path)
        if not latest:
            # 兼容旧数据（无 kg_commits 记录但 kg_nodes 有数据）
            # 检查是否有 UNKNOWN commit 的数据
            result = await self._session.execute(
                select(KGNode.commit_hash)
                .where(KGNode.repo_path == repo_path)
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return row or "UNKNOWN"
        return latest

    async def get_nodes_by_type(
        self, repo_path: str, node_type: str,
        commit_hash: str | None = None, limit: int = 100,
    ) -> list[GraphNode]:
        """按类型查询节点"""
        ch = await self._resolve_commit(repo_path, commit_hash)
        result = await self._session.execute(
            select(KGNode)
            .where(KGNode.repo_path == repo_path)
            .where(KGNode.commit_hash == ch)
            .where(KGNode.type == node_type)
            .limit(limit)
        )
        return [self._to_graph_node(row) for row in result.scalars()]

    async def find_nodes_by_name(
        self, repo_path: str, name_query: str,
        commit_hash: str | None = None, limit: int = 50,
    ) -> list[GraphNode]:
        """按名称模糊搜索节点"""
        ch = await self._resolve_commit(repo_path, commit_hash)
        result = await self._session.execute(
            select(KGNode)
            .where(KGNode.repo_path == repo_path)
            .where(KGNode.commit_hash == ch)
            .where(KGNode.name.ilike(f"%{name_query}%"))
            .limit(limit)
        )
        return [self._to_graph_node(row) for row in result.scalars()]

    async def get_relationships_for_node(
        self, repo_path: str, node_id: str,
        commit_hash: str | None = None,
    ) -> list[GraphRelationship]:
        """获取某节点关联的所有关系"""
        ch = await self._resolve_commit(repo_path, commit_hash)
        result = await self._session.execute(
            select(KGRelationship)
            .where(KGRelationship.repo_path == repo_path)
            .where(KGRelationship.commit_hash == ch)
            .where(
                or_(
                    KGRelationship.source_node_id == node_id,
                    KGRelationship.target_node_id == node_id,
                )
            )
        )
        return [self._to_graph_rel(row) for row in result.scalars()]

    async def get_node_count(self, repo_path: str, commit_hash: str | None = None) -> int:
        """获取仓库的节点数"""
        ch = await self._resolve_commit(repo_path, commit_hash)
        result = await self._session.execute(
            select(func.count(KGNode.id))
            .where(KGNode.repo_path == repo_path)
            .where(KGNode.commit_hash == ch)
        )
        return result.scalar() or 0

    async def get_relationship_count(self, repo_path: str, commit_hash: str | None = None) -> int:
        result = await self._session.execute(
            select(func.count(KGRelationship.id))
            .where(KGRelationship.repo_path == repo_path)
            .where(KGRelationship.commit_hash == await self._resolve_commit(repo_path, commit_hash))
        )
        return result.scalar() or 0

    async def get_nodes_by_repo(
        self, repo_path: str, commit_hash: str | None = None, limit: int = 200,
    ) -> list[GraphNode]:
        ch = await self._resolve_commit(repo_path, commit_hash)
        result = await self._session.execute(
            select(KGNode)
            .where(KGNode.repo_path == repo_path)
            .where(KGNode.commit_hash == ch)
            .limit(limit)
        )
        return [self._to_graph_node(row) for row in result.scalars()]

    async def get_relationships_by_repo(
        self, repo_path: str, commit_hash: str | None = None, limit: int = 500,
    ) -> list[GraphRelationship]:
        ch = await self._resolve_commit(repo_path, commit_hash)
        result = await self._session.execute(
            select(KGRelationship)
            .where(KGRelationship.repo_path == repo_path)
            .where(KGRelationship.commit_hash == ch)
            .limit(limit)
        )
        return [self._to_graph_rel(row) for row in result.scalars()]

    async def get_type_counts(self, repo_path: str, commit_hash: str | None = None) -> dict[str, int]:
        """按类型统计节点数量"""
        ch = await self._resolve_commit(repo_path, commit_hash)
        result = await self._session.execute(
            select(KGNode.type, func.count(KGNode.id))
            .where(KGNode.repo_path == repo_path)
            .where(KGNode.commit_hash == ch)
            .group_by(KGNode.type)
        )
        return {row[0]: row[1] for row in result.all()}

    async def get_all_nodes_for_commit(
        self, repo_path: str, commit_hash: str,
    ) -> list[GraphNode]:
        """获取某个 commit 的所有节点（无 limit，用于版本对比）"""
        result = await self._session.execute(
            select(KGNode)
            .where(KGNode.repo_path == repo_path)
            .where(KGNode.commit_hash == commit_hash)
        )
        return [self._to_graph_node(row) for row in result.scalars()]

    async def get_all_relationships_for_commit(
        self, repo_path: str, commit_hash: str,
    ) -> list[GraphRelationship]:
        """获取某个 commit 的所有关系（无 limit，用于版本对比）"""
        result = await self._session.execute(
            select(KGRelationship)
            .where(KGRelationship.repo_path == repo_path)
            .where(KGRelationship.commit_hash == commit_hash)
        )
        return [self._to_graph_rel(row) for row in result.scalars()]

    # ── 转换方法 ──────────────────────────────────────────────────────────

    @staticmethod
    def _to_graph_node(row) -> GraphNode:
        return GraphNode(
            id=row.node_id,
            type=row.type,
            name=row.name,
            file_path=row.file_path,
            start_line=row.start_line,
            end_line=row.end_line,
            properties=row.properties or {},
        )

    @staticmethod
    def _to_graph_rel(row) -> GraphRelationship:
        return GraphRelationship(
            id=row.rel_id,
            source_id=row.source_node_id,
            target_id=row.target_node_id,
            type=row.type,
            properties=row.properties or {},
        )
