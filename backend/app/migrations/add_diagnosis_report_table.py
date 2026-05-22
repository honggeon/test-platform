"""
诊断报告表迁移脚本

创建 diagnosis_reports 表
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
                WHERE table_schema = 'public' AND table_name = 'diagnosis_reports'
            """)
        )
        if result.fetchone():
            print("[SKIP] diagnosis_reports 表已存在")
            return

        # 创建表
        await conn.execute(
            text("""
                CREATE TABLE diagnosis_reports (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    run_id UUID NOT NULL,
                    dedup_key VARCHAR(255) NOT NULL UNIQUE,
                    report_type VARCHAR(50) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    summary_json JSONB NOT NULL DEFAULT '{}',
                    source_type VARCHAR(50) NOT NULL,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    degradation_level VARCHAR(50) NOT NULL DEFAULT 'none',
                    llm_tokens_used INTEGER NOT NULL DEFAULT 0,
                    analysis_duration_ms INTEGER NOT NULL DEFAULT 0,
                    mongo_id VARCHAR(50) NOT NULL,
                    completed_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
        )
        # 创建索引
        await conn.execute(
            text("""
                CREATE INDEX idx_diagnosis_reports_project_id ON diagnosis_reports(project_id)
            """)
        )
        await conn.execute(
            text("""
                CREATE INDEX idx_diagnosis_reports_run_id ON diagnosis_reports(run_id)
            """)
        )
        await conn.execute(
            text("""
                CREATE INDEX idx_diagnosis_reports_dedup_key ON diagnosis_reports(dedup_key)
            """)
        )
        print("[OK] 创建 diagnosis_reports 表")


if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate())
