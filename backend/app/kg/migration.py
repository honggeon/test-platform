"""
知识图谱数据库迁移

创建/升级 kg_nodes、kg_relationships 表，以及 kg_commits 元信息表。
支持从 v1（无 commit_hash）安全升级到 v2。
"""

from sqlalchemy import text

from app.config.database import engine


# ── Migration V2: 多版本图谱存储 ───────────────────────────────────────────


async def run_migration():
    """执行迁移（幂等：可安全重复执行）"""
    async with engine.begin() as conn:
        # 启用 pg_trgm 扩展（用于模糊搜索）
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

        # ── 1. 检查当前 schema 版本 ──
        check = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = 'kg_nodes' AND column_name = 'commit_hash')"
        ))
        has_commit_hash = check.scalar()

        if has_commit_hash:
            # 已经是 v2，只需确保 kg_commits 表存在
            await _ensure_commits_table(conn)
            print("[迁移] Schema 已为 v2，跳过表结构升级")
        else:
            # 检查 kg_nodes 是否存在（区分全新安装 vs v1 升级）
            check2 = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'kg_nodes')"
            ))
            kg_nodes_exists = check2.scalar()

            if kg_nodes_exists:
                await _upgrade_v1_to_v2(conn)
            else:
                await _create_v2(conn)

        print("[迁移] 数据库 Schema v2 就绪（多版本图谱存储）")


async def _create_v2(conn):
    """全新创建 v2 表（含 commit_hash）"""
    statements = [
        # kg_nodes 表
        """
        CREATE TABLE IF NOT EXISTS kg_nodes (
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
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(repo_path, commit_hash, node_id)
        )
        """,
        "COMMENT ON TABLE kg_nodes IS '代码知识图谱节点表'",
        "COMMENT ON COLUMN kg_nodes.commit_hash IS 'Git commit hash，标识图谱版本'",
        "COMMENT ON COLUMN kg_nodes.node_id IS '图中唯一 ID'",
        "COMMENT ON COLUMN kg_nodes.type IS '节点类型 (file/folder/class/function/...)'",

        # kg_relationships 表
        """
        CREATE TABLE IF NOT EXISTS kg_relationships (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            repo_path TEXT NOT NULL,
            commit_hash TEXT NOT NULL DEFAULT 'UNKNOWN',
            rel_id TEXT NOT NULL,
            type TEXT NOT NULL,
            source_node_id TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            properties JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(repo_path, commit_hash, rel_id)
        )
        """,
        "COMMENT ON TABLE kg_relationships IS '代码知识图谱关系表'",
        "COMMENT ON COLUMN kg_relationships.commit_hash IS 'Git commit hash，标识图谱版本'",
        "COMMENT ON COLUMN kg_relationships.type IS '关系类型 (CONTAINS/IMPORTS/CALLS/EXTENDS/...)'",

        # kg_commits 元信息表
        """
        CREATE TABLE IF NOT EXISTS kg_commits (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            repo_path TEXT NOT NULL,
            commit_hash TEXT NOT NULL,
            commit_message TEXT,
            commit_author TEXT,
            commit_timestamp TIMESTAMP WITH TIME ZONE,
            node_count INTEGER DEFAULT 0,
            rel_count INTEGER DEFAULT 0,
            analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(repo_path, commit_hash)
        )
        """,
        "COMMENT ON TABLE kg_commits IS '已分析的 commit 版本元信息'",
        "CREATE INDEX IF NOT EXISTS idx_kg_commits_repo ON kg_commits(repo_path, analyzed_at DESC)",
    ]
    for stmt in statements:
        await conn.execute(text(stmt))

    # 创建 v2 索引
    await _create_v2_indexes(conn)


async def _upgrade_v1_to_v2(conn):
    """从 v1 升级：添加 commit_hash 字段、更新约束和索引"""
    statements = [
        # 1. 添加 commit_hash 字段
        "ALTER TABLE kg_nodes ADD COLUMN IF NOT EXISTS commit_hash TEXT NOT NULL DEFAULT 'UNKNOWN'",
        "ALTER TABLE kg_relationships ADD COLUMN IF NOT EXISTS commit_hash TEXT NOT NULL DEFAULT 'UNKNOWN'",

        # 2. 删除旧唯一约束（v1: repo_path + node_id/rel_id）
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'kg_nodes_repo_path_node_id_key') THEN
                ALTER TABLE kg_nodes DROP CONSTRAINT kg_nodes_repo_path_node_id_key;
            END IF;
        END $$;
        """,
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'kg_relationships_repo_path_rel_id_key') THEN
                ALTER TABLE kg_relationships DROP CONSTRAINT kg_relationships_repo_path_rel_id_key;
            END IF;
        END $$;
        """,

        # 3. 添加新唯一约束（v2: repo_path + commit_hash + node_id/rel_id）
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'kg_nodes_repo_commit_node_key') THEN
                ALTER TABLE kg_nodes ADD CONSTRAINT kg_nodes_repo_commit_node_key UNIQUE(repo_path, commit_hash, node_id);
            END IF;
        END $$;
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'kg_rels_repo_commit_rel_key') THEN
                ALTER TABLE kg_relationships ADD CONSTRAINT kg_rels_repo_commit_rel_key UNIQUE(repo_path, commit_hash, rel_id);
            END IF;
        END $$;
        """,
    ]
    for stmt in statements:
        await conn.execute(text(stmt))

    # 4. 删除旧索引，创建新索引
    await _drop_v1_indexes(conn)
    await _create_v2_indexes(conn)

    # 5. 创建 kg_commits 表
    await _ensure_commits_table(conn)

    print("[迁移] v1 → v2 升级完成")


async def _ensure_commits_table(conn):
    """确保 kg_commits 表存在"""
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS kg_commits (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            repo_path TEXT NOT NULL,
            commit_hash TEXT NOT NULL,
            commit_message TEXT,
            commit_author TEXT,
            commit_timestamp TIMESTAMP WITH TIME ZONE,
            node_count INTEGER DEFAULT 0,
            rel_count INTEGER DEFAULT 0,
            analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(repo_path, commit_hash)
        )
    """))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_kg_commits_repo ON kg_commits(repo_path, analyzed_at DESC)"))


async def _drop_v1_indexes(conn):
    """删除 v1 索引（如果存在）"""
    old_indexes = [
        "idx_kg_nodes_repo_type",
        "idx_kg_nodes_name",
        "idx_kg_nodes_fts",
        "idx_kg_rels_repo_type",
        "idx_kg_rels_source",
        "idx_kg_rels_target",
        # 也可能存在之前命名风格的索引
        "kg_nodes_fts_idx",
        "kg_nodes_repo_type_idx",
        "kg_rels_repo_type_idx",
        "kg_rels_source_target_idx",
    ]
    for idx in old_indexes:
        await conn.execute(text(f"DROP INDEX IF EXISTS {idx}"))


async def _create_v2_indexes(conn):
    """创建 v2 复合索引（含 commit_hash）"""
    indexes = [
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
    ]
    for stmt in indexes:
        await conn.execute(text(stmt))


# ── 回滚 ──────────────────────────────────────────────────────────────────


ROOLBACK_SQL = """
DROP TABLE IF EXISTS kg_commits;
DROP TABLE IF EXISTS kg_relationships;
DROP TABLE IF EXISTS kg_nodes;
"""


async def rollback_migration():
    """回滚迁移（删除所有 KG 表）"""
    async with engine.begin() as conn:
        for statement in ROOLBACK_SQL.split(";"):
            stmt = statement.strip()
            if stmt:
                await conn.execute(text(stmt))
        print("[迁移] kg_nodes + kg_relationships + kg_commits 表已删除")
