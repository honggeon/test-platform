# ─── 测试管理平台 - Makefile ──────────────────────────────────────────────
# 用法:
#   make start        后台启动全部服务
#   make stop         停止全部服务
#   make status       查看服务状态
#   make dev          前台开发模式启动 (推荐开发时使用)
#   make logs         查看实时日志
#   make restart      重启全部服务
#   make build        构建前端
#   make init         初始化环境 (.env / 依赖 / 数据库)
# ──────────────────────────────────────────────────────────────────────────

.PHONY: help init build \
        start start-backend start-langgraph start-ui start-dev start-all \
        dev dev-backend dev-langgraph dev-ui \
        stop stop-all restart \
        status logs log-backend log-langgraph log-ui \
        kg-migrate kg-rollback kg-analyze kg-analyze-full kg-shell \
        clean

BACKEND = backend
UI = ui
PYTHON = $(CURDIR)/.venv/bin/python
LOG_DIR = $(CURDIR)/logs

# ─── 帮助 ────────────────────────────────────────────────────────────────

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ─── 初始化 ──────────────────────────────────────────────────────────────

init: ## 初始化环境 (检查 .env / 安装依赖 / 数据库迁移)
	@echo "🔧 初始化环境..."
	@if [ ! -f "$(BACKEND)/.env" ]; then \
		echo "  ⚠️  $(BACKEND)/.env 不存在，请从 .env.example 复制"; \
	fi
	@if [ ! -f "$(UI)/.env.local" ] && [ ! -f "$(UI)/.env" ]; then \
		echo "  ⚠️  $(UI)/.env.local 不存在，请从 .env.example 复制"; \
	fi
	@echo "  📦 检查 Python 依赖..."
	@uv sync >/dev/null 2>&1 || pip install -r requirements.txt 2>/dev/null || true
	@echo "  📦 检查 Node 依赖..."
	@cd $(UI) && npm install >/dev/null 2>&1 || true
	@echo "  🗄️  数据库迁移..."
	@make kg-migrate >/dev/null 2>&1 || true
	@echo "✅ 初始化完成"

# ─── 构建 ────────────────────────────────────────────────────────────────

build: ## 构建 Next.js 前端 (生产模式需要先构建)
	@echo "🔨 构建前端..."
	@cd $(UI) && npm run build
	@echo "✅ 构建完成"

# ─── 一键启动 ────────────────────────────────────────────────────────────

start: start-all ## 后台启动全部服务 (别名)

restart: stop start-all ## 重启全部服务

# ─── 后台启动 ────────────────────────────────────────────────────────────

start-all: ## 后台启动全部服务 (FastAPI + LangGraph + Next.js)
	@bash scripts/start-all.sh

stop: stop-all ## 停止后台全部服务

stop-all: ## 停止后台全部服务
	@bash scripts/stop-all.sh

status: ## 查看服务运行状态
	@echo ""
	@echo "📊 服务状态"
	@echo "─────────────────────────────"
	@for pair in "FastAPI 后端:8000" "LangGraph API:2026" "Next.js 前端:3000"; do \
		name=$${pair%:*}; port=$${pair#*:}; \
		pid=$$(lsof -ti :$$port 2>/dev/null); \
		if [ -z "$$pid" ] && [ "$$port" = "3000" ]; then \
			pid=$$(ss -tlnp 2>/dev/null | grep ":3000" | grep -oP "pid=\K[0-9]+" | head -1); \
		fi; \
		if [ -n "$$pid" ]; then \
			echo "  ✅ $$name  端口 $$port  PID $$pid"; \
		else \
			echo "  ❌ $$name  端口 $$port"; \
		fi; \
	done
	@echo ""
	@echo "📁 日志目录: $(LOG_DIR)"
	@echo "🌐 访问地址:"
	@echo "   FastAPI    http://localhost:8000/docs"
	@echo "   LangGraph  http://localhost:2026/docs"
	@echo "   前端       http://localhost:3000"
	@echo ""

# ─── 前台开发模式 ────────────────────────────────────────────────────────

# dev 目标会并行启动 3 个服务，适合开发调试
# 使用 `tmux` 或开多个终端分别运行:
#   make dev-backend  (终端 1)
#   make dev-langgraph (终端 2)
#   make dev-ui       (终端 3)

dev: ## 提示如何启动开发环境
	@echo ""
	@echo "🚀 开发模式启动方式 (推荐开 3 个终端):"
	@echo ""
	@echo "  终端 1: make dev-backend"
	@echo "  终端 2: make dev-langgraph"
	@echo "  终端 3: make dev-ui"
	@echo ""
	@echo "或后台一键启动: make start"
	@echo ""

dev-backend: ## [终端1] 前台启动 FastAPI 后端 (带热重载)
	cd $(BACKEND) && PYTHONPATH=. $(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

dev-langgraph: ## [终端2] 前台启动 LangGraph API
	$(PYTHON) start_server.py

dev-ui: ## [终端3] 前台启动 Next.js 开发服务器
	cd $(UI) && npm run dev

# ─── 前台生产模式 ────────────────────────────────────────────────────────

start-backend: ## [前台] 启动 FastAPI 后端 :8000
	cd $(BACKEND) && PYTHONPATH=. $(PYTHON) app/main.py

start-ui: ## [前台] 启动 Next.js 前端生产模式 :3000
	cd $(UI) && npm run start

start-langgraph: ## [前台] 启动 LangGraph API :2026
	$(PYTHON) start_server.py

# ─── 日志 ────────────────────────────────────────────────────────────────

logs: ## 查看所有服务日志 (tail -f)
	@echo "📋 实时日志 (按 Ctrl+C 退出)..."
	@tail -f $(LOG_DIR)/backend.log $(LOG_DIR)/langgraph.log $(LOG_DIR)/ui.log 2>/dev/null || echo "日志文件不存在，先执行 make start"

log-backend: ## 查看 FastAPI 后端日志
	@tail -f $(LOG_DIR)/backend.log 2>/dev/null || echo "日志文件不存在"

log-langgraph: ## 查看 LangGraph 日志
	@tail -f $(LOG_DIR)/langgraph.log 2>/dev/null || echo "日志文件不存在"

log-ui: ## 查看 Next.js 前端日志
	@tail -f $(LOG_DIR)/ui.log 2>/dev/null || echo "日志文件不存在"

# ─── 数据库 ──────────────────────────────────────────────────────────────

kg-migrate: ## 创建知识图谱数据库表
	cd $(BACKEND) && PYTHONPATH=. $(PYTHON) -c "import asyncio; from app.kg.migration import run_migration; asyncio.run(run_migration())"

kg-rollback: ## 回滚知识图谱数据库表
	cd $(BACKEND) && PYTHONPATH=. $(PYTHON) -c "import asyncio; from app.kg.migration import rollback_migration; asyncio.run(rollback_migration())"

# ─── 代码分析 ────────────────────────────────────────────────────────────

kg-analyze: ## 分析代码仓库 (make kg-analyze REPO=/path)
	cd $(BACKEND) && PYTHONPATH=. $(PYTHON) -c "from app.kg.pipeline import run_pipeline_from_repo; o=run_pipeline_from_repo('$(REPO)'); print(f'OK: {o.graph.node_count} nodes, {o.graph.relationship_count} rels')"

kg-analyze-full: ## 分析并持久化到数据库 (make kg-analyze-full REPO=/path)
	PYTHONPATH=$(BACKEND) $(PYTHON) scripts/kg_analyze_full.py $(REPO)

kg-shell: ## 搜索代码 (make kg-shell REPO=/path QUERY=xxx)
	cd $(BACKEND) && PYTHONPATH=. $(PYTHON) -c "\
import asyncio; \
from app.config.database import async_session_factory; \
from app.kg.search import CodeSearcher; \
async def q(): \
  async with async_session_factory() as s: \
    searcher=CodeSearcher(s); \
    results=await searcher.search('$(REPO)','$(QUERY)',limit=10); \
    for r in results: print(f'  [{r.type:8}] {r.name:40} ({r.file_path})'); \
asyncio.run(q())"

# ─── 清理 ────────────────────────────────────────────────────────────────

clean: ## 清理 Python/Next.js 缓存、日志和 PID 文件
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf ui/.next
	@rm -f $(LOG_DIR)/*.pid
	@echo "✅ 缓存已清理"
