"""
数据库迁移：给 projects 表添加代码仓库字段

运行方式:
  cd ~/test-platform/ai-test-agent-system-platform
  source .venv/bin/activate
  python backend/app/migrations/add_code_repo_fields.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import text

from app.config.database import engine


async def migrate():
    async with engine.begin() as conn:
        # 检查字段是否已存在
        result = await conn.execute(
            text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'projects' AND column_name = 'code_repo_url'
            """)
        )
        if result.fetchone():
            print("[OK] 字段已存在，跳过迁移")
            return

        # 添加字段
        await conn.execute(text("""
            ALTER TABLE projects
            ADD COLUMN code_repo_url VARCHAR(500),
            ADD COLUMN code_repo_path VARCHAR(500),
            ADD COLUMN code_repo_branch VARCHAR(100) DEFAULT 'main'
        """))
        print("[OK] 成功添加 code_repo_url, code_repo_path, code_repo_branch 字段")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
