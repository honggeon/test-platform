# AI 测试智能体系统平台 — 技术文档

| 目录

0. [环境准备与快速启动](#0-环境准备与快速启动)
1. [项目概述](#1-项目概述)
2. [系统架构总览](#2-系统架构总览)
3. [技术栈清单](#3-技术栈清单)
4. [后端架构详解](#4-后端架构详解)
5. [前端架构详解](#5-前端架构详解)
6. [AI 智能体系统](#6-ai-智能体系统)
7. [数据库设计](#7-数据库设计)
8. [API 路由体系](#8-api-路由体系)
9. [核心业务流程](#9-核心业务流程)
10. [数据流图](#10-数据流图)
11. [部署架构](#11-部署架构)
12. [安全与中间件](#12-安全与中间件)

---

## 0. 环境准备与快速启动

### 0.1 系统依赖

| 组件 | 版本要求 | 说明 |
|------|----------|------|
| **Python** | >= 3.13 | 后端运行环境 |
| **PostgreSQL** | 14+ | 主数据库（关系数据） |
| **MongoDB** | 5+ | 详细日志存储（非结构化数据） |
| **MinIO** | 最新版 | S3 兼容对象存储 |
| **Node.js** | 18+ | 前端构建环境（可选） |
| **pnpm** | 8+ | 前端包管理器（可选） |

### 0.2 项目结构

```
ai-test-agent-system-platform/          # 项目根目录
├── backend/                            # Python 后端
│   └── app/                            # FastAPI 应用包
│       ├── main.py                     # 服务入口
│       ├── .env                        # 环境变量配置（敏感信息）
│       ├── agents/                     # AI Agent 系统
│       ├── api/                        # RESTful API 路由
│       ├── config/                     # 配置（Settings, DB, MinIO）
│       ├── middleware/                 # 中间件
│       ├── models/                     # SQLAlchemy ORM 模型
│       ├── repositories/              # 数据访问层
│       ├── schemas/                    # Pydantic 请求/响应模型
│       ├── services/                   # 业务逻辑层
│       └── utils/                      # 工具类
├── ui/                                 # Next.js 前端（可选）
├── start_server.py                     # LangGraph 服务器启动脚本
├── graph.json                          # LangGraph 图定义
├── pyproject.toml                      # Python 项目配置
└── uv.lock                             # 依赖锁定文件
```

### 0.3 环境变量配置

配置文件位于 `backend/app/.env`（**敏感信息，不要提交到 Git**），基于 `.env.example` 创建：

```bash
# 复制示例配置
cp backend/app/.env.example backend/app/.env
```

关键配置项说明：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `POSTGRES_HOST` | `localhost` | PostgreSQL 主机地址 |
| `POSTGRES_PORT` | `5432` | PostgreSQL 端口 |
| `POSTGRES_USER` | `postgres` | 数据库用户 |
| `POSTGRES_PASSWORD` | `postgres` | 数据库密码 |
| `POSTGRES_DB` | `ai_test_management` | 数据库名称 |
| `MONGODB_HOST` | `121.40.159.60` | MongoDB 主机地址 |
| `MINIO_ENDPOINT` | `114.55.110.60:9000` | MinIO 服务地址 |
| `DEEPSEEK_API_KEY` | — | DeepSeek API 密钥 |
| `DEBUG` | `False` | 调试模式（开发环境设为 `True`） |

> **注意**：`settings.py` 中 `postgres_db` 默认值为 `ai_test_management`，但 `.env` 可能覆盖为其他名称（如 `ai_test_agent_system_db`）。实际使用的数据库名以 `.env` 文件中的 `POSTGRES_DB` 值为准。

### 0.4 Python 环境安装

项目使用 **uv** 作为包管理器（基于 `uv.lock` 锁定依赖）：

```bash
cd ai-test-agent-system-platform

# 创建虚拟环境（如不存在）
uv venv

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
uv sync
```

> 如果使用 `pip`，注意 Python >= 3.13 的要求，并手动安装 `pyproject.toml` 中声明的依赖。

### 0.5 创建 PostgreSQL 数据库

根据 `.env` 中配置的数据库名称创建：

```bash
# 连接 PostgreSQL（本地）
sudo -u postgres psql

# 或远程连接
psql -h <POSTGRES_HOST> -U <POSTGRES_USER> -W

# 在 psql 中执行
CREATE DATABASE ai_test_agent_system_db;   -- 以 .env 中 POSTGRES_DB 为准
```

> **重要**：数据库名称必须与 `.env` 中 `POSTGRES_DB` 的值一致。检查方式：
> ```bash
> grep POSTGRES_DB backend/app/.env
> ```

### 0.6 启动后端服务

```bash
# 进入后端目录
cd backend/

# 确保 .env 能被正确加载（关键！）
# Pydantic Settings 在当前工作目录查找 .env，而 .env 在 app/ 子目录下
ln -sf app/.env .env

# 重要：必须从 backend/ 目录下使用 -m 方式启动
# python app/main.py 或 python main.py 都会报 ModuleNotFoundError
python -m app.main
```

> **解释**：`main.py` 中使用的是 `from app.api import api_router` 这样的**绝对导入**，必须将 `backend/` 目录加入 `sys.path`。`python -m app.main` 会把当前工作目录加入路径，从而正确找到 `app` 包。
>
> 也可以用 uvicorn 直接启动：
> ```bash
> uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
> ```

启动成功标志：
```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
[OK] Created default test user: admin@test.com
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 0.7 常见启动问题

| 错误 | 原因 | 解决方法 |
|------|------|----------|
| `ModuleNotFoundError: No module named 'app'` | 从错误目录运行脚本 | 使用 `python -m app.main` 从 `backend/` 目录启动 |
| `InvalidCatalogNameError: database "..." does not exist` | PostgreSQL 数据库未创建 | 创建数据库：`CREATE DATABASE <POSTGRES_DB>;` |
| `Connection refused` — PostgreSQL | 数据库服务未运行或地址错误 | 检查 `POSTGRES_HOST` 和端口，确保服务可达 |
| `.env` 配置未生效 | Pydantic Settings 在 CWD 查找 `.env`，但 `.env` 位于 `backend/app/.env` | 创建符号链接：`ln -sf app/.env .env`（在 `backend/` 目录下执行）|

### 0.8 启动 LangGraph Agent 服务（可选）

```bash
# 在项目根目录下
python start_server.py
```

默认运行在 `http://localhost:2026`。

### 0.9 启动前端（可选）

```bash
cd ui/
pnpm install
pnpm dev
```

默认运行在 `http://localhost:3000`。

---

## 1. 项目概述

### 1.1 产品定位
AI 驱动的智能测试管理系统（Test Management System），覆盖**测试用例管理、API 自动化测试、Web UI 测试、场景编排测试**的全生命周期。

### 1.2 核心能力
- **测试用例管理**: 支持普通/BDD 测试用例的 CRUD、标签、优先级、版本管理
- **API 测试**: 基于 OpenAPI/Swagger 文档自动解析端点，AI 生成测试计划/脚本/用例
- **Web 测试**: AI 驱动的 Web 功能/页面测试生成与管理
- **场景测试**: 多接口业务流程编排（步骤→数据依赖→断言→执行）
- **AI 智能体**: 基于 DeepSeek + LangGraph 的自主测试 Agent，支持技能（Skills）体系
- **多语言 UI**: 支持中/英/日三语界面

### 1.3 项目结构

```
ai-test-agent-system-platform/
├── backend/                        # Python 后端
│   └── app/
│       ├── agents/                 # AI Agent 系统
│       │   └── api/                # API 测试 Agent
│       │       ├── agent.py        # Agent 定义 + 系统提示词
│       │       ├── tool_registry.py # 工具注册
│       │       └── tools/          # 原子工具集
│       ├── api/                    # RESTful API 路由
│       │   └── v2/                 # API v2 版本
│       ├── config/                 # 配置（Settings, DB, MinIO）
│       ├── middleware/             # 中间件（限流、异常处理）
│       ├── models/                 # SQLAlchemy ORM 模型
│       │   └── mongodb/            # MongoDB 文档模型
│       ├── repositories/           # 数据访问层（Repository 模式）
│       ├── schemas/                # Pydantic 请求/响应模型
│       ├── services/               # 业务逻辑层
│       └── utils/                  # 工具类
├── ui/                             # Next.js 前端
│   ├── app/                        # App Router 页面
│   ├── components/                 # React 组件
│   │   ├── api-tests/              # API 测试组件
│   │   ├── langgraph/              # AI 对话组件
│   │   ├── layout/                 # 布局组件（侧边栏、顶部栏）
│   │   ├── scenario-tests/         # 场景测试组件
│   │   ├── test-cases/             # 测试用例组件
│   │   ├── ui/                     # 通用 UI 组件库
│   │   └── web-tests/              # Web 测试组件
│   ├── hooks/                      # 自定义 Hooks
│   ├── lib/                        # 工具库
│   │   ├── api/                    # API 客户端封装
│   │   ├── langgraph/              # LangGraph SDK 配置
│   │   └── translations/           # 国际化（zh, en, ja）
│   └── providers/                  # React Context Provider
├── backend/workspace/api/          # API Agent 工作区
│   └── skills/                     # Skills 知识库
│       ├── executor/               # 执行 Skill
│       ├── generator/              # 代码生成 Skill
│       ├── healer/                 # 修复 Skill
│       ├── planner/                # 测试计划 Skill
│       ├── reporter/               # 报告 Skill
│       └── scenario/               # 场景 Skill
├── pyproject.toml                  # Python 项目配置
├── graph.json                      # LangGraph 图定义
└── start_server.py                 # LangGraph 服务器启动脚本
```

---

## 2. 系统架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                     用户层 (Browser)                         │
│              Next.js SPA + Tailwind CSS + Radix UI           │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP REST API
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    API 网关层 (Nginx/反向代理)                 │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
┌─────────────────────┐ ┌─────────┐ ┌────────────────────┐
│   FastAPI 主服务     │ │LangGraph│ │    MinIO 对象存储    │
│   Port 8000          │ │API Srv  │ │    S3 兼容          │
│                      │ │Port 2026│ │    Port 9000        │
│  REST API v2         │ │         │ │                     │
│  Rate Limiter        │ │AI Agent │ │ 测试脚本/附件/报告   │
│  Error Handler       │ │服务     │ │                     │
└──────┬──────────────┘ └─────────┘ └────────────────────┘
       │
       ├──────────────────────┐
       ▼                      ▼
┌──────────────┐     ┌──────────────┐
│  PostgreSQL   │     │   MongoDB    │
│  主数据库      │     │  详细日志存储 │
│  SQLAlchemy   │     │  Motor驱动   │
│  asyncpg      │     │              │
└──────────────┘     └──────────────┘
```

### 架构模式

| 层次 | 模式 | 说明 |
|------|------|------|
| **展示层** | Next.js App Router | React 18 SPA, SWR 数据请求 |
| **API 层** | FastAPI + Dependency Injection | 依赖注入解析 DB Session、用户 ID |
| **业务层** | Service 模式 | 场景执行引擎、测试执行器、配置管理 |
| **数据层** | Repository 模式 | 封装 SQLAlchemy 异步查询 |
| **AI 层** | LangGraph + DeepAgents | 图状态机编排 Agent 工作流 |

---

## 3. 技术栈清单

### 3.1 后端 (Python 3.13+)

| 技术 | 用途 | 版本 |
|------|------|------|
| **FastAPI** | Web 框架 | 0.136+ |
| **SQLAlchemy** | ORM | 2.0+ |
| **asyncpg** | PostgreSQL 异步驱动 | 0.31+ |
| **Motor** | MongoDB 异步驱动 | 3.7+ |
| **MinIO** | S3 兼容对象存储 | 7.2+ |
| **LangGraph** | AI Agent 框架 | CLI 0.4+ |
| **DeepAgents** | Agent 构建工具包 | 0.6+ |
| **DeepSeek** | LLM 模型 | deepseek-chat |
| **LangChain** | LLM 集成框架 | - |
| **Pydantic v2** | 数据验证 | 2.14+ |
| **Uvicorn** | ASGI 服务器 | 0.46+ |
| **httpx** | HTTP 客户端 | 0.28+ |
| **jsonpath_ng** | JSONPath 数据提取 | 1.8+ |

### 3.2 前端 (TypeScript 5.6+)

| 技术 | 用途 | 版本 |
|------|------|------|
| **Next.js** | React 框架 | 14.2 |
| **React** | UI 库 | 18.3 |
| **Tailwind CSS** | 样式框架 | 3.4 |
| **Radix UI** | 无样式 UI 组件 | 多版本 |
| **SWR** | 数据请求 | 2.4 |
| **Monaco Editor** | 代码编辑器 | 0.55 |
| **Lucide React** | 图标库 | 0.46 |
| **Nuqs** | URL 查询参数状态 | 2.0 |
| **Sonner** | 消息通知 | 1.5 |
| **React Markdown** | Markdown 渲染 | 10.1 |
| **DnD Kit** | 拖拽 | 6.3 |
| **date-fns** | 日期处理 | 4.1 |

### 3.3 基础设施

| 组件 | 用途 |
|------|------|
| **PostgreSQL** | 主数据库（关系数据） |
| **MongoDB** | 详细日志存储（非结构化数据） |
| **MinIO** | 文件存储（测试脚本、附件、报告） |
| **LangGraph API Server** | AI Agent 运行时服务 |
| **Nginx** | 反向代理 |

---

## 4. 后端架构详解

### 4.1 分层架构 (Layer Architecture)

```
┌─────────────────────────────────────────────────┐
│  API Layer (api/v2/*.py)                        │
│  FastAPI Router + Dependency Injection          │
│  ├─ projects.py    项目管理                     │
│  ├─ folders.py     文件夹管理                    │
│  ├─ test_cases.py  测试用例管理                  │
│  ├─ test_plans.py  测试计划管理                  │
│  ├─ test_runs.py   测试运行管理                  │
│  ├─ test_results.py 测试结果管理                 │
│  ├─ api_tests.py   API 测试管理                 │
│  ├─ api_endpoints.py API 端点管理               │
│  ├─ scenarios.py   场景测试管理                  │
│  ├─ web_tests.py   Web 测试管理                 │
│  ├─ web_functions.py Web 功能管理               │
│  ├─ configurations.py 配置管理                  │
│  ├─ attachments.py  附件管理                     │
│  └─ documents.py   文档管理                      │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│  Service Layer (services/*.py)                   │
│  ├─ project_service.py                          │
│  ├─ test_case_service.py                        │
│  ├─ test_run_service.py                         │
│  ├─ test_plan_service.py                        │
│  ├─ scenario_service.py                         │
│  ├─ scenario_execution_engine.py  ← 场景执行引擎  │
│  ├─ api_test_executor.py        ← API 测试执行器 │
│  ├─ api_test_service.py                         │
│  ├─ web_test_service.py                         │
│  ├─ web_function_service.py                     │
│  ├─ openapi_parser.py         ← OpenAPI 解析器   │
│  ├─ export_service.py         ← 导出服务         │
│  ├─ attachment_service.py     ← 附件服务         │
│  ├─ configuration_service.py                    │
│  ├─ mongodb_service.py                          │
│  └─ folder_service.py                           │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│  Repository Layer (repositories/*.py)            │
│  Repository 模式封装数据库查询                    │
│  ├─ base.py             基础 CRUD 操作           │
│  ├─ project_repo.py                              │
│  ├─ test_case_repo.py                            │
│  ├─ api_test_repo.py                             │
│  └─ ...                                         │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│  Model Layer (models/*.py)                       │
│  SQLAlchemy ORM + Pydantic Schema               │
│  22 个表 + 4 个 MongoDB 文档模型                 │
└─────────────────────────────────────────────────┘
```

### 4.2 配置管理 (Settings)

Pydantic Settings (`config/settings.py`) 统一管理所有配置，支持 `.env` 文件：

- **应用**: app_name, app_version, debug, api_prefix
- **PostgreSQL**: host, port, user, password, db → 自动拼接连接 URL
- **MongoDB**: host, port, user, password, db
- **MinIO**: endpoint, access_key, secret_key, bucket
- **CORS**: origins 列表
- **JWT**: secret_key, algorithm, token_expire
- **速率限制**: 300 请求/分钟
- **Agent 工作区**: API/Web/Perf/TestCase 各 Agent 的 workspace 路径

### 4.3 依赖注入 (Dependency Injection)

```python
# api/deps.py
async def get_db() -> AsyncSession        # 获取数据库会话
def get_current_user_id() -> UUID          # 获取当前用户 ID
DbSessionDep                               # 组合注入
CurrentUserIdDep                           # 组合注入
```

---

## 5. 前端架构详解

### 5.1 页面路由结构

```
/ui/app/
├── page.tsx                         # 首页/仪表盘
├── layout.tsx                       # 根布局（国际化 + Toaster）
├── globals.css                      # Tailwind 全局样式
└── projects/
    ├── page.tsx                     # 项目列表
    └── [projectId]/
        ├── test-cases/page.tsx      # 测试用例管理 ⭐
        ├── api-tests/page.tsx       # API 测试管理 ⭐
        ├── web-tests/page.tsx       # Web 测试管理
        ├── scenario-tests/page.tsx  # 场景测试管理 ⭐
        ├── test-plans/page.tsx      # 测试计划管理
        ├── test-runs/page.tsx       # 测试运行管理
        └── reports/page.tsx         # 测试报告
```

### 5.2 组件架构

```
components/
├── layout/                          # 布局组件
│   ├── header.tsx                   # 顶部导航栏（国际化切换、用户菜单）
│   ├── sidebar.tsx                  # 左侧导航菜单
│   ├── main-layout.tsx              # 主布局（侧边栏+内容区）
│   └── language-selector.tsx        # 语言选择器
│
├── api-tests/                       # API 测试模块
│   ├── APIEndpointList.tsx          # 端点列表
│   ├── APITestList.tsx              # 测试列表
│   ├── APITestDialog.tsx            # 测试编辑对话框
│   ├── ai-generate-dialog.tsx       # AI 测试生成（旧版）
│   ├── ai-generate-dialog-v2.tsx    # AI 测试生成（新版）
│   ├── api-parse-dialog.tsx         # OpenAPI 文档解析
│   ├── code-viewer.tsx              # 代码查看器
│   ├── folder-tree.tsx              # 文件夹树
│   ├── folder-tree-index.tsx        # 文件夹索引
│   ├── endpoint-sidebar.tsx         # 端点侧边栏
│   ├── api-endpoint-sidebar.tsx     # API 端点侧边栏
│   ├── test-artifacts-panel.tsx     # 测试制品面板
│   └── test-artifacts-panel-enhanced.tsx  # 增强版
│
├── scenario-tests/                  # 场景测试模块
│   ├── scenario-list-panel.tsx      # 场景列表
│   ├── scenario-create-dialog.tsx   # 创建场景
│   ├── scenario-detail-sidebar.tsx  # 场景详情
│   ├── scenario-execution-monitor.tsx # 执行监控
│   ├── scenario-orchestration-view.tsx # 编排视图 ⭐
│   ├── step-create-dialog.tsx       # 添加步骤
│   ├── step-edit-dialog.tsx         # 编辑步骤
│   └── ai-generate-scenario-dialog.tsx # AI 生成场景
│
├── langgraph/                       # AI 对话模块
│   ├── index.tsx                    # 主入口
│   ├── ChatInterface.tsx            # 聊天界面
│   ├── ChatMessage.tsx              # 消息气泡
│   ├── AIChatContainer.tsx          # AI 对话容器
│   ├── ThreadList.tsx               # 线程列表
│   ├── ToolCallBox.tsx              # 工具调用展示
│   ├── ToolApprovalInterrupt.tsx    # 工具审批中断
│   ├── InterruptActions.tsx         # 中断操作
│   ├── SubAgentIndicator.tsx        # 子 Agent 指示器
│   ├── MarkdownContent.tsx          # Markdown 渲染
│   ├── TasksFilesSidebar.tsx        # 任务/文件侧边栏
│   └── FileViewDialog.tsx           # 文件查看
│
├── test-cases/                      # 测试用例模块
│   ├── test-case-list.tsx           # 用例列表
│   ├── test-case-dialog.tsx         # 用例编辑
│   ├── folder-tree.tsx              # 文件夹树
│   ├── test-case-filter-panel.tsx   # 过滤面板
│   ├── ai-generate-dialog.tsx       # AI 生成
│   ├── ai-generate-from-document-dialog.tsx # 从文档生成
│   ├── ai-generate-result-dialog.tsx
│   ├── ai-chat-dialog.tsx           # AI 对话
│   └── attachment-upload.tsx        # 附件上传
│
├── web-tests/                       # Web 测试模块
├── ui/                              # Radix UI 封装组件库
└── editor/                          # Monaco 代码编辑器
```

### 5.3 状态管理

- **无全局状态管理库**: 不采用 Redux/Zustand
- **SWR**: 服务端数据获取与缓存（getStaticProps/getServerSideProps 替代方案）
- **Nuqs**: URL Query Parameters 状态同步（过滤、分页）
- **React Context**: 国际化（LanguageProvider）、AI 聊天（ChatProvider）
- **Hooks**: `useChat`, `useThreads` 管理 LangGraph 会话状态

### 5.4 国际化支持

```
lib/translations/
├── index.ts         # 导出 + 类型
├── zh.ts            # 简体中文
├── en.ts            # 英文
└── ja.ts            # 日语
```

所有 UI 文本通过 `useTranslation()` hook 动态渲染。

---

## 6. AI 智能体系统

### 6.1 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph API Server                      │
│                    Port 2026                                 │
│                    langgraph_api.server:app                  │
└────────────────────────┬────────────────────────────────────┘
                         │ graph.json
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    api_agent (Pregel Graph)                  │
│                                                             │
│  ┌────────────┐  Skills Middleware  ┌──────────────────┐   │
│  │   Model     │────────────────────▶│ Skills 知识库     │   │
│  │ (DeepSeek)  │                     │ ├ planner        │   │
│  └─────┬──────┘                     │ ├ generator      │   │
│        │                            │ ├ executor       │   │
│  ┌─────▼──────┐                     │ ├ healer         │   │
│  │  Tools 集   │                     │ ├ reporter       │   │
│  │ (15 个工具) │                     │ └ scenario       │   │
│  └────────────┘                     └──────────────────┘   │
│                                                             │
│  Context Injection Middleware                                │
│  ├ project_identifier                                       │
│  ├ folder_id                                                │
│  └ current_user_id                                          │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Agent 定义 (agent.py)

**模型**: `deepseek:deepseek-chat` (通过 LangChain `init_chat_model`)

**系统提示词**: 定义为 `SYSTEM_PROMPT`，包含：
1. **角色定位**: API 自动化测试专家
2. **核心能力**: 测试计划生成、测试代码生成、场景测试、测试执行、修复、报告
3. **标准工作流**: 4 种流程（A: 单端点测试, B: 测试修复, C: 批量测试, D: 场景测试）
4. **工具速查表**: 15+ 工具的用途和参数
5. **重要原则**: 自动获取接口信息、保存成果物、路径处理、测试质量

**Context 注入**:
```python
@dataclass
class APIAgentContext:
    project_identifier: str = ""
    folder_id: str = ""
    current_user_id: str = "00000000-0000-0000-0000-000000000001"
```

### 6.3 Skills 知识库

按需加载的领域知识，每个 Skill 是一个独立的 SKILL.md 文件：

| Skill | 目录 | 触发条件 |
|-------|------|----------|
| **planner** | `skills/planner/` | 生成测试计划 |
| **generator** | `skills/generator/` | 生成测试代码 |
| **scenario** | `skills/scenario/` | 创建场景测试 |
| **executor** | `skills/executor/` | 执行测试 |
| **healer** | `skills/healer/` | 修复失败测试 |
| **reporter** | `skills/reporter/` | 生成报告 |

### 6.4 工具集 (Tools)

Agent 拥有的 15+ 工具（`tools/` 目录）：

| 工具 | 功能 | 所属文件 |
|------|------|----------|
| `get_endpoint_details` | 获取端点完整信息 | openapi_tools |
| `get_multiple_endpoints_details` | 批量获取端点信息 | openapi_tools |
| `save_test_plan` | 保存测试计划 | test_artifacts_tools |
| `save_test_cases` | 保存测试用例 | test_artifacts_tools |
| `save_test_script` | 保存测试脚本 | test_artifacts_tools |
| `run_tests` | 运行测试文件 | test_execution_tools |
| `get_api_script_info` | 查询脚本信息 | script_tools |
| `download_api_script` | 下载脚本到本地 | script_tools |
| `execute_api_script` | 执行本地脚本 | script_execution_tools |
| `parse_test_results` | 解析测试输出 | script_execution_tools |
| `list_api_endpoints` | 列出端点 | openapi_tools |
| `batch_generate_tests` | 批量生成 | batch_tools |
| `batch_run_tests` | 批量执行 | batch_tools |
| `create_test_scenario` | 创建场景 | scenario_tools |
| `add_scenario_step` | 添加场景步骤 | scenario_tools |
| `add_data_mapping` | 添加数据映射 | scenario_tools |
| `add_step_assertion` | 添加断言 | scenario_tools |
| `add_step_extractor` | 添加数据提取器 | scenario_tools |
| `execute_scenario` | 执行场景 | scenario_tools |

### 6.5 Agent 工作流（4 种流程）

**流程 A — 单端点完整测试**:
```
获取端点 → 生成计划 → 保存计划 → 生成用例 → 保存用例
→ 生成代码 → 保存脚本 → 下载 → 执行 → 解析结果
```

**流程 B — 测试修复**:
```
执行发现失败 → 分析原因 → 修改代码 → 保存 → 验证
```

**流程 C — 批量测试**:
```
列出端点 → 批量生成 → 批量执行
```

**流程 D — 场景测试**:
```
创建场景 → 添加步骤 → 配置数据依赖 → 添加断言 → 执行
```

---

## 7. 数据库设计

### 7.1 PostgreSQL — 22 张表

#### 核心业务表

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `users` | 用户 | id, email, username, password_hash |
| `projects` | 项目 | id, identifier, name, description |
| `folders` | 无限层级文件夹 | id, project_id, parent_id, name, folder_type |
| `tags` | 标签 | id, project_id, name |
| `test_case_tags` | 用例-标签关联 | test_case_id, tag_id |

#### 测试用例

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `test_cases` | 测试用例主表 | identifier, name, priority, state, type, template, automation_status, custom_fields, version |
| `test_steps` | 测试步骤 | test_case_id, step_number, action, expected_result |
| `test_plans` | 测试计划 | identifier, name, description, status, active_state |
| `test_runs` | 测试运行 | identifier, status, assigned_to, environment, milestone |
| `test_run_cases` | 运行-用例关联 | test_run_id, test_case_id, status |
| `test_results` | 测试结果 | test_run_id, test_case_id, status, duration_ms |
| `test_step_results` | 步骤结果 | test_result_id, step_number, status, actual_result |

#### API 测试

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `api_endpoints` | API 端点 | project_id, path, method, display_name, parameters, request_body, responses, security, tag_group |
| `api_tests` | 测试脚本 | project_id, identifier, schema_url, script_path, script_format, test_config |
| `api_test_runs` | API 运行记录 | api_test_id, status, execution_config, total_tests, passed_tests |
| `api_test_results` | API 结果 | test_run_id, scenario_name, endpoint, method, status, request_summary, response_summary |

#### 场景测试

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `test_scenarios` | 测试场景 | project_id, identifier, name, global_variables, setup_config, retry_count, parallel_execution |
| `scenario_steps` | 场景步骤 | scenario_id, endpoint_id, step_order, request_override, extractors, assertions, condition_expression |
| `step_data_mappings` | 步骤数据映射 | step_id, source_type, source_step_id, source_path, target_path, transform_expression |
| `scenario_variables` | 场景变量 | scenario_id, name, type, default_value, scope, is_secret |
| `scenario_runs` | 场景运行记录 | scenario_id, status, runtime_variables, passed_steps, failed_steps, duration_ms |
| `scenario_step_results` | 步骤执行结果 | run_id, step_id, status, request_data, response_data, assertion_results, error_message |

#### 辅助表

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `configurations` | 测试配置（OS/浏览器/设备） | name, os, browser, device, is_system |
| `attachments` | 附件 | project_id, file_name, file_size, mime_type, storage_path |
| `teams` | 团队 | name, description |

#### 模型继承体系

```python
class Base(DeclarativeBase)     # SQLAlchemy 声明式基类
class UUIDMixin                 # UUID 主键混入
class TimestampMixin            # created_at + updated_at 混入
```

所有业务模型继承自 `Base, UUIDMixin, TimestampMixin`。

### 7.2 MongoDB — 4 个集合

| 集合 | 说明 | 关键字段 |
|------|------|----------|
| `api_test_logs` | API 测试详细日志 | log_id, test_result_id, request, response, assertions, retry_history |
| `audit_logs` | 操作审计日志 | - |
| `version_history` | 版本历史 | - |
| `attachments` | 附件元数据 | - |

MongoDB 用于**大规模非结构化数据**存储：详细的请求/响应日志、审计追踪、版本历史。

### 7.3 MinIO 对象存储

| 用途 | 路径格式 |
|------|----------|
| 测试脚本 | `api_tests/{project_id}/{test_id}/script.ts` |
| 测试报告 | `api_tests/{project_id}/{run_id}/report.html` |
| 附件 | `attachments/{project_id}/{uuid}.{ext}` |
| OpenAPI Schema | `schemas/{project_id}/{uuid}.json` |

---

## 8. API 路由体系

### 8.1 路由注册

```python
api_router = APIRouter(prefix="/api/v2")

api_router.include_router(projects.router, tags=["项目管理"])
api_router.include_router(folders.router, tags=["文件夹管理"])
api_router.include_router(test_cases.router, tags=["测试用例管理"])
api_router.include_router(test_cases.exports_router, tags=["导出管理"])
api_router.include_router(test_plans.router, tags=["测试计划管理"])
api_router.include_router(test_runs.router, tags=["测试运行管理"])
api_router.include_router(test_results.router, tags=["测试结果管理"])
api_router.include_router(attachments.*, tags=["附件管理"])
api_router.include_router(configurations.router, tags=["配置管理"])
api_router.include_router(documents.router, tags=["文档管理"])
api_router.include_router(api_tests.router, tags=["API 测试管理"])
api_router.include_router(api_tests_extended.router, tags=["API 测试扩展"])
api_router.include_router(api_endpoints.router, tags=["API 端点管理"])
api_router.include_router(scenarios.router, prefix="/scenarios", tags=["场景测试管理"])
api_router.include_router(web_tests.router, tags=["Web 测试管理"])
api_router.include_router(web_functions.router, tags=["Web 功能管理"])
```

### 8.2 关键 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/v2/projects` | 项目列表 |
| POST | `/api/v2/projects` | 创建项目 |
| GET | `/api/v2/projects/{id}` | 项目详情 |
| DELETE | `/api/v2/projects/{id}` | 删除项目 |
| GET | `/api/v2/projects/{id}/folders` | 文件夹树 |
| POST | `/api/v2/folders` | 创建文件夹 |
| PUT | `/api/v2/folders/{id}/move` | 移动文件夹 |
| GET | `/api/v2/projects/{id}/test-cases` | 测试用例列表（分页） |
| POST | `/api/v2/test-cases` | 创建测试用例 |
| GET | `/api/v2/test-cases/{id}` | 测试用例详情 |
| GET | `/api/v2/projects/{id}/api-tests` | API 测试列表 |
| POST | `/api/v2/api-tests` | 创建 API 测试 |
| POST | `/api/v2/api-tests/parse-openapi` | 解析 OpenAPI 文档 |
| POST | `/api/v2/api-tests/{id}/run` | 运行 API 测试 |
| GET | `/api/v2/scenarios` | 场景列表 |
| POST | `/api/v2/scenarios` | 创建场景 |
| POST | `/api/v2/scenarios/{id}/execute` | 执行场景 |
| GET | `/api/v2/scenarios/{id}/runs` | 场景运行历史 |
| GET | `/api/v2/projects/{id}/test-runs` | 测试运行列表 |
| POST | `/api/v2/test-runs` | 创建测试运行 |
| POST | `/api/v2/test-runs/{id}/execute` | 执行测试运行 |

### 8.3 统一响应格式

```json
// 成功
{
  "success": true,
  "data": { ... },
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100
  }
}

// 失败
{
  "success": false,
  "error": "validation_error",
  "message": "请求参数验证失败",
  "details": [
    { "field": "name", "message": "字段必填", "code": "missing" }
  ]
}
```

---

## 9. 核心业务流程

### 9.1 测试用例管理生命周期

```
创建项目
    │
    ▼
创建文件夹（可选，支持无限层级）
    │
    ▼
创建测试用例 ────▶ 普通用例 (TEST_CASE)
│                      ├ 步骤 (action + expected_result)
│                      ├ 优先级 (low/medium/high/critical)
│                      ├ 类型 (functional/regression/performance...)
│                      ├ 标签
│                      └ 自定义字段
│
└───▶ BDD 用例 (TEST_CASE_BDD)
       ├ Feature
       ├ Scenario
       └ Background
    │
    ▼
关联 API 测试或 Web 测试
    │
    ▼
加入测试计划 ──▶ 创建测试运行 ──▶ 执行 ──▶ 记录结果
```

### 9.2 API 测试流程

```
┌──────────────────┐
│  导入 OpenAPI     │
│  文档             │
└────────┬─────────┘
         ▼
┌──────────────────┐
│  解析 API 端点    │
│  (OpenAPI Parser) │
└────────┬─────────┘
         ▼
┌──────────────────┐     ┌─────────────────────┐
│  AI Agent         │────▶│  1. 生成测试计划     │
│  (DeepSeek+       │     │  2. 生成测试用例     │
│   LangGraph)      │     │  3. 生成测试脚本     │
└────────┬─────────┘     │  4. 保存到 MinIO    │
         │               └─────────────────────┘
         ▼
┌──────────────────┐
│  执行测试         │
│  (Playwright)    │
└────────┬─────────┘
         ▼
┌──────────────────┐
│  收集结果          │
│  ├ 摘要 → PostgreSQL │
│  └ 详细 → MongoDB    │
└────────┬─────────┘
         ▼
┌──────────────────┐
│  失败 → AI 修复   │
│  (Healer Skill)  │
└──────────────────┘
```

### 9.3 场景测试执行引擎

```
场景执行引擎 (ScenarioExecutionEngine)
│
├─ 1. 加载场景 (load_scenario)
│   ├ 场景元数据
│   ├ 步骤列表（按 order 排序）
│   └ 全局变量
│
├─ 2. 初始化 ExecutionContext
│   ├ global_variables + runtime_variables
│   └ 设置 baseUrl
│
├─ 3. 循环执行步骤 (for each step)
│   │
│   ├─ 3.1 加载端点定义
│   │
│   ├─ 3.2 数据依赖解析 (DataDependencyResolver)
│   │   ├ 基础请求 ← 端点定义
│   │   ├ 请求覆盖 ← step.request_override
│   │   ├ 请求头覆盖 ← step.headers_override
│   │   ├ 数据映射 ← StepDataMapping
│   │   │   ├ previous_response: JSONPath 提取上一步响应
│   │   │   ├ variable: 获取场景变量
│   │   │   ├ static: 静态值
│   │   │   └ transform: 转换表达式（如 'Bearer ' + value）
│   │   └ 模板变量替换 {{variable}}
│   │
│   ├─ 3.3 发送 HTTP 请求 (httpx.AsyncClient)
│   │
│   ├─ 3.4 数据提取 (JSONPath)
│   │   └ 存入 context.step_data
│   │
│   ├─ 3.5 执行断言
│   │
│   ├─ 3.6 检查 continue_on_failure
│   │
│   └─ 3.7 应用步骤延迟 (delay_ms)
│
├─ 4. 更新运行记录
│   ├ status (completed/failed)
│   ├ passed/failed_steps 统计
│   └ duration_ms
│
└─ 5. 返回 ScenarioRun
```

### 9.4 AI Agent 交互流程

```
用户输入（例如："帮我测试 GET /api/v1/Activities"）
    │
    ▼
FastAPI → LangGraph API Server → api_agent
    │
    ├─ Skills Middleware 加载相关 Skill
    ├─ Context Middleware 注入 project/folder
    ├─ Model (DeepSeek) 生成决策
    ├─ 调用工具: get_endpoint_details
    ├─ 分析接口信息
    ├─ 调用工具: save_test_plan
    ├─ 调用工具: save_test_cases
    ├─ 调用工具: save_test_script
    └─ 返回结果给用户
```

---

## 10. 数据流图

### 10.1 请求处理流程

```
Browser (Next.js SPA)
    │  fetch /api/v2/projects/xxx/test-cases
    ▼
Nginx Reverse Proxy
    │
    ▼
FastAPI (Port 8000)
    │
    ├─ CORSMiddleware
    ├─ RateLimiterMiddleware (300 req/min window)
    │   └─ 滑动窗口算法
    │
    ▼
API Router → 路由分发
    │
    ▼
Dependency Injection
    ├─ get_db() → async_session_factory → AsyncSession
    └─ get_current_user_id()
    │
    ▼
Service Layer
    │
    ▼
Repository Layer
    │
    ▼
PostgreSQL (asyncpg)
```

### 10.2 文件上传流程

```
Client → POST /api/v2/attachments/upload
    │
    ▼
FastAPI → UploadFile
    │
    ├─ 验证文件类型和大小
    ├─ MinIOClient.upload_file()
    │   ├─ ensure_bucket() 确保桶存在
    │   └─ put_object() 上传到 MinIO
    │
    └─ 记录元数据到 PostgreSQL (attachments 表)
```

### 10.3 AI Agent 请求流程

```
Frontend (ChatInterface)
    │  LangGraph SDK
    ▼
LangGraph API Server (Port 2026)
    │  graph.json → api_agent
    ▼
api_agent (Pregel Graph)
    │
    ├─ SkillsMiddleware → 加载 Skills
    ├─ ContextInjectionMiddleware
    ├─ DeepSeek Model → 推理 → 工具调用
    │
    ▼
Tools → 操作数据库/MinIO/文件系统
    │
    ▼
返回响应 → 前端渲染
```

---

## 11. 部署架构

### 11.1 服务拓扑

```
┌─────────────────────────────────────────────────────────────┐
│                         用户                                │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │   Nginx 80/443 │
                    │  反向代理+SSL  │
                    └───────┬───────┘
                            │
              ┌─────────────┼──────────────┐
              ▼             ▼              ▼
      ┌────────────┐ ┌──────────┐ ┌──────────────┐
      │ FastAPI    │ │LangGraph │ │  Next.js     │
      │ :8000      │ │ :2026    │ │  :3000       │
      │ REST API   │ │ Agent    │ │  SPA         │
      │            │ │ Service  │ │              │
      └─────┬──────┘ └──────────┘ └──────────────┘
            │
      ┌─────┼──────────┐
      ▼     ▼          ▼
  ┌──────┐ ┌──────┐ ┌──────┐
  │ PGSQL │ │Mongo │ │MinIO │
  │ :5432 │ │:27017│ │:9000 │
  └──────┘ └──────┘ └──────┘
```

### 11.2 开发环境

| 服务 | 地址 | 备注 |
|------|------|------|
| FastAPI | `http://localhost:8000` | API 服务 |
| FastAPI Docs | `http://localhost:8000/docs` | Swagger UI |
| LangGraph | `http://localhost:2026` | Agent 服务 |
| LangGraph UI | `http://localhost:2026/ui` | Agent Studio |
| Next.js | `http://localhost:3000` | 前端 SPA |
| PostgreSQL | `localhost:5432` | 主数据库 |
| MongoDB | `121.40.159.60:27017` | 详细日志 |
| MinIO | `114.55.110.60:9000` | 对象存储 |

### 11.3 LangGraph 启动

```bash
# start_server.py
uvicorn.run("langgraph_api.server:app", host="0.0.0.0", port=2026)
```

配置了内存存储 (`:memory:`) 和本地开发模式。

---

## 12. 安全与中间件

### 12.1 中间件栈

| 中间件 | 说明 |
|--------|------|
| `CORSMiddleware` | 跨域支持（允许 localhost:3000, :8080） |
| `RateLimiterMiddleware` | 速率限制（滑动窗口，300 req/min） |
| `Error Handler` | 统一异常处理（4 级异常处理） |

### 12.2 速率限制

- **算法**: 滑动窗口算法
- **限制**: 300 请求/分钟/客户端
- **识别**: 优先用户 ID，回退为 IP
- **响应头**: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- **超限响应**: 429 + `Retry-After` 头

### 12.3 异常处理体系

```
AppException (基类)
├── RateLimitExceededException  (429)
├── HTTPException 映射
│   ├── 400 bad_request
│   ├── 401 unauthorized
│   ├── 403 forbidden
│   ├── 404 not_found
│   ├── 422 unprocessable_entity
│   └── 500 internal_server_error
└── RequestValidationError (422)
    └── 字段级别验证错误
```

### 12.4 认证

- **JWT 配置**: 已定义 secret_key、algorithm (HS256)、token expire (30min)
- **当前状态**: 开发环境使用默认用户 (`admin@test.com`)
- **待实现**: 完整的 JWT 认证流程

---

## 附录

### A. 关键文件索引

| 文件 | 说明 |
|------|------|
| `start_server.py` | LangGraph API 服务器启动入口 |
| `backend/app/main.py` | FastAPI 主服务入口 |
| `backend/app/config/settings.py` | 全局配置管理 |
| `backend/app/config/database.py` | PostgreSQL + MongoDB 连接 |
| `backend/app/config/minio_client.py` | MinIO 客户端封装 |
| `backend/app/agents/api/agent.py` | API 测试智能体定义 |
| `backend/app/agents/api/tool_registry.py` | Agent 工具注册 |
| `backend/app/services/scenario_execution_engine.py` | 场景执行引擎（核心） |
| `backend/app/services/api_test_executor.py` | API 测试执行器 |
| `backend/app/services/openapi_parser.py` | OpenAPI 文档解析器 |
| `backend/app/schemas/enums.py` | 系统枚举定义 |
| `graph.json` | LangGraph 图配置 |
| `ui/lib/api/client.ts` | 前端 API 客户端 |
| `ui/lib/langgraph/config.ts` | LangGraph SDK 配置 |
| `ui/lib/translations/` | 国际化翻译文件 |

### B. 枚举定义速查

```
Priority:        low | medium | high | critical
TestCaseState:   new | review_pending | reviewed | not_run | passed | failed | blocked | skipped
TestCaseType:    acceptance | accessibility | compatibility | destructive | functional | other | performance | regression | security | smoke_sanity | usability
TestCaseTemplate: test_case | test_case_bdd
AutomationStatus: not_automated | automated | in_progress | obsolete
TestResultStatus: passed | failed | skipped | blocked | not_executed
TestRunState:    new_run | in_progress | under_review | rejected | done | closed
TestPlanStatus:  draft | active | completed | archived
APIScriptFormat: playwright | jest | postman
APISchemaType:   openapi | swagger | graphql
WebScriptFormat: playwright | cypress | selenium
```

### C. 跨平台注意事项

- **Windows 路径**: `FixedFilesystemBackend` 修复反斜杠 → 正斜杠
- **Agent 工作区**: 配置中混合了 Linux 和 Windows 绝对路径（需根据部署环境调整）
- **Python 版本**: 要求 ≥ 3.13

---

> 本文档由 AI 自动分析生成，基于项目代码的架构逆向工程。
