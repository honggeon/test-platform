"""
迁移：给 projects 表添加 last_commit 字段
"""
from sqlalchemy import text
from app.config.database import engine


MIGRATION_SQL = """
ALTER TABLE projects ADD COLUMN IF NOT EXISTS last_commit VARCHAR(100);
COMMENT ON COLUMN projects.last_commit IS '最后分析的 Git commit SHA';
"""


async def run_migration():
    async with engine.begin() as conn:
        for statement in MIGRATION_SQL.split(";"):
            stmt = statement.strip()
            if stmt:
                await conn.execute(text(stmt))
        print("[迁移] projects.last_commit 字段已添加")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_migration())
