"""
LLM 配置表迁移脚本

创建 llm_configs 表
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from sqlalchemy import text

from app.config.database import engine


async def migrate():
    """执行迁移"""
    async with engine.begin() as conn:
        # 检查表是否已存在
        result = await conn.execute(
            text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'llm_configs'
            """)
        )
        if result.fetchone():
            print("[SKIP] llm_configs 表已存在")
            return

        # 创建表
        await conn.execute(
            text("""
                CREATE TABLE llm_configs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    provider VARCHAR(50) NOT NULL DEFAULT 'deepseek',
                    model_name VARCHAR(100) NOT NULL DEFAULT 'deepseek-chat',
                    api_key VARCHAR(500),
                    base_url VARCHAR(500),
                    temperature FLOAT DEFAULT 0.7,
                    max_tokens INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(project_id)
                )
            """)
        )
        print("[OK] 创建 llm_configs 表")


if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate())
