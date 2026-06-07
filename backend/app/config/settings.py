"""
应用配置管理

使用 Pydantic Settings 管理应用配置，支持环境变量和 .env 文件
跨平台支持：自动适配 Windows/Linux 工作目录路径
"""

import os
import platform
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _CONFIG_DIR.parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
_DEFAULT_PUBLIC_API_URL = "http://localhost:8000"


def _discover_env_files() -> tuple[str, ...]:
    """加载项目根目录与 backend 目录下的 .env（后者覆盖前者）。"""
    candidates = (_REPO_ROOT / ".env", _BACKEND_DIR / ".env")
    return tuple(str(path) for path in candidates if path.is_file()) or (".env",)


def _default_workspace(sub_dir: str) -> str:
    """根据操作系统返回工作目录默认路径

    可通过 WORKSPACE_BASE 环境变量统一覆盖根路径。
    优先级: WORKSPACE_BASE 环境变量 > 平台自动检测

    Windows: C:\\Users\\<用户名>\\workspace\\backend\\workspace\\<sub_dir>
    Linux:   backend/workspace/<sub_dir>（相对于项目根目录）
    """
    base = os.environ.get("WORKSPACE_BASE", "")
    if base:
        # Windows: WORKSPACE_BASE=C:/Users/xxx/workspace
        # Linux:   WORKSPACE_BASE=/opt/workspace
        return os.path.join(base, sub_dir).replace("\\", "/")

    if platform.system() == "Windows":
        home = Path.home()
        base = home / "workspace" / "backend" / "workspace"
    else:
        # Linux / macOS：使用相对路径（从项目根目录执行）
        base = Path("backend/workspace")
    return str(base / sub_dir)


def _default_mcp_root(sub_dir: str) -> str:
    """MCP 根目录默认路径（跨平台统一使用相对路径）"""
    return f"backend/mcp/{sub_dir}"


def _default_skills_root(sub_dir: str) -> str:
    """Agent skills 根目录默认路径"""
    return f"backend/app/agents/{sub_dir}/agent_skills"


class Settings(BaseSettings):
    """应用配置类"""

    model_config = SettingsConfigDict(
        env_file=_discover_env_files(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ──────────────────────────────────────────────
    #  应用基础配置
    # ──────────────────────────────────────────────
    app_name: str = "测试管理系统"
    app_version: str = "1.0.0"
    debug: bool = False
    api_prefix: str = "/api/v2"

    # ──────────────────────────────────────────────
    #  PostgreSQL 数据库配置
    # ──────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "ai_test_management"

    @property
    def postgres_url(self) -> str:
        """获取 PostgreSQL 连接 URL（异步）"""
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

    # ──────────────────────────────────────────────
    #  MongoDB 配置
    # ──────────────────────────────────────────────
    mongodb_host: str = "localhost"
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
                f"@{self.mongodb_host}:{self.mongodb_port}/{self.mongodb_db}"
            )
        return (
            f"mongodb://{self.mongodb_host}:{self.mongodb_port}/{self.mongodb_db}"
        )

    # ──────────────────────────────────────────────
    #  速率限制 & 分页配置
    # ──────────────────────────────────────────────
    rate_limit_requests: int = 200
    rate_limit_window: int = 60
    pagination_default_size: int = 20
    pagination_max_size: int = 100

    @property
    def default_page_size(self) -> int:
        return self.pagination_default_size

    @property
    def max_page_size(self) -> int:
        return self.pagination_max_size

    # ──────────────────────────────────────────────
    #  CORS 配置
    # ──────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # ──────────────────────────────────────────────
    #  JWT 配置（用于认证）
    # ──────────────────────────────────────────────
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # ──────────────────────────────────────────────
    #  认证 SQLite 数据库（独立于 PostgreSQL，便于后续迁移）
    # ──────────────────────────────────────────────
    auth_db_path: str = "backend/data/auth.db"

    # ──────────────────────────────────────────────
    #  默认测试用户（开发环境使用）
    # ──────────────────────────────────────────────
    default_user_id: str = "00000000-0000-0000-0000-000000000001"
    default_user_email: str = "admin@test.com"
    default_user_name: str = "管理员"

    # ──────────────────────────────────────────────
    #  MinIO 对象存储配置
    # ──────────────────────────────────────────────
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "test-management"
    minio_secure: bool = False
    minio_region: Optional[str] = None

    # ──────────────────────────────────────────────
    #  附件配置
    # ──────────────────────────────────────────────
    attachment_max_size: int = 50 * 1024 * 1024  # 50 MB
    attachment_allowed_types: list[str] = [
        "image/jpeg", "image/png", "image/gif", "image/webp",
        "application/pdf", "application/zip", "application/x-rar-compressed",
        "text/plain", "text/csv",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ]

    # ──────────────────────────────────────────────
    #  PDF 解析配置
    # ──────────────────────────────────────────────
    enable_pdf_multimodal: bool = False

    # ──────────────────────────────────────────────
    #  大模型配置
    # ──────────────────────────────────────────────
    deepseek_api_key: Optional[str] = None

    # ──────────────────────────────────────────────
    #  性能测试 - 工作目录配置
    #  说明: 这些默认值使用相对路径（Linux），或用户主目录下路径（Windows）。
    #        如需自定义，在 .env 中设置对应变量即可覆盖。
    # ──────────────────────────────────────────────
    perf_workspace_root: str = "backend/app/agents/perf/workspace"
    perf_mcp_root: str = "backend/mcp/perf"
    perf_yaml_tests: str = "backend/app/agents/perf/yaml-tests"
    perf_skills_root: str = "backend/app/agents/perf/agent_skills"

    # ──────────────────────────────────────────────
    #  HAT 测试框架根目录（含 run_hat.py、conftest.py、HAT/）
    #  留空则自动从代码位置推导 backend/；可通过 HAT_HOME 环境变量覆盖
    # ──────────────────────────────────────────────
    hat_home: str = ""

    # ──────────────────────────────────────────────
    #  接口测试 - 工作目录配置
    # ──────────────────────────────────────────────
    api_workspace_root: str = "backend/workspace/api"
    api_mcp_root: str = "backend/mcp/api"
    api_skills_root: str = "backend/workspace/api"

    # ──────────────────────────────────────────────
    #  UI 测试 - 工作目录配置（暂未启用）
    # ──────────────────────────────────────────────
    # ui_workspace_root: str = "backend/app/agents/ui/workspace"
    # ui_mcp_root: str = "backend/mcp/ui"
    # ui_skills_root: str = "backend/app/agents/ui/workspace"

    # ──────────────────────────────────────────────
    #  Web 测试 - 工作目录配置
    # ──────────────────────────────────────────────
    web_workspace_root: str = "backend/workspace/web"
    web_mcp_root: str = "backend/mcp/web"
    web_skills_root: str = "backend/workspace/web"

    # ──────────────────────────────────────────────
    #  Web Chrome 测试 - 工作目录配置
    # ──────────────────────────────────────────────
    web_chrome_workspace_root: str = "backend/workspace/web_chrome"
    web_chrome_mcp_root: str = "backend/mcp/web_chrome"
    web_chrome_skills_root: str = "backend/workspace/web_chrome"

    # ──────────────────────────────────────────────
    #  测试用例 - 工作目录配置
    # ──────────────────────────────────────────────
    testcase_workspace_root: str = "backend/workspace/testcase"
    testcase_skills_root: str = "backend/workspace/testcase"

    # ──────────────────────────────────────────────
    #  日志分析 Agent - 工作目录配置
    # ──────────────────────────────────────────────
    log_analysis_workspace_root: str = "backend/workspace/diagnosis"
    log_analysis_skills_root: str = "backend/app/agents/log_analysis/agent_skills"

    # ──────────────────────────────────────────────
    #  A2A / 诊断相关配置
    # ──────────────────────────────────────────────
    public_api_url: str = _DEFAULT_PUBLIC_API_URL
    # 外部认证服务，供 HAT 登录步骤 / 执行前自动取 Token
    arag_auth_url: str = ""
    # HAT 场景测试账号（执行时注入 g_context，勿提交真实值到 Git）
    hat_test_email: str = ""
    hat_test_password: str = ""
    hat_admin_email: str = ""
    hat_admin_password: str = ""
    instance_count: int = 1
    redis_url: Optional[str] = None
    a2a_api_keys: list[str] = []
    diagnosis_report_ttl_days: int = 90


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
