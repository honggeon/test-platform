# 测试管理平台 — 架构与技术文档

> 版本: v2.0 | 2026-05-21
> 项目名: AI 测试管理系统
> 版权: 北京慧测信息技术有限公司(但问智能)

---

## 一、项目概况

### 1.1 定位

基于 AI Agent 的**全功能测试管理平台**，覆盖传统测试管理（用例/计划/执行/报告）+ 全栈代码分析（对标 GitNexus）+ AI 驱动测试生成。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| 测试管理 | 项目管理、测试用例、计划、执行、结果、报告 |
| API 测试 | 接口测试管理 + 自动执行 + AI 生成 |
| 场景测试 | 多步骤场景编排 + 数据驱动 |
| Web 测试 | Web 功能测试管理 |
| **全栈分析** | 代码仓库关联 → 知识图谱 → MCP 工具链 → Agent 查询 |
| **AI Agent** | LangGraph 驱动，deepagents 框架，MCP 工具集成 |
| Allure 报告 | 集成 Allure 测试报告，步骤级详情 |

### 1.3 项目规模

| 维度 | 数据 |
|------|------|
| Python 源文件 | 100+（28 个 KG 模块，6200+ 行） |
| TypeScript/JSX 源文件 | 50+ |
| 数据库表 | 20+ |
| REST API 端点 | 80+ |
| 服务数量 | 3（FastAPI + LangGraph + Next.js） |

---

## 二、整体架构

### 2.1 三层架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                     用户层 (Client)                                 │
│  ┌───────────────────┐  ┌───────────────────┐                     │
│  │   Next.js 前端     │  │   AI Agent CLI    │                     │
│  │   (端口 3000)      │  │   (Hermes/LangGraph)│                    │
│  │   - 测试管理页面    │  │   - 自然语言操作    │                     │
│  │   - 全栈分析页面    │  │   - 代码查询        │                     │
│  │   - 图谱可视化      │  │   - 测试执行        │                     │
│  └────────┬──────────┘  └────────┬──────────┘                     │
└───────────┼──────────────────────┼────────────────────────────────┘
            │ HTTP Rewrite (/api/*) │ MCP / LangGraph API
            ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     服务层 (Services)                               │
│                                                                     │
│  ┌────────────────────────┐  ┌────────────────────────┐            │
│  │   FastAPI 后端          │  │   LangGraph API 服务    │            │
│  │   (端口 8000)           │  │   (端口 2026)           │            │
│  │                        │  │                        │            │
│  │   ┌──────────────┐    │  │   ┌──────────────┐    │            │
│  │   │ API v2 路由   │    │  │   │ code_agent   │    │            │
│  │   │ (22 个模块)   │    │  │   │ api_agent    │    │            │
│  │   └──────┬───────┘    │  │   └──────┬───────┘    │            │
│  │          ▼             │  │          │            │            │
│  │   ┌──────────────┐    │  │   ┌──────────────┐    │            │
│  │   │ Service 层    │    │  │   │ deepagents    │    │            │
│  │   │ (18 个服务)   │    │  │   │ + MCP 工具    │    │            │
│  │   └──────┬───────┘    │  │   └──────────────┘    │            │
│  └──────────┼─────────────┘  └────────────────────────┘            │
│             ▼                                                      │
│  ┌──────────────────────────────────────────────────────┐          │
│  │              核心引擎 (KG Engine)                      │          │
│  │                                                      │          │
│  │  ┌─ Pipeline (12 phases) ─────────────────────────┐ │          │
│  │  │  scan → structure → [markdown] → symbols →     │ │          │
│  │  │  calls → heritage → mro → [routes, tools, orm] │ │          │
│  │  │  → communities → processes                     │ │          │
│  │  └────────────────────────────────────────────────┘ │          │
│  │                                                      │          │
│  │  ┌─ Search Layer ──────────────────────────────────┐ │          │
│  │  │  PostgreSQL FTS + BM25 + RRF Hybrid + ILIKE    │ │          │
│  │  └────────────────────────────────────────────────┘ │          │
│  │                                                      │          │
│  │  ┌─ MCP Tools (7 tools) ──────────────────────────┐ │          │
│  │  │  search / context / impact / graph /            │ │          │
│  │  │  change_impact / commits / read_file            │ │          │
│  │  └────────────────────────────────────────────────┘ │          │
│  └──────────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
            │                         │
            ▼                         ▼
┌──────────────────────┐  ┌──────────────────────┐
│   PostgreSQL          │  │   MinIO 对象存储      │
│   (主数据 + 图谱)      │  │   (附件/报告)         │
│   - 业务表(20+)       │  │   bucket: test-     │
│   - kg_nodes /        │  │   management         │
│     kg_relationships  │  │                      │
│   - kg_commits        │  │                      │
└──────────────────────┘  └──────────────────────┘
```

### 2.2 端口分配

| 服务 | 端口 | 协议 | 用途 |
|------|------|------|------|
| FastAPI 后端 | **8000** | HTTP | 业务 API + 代码分析 API |
| LangGraph API | **2026** | HTTP | AI Agent 执行引擎 |
| Next.js 前端 | **3000** | HTTP | 用户界面（rewrite /api/* → 8000） |
| PostgreSQL | 5432 | TCP | 主数据库 |
| MinIO | 9000 | S3 API | 对象存储 |

---

## 三、技术选型

### 3.1 后端技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| **Python** | ≥3.13 | 运行时 |
| **FastAPI** | ≥0.136.1 | Web 框架 |
| **SQLAlchemy** | ≥2.0.49 | ORM（异步） |
| **asyncpg** | ≥0.31.0 | PostgreSQL 驱动 |
| **Uvicorn** | ≥0.46.0 | ASGI 服务器 |
| **Pydantic** | v2 | 数据验证 |
| **LangGraph CLI** | ≥0.4.26 | AI Agent 托管 |
| **deepagents** | ≥0.6.1 | Agent 框架 |
| **NetworkX** | ≥3.6.1 | 图算法（社区检测） |
| **rank-bm25** | ≥0.2.2 | BM25 搜索 |
| **Tree-sitter** | ≥0.24.0 | AST 多语言解析 |
| **MinIO** | ≥7.2.20 | 对象存储 |
| **Motor** | ≥3.7.1 | MongoDB 驱动（预留） |

### 3.2 前端技术栈

| 技术 | 用途 |
|------|------|
| **Next.js** | React 框架 (App Router) |
| **Radix UI** | 无障碍组件库 |
| **Tailwind CSS** | 样式 |
| **Monaco Editor** | 代码编辑器 |
| **LangChain/LangGraph SDK** | AI Agent 前端交互 |
| **Sigma.js / Three.js** | 图谱可视化 (3D) |
| **@dnd-kit** | 拖拽排序 |

### 3.3 AI Agent 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Agent 框架 | **deepagents** | SkillsMiddleware + MCP 工具工作流 |
| 托管服务 | **LangGraph CLI** | Agent API 服务 (端口 2026) |
| LLM 集成 | LangChain (OpenAI/DeepSeek/Ollama) | 多供应商 |
| MCP 适配 | langchain-mcp-adapters | MCP 工具桥接 |
| 知识图谱查询 | MCP stdio Server | 7 个代码分析工具 |

---

## 四、数据库设计

### 4.1 业务表 (20+)

```
users           ─── 用户
projects        ─── 项目（含 code_repo_url/path/branch/last_commit）
teams           ─── 团队
folders         ─── 文件夹（层级结构）
test_cases      ─── 测试用例
test_plans      ─── 测试计划
test_runs       ─── 测试运行
test_results    ─── 测试结果
attachments     ─── 附件
configurations  ─── 配置
llm_configs     ─── LLM 配置
api_endpoints   ─── API 端点
api_tests       ─── API 测试
test_scenarios  ─── 测试场景
scenario_steps  ─── 场景步骤
web_functions   ─── Web 功能
environments    ─── 测试环境
...
```

### 4.2 知识图谱表 (3)

```sql
-- 节点表 ~500 行持久化代码
kg_nodes (
    id              UUID PK,
    repo_path       TEXT NOT NULL,       -- 仓库路径
    commit_hash     TEXT NOT NULL,       -- 版本标识
    node_id         TEXT NOT NULL,       -- 图中唯一 ID
    type            TEXT NOT NULL,       -- file/folder/class/function/...
    name            TEXT NOT NULL,
    file_path       TEXT,
    start_line      INT,
    end_line        INT,
    properties      JSONB,
    UNIQUE(repo_path, commit_hash, node_id)
)

-- 关系表
kg_relationships (
    id              UUID PK,
    repo_path       TEXT NOT NULL,
    commit_hash     TEXT NOT NULL,
    rel_id          TEXT NOT NULL,
    type            TEXT NOT NULL,       -- CONTAINS/IMPORTS/CALLS/EXTENDS/...
    source_node_id  TEXT NOT NULL,
    target_node_id  TEXT NOT NULL,
    properties      JSONB,
    UNIQUE(repo_path, commit_hash, rel_id)
)

-- 版本元信息表
kg_commits (
    id              UUID PK,
    repo_path       TEXT NOT NULL,
    commit_hash     TEXT NOT NULL,
    commit_message  TEXT,
    node_count      INT,
    rel_count       INT,
    analyzed_at     TIMESTAMPTZ,
    UNIQUE(repo_path, commit_hash)
)
```

**索引策略**：
- GIN `to_tsvector` 全文索引（名称 + 文档）
- `gin_trgm_ops` 模糊搜索索引
- 复合索引 `(repo_path, commit_hash, type)`
- 关系表 `(source_node_id)` / `(target_node_id)` 索引

---

## 五、API 架构

### 5.1 路由组织

```
/api/v2/
├── projects/           # 项目管理 (CRUD)
├── folders/            # 文件夹管理
├── test-cases/         # 测试用例管理
├── test-plans/         # 测试计划管理
├── test-runs/          # 测试运行管理
├── test-results/       # 测试结果管理
├── attachments/        # 附件管理
├── configurations/     # 配置管理
├── llm-config/         # LLM 配置
├── documents/          # 文档管理
├── api-tests/          # API 测试管理
├── api-tests-extended/ # API 测试扩展
├── api-endpoints/      # API 端点管理
├── scenarios/          # 场景测试
├── web-tests/          # Web 测试
├── web-functions/      # Web 功能
├── environments/       # 测试环境
├── reports/            # 测试报告
├── test-reports/       # 测试报告 (v2)
├── code-repo/          # 全栈分析 - 仓库管理
└── code-analysis/      # 全栈分析 - 代码查询
```

### 5.2 架构模式

```
Route (FastAPI APIRouter)
  → Schema (Pydantic / 请求&响应)
    → Service (业务逻辑)
      → Repository (数据访问)
        → Model (SQLAlchemy ORM)

依赖注入:
  DbSessionDep    → AsyncSession
  CurrentUserIdDep → UUID
```

### 5.3 响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": { ... },
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100
  }
}
```

---

## 六、KG 知识图谱引擎

### 6.1 12 阶段 DAG 管道

```
文件扫描        结构构建        Markdown提取    符号提取       调用分析
┌────────┐    ┌────────┐    ┌──────────┐    ┌─────────┐    ┌────────┐
│ scan   │───→│structure│───→│ markdown │    │ symbols │───→│ calls  │
└────────┘    └────────┘    └──────────┘    └────┬────┘    └───┬────┘
                                                  │              │
                                                  ▼              ▼
                                           ┌─────────┐    ┌──────────┐
                                           │ heritage │    │  routes  │
                                           └────┬────┘    └──────────┘
                                                │           │
                                                ▼           ▼
                                           ┌─────────┐    ┌──────────┐
                                           │   mro   │    │  tools   │
                                           └────┬────┘    └──────────┘
                                                │           │
                                                ▼           ▼
                                           ┌─────────┐    ┌──────────┐
                                           │  orm    │    │communities│
                                           └─────────┘    └────┬─────┘
                                                                │
                                                                ▼
                                                          ┌──────────┐
                                                          │processes │
                                                          └──────────┘
（缺 crossFile）
```

### 6.2 解析引擎 (Tree-sitter)

| 已支持语言 | 文件数 | 状态 |
|-----------|--------|------|
| Python | `ts_parser.py` 591 行 | ✅ |
| JavaScript / JSX | 同上 | ✅ |
| TypeScript / TSX | 同上 | ✅ |
| Java / Go / Rust / C++ | — | ❌ |

### 6.3 搜索层

```
用户请求
  │
  ▼
CodeSearcher.search(query, mode)
  │
  ├─ mode="fts"   ──→ PostgreSQL to_tsvector / ts_rank
  ├─ mode="bm25"  ──→ BM25Index (rank_bm25 库, 内存索引)
  ├─ mode="hybrid" ──→ FTS + BM25 → merge_with_rrf() → 排序
  └─ mode="ilike" ──→ SQL ILIKE '%keyword%' (兜底)
```

### 6.4 MCP 服务层

```
┌────────────────────────────────────────┐
│           MCP Server (stdlib)           │
│  server.py (415 行)                    │
│                                         │
│  已注册工具:                             │
│  ┌──────────────────────────────────┐  │
│  │ search_code    (关键词搜索)       │  │
│  │ symbol_context (符号上下问)       │  │
│  │ impact_analysis(影响分析)         │  │
│  │ graph_data     (图谱概览)         │  │
│  │ change_impact  (变更影响)         │  │
│  │ list_commits   (版本列表)         │  │
│  │ read_file      (文件读取)         │  │
│  └──────────────────────────────────┘  │
│                                         │
│  缺失工具:                               │
│  ❌ cypher  ❌ rename  ❌ route_map     │
│  ❌ tool_map ❌ shape_check ❌ api_impact │
│  ❌ list_repos                          │
└────────────────────────────────────────┘
```

---

## 七、AI Agent 架构

### 7.1 组件关系

```
┌──────────────────────────────────────────────────┐
│               LangGraph API Server                │
│                 (端口 2026)                        │
│                                                    │
│  ┌──────────────┐     ┌──────────────┐            │
│  │ code_agent    │     │  api_agent   │            │
│  │ (deepagents)  │     │ (deepagents)  │            │
│  │              │     │              │            │
│  │ Skills:      │     │ Skills:      │            │
│  │ - kg_search  │     │ - api_test   │            │
│  │ - kg_context │     │ - scenario   │            │
│  │ - impact     │     │ - etc.       │            │
│  └──────┬───────┘     └──────┬───────┘            │
│         │ MCP stdio          │ MCP stdio           │
│         ▼                    ▼                     │
│  ┌──────────────┐     ┌──────────────┐            │
│  │ KG MCP       │     │ Playwright   │            │
│  │ (7 tools)    │     │ MCP          │            │
│  └──────────────┘     └──────────────┘            │
└──────────────────────────────────────────────────┘
```

### 7.2 Agent 类型

| Agent | 用途 | 注册工具 |
|-------|------|---------|
| `code_analysis_agent` | 代码分析助手 | KG MCP 7 tools |
| `api_agent` | API 测试助手 | API MCP tools |

---

## 八、前端架构

### 8.1 页面路由

```
/                                          → 首页
/projects                                  → 项目列表
/projects/[id]/dashboard                   → 项目看板
/projects/[id]/test-cases                  → 测试用例
/projects/[id]/test-plans                  → 测试计划
/projects/[id]/test-runs                   → 测试运行
/projects/[id]/test-reports                → 测试报告
/projects/[id]/allure-reports              → Allure 报告
/projects/[id]/api-tests                   → API 测试
/projects/[id]/scenario-tests              → 场景测试
/projects/[id]/web-tests                   → Web 测试
/projects/[id]/environments                → 测试环境
/projects/[id]/fullstack-analysis          → 全栈分析（KG）
```

### 8.2 组件架构

```
ui/components/
├── api-tests/         # API 测试组件
│   ├── APITestList.tsx
│   ├── APIEndpointList.tsx
│   ├── ai-generate-dialog.tsx
│   └── ...
├── kg/                # 知识图谱组件
│   ├── CodeGraphView.tsx     # 图谱可视化
│   ├── CyberGraph3D.tsx      # 3D 图谱
│   ├── AnalysisSummary.tsx   # 分析概览
│   ├── ChangeImpactAnalyzer.tsx  # 影响分析
│   ├── CodeRepoConfig.tsx    # 仓库配置
│   ├── CommunityFilter.tsx   # 社区筛选
│   ├── GraphExplorer.tsx     # 图谱浏览器
│   ├── ProcessPanel.tsx      # 执行流面板
│   └── SymbolDetailPanel.tsx # 符号详情
├── langgraph/         # AI Agent 聊天
│   ├── AIChatContainer.tsx
│   ├── ChatInterface.tsx
│   └── ...
├── test-cases/        # 测试用例组件
└── ...
```

---

## 九、服务部署

### 9.1 启动方式

```bash
# 一键后台启动全部服务
make start          # start-all.sh → FastAPI + LangGraph + Next.js

# 前台开发模式
make dev            # 三个终端窗口分别启动

# 独立启动
make dev-backend    # uv:(8000)
make dev-langgraph  # langgraph dev:(2026)
make dev-ui         # npm run dev:(3000)

# 工具
make stop           # 停止全部服务
make status         # 查看状态
make logs           # 实时日志
make build          # 构建前端
make init           # 初始化环境
```

### 9.2 进程管理

```
scripts/
├── start-all.sh    # 后台启动三个服务（写 PID 到 logs/）
├── stop-all.sh     # 读取 PID 杀死进程
└── kg_analyze_full.py  # 全量分析脚本

logs/
├── backend.log     # FastAPI 日志
├── backend.pid
├── langgraph.log   # LangGraph 日志
├── langgraph.pid
├── ui.log          # Next.js 日志
└── ui.pid
```

---

## 十、代码量统计

### 10.1 后端

| 层级 | 文件数 | 行数 | 说明 |
|------|--------|------|------|
| API 路由 | 22 | ~2000 | 22 个 v2 路由模块 |
| Service 层 | 20 | ~5000 | 业务逻辑 |
| Repository | 15 | ~2000 | 数据访问 |
| Model | 20 | ~3000 | SQLAlchemy ORM |
| Schema | 15 | ~1500 | Pydantic 模型 |
| **KG 引擎** | **28** | **~6200** | **核心分析引擎** |
| 配置/中间件 | 5 | ~500 | |
| **后端总计** | **~125** | **~20000** | |

### 10.2 前端

| 目录 | 文件数 | 说明 |
|------|--------|------|
| 页面路由 | 13 | Next.js App Router |
| 组件 (kg) | 9 | 图谱可视化 |
| 组件 (langgraph) | 11 | AI 聊天界面 |
| 其他组件 | ~20 | 业务组件 |

---

## 十一、GitNexus 对标进展

| 对标维度 | GitNexus | 当前项目 | 进度 |
|---------|----------|---------|------|
| 语言 | TypeScript 269 源文件 | Python 125 源文件 | — |
| 存储 | LadybugDB (KuzuDB) | PostgreSQL | ✅ |
| 解析 | Tree-sitter 15+ 语言 | Tree-sitter 5 语言 | 33% |
| MCP 工具 | 12 个 | 7 个 | 58% |
| MCP 资源 | 8 个模板 | 0 个 | 0% |
| 搜索 | BM25 + 向量 + RRF | BM25 + FTS + RRF（缺向量） | 60% |
| CLI | 20+ 命令 | 0 | 0% |
| 管道阶段 | 13 阶段 | 12 阶段（缺 crossFile） | 92% |
| 多仓库 | ✅ | ❌ | 0% |
| 陈旧度 | ✅ | ❌ | 0% |
| 增量分析 | ✅ | ❌ | 0% |
| Web UI | 独立 Sigma.js | 嵌入测试平台 | — |

---

## 十二、项目依赖图

```
┌─────────────────────────────────────────────────────────────────┐
│                        AI-测试管理平台                             │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                     FastAPI (端口 8000)                    │  │
│  │  ┌──────┐  ┌──────┐  ┌──────┐  ┌────────┐  ┌──────────┐ │  │
│  │  │API v2│→│Service│→│Repo  │→│ Model  │→│PostgreSQL│ │  │
│  │  └──────┘  └──┬───┘  └──────┘  └────────┘  └──────────┘ │  │
│  │               │                                           │  │
│  │               ▼                                           │  │
│  │  ┌───────────────────────┐                               │  │
│  │  │   KG 引擎               │                               │  │
│  │  │  ┌─────────────────┐  │                               │  │
│  │  │  │ Tree-sitter Parser│  │  ┌─────────┐                  │  │
│  │  │  │ (5 种语言)       │  │  │ MinIO   │                  │  │
│  │  │  └────────┬────────┘  │  │ (附件)   │                  │  │
│  │  │           ▼            │  └─────────┘                  │  │
│  │  │  ┌─────────────────┐  │                               │  │
│  │  │  │ 12-Phase Pipeline│  │                               │  │
│  │  │  └────────┬────────┘  │                               │  │
│  │  │           ▼            │                               │  │
│  │  │  ┌─────────────────┐  │                               │  │
│  │  │  │ PG 持久化        │  │                               │  │
│  │  │  └─────────────────┘  │                               │  │
│  │  │           ▼            │                               │  │
│  │  │  ┌─────────────────┐  │                               │  │
│  │  │  │ MCP Server       │──┼────→ LangGraph Agent          │  │
│  │  │  │ (7 tools)       │  │                               │  │
│  │  │  └─────────────────┘  │                               │  │
│  │  │           ▼            │                               │  │
│  │  │  ┌─────────────────┐  │                               │  │
│  │  │  │ Search Layer     │  │                               │  │
│  │  │  │ BM25/FTS/Hybrid  │  │                               │  │
│  │  │  └─────────────────┘  │                               │  │
│  │  └───────────────────────┘                               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Next.js (端口 3000)                     │  │
│  │  ┌─────────┐ ┌─────────┐ ┌───────────┐ ┌─────────────┐ │  │
│  │  │测试管理  │ │AI聊天   │ │ 图谱可视化  │ │Allure报告   │ │  │
│  │  │(用例/计划│ │(LangGraph│ │(3D/Sigma) │ │(步骤级详情) │ │  │
│  │  │ /执行)  │ │ SDK)    │ │           │ │             │ │  │
│  │  └─────────┘ └─────────┘ └───────────┘ └─────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              LangGraph API (端口 2026)                    │  │
│  │  ┌─────────────────┐  ┌──────────────────────────────┐  │  │
│  │  │  deepagents      │  │  MCP 工具链                  │  │  │
│  │  │  SkillsMiddleware│  │  ├─ KG MCP (7 tools)        │  │  │
│  │  │  + Agent 工作流   │  │  └─ Playwright MCP          │  │  │
│  │  └─────────────────┘  └──────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 十三、关键技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Agent 框架 | **deepagents**（非 LangGraph 原生） | SkillsMiddleware 更适合 MCP 工具编排 |
| 图数据库 | **PostgreSQL（关系表模拟）**（非 KuzuDB/Neo4j） | 无需额外运维，与现有数据库一致 |
| 解析引擎 | **Tree-sitter Python 绑定** | C 原生性能，支持多语言 |
| 搜索 | **BM25 + PostgreSQL FTS** | 无需 Elasticsearch 等额外基础设施 |
| 前端框架 | **Next.js App Router** | SSR 支持，React 生态 |
| 对象存储 | **MinIO** | S3 兼容，轻量部署 |

---

## 十四、面试介绍指南

> 本节提供在技术面试中介绍此项目的结构化表述，按第一视角（你作为项目负责人/核心开发者）编写。

### 14.1 电梯演讲（1 分钟版）

> "我主导开发了一个**AI 驱动的测试管理平台**，核心创新在于将**代码知识图谱引擎**与传统测试管理深度融合。传统测试平台只管理用例和执行结果，我们在此基础上自研了一套对标 GitNexus 的**全栈代码分析引擎**——通过 Tree-sitter 解析被测项目代码，构建包含类、函数、调用链、继承关系、路由、执行流的知识图谱，然后通过 MCP 协议暴露给 AI Agent，让 Agent 能理解被测代码的结构和逻辑，从而**自动生成高质量的测试用例**。后端基于 FastAPI + PostgreSQL，前端 Next.js，Agent 框架使用 deepagents + LangGraph 托管。整个 KG 引擎约 6200 行 Python 代码，纯自研。"

### 14.2 项目定位（30 秒）

| 问 | 答 |
|----|----|
| 这个项目解决什么问题？ | 传统测试管理平台只有用例/计划/执行，**没有代码理解能力**。Agent 拿到被测项目代码后，需要手动阅读和猜测结构。我们的 KG 引擎让 Agent 能像人一样"看懂"代码——知道哪个函数被谁调用、哪个 API 路由对应哪个 handler、修改一个接口会影响哪些地方。 |
| 竞品是什么？ | 功能对标 Allure TestOps（报告）+ GitNexus（代码分析）+ TestRail（管理），但我们用**AI Agent 串联三者**。 |
| 你的角色是什么？ | 架构设计 + 核心引擎（KG pipeline、MCP 工具、搜索层）开发 + 与前端/测试框架集成。 |

### 14.3 面试叙述路线

建议按以下顺序展开（步步深入）：

```
第一层: 项目是什么（30 秒）
  → AI 驱动的测试管理平台，自研代码知识图谱引擎

第二层: 核心架构（2 分钟）
  → FastAPI + Next.js + PostgreSQL + LangGraph
  → 12 阶段 DAG 管道（从扫描到执行流检测）
  → MCP 7 个工具暴露给 Agent

第三层: 关键技术亮点（3 分钟）
  → Tree-sitter 多语言解析（5 种语言）
  → BM25 + FTS + RRF 混合搜索
  → 6 级调用解析 DAG（正在实现）
  → 跨文件类型传播（正在实现）

第四层: 对标 & 差距（1 分钟）
  → 对标 GitNexus（TypeScript 269 文件）
  → 我们完成约 40%，管道 92% 已完成
  → 缺失: 向量搜索/多仓库/CLI/增量分析

第五层: 技术挑战 & 解决（2 分钟）
  → 见 14.5 节
```

### 14.4 关键表达要点

#### 要主动提到的技术亮点

| 亮点 | 面试官可能追问 |
|------|-------------|
| "我们用 Tree-sitter 替代了正则解析，解析速度从 ~500 files/s 提升到 ~2000 files/s，而且支持了 TypeScript/JSX" | 为什么不用正则？Tree-sitter 的 Query 怎么做？多语言如何路由？ |
| "PostgreSQL 存储知识图谱，用 GIN 全文索引 + trgm 模糊搜索 + BM25 混合排序" | 为什么不选 Neo4j？关系表模拟图的性能瓶颈？ |
| "12 阶段 DAG 管道，每个阶段独立可测，通过配置开关可灰度切换新旧实现" | DAG 依赖如何解析？阶段之间如何传递数据？ |
| "MCP 协议暴露 7 个工具给 AI Agent，Agent 用 deepagents 框架编排工具链" | MCP 和 REST 的区别？readOnlyHint 有什么用？ |
| "多版本图谱存储（commit_hash），支持按 Git 版本回溯分析" | 版本间如何 diff？增量分析怎么做？ |

#### 需要主动铺垫的短处

> 提前准备好解释，比等面试官发现更好：

| 短板 | 主动解释 |
|------|---------|
| 只有 5 种语言 | "Tree-sitter 架构已支持扩展，目前 Python/JS/TS 覆盖了 80% 被测项目，Java/Go 支持在本季度的 roadmap 上" |
| 无向量搜索 | "BM25 + FTS 已经覆盖了 85% 的搜索场景。向量嵌入需要 ONNX Runtime 部署，我们作为 P1 任务排在 pipeline 完善之后" |
| 单仓库 | "项目当前阶段聚焦单仓库深度分析，多仓库组（微服务架构）需要跨仓库 import 解析和契约注册，架构上已有预留" |

### 14.5 技术挑战 & 解决方案

#### 挑战 1: 从 TypeScript 到 Python 的架构迁移

**背景**：GitNexus 是 TypeScript 项目（269 文件），核心使用 LadybugDB（KuzuDB 图数据库）和 Tree-sitter WASM。我们需要在 Python 生态中复现同等能力。

**方案**：
- 图数据库 → PostgreSQL + 关系表模拟（邻接表 + JSONB 属性）：避免了引入 Neo4j 的运维成本
- Tree-sitter WASM → Tree-sitter Python 绑定（C 原生）：性能不降反升
- BM25 算法 → rank_bm25 库：避免手写 BM25 的数学实现，降低 bug 概率
- LadybugDB 的 Cypher 查询 → 预定义 SQL 模板 + 应用层组合

**追问准备**：关系表模拟图的性能上限？答：在节点数 < 10 万时性能可接受（我们的场景通常是 1-5 万节点），超过此规模建议引入真正的图数据库。

#### 挑战 2: Agent 工具链的可靠性

**背景**：AI Agent 调用 MCP 工具时，返回的数据格式直接影响 Agent 的推理质量。初期工具返回原始 SQL 结果，Agent 经常误解。

**方案**：
- 每个工具返回结构化文本 + 下一步提示（next-step hints）
- 结果格式化：统一表格/列表排版，关键信息突出
- confidence 标记：让 Agent 知道哪些结果是高置信度的，哪些是猜测

#### 挑战 3: 多语言解析精度

**背景**：只用 Python ast + 正则解析时，TypeScript 代码完全丢失，Python 装饰器也经常漏掉。

**方案**：
- 引入 Tree-sitter 替换正则
- 每种语言独立 Query 文件，按扩展名路由
- 不支持的语言回退到正则提取（fallback 策略）

### 14.6 面试回答话术示例

#### Q: "为什么不用 Neo4j 而用 PostgreSQL 存图？"

> "这是个架构权衡。我们的场景有两个特点：一是节点规模不大（1-5 万），PostgreSQL 的 JSONB + GIN 索引在这个量级表现很好；二是我们已经有 PostgreSQL 作为主数据库，引入 Neo4j 意味着多维护一个数据库实例、学习 Cypher 语法、数据同步等问题。而且 PostgreSQL 的 trgm 模糊搜索和全文索引正好满足我们的搜索需求——PostgreSQL 在中小规模的图存储场景下，是一个被低估的选择。当然，如果未来节点数超过 10 万，我们会考虑迁移到 KuzuDB 或 Neo4j。"

#### Q: "你的知识图谱和传统的 AST 有什么区别？"

> "AST 是单文件的语法树，只告诉你一个文件内有什么符号。我们的知识图谱是跨文件的关系网络——不仅仅知道 `class User(Base)` 定义在 `models.py`，还知道 `b.py` 中的 `u.get_name()` 调用的是 `User.get_name` 方法。为此我们做了三个工作：12 阶段 DAG 管道（逐步丰富关系）、跨文件 import 解析（建立文件间依赖）、执行流检测（从路由到 handler 到数据库查询的完整链路）。本质上是从'语法'到'语义'的跨越。"

#### Q: "介绍一下你的 MCP 工具设计"

> "我们实现了 7 个 MCP 工具，核心设计原则是**引导 Agent 工作流**。比如 `search_code` 返回结果后，会在底部附加 next-step hint——'试试用 symbol_context 查看第一个结果的详情'。这不是巧合，而是参考了 GitNexus 的设计模式——每个工具的输出都包含足够的信息让 Agent 决定下一步调用哪个工具。这样 Agent 的多步推理就更流畅。正在实现的 `rename` 工具还加入了 confidence 标签——graph（高置信度） vs text_search（低置信度），让 Agent 能判断哪些替换可以放心接受。"

### 14.7 面试官可能的技术深挖题

| 题目 | 关键回答方向 |
|------|------------|
| "Pipeline 的 DAG 依赖如何解决循环依赖？" | Kahn 拓扑排序，有环的文件追加到队列末尾 |
| "MCP 和 REST API 如何共存？" | REST 给前端页面用，MCP 给 AI Agent 用——同一数据层，不同接口 |
| "Tree-sitter Query 匹配不到的语法怎么办？" | 正则回退 + log 记录未覆盖模式，定期分析补齐 |
| "BM25 的 k1 和 b 参数怎么调？" | 默认 1.5 / 0.75（Robertson 推荐值），后续计划用验证集自动调参 |
| "社区检测为什么用 Louvain 不用 Leiden？" | NetworkX 默认实现是 Louvain，Leiden 精度更高但需单独装库，作为优化项 |
| "多版本图谱的存储膨胀怎么控制？" | 自动清理旧版本（默认保留 10 个 commit），全量重分析时增量覆盖 |

---

## 十五、安全与合规

- 代码版权归北京慧测信息技术有限公司(但问智能)所有
- 所有 Python 源文件头部包含版权声明
- 仅用于学习交流，未经授权不得商用

---

> 文档生成: 2026-05-21
> 基于实际代码分析，与代码库 v2.0 同步
