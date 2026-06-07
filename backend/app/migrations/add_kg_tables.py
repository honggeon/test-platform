"""
数据库迁移：创建知识图谱相关表 (kg_nodes, kg_relationships, kg_commits)

运行方式:
  cd ~/test-platform/ai-test-agent-system-platform
  source .venv/bin/activate
  python backend/app/migrations/add_kg_tables.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import text

from app.config.database import engine


async def migrate():
    async with engine.begin() as conn:
        # 检查 kg_nodes 表是否已存在
        result = await conn.execute(
            text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_name = 'kg_nodes'
            """)
        )
        if result.fetchone():
            print("[OK] 知识图谱表已存在，跳过迁移")
            return

        # 创建 kg_nodes 表
        await conn.execute(text("""
            CREATE TABLE kg_nodes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                repo_path TEXT NOT NULL,
                commit_hash TEXT NOT NULL DEFAULT 'UNKNOWN',
                node_id TEXT NOT NULL,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                file_path TEXT,
                start_line INTEGER,
                end_line INTEGER,
                properties JSONB DEFAULT '{}',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # 创建 kg_relationships 表
        await conn.execute(text("""
            CREATE TABLE kg_relationships (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                repo_path TEXT NOT NULL,
                commit_hash TEXT NOT NULL DEFAULT 'UNKNOWN',
                rel_id TEXT NOT NULL,
                type TEXT NOT NULL,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                properties JSONB DEFAULT '{}',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # 创建 kg_commits 表
        await conn.execute(text("""
            CREATE TABLE kg_commits (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                repo_path TEXT NOT NULL,
                commit_hash TEXT NOT NULL,
                commit_message TEXT,
                commit_author TEXT,
                commit_timestamp TIMESTAMPTZ,
                node_count INTEGER DEFAULT 0,
                rel_count INTEGER DEFAULT 0,
                analyzed_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # 创建索引
        await conn.execute(text("""
            CREATE INDEX idx_kg_nodes_repo_commit_type ON kg_nodes(repo_path, commit_hash, type)
        """))
        await conn.execute(text("""
            CREATE INDEX idx_kg_nodes_file_path ON kg_nodes(repo_path, commit_hash, file_path)
        """))
        await conn.execute(text("""
            CREATE INDEX idx_kg_rels_repo_commit_type ON kg_relationships(repo_path, commit_hash, type)
        """))
        await conn.execute(text("""
            CREATE INDEX idx_kg_rels_source ON kg_relationships(source_node_id)
        """))
        await conn.execute(text("""
            CREATE INDEX idx_kg_rels_target ON kg_relationships(target_node_id)
        """))
        await conn.execute(text("""
            CREATE INDEX idx_kg_commits_repo ON kg_commits(repo_path, analyzed_at DESC)
        """))

        print("[OK] 成功创建知识图谱表: kg_nodes, kg_relationships, kg_commits")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
