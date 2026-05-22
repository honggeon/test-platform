"""
应用配置管理

使用 Pydantic Settings 管理应用配置，支持环境变量和 .env 文件
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
    
    # 应用基础配置
    app_name: str = "测试管理系统"
    app_version: str = "1.0.0"
    debug: bool = False
    api_prefix: str = "/api/v2"
    
    # PostgreSQL 数据库配置
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "ai_test_management"
    
    @property
    def postgres_url(self) -> str:
        """获取 PostgreSQL 连接 URL"""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    @property
    def postgres_sync_url(self) -> str:
        """获取 PostgreSQL 同步连接 URL（用于 Alembic）"""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    # MongoDB 配置
    mongodb_host: str = "121.40.159.60"
    mongodb_port: int = 27017
    mongodb_user: Optional[str] = None
    mongodb_password: Optional[str] = None
    mongodb_db: str = "ai_test_management"
    
    @property
    def mongodb_url(self) -> str:
        """获取 MongoDB 连接 URL"""
        if self.mongodb_user and self.mongodb_password:
            return (
                f"mongodb://{self.mongodb_user}:{self.mongodb_password}"
                f"@{self.mongodb_host}:{self.mongodb_port}"
            )
        return f"mongodb://{self.mongodb_host}:{self.mongodb_port}"
    
    # 速率限制配置
    rate_limit_requests: int = 300  # 每分钟最大请求数
    rate_limit_window: int = 60  # 时间窗口（秒）
    
    # 分页配置
    pagination_default_size: int = 30
    pagination_max_size: int = 300

    @property
    def default_page_size(self) -> int:
        """获取默认分页大小（别名）"""
        return self.pagination_default_size

    @property
    def max_page_size(self) -> int:
        """获取最大分页大小（别名）"""
        return self.pagination_max_size
    
    # CORS 配置
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # JWT 配置（用于认证）
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # 默认测试用户配置（开发环境使用）
    default_user_id: str = "00000000-0000-0000-0000-000000000001"
    default_user_email: str = "admin@test.com"
    default_user_name: str = "管理员"

    # MinIO 对象存储配置
    minio_endpoint: str = "114.55.110.60:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "test-management"
    minio_secure: bool = False  # 是否使用 HTTPS
    minio_region: Optional[str] = None

    # 附件配置
    attachment_max_size: int = 50 * 1024 * 1024  # 50 MB
    attachment_allowed_types: list[str] = [
        "image/jpeg", "image/png", "image/gif", "image/webp",
        "application/pdf", "application/zip", "application/x-rar-compressed",
        "text/plain", "text/csv",
        "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ]

    # PDF 解析配置
    enable_pdf_multimodal: bool = False  # 是否启用 PDF 多模态图片解析（需要配置 DOUBAO_API_KEY）

    # 大模型配置
    deepseek_api_key: Optional[str] = None

    # 性能测试工作目录配置
    perf_workspace_root: str = "backend/app/agents/perf/workspace"
    perf_mcp_root: str = "backend/mcp/perf"
    perf_yaml_tests: str = "backend/app/agents/perf/yaml-tests"
    perf_skills_root: str = "backend/app/agents/perf/agent_skills"

    # 接口测试工作目录配置
    api_workspace_root: str = "C:/Users/65132/Desktop/workspace/testing/ai-test-management/backend/workspace/api"
    api_mcp_root: str = "backend/mcp/api"
    api_skills_root: str = "C:/Users/65132/Desktop/workspace/testing/ai-test-management/backend/workspace/api"

    # UI 测试工作目录配置
    # ui_workspace_root: str = "backend/app/agents/ui/workspace"
    # ui_mcp_root: str = "backend/mcp/ui"
    # ui_skills_root: str = "backend/app/agents/ui/workspace"

    # Web 测试工作目录配置
    web_workspace_root: str = "C:/Users/65132/Desktop/workspace/testing/ai-test-management/backend/workspace/web"
    web_mcp_root: str = "backend/mcp/web"
    web_skills_root: str = "C:/Users/65132/Desktop/workspace/testing/ai-test-management/backend/workspace/web"

    # Web Chrome 测试工作目录配置
    web_chrome_workspace_root: str = "C:/Users/65132/Desktop/workspace/testing/ai-test-management/backend/workspace/web_chrome"
    web_chrome_mcp_root: str = "backend/mcp/web_chrome"
    web_chrome_skills_root: str = "C:/Users/65132/Desktop/workspace/testing/ai-test-management/backend/workspace/web_chrome"

    # 测试用例工作目录配置
    testcase_workspace_root: str = "C:/Users/65132/Desktop/workspace/testing/ai-test-management/backend/workspace/testcase"
    testcase_skills_root: str = "C:/Users/65132/Desktop/workspace/testing/ai-test-management/backend/workspace/testcase"

    # 日志分析 Agent 工作目录配置
    log_analysis_workspace_root: str = "backend/workspace/diagnosis"
    log_analysis_skills_root: str = "backend/app/agents/log_analysis/agent_skills"

    # A2A / 诊断相关配置
    public_api_url: str = "http://localhost:8000"
    instance_count: int = 1
    redis_url: Optional[str] = None
    a2a_api_keys: list[str] = []
    diagnosis_report_ttl_days: int = 90


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()

