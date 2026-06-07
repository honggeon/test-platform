# 玄鉴智能测试平台 — 技术架构深度文档

> 版本 2.0.0 | 最后更新: 2026-05-24
> 项目: ai-test-agent-system-platform

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构总览](#2-系统架构总览)
3. [后端架构详解](#3-后端架构详解)
4. [前端架构详解](#4-前端架构详解)
5. [AI Agent 系统](#5-ai-agent-系统)
6. [代码知识图谱 (GitNexus KG)](#6-代码知识图谱-gitnexus-kg)
7. [HAT 测试框架](#7-hat-测试框架)
8. [数据库设计](#8-数据库设计)
9. [API 设计规范](#9-api-设计规范)
10. [基础设施与部署](#10-基础设施与部署)
11. [服务间通信与数据流](#11-服务间通信与数据流)
12. [核心工作流详解](#12-核心工作流详解)
13. [关键设计决策](#13-关键设计决策)
14. [附录: 项目管理与扩展指南](#14-附录-项目管理与扩展指南)

---

## 1. 项目概述

### 1.1 定位与目标

玄鉴智能测试平台是一套 **AI 驱动的智能软件测试管理系统**，覆盖**全测试生命周期**：

- **测试用例管理** — 结构化用例库，含步骤、标签、附件、版本
- **API 自动化测试** — OpenAPI 文档驱动，AI 生成 HAT YAML 脚本，Allure 报告
- **Web/UI 自动化测试** — Web 函数管理、页面对象模型、AI 生成测试
- **场景编排测试** — 多接口业务流编排，变量传递，数据依赖解析
- **测试计划与执行** — 计划关联用例，批量/定时执行
- **测试报告看板** — Dashboard 聚合、Allure 集成
- **代码知识图谱** — GitNexus 启发，全栈代码分析、变更影响分析
- **智能诊断** — 失败日志 AI 分析、规则引擎、KG 辅助定位
- **智能 AI 对话** — 3 个专用 Agent（API 测试、代码分析、日志诊断）

### 1.2 核心数据流

```
用户 (UI) → FastAPI Backend ↔ PostgreSQL / MongoDB / MinIO
                        ↔ LangGraph API (2026) ↔ deepagents Agent
                        ↔ MCP Tools ↔ 文件系统 / MinIO
                        ↔ WebSocket → 前端实时推送
```

### 1.3 技术栈总览

| 层级 | 技术 | 用途 |
|------|------|------|
| 后端框架 | FastAPI (Python 3.13+) | REST API 服务 |
| 前端框架 | Next.js 14 (React 18) | 管理 UI |
| ORM | SQLAlchemy 2.0 (异步) | PostgreSQL 操作 |
| 文档数据库 | MongoDB (Motor) | 日志、大文档存储 |
| 对象存储 | MinIO (S3-compatible) | 测试附件、脚本 |
| Agent 框架 | deepagents + LangGraph | AI Agent 工作流 |
| 知识图谱 | GitNexus (Python 改写) | 代码分析 |
| 测试框架 | HAT (pytest + Allure) | API 自动化测试 |
| 容器化 | Docker / Docker Compose | 基础设施 |
| 包管理 | uv / pnpm / npm | 依赖管理 |

---

## 2. 系统架构总览

### 2.1 服务拓扑

```
┌─────────────────────────────────────────────────────────────┐
│                       客户端 (Browser)                        │
│                   http://localhost:3000                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Next.js Frontend (:3000)                                    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  /api/* → proxy → FastAPI Backend (:8000)            │    │
│  │  /lg/*  → proxy → LangGraph API (:2026)              │    │
│  │  LangGraph SDK → 直连 LangGraph API (:2026)          │    │
│  │  WebSocket    → 直连 FastAPI Backend (:8000)         │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
┌─────────────────┐┌──────────┐┌──────────┐
│ FastAPI Backend ││LangGraph ││ MinIO    │
│ (:8000)         ││API (:2026)││ (:9000)  │
└────────┬────────┘└────┬─────┘└──────────┘
         │              │
         ▼              ▼
┌──────────────────────────────┐
│ PostgreSQL (:5432)           │
│ ai_test_agent_system_db      │
│  + MongoDB (:27017)          │
└──────────────────────────────┘
```

### 2.2 微架构 vs 单体

项目选择了 **单体应用 + 独立 AI Agent 服务** 的混合架构：

- **FastAPI** 单体承载所有业务 REST API（~400+ 端点）
- **LangGraph API 服务** 独立部署于 :2026，承载 3 个 AI Agent
- **MinIO** 独立对象存储，用于附件、测试脚本、Artifacts
- 数据库（PG + MongoDB）共用，Agent 和 API 共享

### 2.3 端口分配

| 服务 | 端口 | 用途 |
|------|------|------|
| FastAPI Backend | 8000 | 业务 REST API |
| LangGraph API | 2026 | Agent 运行时 API |
| Next.js UI | 3000 | 用户界面 |
| PostgreSQL | 5432 | 关系数据库 |
| MongoDB | 27017 | 文档数据库 |
| MinIO | 9000 | 对象存储 |

---

## 3. 后端架构详解

### 3.1 分层架构 (Layered Architecture)

后端采用经典的 **分层架构** + **依赖注入** 模式：

```
app/
├── api/              # 路由层 (Router)
│   ├── deps.py       # 依赖注入 (FastAPI Depends)
│   └── v2/           # API v2 端点 (~25 个路由文件)
├── models/           # ORM 模型层 (SQLAlchemy)
│   ├── base.py       # Base, UUIDMixin, TimestampMixin
│   ├── mongodb/      # MongoDB 文档模型
│   └── *.py          # 各业务模型
├── schemas/          # Pydantic Schema (请求/响应)
├── services/         # 业务逻辑层 (~25 个服务)
├── repositories/     # 数据访问层 (可选)
├── agents/           # AI Agent 定义
├── kg/               # 知识图谱引擎
├── config/           # 配置 (settings, database, minio)
├── middleware/       # 中间件 (CORS, 限流, 异常处理)
├── migrations/       # 数据库迁移脚本
└── utils/            # 工具函数
```

### 3.2 各层职责

#### 路由层 (api/v2/)

每个模块一个路由文件，通过 `app/api/__init__.py` 统一注册：

```python
api_router.include_router(projects.router, tags=["项目管理"])
api_router.include_router(test_cases.router, tags=["测试用例管理"])
# ... 共 15+ 模块
```

典型路由文件模式（以 `api_endpoints.py` 为例）：
- `APIRouter()` 实例
- `Depends(get_db)` 注入数据库会话
- `CurrentUserIdDep` 注入用户 ID
- Pydantic schema 做请求/响应校验
- 调用 Service 层处理业务逻辑

#### 模型层 (models/)

**SQLAlchemy 2.0 异步 ORM** + **MongoDB (Motor)** 双数据库。

**基类设计** (`base.py`):
```python
class Base(DeclarativeBase): ...
class UUIDMixin:          # UUID 主键
class TimestampMixin:     # created_at / updated_at
```

**数据模型分类**:
- 项目管理: `Project`, `Team`, `User`
- 用例: `TestCase`, `TestStep`, `Tag`, `TestCaseTag`
- API 测试: `APITest`, `APITestRun`, `APITestResult`, `APIEndpoint`
- 场景测试: `TestScenario`, `ScenarioStep`, `StepDataMapping`, `ScenarioVariable`, `ScenarioRun`, `ScenarioStepResult`
- Web 测试: `WebFunction`, `WebTest`, `WebPage`
- 执行: `TestRun`, `TestRunTestCase`, `TestResult`, `TestStepResult`
- 配置: `Configuration`, `LLMConfig`
- 诊断: `DiagnosisReportPG` (PG) + `DiagnosisReport` (MongoDB)
- 基础: `Folder`, `Attachment`

#### Schema 层 (schemas/)

Pydantic v2 模型，用于 API 请求/响应校验、OpenAPI 文档生成。

关键 schema 分类：
- 通用: `common.py` (SuccessResponse, ErrorResponse), `pagination.py` (PaginationParams, PaginatedResponse)
- 各业务: `project.py`, `test_case.py`, `api_endpoint.py`, `scenario.py`, `test_report.py` 等
- 枚举: `enums.py`

#### 服务层 (services/)

**核心业务逻辑服务** (25 个):

| 服务 | 职责 |
|------|------|
| `project_service` | 项目 CRUD、成员管理 |
| `test_case_service` | 测试用例 CRUD、步骤管理 |
| `api_test_service` | API 测试管理 |
| `api_test_executor` | API 测试执行引擎 |
| `scenario_execution_engine` | 场景编排执行 (811 行核心引擎) |
| `openapi_parser` | OpenAPI 文档解析与文件夹结构创建 |
| `report_service` | 项目 Dashboard 聚合统计 |
| `test_diagnosis_service` | 失败日志诊断引擎 |
| `analyze_service` | 代码仓库分析 (KG 分析发起) |
| `code_repo_service` | 代码仓库配置管理 |
| `scenario_service` | 场景管理 |
| `web_test_service` | Web 测试管理 |
| `web_function_service` | Web 函数管理 |
| `export_service` | 用例导出 |
| `attachment_service` | 附件管理 |
| `configuration_service` | 配置管理 |
| `llm_config_service` | LLM 配置管理 |
| `folder_service` | 文件夹管理 |
| `mongodb_service` | MongoDB 通用服务 |
| `diagnosis_notification_service` | WebSocket 推送 |

#### 仓库层 (repositories/)

可选的 Repository 模式，部分模块使用（多为直接 Service 操作 Session）。

### 3.3 依赖注入设计

```python
# app/api/deps.py
DbSessionDep = Depends(get_db)        # PostgreSQL session
CurrentUserIdDep = "..."              # 当前用户 ID
```

路由中通过 `Depends()` 注入依赖，FastAPI 自动管理生命周期。

### 3.4 中间件栈

```
请求 → CORSMiddleware → RateLimiterMiddleware → Router → Exception Handler
```

1. **CORS**: 允许开发环境前端域名
2. **Rate Limiter**: 每分钟 300 请求
3. **Exception Handler**: 统一错误格式 `{"detail": "...", "code": "..."}`

### 3.5 应用生命周期 (`main.py`)

1. `lifespan` 协程上下文管理器:
   - 启动时: 创建 PG 表 (debug=true)、创建默认用户
   - 关闭时: `engine.dispose()`
2. MongoDB 连接已实现但暂未启用 (`await MongoDB.connect()` 注释)

---

## 4. 前端架构详解

### 4.1 Next.js App Router 结构

```
ui/
├── app/                          # App Router 页面
│   ├── layout.tsx                # 根布局 (LanguageProvider + Toaster)
│   ├── page.tsx                  # 首页
│   ├── projects/page.tsx         # 项目列表
│   └── projects/[projectId]/
│       ├── dashboard/            # 测试报告看板
│       ├── api-tests/            # API 测试
│       ├── web-tests/            # Web 测试
│       ├── scenario-tests/       # 场景测试
│       ├── test-cases/           # 测试用例
│       ├── test-plans/           # 测试计划
│       ├── test-runs/            # 测试执行
│       ├── test-reports/         # 测试报告
│       ├── allure-reports/       # Allure 报告
│       ├── diagnosis/            # 日志诊断
│       ├── environments/         # 环境管理
│       └── fullstack-analysis/   # 全栈分析
├── components/                   # React 组件
│   ├── layout/                   # 布局组件 (sidebar, header, main-layout)
│   ├── ui/                       # shadcn/ui 基础组件 (button, dialog, card, etc.)
│   ├── test-cases/               # 测试用例组件
│   ├── api-tests/                # API 测试组件
│   ├── web-tests/                # Web 测试组件
│   ├── scenario-tests/           # 场景测试组件
│   ├── kg/                       # 知识图谱组件
│   ├── langgraph/                # AI 对话组件
│   ├── diagnosis/                # 诊断组件
│   ├── editor/                   # 代码编辑器 (Monaco)
│   └── settings/                 # 设置组件
├── hooks/                        # React Hooks
│   ├── useChat.ts                # AI 对话 Hook
│   ├── useThreads.ts             # 线程管理 Hook
│   └── useDiagnosisWebSocket.ts  # WebSocket 诊断
├── lib/                          # 工具库
│   ├── api/                      # API 客户端 (~20 个文件)
│   ├── langgraph/                # LangGraph SDK 集成
│   └── translations/             # i18n (zh/en/ja)
├── providers/                    # React Context
│   ├── LanguageProvider.tsx      # 多语言
│   └── ChatProvider.tsx          # 聊天状态
└── types/                        # TypeScript 类型
```

### 4.2 组件架构模式

所有业务页面采用 **SSR 页面 + 客户端组件** 混合模式：

- **Page 组件** (`page.tsx`)：SSR 获取初始数据，调用 `MainLayout`
- **子组件**：`'use client'` 客户端组件，交互逻辑
- **API 调用**：统一通过 `lib/api/*.ts` 封装，使用 fetch

### 4.3 状态管理

项目 **未使用 Redux/Zustand**，而是采用：
- **SWR** — 数据获取与缓存（`useSWR`）
- **React Context** — 全局状态（语言、聊天）
- **URL 参数** — 部分筛选状态（`nuqs`）
- **Sonner** — Toast 通知

### 4.4 UI 框架

- **shadcn/ui** (Radix UI 原语) — 基础组件库
- **Tailwind CSS** — 样式框架
- **lucide-react** — 图标库
- **Monaco Editor** — 代码编辑器
- **Sigma.js / 3D-Force-Graph** — 知识图谱可视化
- **react-markdown + remark-gfm** — Markdown 渲染
- **react-syntax-highlighter** — 代码语法高亮
- **@dnd-kit** — 拖拽排序

### 4.5 多语言支持 (i18n)

```typescript
// 支持: 中文(zh), English(en), 日本語(ja)
const translations = { zh: {...}, en: {...}, ja: {...} };
// 使用: const { t } = useLanguage();
// t("nav.testCases") → "测试用例" / "Test Cases"
```

### 4.6 AI 对话界面 (LangGraph)

与 LangGraph Agent 的交互通过 `@langchain/langgraph-sdk` 实现：

- **`ChatInterface`**: 对话消息列表 + 输入框
- **`ChatMessage`**: 消息气泡（支持 tool calls、Markdown）
- **`ToolCallBox`**: 工具调用可视化
- **`InterruptActions`**: 人工审批（Tool Approval）
- **`SubAgentIndicator`**: 子 Agent 状态指示
- **`ThreadList`**: 对话线程管理

---

## 5. AI Agent 系统

### 5.1 总体架构

项目使用 **deepagents** 框架创建 Agent，通过 **LangGraph CLI** 托管 API 服务。

```
graph.json (Agent 注册)
  ├── api_agent          → app.agents.api.agent:agent
  ├── code_analysis_agent → app.agents.code.agent:agent
  └── log_analysis_agent  → app.agents.log_analysis.agent:agent

LangGraph API Server (:2026)
  └── Agent Runtime (Pregel) → deepagents Agent
       ├── SkillsMiddleware (按需加载)
       ├── Context Injection Middleware
       └── Tools (MCP + 本地)
```

### 5.2 三个 Agent 详解

#### 5.2.1 API 测试 Agent (`agents/api/`)

| 属性 | 值 |
|------|-----|
| 模型 | DeepSeek (langchain init_chat_model) |
| 框架 | deepagents + SkillsMiddleware |
| 设计模式 | Agent + Skills + Tools 三层 |
| Skills 目录 | `backend/workspace/api/hat_skills/` |

**系统提示词核心能力**:
- 测试计划生成 → OpenAPI 端点分析
- HAT YAML 脚本生成 → 关键字驱动
- 场景测试 → 跨文件编排
- 测试执行 → pytest + TestRunner
- 测试修复 → 7 类失败原因诊断
- 报告生成 → Allure 解析

**工具体系**:

| 工具分类 | 文件 | 工具数 |
|----------|------|--------|
| OpenAPI 管理 | `openapi_tools.py` | 5 (list/get/detail) |
| 测试成果物 | `test_artifacts_tools.py` | 5 (save/load) |
| 测试执行 | `test_execution_tools.py` | 3 (run/parse) |
| 脚本管理 | `script_tools.py` | 3 (info/download/delete) |
| 脚本执行 | `script_execution_tools.py` | 2 (execute/status) |
| 批量操作 | `batch_tools.py` | 2 (batch_generate/run) |
| 场景测试 | `scenario_tools.py` | 场景编排 |
| 环境管理 | `environment_tools.py` | 环境操作 |
| 诊断触发 | `diagnosis_trigger_tools.py` | 诊断联动 |
| KG 集成 | `kg_tools.py` | 代码定位 |

**上下文注入** (`APIContextInjectionMiddleware`):
- 动态注入 `project_identifier` 和 `folder_id`
- Agent 无需询问用户，降低交互成本

#### 5.2.2 代码分析 Agent (`agents/code/`)

| 属性 | 值 |
|------|-----|
| 设计 | 独立 Agent，复用 LangGraph + DeepSeek |
| 核心工作流 | Search → Read → Trace → Cite → Validate |
| 关键约束 | 必须搜索后才回答，必须引用代码位置 `[[file:line]]` |
| 工具 | `kg_search_code`, `kg_get_symbol_context`, `kg_impact_analysis`, `kg_graph_data`, `kg_change_impact`, `kg_list_commits`, `kg_read_file`, `kg_search_by_type`, `kg_get_processes` |
| 用途 | 代码知识图谱问答 |

**对话模板**:
- 用户: "这个函数被哪些地方调用了？"
- Agent: 搜索 → 追踪调用链 → 回答 `[[app/service.py:42]]`

#### 5.2.3 日志诊断 Agent (`agents/log_analysis/`)

| 属性 | 值 |
|------|-----|
| 设计 | Agent + Skills + Tools |
| Skills 目录 | `backend/app/agents/log_analysis/agent_skills/` |
| 核心工具 | `query_test_logs`, `get_log_detail`, `diagnose_failure`, `save_diagnosis_report`, `notify_frontend` |

**诊断工作流**:
1. `query_test_logs` — 查询失败日志
2. `get_log_detail` — 获取详细日志
3. `diagnose_failure` — LLM + 规则引擎根因分类
4. `save_diagnosis_report` — 持久化到 PG + MongoDB
5. `notify_frontend` — WebSocket 推送

**诊断引擎** (`test_diagnosis_service.py`):
- 敏感数据脱敏（Authorization/Cookie/Token）
- KG 超时: 3s, LLM 超时: 10s
- 幂等检查 (dedup_key)
- 规则引擎 YAML 配置 (`config/failure_rules.yaml`)
- 分布式锁（可选 Redis）

### 5.3 Skills 机制

Skills 通过 `SkillsMiddleware` 按需加载，大幅减少 token 消耗：

```python
skills_backend = FixedFilesystemBackend(
    root_dir=skills_root, virtual_mode=True
)
```

**API Agent Skills** (位于 `backend/workspace/api/hat_skills/`):
- `hat-test-planner` — 测试计划生成
- `hat-test-generator` — HAT YAML 脚本生成
- `hat-test-healer` — 测试修复
- `hat-test-reporter` — 报告生成

**日志诊断 Skills** (位于 `backend/app/agents/log_analysis/agent_skills/`):
- 诊断领域知识
- 最佳实践指导

---

## 6. 代码知识图谱 (GitNexus KG)

### 6.1 概述

从开源项目 [GitNexus](https://github.com/ohmplatform/GitNexus) 的 TypeScript 实现改写为 Python。目标是对**被测项目**的代码进行全量分析，生成代码知识图谱，供 Agent 进行代码理解和诊断定位。

> 注意: KG 分析的是外部被测项目的代码，不是平台自身的代码。

### 6.2 12 阶段 DAG 管道

```
scan → structure → symbols → imports → calls → heritage
→ mro → routes → tools → orm → communities → processes → markdown
```

| 阶段 | 文件 | 功能 |
|------|------|------|
| 1. scan | `phases/scan.py` | 文件系统扫描，.gitignore 过滤，二进制过滤 |
| 2. structure | `phases/structure.py` | 文件和目录结构节点 |
| 3. symbols | `phases/symbol_extractor.py` | AST 解析提取类、函数、方法、变量 |
| 4. calls | `phases/calls.py` | 函数调用关系分析 |
| 5. heritage | `phases/heritage_processor.py` | 类继承关系解析 |
| 6. mro | `phases/mro.py` | MRO (Method Resolution Order) |
| 7. routes | `phases/route_extractor.py` | Web 路由提取 (Flask/FastAPI/Django) |
| 8. tools | `phases/tool_extractor.py` | MCP/LangChain 工具定义提取 |
| 9. orm | `phases/orm_extractor.py` | SQLAlchemy ORM 模型提取 |
| 10. communities | `phases/communities.py` | 社区发现（图聚类） |
| 11. processes | `phases/process_extractor.py` | 业务流程提取 |
| 12. markdown | `phases/markdown.py` | Markdown 文档结构分析 |

### 6.3 数据类型

**节点类型** (15 种):
```python
NODE_FILE, NODE_FOLDER           # 文件系统
NODE_CLASS, NODE_FUNCTION,       # 代码符号
  NODE_METHOD, NODE_VARIABLE,
  NODE_MODULE, NODE_INTERFACE,
  NODE_ENUM, NODE_STRUCT
NODE_ROUTE, NODE_API_ENDPOINT   # 路由
NODE_TOOL, NODE_CODE_ELEMENT    # 工具
NODE_COMMUNITY, NODE_PROCESS,   # 图结构
  NODE_MARKDOWN_SECTION
```

**关系类型** (14 种):
```python
REL_CONTAINS, REL_IMPORTS, REL_CALLS,
REL_EXTENDS, REL_IMPLEMENTS,
REL_METHOD_OVERRIDES, REL_METHOD_IMPLEMENTS,
REL_DEFINED_IN, REL_MEMBER_OF,
REL_HANDLES_ROUTE, REL_QUERIES,
REL_STEP_IN_PROCESS, REL_ENTRY_POINT_OF,
REL_LINKS_TO
```

### 6.4 搜索系统

**混合搜索** (RRF / Reciprocal Rank Fusion):
```
FTS (PostgreSQL full-text search) + BM25 (rank_bm25)
→ RRF 融合 (K=60) → 排序结果
```

### 6.5 持久化

**PostgreSQL 三表**:
| 表 | 用途 | 关键字段 |
|----|------|----------|
| `kg_nodes` | 节点存储 | repo_path, commit_hash, node_id, type, name, file_path, properties (JSONB) |
| `kg_relationships` | 关系存储 | repo_path, commit_hash, rel_id, type, source_node_id, target_node_id |
| `kg_commits` | Commit 元信息 | repo_path, commit_hash, message, author, node_count |

**多版本共存**: 按 `commit_hash` 区分版本，支持增量分析。

### 6.6 MCP 服务

KG 暴露为 MCP 服务 (`app/kg/mcp/server.py`)，供 AI Agent 通过 MCP 协议调用：

```
KGTools:
  search_code(query, node_type, limit, commit_hash)
  get_symbol_context(node_id, commit_hash)
  impact_analysis(symbol, direction, depth)
  graph_data()
  change_impact(changes)
  list_commits(repo_path)
  read_file(file_path, commit_hash)
  search_by_type(node_type, repo_path)
  get_processes(repo_path, commit_hash)
```

### 6.7 可视化前端

| 组件 | 用途 | 技术 |
|------|------|------|
| `CodeGraphView` | 2D 图谱 | Sigma.js + graphology |
| `CyberGraph3D` | 3D 赛博朋克图谱 | 3D-Force-Graph + Three.js |
| `GraphExplorer` | 图谱搜索与浏览 | 综合面板 |
| `SymbolDetailPanel` | 符号详情 | 源码 + 调用链 |
| `ChangeImpactAnalyzer` | 变更影响 | 调用链追踪 |
| `ProcessPanel` | 业务流程 | 流程图 |
| `ProcessTracePanel` | 流程追踪 | 执行路径 |
| `AnalysisSummary` | 分析摘要 | 统计指标 |
| `CommunityFilter` | 社区过滤 | 多选标签 |
| `CodeRepoConfig` | 仓库配置 | 表单 |

---

## 7. HAT 测试框架

### 7.1 概述

HAT (Http API Test) 是一个**关键字驱动**的 API 自动化测试框架，基于 pytest + Allure 构建。用户通过 YAML/Excel 编写测试用例，框架自动解析、执行并生成 Allure 报告。

### 7.2 架构

```
HAT/
├── core/
│   ├── TestRunner.py      # 核心测试运行器
│   ├── globalContext.py   # 全局上下文 (变量共享)
│   └── CasePlugin.py      # 用例插件
├── keywords/
│   └── api_keywords.py    # 关键字库 (发送请求POST/GET, 断言, 数据库等)
├── parse/
│   ├── YamlCaseParser.py  # YAML 用例解析器
│   ├── ExcelCaseParser.py # Excel 用例解析器
│   └── CaseParser.py      # 抽象解析器
├── context/
│   └── ApiCaseContext.py  # API 上下文管理
├── extend/script/
│   └── run_script.py      # 脚本执行扩展
├── utils/
│   ├── VarRender.py       # 变量渲染 {{var}}
│   └── allure_step_logger.py  # Allure 步骤日志
├── key_dir/               # 关键字目录（扩展）
└── img/                   # 报告图片
```

### 7.3 测试用例结构 (YAML)

```yaml
# 基础配置
基础配置:
  用例标题: "登录接口测试"
  用例类型: "ApiCase"
  一级模块: "用户管理"
  二级模块: "登录"

# 数据驱动
数据驱动:
  - username: "admin"
    password: "123456"
  - username: "user1"
    password: "abc123"

# 前置脚本
前置脚本:
  - "context.update({'token': get_token()})"

# 用例步骤
用例步骤:
  - 发送登录请求:
      操作类型: "发送请求POST"
      请求地址: "https://api.example.com/login"
      请求头: {"Content-Type": "application/json"}
      请求体: |
        {
          "username": "{{username}}",
          "password": "{{password}}"
        }
  - 验证响应:
      操作类型: "断言"
      表达式: "status_code == 200"
```

### 7.4 执行流程

```
pytest TestRunner.py
  → YamlCaseParser.parse()  # 解析 YAML → case_infos
  → pytest.mark.parametrize  # 参数化每一条用例
  → TestRunner.test_case_execute()
    → 加载全局上下文 (context.yaml)
    → 执行前置脚本
    → 循环执行用例步骤:
      → 变量渲染 ({{var}} → 实际值)
      → 根据操作类型派发到对应关键字
      → Allure 步骤日志
    → 生成 Allure 报告
```

### 7.5 关键字体系

`api_keywords.py` 中的关键字引擎，支持的操作类型:
- 发送请求 (POST/GET/PUT/DELETE/PATCH)
- 断言 (状态码、JSON 字段、响应时间)
- 数据库操作 (MySQL 查询)
- 变量设置
- 脚本执行
- Base64/AES 加解密

### 7.6 数据驱动 (DDT)

框架原生支持 DDT（Data-Driven Testing）：
- YAML 中定义 `数据驱动` 列表
- 解析器将每条 DDT 展开为独立用例
- 变量渲染通过 Jinja2 风格 `{{var}}`

### 7.7 Allure 报告集成

```python
allure.dynamic.feature(base_info.get("一级模块"))
allure.dynamic.story(base_info.get("二级模块"))
allure.dynamic.title(base_info.get("用例标题"))
# 每个步骤: allure_step_with_log(step_name)
```

---

## 8. 数据库设计

### 8.1 PostgreSQL (关系型)

**核心表结构**:

```
projects
  ├── id (UUID PK)
  ├── identifier (VARCHAR 50, UNIQUE)  # 外部标识符
  ├── name (VARCHAR 500)
  └── ...

folders
  ├── id (UUID PK)
  ├── project_id → projects.id
  ├── parent_id → folders.id (自引用树)  # 层级文件夹
  └── ...

test_cases
  ├── id (UUID PK)
  ├── project_id → projects.id
  ├── folder_id → folders.id
  ├── title (VARCHAR 500)
  ├── priority / severity / status
  └── ...

test_steps
  ├── id (UUID PK)
  ├── test_case_id → test_cases.id
  ├── step_number (INT)
  └── operation / expected_result

api_endpoints
  ├── id (UUID PK)
  ├── project_id → projects.id
  ├── method / path / tag
  └── last_run_status

test_scenarios
  ├── id (UUID PK)
  ├── project_id → projects.id
  ├── identifier (UNIQUE)
  ├── global_variables (JSONB)
  ├── setup_config / teardown_config
  └── retry_count / timeout_seconds / parallel_execution

scenario_steps
  ├── id (UUID PK)
  ├── scenario_id → test_scenarios.id
  ├── step_order (INT)
  ├── endpoint_id → api_endpoints.id
  └── data_mappings (JSONB) / extraction_rules (JSONB)

test_plans
  ├── id (UUID PK)
  ├── project_id → projects.id
  ├── name / description / status
  ├── scheduled_at / execution_mode
  └── ...

test_runs
  ├── id (UUID PK)
  ├── test_plan_id → test_plans.id
  ├── status / started_at / finished_at
  └── ...

test_results
  ├── id (UUID PK)
  ├── test_run_id → test_runs.id
  ├── case_id → test_cases.id
  ├── status / duration_ms
  └── ...

diagnosis_reports (kg_nodes, kg_relationships, kg_commits)  # 知识图谱表

configurations / llm_config / attachments  # 配置与附件
```

**关键模式**:
- 所有表使用 `UUID` 主键
- 统一 `created_at`/`updated_at` 时间戳 (TimestampMixin)
- JSONB 存储动态数据（global_variables, data_mappings, properties）
- 自引用外键实现文件夹树

### 8.2 MongoDB (文档型)

**集合**:
| 集合 | 用途 |
|------|------|
| `api_test_logs` | API 测试执行日志 |
| `diagnosis_reports` | 诊断报告详文 |
| `attachments` | 附件元信息（替代 MinIO ？） |
| `audit_logs` | 审计日志 |
| `version_history` | 用例版本历史 |

### 8.3 MinIO 对象存储

| Bucket | 用途 |
|--------|------|
| `test-management` | 测试附件、YAML 脚本、Allure 结果、HAT 成果物 |

客户端(`minio_client.py`)自动检测服务器时间偏差并补偿，避免 S3 签名过期错误。

---

## 9. API 设计规范

### 9.1 通用规范

- **前缀**: `/api/v2/`
- **版本**: 当前 v2, 无 v1
- **响应格式**: `{ "code": 0, "data": {...}, "message": "..." }`
- **分页**: `{ "items": [...], "total": N, "page": N, "page_size": N }`
- **错误**: HTTP 状态码 + `{ "detail": "...", "code": "ERR_XXX" }`

### 9.2 API 模块列表

| 模块 | 路由前缀 | 主要端点 |
|------|----------|----------|
| 项目管理 | `/projects` | CRUD, 成员管理 |
| 文件夹 | `/projects/{id}/folders` | 树结构, 移动 |
| 测试用例 | `/projects/{id}/test-cases` | CRUD, 步骤, 标签, 导出 |
| API 端点 | `/projects/{id}/api-endpoints` | OpenAPI 解析, CRUD |
| API 测试 | `/projects/{id}/api-tests` | 生成, 执行, 结果 |
| 场景测试 | `/scenarios` | 编排, 执行, 变量 |
| Web 测试 | `/projects/{id}/web-tests` | 页面/函数管理 |
| 测试计划 | `/projects/{id}/test-plans` | 计划 CRUD |
| 测试运行 | `/projects/{id}/test-runs` | 执行管理 |
| 测试结果 | `/projects/{id}/test-results` | 结果查询 |
| 测试报告 | `/projects/{id}/reports` | Dashboard, 统计 |
| 环境管理 | `/projects/{id}/environments` | CRUD |
| 配置管理 | `/projects/{id}/configurations` | Key-Value |
| LLM 配置 | `/llm-config` | 模型配置 |
| 诊断报告 | `/projects/{id}/diagnosis/reports` | 诊断 CRUD + WebSocket |
| 代码仓库 | `/projects/{id}/code-repo` | 仓库配置 |
| 全栈分析 | `/projects/{id}/code-analysis` | 分析任务 |
| 附件管理 | `/attachments` / `/test-cases/{id}/attachments` | 上传/下载 |
| 文档管理 | `/projects/{id}/documents` | 文档 CRUD |

### 9.3 开放接口

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
- 健康检查: `GET /health`

### 9.4 LangGraph API 端点

LangGraph API (:2026) 提供 Agent 调用接口:
- `POST /api/agents/{agent_name}/invoke` — 调用 Agent
- `POST /api/agents/{agent_name}/runs` — 创建运行
- `GET /api/agents/{agent_name}/runs/{run_id}` — 查询状态
- WebSocket — 流式推送
- Swagger UI: `http://localhost:2026/docs`

---

## 10. 基础设施与部署

### 10.1 开发环境架构

```
Docker (可选)
  ├── PostgreSQL (:5432)
  └── MinIO (:9000)

本地服务:
  ├── FastAPI Backend (:8000)
  ├── LangGraph API (:2026)
  └── Next.js Frontend (:3000)
```

### 10.2 启动方式 (Makefile)

| 命令 | 功能 | 说明 |
|------|------|------|
| `make dev` | 前台启动全部三个服务 | 开发调试 |
| `make start` | 后台启动全部三个服务 | 日常使用 |
| `make stop` | 停止全部服务 | |
| `make status` | 查看服务状态 | |
| `make build` | 构建前端 | 生产模式 |
| `make init` | 初始化环境 | 安装依赖 + 数据库迁移 |
| `make logs` | 查看日志 | `logs/` 目录 |
| `make restart` | 重启全部服务 | |
| `make kg-migrate` | KG 数据库迁移 | 创建 kg_* 表 |
| `make kg-analyze` | 执行 KG 分析 | |
| `make kg-rollback` | KG 版本回滚 | |

启动脚本: `scripts/start-all.sh` (后台) / `scripts/stop-all.sh` (停止)

### 10.3 依赖管理

- **Python**: `pyproject.toml` (uv / pip)
- **Node**: `package.json` (npm / pnpm)
- **Venv**: `.venv/` (项目根目录)

### 10.4 配置管理

单一配置源 `.env` (项目根目录), 通过 `settings.py` (Pydantic Settings) 加载:

```
APP_NAME=玄鉴测试平台
APP_VERSION=2.0.0
DEBUG=True
POSTGRES_HOST=127.0.0.1
...  # 完整配置参考 .env 文件
```

**跨平台路径策略**:
- Linux: 相对路径 `backend/workspace/xxx`
- Windows: `~/workspace/backend/workspace/xxx`
- 通过 `WORKSPACE_BASE` 环境变量统一覆盖

---

## 11. 服务间通信与数据流

### 11.1 通信方式总览

```
前端 ↔ 后端:     HTTP REST + WebSocket
前端 ↔ Agent:    LangGraph SDK HTTP (端口 2026)
前端 ↔ MinIO:    预签名 URL (浏览器直传/直下)
后端 ↔ MinIO:    MinIO SDK (服务端操作)
后端 ↔ PG:       SQLAlchemy 异步 ORM
后端 ↔ MongoDB:   Motor 异步驱动
Agent ↔ Tools:   MCP 协议 / 本地函数调用
Agent ↔ Skills:  FilesystemBackend (虚拟文件系统)
诊断 → 前端:     WebSocket 实时推送
```

### 11.2 关键数据流

#### API 测试执行流程

```
用户: "生成并执行登录接口测试"
  → UI → POST /api/v2/.../api-tests/generate
  → LangGraph API → api_agent (deepagents)
    → SkillsMiddleware: 加载 hat-test-planner skill
    → Tool: get_endpoint_details (查询端点)
    → Tool: save_test_script (保存 YAML 到 MinIO)
    → Tool: run_tests (pytest TestRunner.py)
    → Tool: parse_test_results (解析 Allure)
    → Agent 返回测试报告
  → UI 展示报告
```

#### 日志诊断流程

```
测试执行失败 → DiagnosisReport 创建
  → 触发诊断 Agent (log_analysis_agent)
    → Tool: query_test_logs (MongoDB)
    → Tool: get_log_detail (MongoDB)
    → Rule Engine: config/failure_rules.yaml 匹配
    → KG Integration: 定位失败代码位置
    → LLM Analysis: 根因分类 + 修复建议
    → Tool: save_diagnosis_report (PG + MongoDB)
    → WebSocket: notify_frontend (实时推送)
  → 前端弹出诊断 Toast → 用户查看报告
```

#### 全栈代码分析流程

```
用户: "分析这个项目的代码"
  → UI → POST /api/v2/.../code-analysis/analyze
  → FastAPI → AnalyzeService
    → Clone repo → 扫描文件
    → KG Pipeline (12 阶段)
    → 持久化到 PostgreSQL (kg_nodes, kg_relationships)
    → 返回分析统计
  → 用户通过 CodeAgent 提问代码相关问题
    → LangGraph API → code_analysis_agent
    → Tool: kg_search_code / kg_impact_analysis
    → 引用代码位置 [[file:line]]
```

#### 场景编排测试流程

```
用户: "编排登录→下单→支付场景"
  → UI → 创建 Scenario (多个步骤)
  → 每个步骤关联 API Endpoint + 数据映射
  → 执行 → ScenarioExecutionEngine
    → 初始化 ExecutionContext
    → 顺序执行每个步骤:
      - HTTP 请求 (httpx)
      - 提取响应数据 (JSONPath)
      - 变量传递 (step_output → next_step_input)
      - 数据依赖解析
    → 记录结果 (ScenarioRun, ScenarioStepResult)
  → UI 展示执行报告
```

---

## 12. 核心工作流详解

### 12.1 用例管理生命周期

```
创建项目
  → 创建文件夹层级
  → 创建测试用例 (title + steps + tags)
  → 关联附件 (MinIO)
  → 加入测试计划
  → 执行测试 (手动/AI)
  → 记录结果
  → 失败触发诊断
```

### 12.2 OpenAPI 导入流程

```
用户提供 URL/文件
  → OpenAPIParser 解析
  → 按 Tag 创建文件夹
  → 每个端点创建子文件夹
  → 存储端点定义 (method, path, params, response)
  → 前端展示端点树
  → AI 可查看端点并生成测试
```

### 12.3 Agent Skills 加载流程

```
Agent 收到用户请求
  → LLM 决定需要哪些 Skills
  → SkillsMiddleware 从 FilesystemBackend 加载 SKILL.md
  → 将 Skill 内容注入 System Prompt
  → Agent 根据 Skill 指导执行工具
  → 完成后释放 Skill 上下文 (节约 token)
```

---

## 13. 关键设计决策

### 13.1 为什么用 deepagents 而非纯 LangGraph？

- deepagents `create_deep_agent()` 封装了 Agent 的创建、Skills 管理、工具注册
- LangGraph CLI 仅用于托管 API 服务（端口 2026），实际工作流由 deepagents 编排
- SkillsMiddleware 提供了按需加载能力，显著节省 token

### 13.2 为什么 KG 分析的是被测项目而非平台自身？

- 平台的目的是测试外部项目
- KG 帮助 Agent 理解被测项目的代码结构，从而生成更精准的测试
- 平台自身的代码结构相对固定，无需实时分析

### 13.3 为什么使用双数据库 (PG + MongoDB)？

- PostgreSQL: 结构化业务数据（项目、用例、结果），需要事务和关联查询
- MongoDB: 日志、大文本、诊断报告详细内容，需要灵活的 Schema 和高效写入
- 知识图谱: PostgreSQL JSONB 存储，兼顾结构化查询和灵活性

### 13.4 为什么使用 YAML 定义测试而非代码？

- 关键字驱动降低测试创建门槛（非开发人员可参与）
- 结构化格式有利于 AI 生成和解析
- 支持 DDT (数据驱动测试) 原生模式
- 与 Allure 深度集成

### 13.5 跨平台路径策略

- Linux 开发环境: 相对路径 `backend/workspace/xxx`
- Windows 开发环境: 自动回退到用户目录 `~/workspace/backend/workspace/xxx`
- 通过 `WORKSPACE_BASE` 环境变量统一覆盖

---

## 14. 附录: 项目管理与扩展指南

### 14.1 新增一个业务实体

1. **Model** — 在 `backend/app/models/` 新增，继承 `Base + UUIDMixin + TimestampMixin`
2. **Schema** — 在 `backend/app/schemas/` 新增请求/响应 Pydantic 模型
3. **Service** — 在 `backend/app/services/` 新增业务逻辑
4. **Router** — 在 `backend/app/api/v2/` 新增路由文件
5. **注册** — 在 `app/api/__init__.py` 注册路由
6. **前端组件** — 在 `ui/components/` 新增 React 组件
7. **前端 API** — 在 `ui/lib/api/` 新增 API 调用
8. **页面** — 在 `ui/app/projects/[projectId]/` 新增页面路由

### 14.2 新增一个 AI Agent

1. 在 `backend/app/agents/` 下创建子目录
2. 实现 `agent.py` (deepagents agent)
3. 定义 Tools (`tools/`)
4. 定义 Skills (`agent_skills/`)
5. 在 `graph.json` 中注册
6. 在 `start_server.py` 中（如需自动加载）

### 14.3 新增一个 KG 阶段

1. 在 `backend/app/kg/phases/` 新增阶段文件
2. 实现 `PhaseHandler` 签名: `(output, repo_path, on_progress)`
3. 在 `pipeline.py` 的 `BUILTIN_PHASES` 列表中添加

### 14.4 数据迁移

- KG 表: `make kg-migrate`（自动建表）
- 业务表: FastAPI 启动时 `Base.metadata.create_all`（debug 模式）
- 字段变更: 手动编写迁移脚本，放在 `backend/app/migrations/`

---

> 本文档是对 ai-test-agent-system-platform 项目的完整技术分析。
> 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
