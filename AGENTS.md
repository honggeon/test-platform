# AI 测试智能体系统平台 — Agent 指南

本文件供 **AI Coding Agent** 阅读，作用类似 Claude Code 的 `CLAUDE.md`：说明项目结构、常用命令与协作约定。深度技术说明见 [TECHNICAL_DOCUMENTATION.md](./TECHNICAL_DOCUMENTATION.md)。

## 语言

- 与用户沟通使用**简体中文**（见 `.cursor/rules/respond-in-chinese.mdc`）。
- 代码、路径、命令、API 名、堆栈保持英文原文。

## 项目概述

**AI 测试智能体系统平台**是一个覆盖软件测试全生命周期的智能化测试管理系统，核心能力包括：

- 测试用例管理（CRUD、步骤、标签、版本、导入导出）
- API 自动化测试（OpenAPI 解析、AI 生成用例、Playwright 执行、Allure 报告）
- Web UI 测试管理
- 场景测试编排（多步骤串联、变量映射、数据驱动）
- 智能诊断（diagnosis）：基于规则引擎 + LLM 的测试失败自动诊断
- 知识图谱（kg）：代码库结构分析、跨文件调用链追踪、智能问答
- HAT 脚本执行框架：自定义 pytest 驱动的 YAML/Excel 用例执行引擎

系统采用三服务架构：FastAPI 后端（:8000）+ LangGraph Agent API（:2026）+ Next.js 前端（:3000）。

## 技术栈

| 层级 | 技术 | 版本/说明 |
|------|------|-----------|
| Python | CPython | >=3.13 |
| 包管理 | uv | `pyproject.toml` + `uv.lock` |
| Web 框架 | FastAPI | >=0.136.1 |
| ORM | SQLAlchemy | 2.0 + asyncpg |
| 文档数据库 | Motor | >=3.7.1（MongoDB 异步驱动）|
| Agent 框架 | LangGraph + deepagents | `langgraph-cli[inmem]>=0.4.26`, `deepagents>=0.6.1` |
| LLM 接入 | LangChain | OpenAI、DeepSeek、Anthropic、Ollama 均支持 |
| 对象存储 | MinIO | >=7.2.20 |
| 缓存/消息 | Redis | >=5.0.0（诊断 WebSocket Pub/Sub 使用）|
| 前端框架 | Next.js | 14.2.16（App Router）|
| 前端 UI | React + Tailwind CSS + shadcn/ui | React 18.3.1, Tailwind 3.4.14 |
| 类型系统 | TypeScript | 5.6.3 |
| 测试框架 | pytest | >=8.0.0 + allure-pytest |

## 项目结构与代码组织

```
├── backend/app/              # FastAPI 应用主目录（203+ 个 .py 文件）
│   ├── main.py               # 应用入口（create_app 工厂模式）
│   ├── api/                  # API 路由层
│   │   ├── __init__.py       # 聚合所有 v2 路由，前缀 /api/v2
│   │   ├── deps.py           # 依赖注入中心（Service 工厂函数）
│   │   ├── auth.py           # JWT 认证路由
│   │   └── v2/               # 24 个路由模块
│   ├── services/             # 业务逻辑层（29 个服务文件）
│   ├── repositories/         # 数据访问层（16 个仓库文件）
│   ├── models/               # ORM 模型（PostgreSQL + SQLite）
│   ├── schemas/              # Pydantic DTO / 校验模型
│   ├── agents/               # LangGraph Agent（3 个 Agent）
│   ├── kg/                   # 知识图谱引擎（33 个文件）
│   ├── config/               # 配置、数据库连接、认证数据库
│   └── middleware/           # 自定义中间件（速率限制、异常处理等）
├── backend/HAT/              # HAT 测试框架（26 个文件）
├── backend/tests/            # 后端测试（14 个测试文件）
├── ui/                       # Next.js 前端
│   ├── app/                  # App Router 页面（全为 Client Component）
│   ├── components/           # 组件（按业务域分目录 + ui/ shadcn 原始组件）
│   ├── lib/api/              # REST API 客户端（按领域分模块）
│   ├── lib/translations/     # i18n（zh/en/ja）
│   ├── providers/            # React Context Providers
│   └── hooks/                # 自定义 Hooks（useChat、useDiagnosisWebSocket 等）
├── scripts/                  # 启动/停止/端口探测等 shell 脚本
├── docs/                     # 架构设计文档（16 个文件）
├── graph.json                # LangGraph CLI 图定义（3 个 Agent）
├── start_server.py           # LangGraph API 启动器
├── Makefile                  # 构建与运维主入口
└── pyproject.toml            # Python 依赖声明
```

### 后端分层约定

| 目录 | 职责 | 禁止事项 |
|------|------|----------|
| `api/v2/` | 路由注册、参数校验、响应封装 | 不写复杂业务逻辑 |
| `services/` | 业务编排、事务协调、外部调用 | 不直接操作 SQL |
| `repositories/` | 数据库访问、ORM 查询 | 不调用其他 Service |
| `models/` | SQLAlchemy ORM 模型定义 | 不写业务方法 |
| `schemas/` | Pydantic 序列化/反序列化模型 | 不依赖 ORM 会话 |
| `agents/` | LangGraph 状态机、工具注册、Prompt 工程 | — |

### 前端目录约定

| 目录 | 职责 |
|------|------|
| `ui/app/` | Next.js App Router 页面，按功能域划分 |
| `ui/components/` | React 组件，按业务域分目录（`api-tests/`、`diagnosis/`、`kg/` 等）|
| `ui/components/ui/` | shadcn/ui 原始组件（29 个）|
| `ui/lib/api/` | REST API 封装模块（与后端 v2 路由一一对应）|
| `ui/lib/api/types.ts` | 前端 TypeScript 类型定义 |
| `ui/lib/translations/zh.ts` | 中文文案（i18n 主文件）|
| `ui/providers/` | AuthProvider、LanguageProvider、ClientProvider、ChatProvider |

## 架构要点

### 三服务运行时架构

```
浏览器 → Next.js(:3000) → [rewrites] → FastAPI(:8000) / LangGraph(:2026)
                                   ↓
                         PostgreSQL(:5432) + MongoDB(:27017) + MinIO(:9000) + Redis
```

- **FastAPI（:8000）**：主业务 API、认证、WebSocket、文件上传下载。
- **LangGraph（:2026）**：Agent 推理服务，通过 `start_server.py` 启动，读取 `graph.json`。
- **Next.js（:3000）**：前端 SPA，通过 `next.config.mjs` 的 rewrites 代理到后端。

### 数据库架构

- **PostgreSQL**：主业务数据库（22+ 张表），SQLAlchemy 2.0 Async ORM。
- **MongoDB**：非结构化数据（API 测试日志、诊断报告完整文档、审计日志、附件元数据）。
- **SQLite**：独立认证数据库（`backend/data/auth.db`），与业务 PG 解耦。
- **MinIO**：对象存储（脚本、报告、附件、OpenAPI schema 文件）。

### Agent 系统

`graph.json` 注册 3 个 Agent：

| Agent | 用途 | 关键路径 |
|-------|------|----------|
| `api_agent` | API 测试全生命周期 | `backend/app/agents/api/agent.py` |
| `code_analysis_agent` | 代码知识图谱问答 | `backend/app/agents/code/agent.py` |
| `log_analysis_agent` | 测试失败日志诊断 | `backend/app/agents/log_analysis/agent.py` |

Agent 使用 `deepagents` 包装 LangGraph，默认模型 `deepseek:deepseek-chat`，支持按项目从 `llm_config` 表动态加载模型配置。

### 前端通信方式

1. **REST API**：`ui/lib/api/client.ts` 封装原生 `fetch` → Next.js rewrite `/api/v2/*` → FastAPI。
2. **认证**：`AuthProvider` 管理 JWT，存储在 `localStorage`；`/auth/*` rewrite 到 FastAPI。
3. **AI 流式对话**：`@langchain/langgraph-sdk/react` 的 `useStream` → `/lg/*` rewrite → LangGraph。
4. **诊断实时推送**：原生 WebSocket 直连 `ws://backend/api/v2/ws/diagnosis/{projectId}`。

## 环境初始化与常用命令

### 首次启动

```bash
# 1. Python 环境
uv venv && uv sync

# 2. 环境变量（backend 与 UI 各需一份）
cp backend/app/.env.example backend/app/.env      # 按实际填写数据库、密钥等
cp ui/.env.example ui/.env.local                  # 通常不需要改，自动探测端口

# 3. 初始化（依赖检查 + 知识图谱数据库迁移）
make init

# 4. 知识图谱表（如 init 未成功执行）
make kg-migrate
```

### 开发模式（推荐开 3 个终端）

```bash
# 终端 1：FastAPI 开发服务器（热重载）
make dev-backend

# 终端 2：LangGraph Agent 服务
make dev-langgraph

# 终端 3：Next.js 开发服务器（自动探测后端端口）
make dev-ui
```

### 后台一键启动/停止

```bash
make start        # 后台启动 FastAPI + LangGraph + Next.js 生产构建
make stop         # 停止全部后台服务
make status       # 查看三个服务的端口/PID
make restart      # 重启全部
```

### 前端单独

```bash
cd ui && npm install && npm run dev    # 开发
cd ui && npm run build                 # 生产构建
```

### 日志查看

```bash
make logs              # 三服务日志合流 tail -f
make log-backend       # 只看 FastAPI
make log-langgraph     # 只看 LangGraph
make log-ui            # 只看 Next.js
```

### 知识图谱操作

```bash
make kg-migrate                    # 创建 KG 数据库表
make kg-analyze REPO=/path/to/code # 分析代码仓库
make kg-analyze-full REPO=/path    # 分析并持久化到数据库
make kg-shell REPO=/path QUERY=xxx # 搜索代码
```

### 其他运维

```bash
make help           # 显示所有 Make 目标
make clean          # 清理 __pycache__、.pyc、Next.js 缓存、PID 文件
make build          # 构建 Next.js 前端生产包
```

## 测试策略

### 后端测试

```bash
# 全量后端测试
.venv/bin/python -m pytest backend/tests -q --tb=short

# 单个文件
.venv/bin/python -m pytest backend/tests/test_diagnosis_service.py -v
```

**测试文件清单**（`backend/tests/` 共 14 个文件）：

| 文件 | 说明 |
|------|------|
| `test_diagnosis_service.py` | 诊断引擎核心测试（402 行），覆盖规则匹配、降级、幂等、脱敏 |
| `test_a2a.py` | A2A 协议端点测试（需 `pytest-asyncio`）|
| `test_auth_service.py` | 认证服务测试 |
| `test_allure_report.py` | Allure 报告生成测试 |
| `test_hat_*.py` (7 个) | HAT 框架测试：关键词、路径 lint、YAML 结构、变量渲染、步骤执行、认证、key_dir |
| `test_environment_url.py` | 环境 URL 模块测试 |
| `test_code_repo_path.py` | 代码仓库路径测试 |
| `test_deploy_hat_keyword.py` | HAT 关键字部署测试 |

**测试配置注意**：
- 含 `@pytest.mark.asyncio` 的异步测试需要 **pytest-asyncio**。
- `backend/conftest.py` 是 **HAT 框架专用**，注册了 `--type`、`--cases`、`--keyDir` 参数和 `pytest_generate_tests` 参数化逻辑，不是通用 fixtures 文件。
- 没有 `pytest.ini` 或 `[tool.pytest.ini_options]`，pytest-asyncio 依赖默认行为。
- **没有代码覆盖率配置**（未引入 pytest-cov）。

### HAT 框架测试执行

```bash
pytest --type yaml --cases <case_dir> --keyDir <keyword_dir>
```

### 前端测试

**当前无前端测试**。`ui/` 下没有 Jest、Vitest、Playwright、Cypress 或 React Testing Library 的配置与用例。
根目录遗留的 `playwright-report/` 和 `test-results/` 是历史产物，未在 `ui/package.json` 中配置。

### Allure 报告

- 依赖：`allure-pytest>=2.13.0`
- HAT 运行时会自动生成 Allure 结果到 `backend/allure-results/`
- FastAPI 提供接口列出并下载存储在 MinIO 中的 Allure 报告 ZIP

## 代码风格与开发约定

### 后端（Python）

1. **分层严格**：`api` → `services` → `repositories`，禁止跨层直接调用。
2. **依赖注入**：FastAPI `Depends` 贯穿全层，Service 工厂函数集中在 `api/deps.py`。
3. **异步优先**：SQLAlchemy `AsyncSession`、Motor（MongoDB async）、httpx `AsyncClient`。
4. **模型导入顺序**：`main.py` 中必须按**外键依赖顺序**显式 import ORM 模型（见 `main.py` 第 33-59 行的注释与代码）。新增模型后务必追加到该 import 块，否则 Alembic/SQLAlchemy 初始化会失败。
5. **环境变量**：统一使用 `app.config.settings.Settings`（Pydantic Settings），`.env` 文件加载顺序：`repo_root/.env` → `backend/.env`（后者覆盖前者）。
6. **跨平台路径**：settings 中显式处理 Windows/Linux 路径差异，工作目录可通过 `WORKSPACE_BASE` 统一覆盖。
7. **Agent 代码**：使用 `deepagents` 的 `create_deep_agent` 创建 Agent；工具注册在 `tool_registry.py`；skill 文件放在 `backend/workspace/` 或 `agent_skills/` 目录。

### 前端（TypeScript / React）

1. **全 Client Component**：所有页面均使用 `"use client"`，无 Server Components 数据获取。
2. **状态管理**：React Context + `nuqs`（URL 状态）+ 局部 `useState`。无 Redux/Zustand。
3. **API 调用**：禁止页面内裸 `fetch`，统一走 `ui/lib/api/*.ts` 模块；类型变更时同步更新 `types.ts`。
4. **i18n**：文案走 `ui/lib/translations/zh.ts`，支持 zh/en/ja。
5. **样式**：Tailwind CSS + shadcn/ui，无 CSS Modules。使用 `cn()`（`clsx` + `tailwind-merge`）合并类名。
6. **构建**：`next.config.mjs` 中 `ignoreBuildErrors: true`（因历史水印注释遗留的类型不匹配）。

### 通用 Agent 工作方式

- **小步修改**：只改与任务相关的文件；匹配现有命名与分层。
- **先读后改**：动 `main.py` 模型 import、路由注册、诊断链路前，先读调用方与被调用方。
- **验证再收尾**：声称「完成 / 通过」前必须执行验证命令并贴出结果（例如 pytest）。不要凭 diff 猜测测试已通过。
- **不要**在未要求时 `git commit` / `git push`；不要改 `git config`。
- **不要**用 `sleep` 或人为延迟「修」时序问题；用事件、重试或正确异步模式。

## 安全注意事项

1. **敏感配置**：`backend/app/.env`、根目录 `.env`、UI 的 `.env.local` 包含数据库密码、JWT Secret、MinIO 密钥、LLM API Key。**绝对不要提交到 Git**，不要在规则文件或 AGENTS 示例中写入真实值。
2. **数据脱敏**：诊断系统（`test_diagnosis_service.py`）自动对 Authorization、Cookie、密码、Token 等字段脱敏。新增敏感字段时需同步加入脱敏规则。
3. **速率限制**：`RateLimiterMiddleware` 默认 300 请求/60 秒滑动窗口（可在 `.env` 调整）。
4. **JWT**：HS256 算法，默认 30 分钟过期；Secret Key 必须在生产环境更换。
5. **CORS**：`cors_origins` 在 `.env` 中配置，生产环境应限制为确切域名。
6. **A2A API Keys**：`a2a_api_keys` 列表用于 Agent-to-Agent 调用鉴权，应配置强随机字符串。
7. **HAT 测试账号**：`hat_test_email`、`hat_test_password` 等用于场景测试执行时注入全局上下文，勿提交真实生产账号。

## 重要注意事项与常见陷阱

### 启动路径与 PYTHONPATH

- **FastAPI 必须以 `python -m app.main` 从 `backend/` 目录启动**，或确保 `PYTHONPATH=.` 包含 `backend/`。直接 `python app/main.py` 会导致 import 错误。
- **LangGraph 必须以 `python start_server.py` 从项目根目录启动**，因为它会设置 `PYTHONPATH` 并解析 `graph.json` 中的相对路径。
- Pydantic Settings 在 `backend/` 目录下寻找 `.env` 文件。建议在 `backend/` 下创建符号链接：`ln -sf app/.env .env`。

### 数据库

- PostgreSQL 表仅在 `DEBUG=true` 时自动创建（`Base.metadata.create_all`）。生产环境应使用迁移工具（项目目前无 Alembic 配置，生产部署需自行补充）。
- MongoDB 连接代码在 `main.py` lifespan 中当前被注释掉，但 MongoDB 模型和工具类已就绪。
- 知识图谱有独立的 migration 系统（`backend/app/kg/migration.py`），通过 `make kg-migrate` 管理。

### 诊断系统

- `test_diagnosis_service.py` 是后端最复杂的服务（894 行），包含完整的降级设计：DB 超时、KG 超时、LLM 超时均有降级处理，标记 `degradation_level`（none/partial/severe）。
- 诊断报告采用 **PostgreSQL + MongoDB 双写**：PG 用于列表查询（upsert），MongoDB 用于完整文档存储（upsert + 补偿写入）。
- WebSocket 管理器支持 Redis Pub/Sub 多实例广播，也支持单实例本地回退。

### 构建与部署

- **无 Docker**：项目当前无任何容器化配置（无 Dockerfile、docker-compose.yml）。
- **无 CI/CD**：没有 GitHub Actions、GitLab CI 或其他自动化流水线。
- 生产部署依赖 Makefile + shell 脚本（`nohup` + PID 文件），需要自行补充进程守护（systemd/PM2/supervisord）和 Nginx 反向代理配置。
- Next.js 生产构建需要先 `make build`，再由 `make start` 启动。`make start-all.sh` 内部会自动执行构建。

## 文档索引

| 文档 | 用途 |
|------|------|
| [TECHNICAL_DOCUMENTATION.md](./TECHNICAL_DOCUMENTATION.md) | 完整架构、数据库设计、API 规范、部署拓扑（12 章）|
| [docs/architecture-deep-dive.md](./docs/architecture-deep-dive.md) | 架构深挖：后端分层、3 个 Agent、HAT、KG 引擎、DAG 管道 |
| [docs/project-architecture.md](./docs/project-architecture.md) | 项目定位、技术选型、代码量统计、面试 Q&A |
| [docs/log-analysis-agent-design.md](./docs/log-analysis-agent-design.md) | 诊断系统完整设计规格（6 阶段流水线、双写、降级、WebSocket）|
| [docs/log-analysis-agent-design-review-v2.md](./docs/log-analysis-agent-design-review-v2.md) | 诊断系统 v2 评审（关键性能与一致性风险）|
| [docs/kg-improvement-plan-v3.md](./docs/kg-improvement-plan-v3.md) | 知识图谱务实改进计划 |
| [docs/kg-p0-improvement-plan.md](./docs/kg-p0-improvement-plan.md) | 知识图谱理想版追赶计划 |
| [docs/cs-test-architecture-design.md](./docs/cs-test-architecture-design.md) | Windows 桌面 UI 自动化远程执行架构 |
| [docs/mcp-tool-reference-cleanup.md](./docs/mcp-tool-reference-cleanup.md) | MCP 工具引用清理说明 |
| [docs/testhub-gap-analysis.md](./docs/testhub-gap-analysis.md) | 与 TestHub 竞品对比分析 |
| `make help` | Makefile 运维命令一览 |

## Cursor 规则文件

| 文件 | 作用范围 |
|------|----------|
| `.cursor/rules/respond-in-chinese.mdc` | 全局：Agent 始终使用简体中文回复 |
| `.cursor/rules/backend-python.mdc` | `backend/**/*.py`：后端分层、import 顺序、测试命令 |
| `.cursor/rules/frontend-ui.mdc` | `ui/**/*.{ts,tsx}`：前端目录、i18n、API 调用约定 |

新增规则时：**一条规则一个主题**，单文件建议 **50 行以内**，用 frontmatter 的 `globs` 或 `alwaysApply` 控制范围。
