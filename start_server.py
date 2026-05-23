#!/usr/bin/env python3
"""
Simple LangGraph API Server

A minimal script to start the LangGraph API server directly using uvicorn.
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


import os
import sys
import json
from pathlib import Path
# fmt: off  MC80OmFIVnBZMlhwbVlqbHJvL3BuYWs2Y2xBM1RnPT06YzI4YzI5Zjk=

def setup_environment():
    """Setup required environment variables"""
    # Add backend to Python path

    src_path = Path(__file__).parent / "backend"
    sys.path.insert(0, str(src_path))
    
    # Load graphs from graph.json
    config_path = Path(__file__).parent / "graph.json"
    graphs = {}
    
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            graphs = config.get("graphs", {})
        
        # 将相对路径解析为绝对路径，避免 LangGraph 内部工作目录变化导致路径错误
        # 注意: 区分文件路径 (含 / 或 .py) 和 Python 模块路径 (如 app.agents.api.agent)
        root_dir = Path(__file__).parent.resolve()
        for name, spec in graphs.items():
            path = spec.get("path", "")
            if ":" in path:
                file_part, var_part = path.rsplit(":", 1)
            else:
                file_part, var_part = path, "agent"
            # Python 模块路径 (用 . 分隔，不含 / 和 .py)，不需要解析为文件路径
            if "/" not in file_part and not file_part.endswith(".py"):
                continue
            file_path = Path(file_part)
            if not file_path.is_absolute():
                file_path = (root_dir / file_path).resolve()
            spec["path"] = f"{file_path}:{var_part}"
    
    # Set environment variables
    os.environ.update({
        # Database and storage - 使用自定义 PostgreSQL checkpointer
        # "POSTGRES_URI": "postgresql://postgres:postgres@localhost:5432/langgraph_checkpointer_db?sslmode=disable",
        # "REDIS_URI": "redis://localhost:6379",
        "DATABASE_URI": ":memory:",
        "REDIS_URI": "fake",
        # "MIGRATIONS_PATH": "/storage/migrations",
        "MIGRATIONS_PATH": "__inmem",
        # Server configuration
        "ALLOW_PRIVATE_NETWORK": "true",
        "LANGGRAPH_UI_BUNDLER": "true",
        "LANGGRAPH_RUNTIME_EDITION": "inmem",
        "LANGSMITH_LANGGRAPH_API_VARIANT": "local_dev",
        "LANGGRAPH_DISABLE_FILE_PERSISTENCE": "false",
        "LANGGRAPH_ALLOW_BLOCKING": "true",
        "LANGGRAPH_API_URL": "http://localhost:2026",

        # "LANGGRAPH_DEFAULT_RECURSION_LIMIT": "1000",
        
        # Graphs configuration
        "LANGSERVE_GRAPHS": json.dumps(graphs) if graphs else "{}",
        
        # Worker configuration
        "N_JOBS_PER_WORKER": "1",
    })
# type: ignore  MS80OmFIVnBZMlhwbVlqbHJvL3BuYWs2Y2xBM1RnPT06YzI4YzI5Zjk=
    
    # Load .env file if exists
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            print(f"✅ Loaded environment from .env")
        except ImportError:
            print("⚠️  python-dotenv not installed, skipping .env file")
# fmt: off  Mi80OmFIVnBZMlhwbVlqbHJvL3BuYWs2Y2xBM1RnPT06YzI4YzI5Zjk=

def main():
    """Start the server"""
    print("🚀 Starting Simple LangGraph API Server...")
    
    # Setup environment
    setup_environment()
    
    # Print server information
    print("\n" + "="*60)
    print("📍 Server URL: http://localhost:2026")
    print("📚 API Documentation: http://localhost:2026/docs")
    print("🎨 Studio UI: http://localhost:2026/ui")
    print("💚 Health Check: http://localhost:2026/ok")
    print("="*60)
    
    try:
        # Import uvicorn after environment setup
        import uvicorn
        from langgraph_api.server import app
        from starlette.middleware.cors import CORSMiddleware
        
        # 添加 CORS 中间件，允许前端开发服务器跨域访问
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
            ],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Start the server directly
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=2026,
            reload=False,
            access_log=False,
            log_config={
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "default": {
                        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    }
                },
                "handlers": {
                    "default": {
                        "formatter": "default",
                        "class": "logging.StreamHandler",
                        "stream": "ext://sys.stdout",
                    }
                },
                "root": {
                    "level": "INFO",
                    "handlers": ["default"],
                },
                "loggers": {
                    "uvicorn": {"level": "INFO"},
                    "uvicorn.error": {"level": "INFO"},
                    "uvicorn.access": {"level": "WARNING"},
                }
            }
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Server failed to start: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
# pylint: disable  My80OmFIVnBZMlhwbVlqbHJvL3BuYWs2Y2xBM1RnPT06YzI4YzI5Zjk=

if __name__ == "__main__":
    main()
