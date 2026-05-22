# GitNexus 重写方案：代码知识图谱引擎

## 概述

将 GitNexus（TypeScript，~100K 行）的核心功能**重写为 Python 代码**，完全贴合现有测试管理平台（FastAPI + Next.js）架构。

### 目标

- 用户关联被测项目（Git URL / 本地路径）
- 分析被测项目代码，构建**知识图谱**
- AI Agent 通过 MCP 工具查询代码结构、调用链、变动影响
- 前端可视化图谱

---

## 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    你的测试管理平台                            │
│                                                             │
│  ┌─────────────────┐  ┌───────────────────┐                 │
│  │   Next.js 前端    │  │  FastAPI 后端       │                 │
│  │  (端口 3000)     │  │  (端口 8000)        │                 │
│  │                  │  │                    │                 │
│  │  代码分析页面 ────────→ 代码分析 API        │                 │
│  │  知识图谱可视化   │  │  图谱查询 API        │                 │
│  │  搜索界面        │  │  搜索 API           │                 │
│  └─────────────────┘  └────────┬───────────┘                 │
│                                │                             │
│               ┌────────────────▼───────────────┐             │
│               │        Python 重写核心            │             │
│               │    (backend/app/kg/*)            │             │
│               │                                  │             │
│               │ ┌──────────────────────────────┐ │             │
│               │ │ Phase 1: 文件扫描            │ │             │
│               │ │ (FilesystemWalker)           │ │             │
│               │ └──────────┬───────────────────┘ │             │
│               │ ┌──────────▼───────────────────┐ │             │
│               │ │ Phase 2: 结构分析            │ │             │
│               │ │ (StructureBuilder)           │ │             │
│               │ └──────────┬───────────────────┘ │             │
│               │ ┌──────────▼───────────────────┐ │             │
│               │ │ Phase 3: 符号提取            │ │             │
│               │ │ (SymbolExtractor)            │ │             │
│               │ │ - Python ast                 │ │             │
│               │ │ - regex 扫描                 │ │             │
│               │ └──────────┬───────────────────┘ │             │
│               │ ┌──────────▼───────────────────┐ │             │
│               │ │ Phase 4: 关系构建            │ │             │
│               │ │ (RelationshipBuilder)        │ │             │
│               │ │ - import/call/heritage       │ │             │
│               │ └──────────┬───────────────────┘ │             │
│               │ ┌──────────▼───────────────────┐ │             │
│               │ │ Phase 5: 写入 PostgreSQL     │ │             │
│               │ │ (GraphPersistence)           │ │             │
│               │ └──────────────────────────────┘ │             │
│               │                                  │             │
│               │ ┌──────────────────────────────┐ │             │
│               │ │ Search (BM25 + pg FTS)       │ │             │
│               │ │ Impact Analysis              │ │             │
│               │ │ MCP Tools for Agent          │ │             │
│               │ └──────────────────────────────┘ │             │
│               └──────────────────────────────────┘             │
│                                │                             │
│               ┌────────────────▼───────────────┐             │
│               │      PostgreSQL 数据库           │             │
│               │  (现有) + 代码图谱表              │             │
│               └────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

---

## 文件结构（在 backend/app/ 下新增）

```
backend/app/kg/                          # Knowledge Graph 核心
├── __init__.py
├── types.py                            # 知识图谱数据类型（从 GitNexus graph/types 改写）
├── graph.py                            # 内存图结构（从 GitNexus graph/graph.ts 改写）
├── pipeline.py                         # DAG 管道编排器（从 GitNexus pipeline.ts 改写）
├── phases/
│   ├── __init__.py
│   ├── scan.py                        # 文件扫描（从 filesystem-walker.ts）
│   ├── structure.py                   # 文件/目录结构构建（从 structure-processor.ts）
│   ├── symbol_extractor.py            # 符号提取（从 parsing-processor.ts → Python ast 替代）
│   ├── import_processor.py            # import 关系提取（从 import-processor.ts）
│   ├── heritage_processor.py          # 继承关系提取（从 heritage-processor.ts）
│   ├── call_processor.py              # 函数调用分析（从 call-processor.ts，简化版）
│   ├── route_extractor.py             # API 路由提取（从 routes.ts）
│   └── process_extractor.py           # 执行流提取（从 process-processor.ts，简化版）
├── persistence.py                      # PostgreSQL 持久化（替代 LadybugDB）
├── search/
│   ├── __init__.py
│   ├── bm25_index.py                  # BM25 索引（从 bm25-index.ts 改写）
│   ├── fts_search.py                  # PostgreSQL FTS 搜索
│   └── hybrid_search.py              # RRF 混合搜索（从 hybrid-search.ts 改写）
├── mcp/
│   ├── __init__.py
│   ├── server.py                      # MCP 工具注册
│   └── tools.py                       # MCP 工具实现（query, context, impact 等）
└── migration.py                       # 数据库迁移脚本

backend/app/api/v2/code_analysis.py     # 新增 API 路由
backend/app/schemas/code_analysis.py    # 新增 Pydantic 模型
backend/app/services/analyze_service.py # 分析业务逻辑

ui/app/projects/[projectId]/code-analysis/
├── page.tsx                           # 代码分析配置页
├── graph-view.tsx                     # 图谱可视化
└── search-view.tsx                    # 代码搜索页
```

---

## 第一阶段：核心图结构 + 扫描

### 可复制代码：`graph/types.ts` + `graph/graph.ts`

GitNexus 的 `KnowledgeGraph` 是纯内存数据结构，语言无关，直接重写成 Python。

```python
# backend/app/kg/types.py
@dataclass
class GraphNode:
    id: str                 # 唯一标识
    type: str               # NodeLabel: "file", "folder", "class", "function", ...
    name: str
    file_path: str
    start_line: int
    end_line: int
    properties: dict

@dataclass
class GraphRelationship:
    id: str
    source_id: str
    target_id: str
    type: str               # "CONTAINS", "IMPORTS", "CALLS", "EXTENDS", ...
    properties: dict

class KnowledgeGraph:
    """从 GitNexus graph.ts 改写"""
    _nodes: dict[str, GraphNode]
    _relationships: dict[str, GraphRelationship]
    _rels_by_type: dict[str, dict[str, GraphRelationship]]
    _rels_by_node: dict[str, set[str]]
```

### 文件扫描：`filesystem-walker.ts` → Python

```python
# backend/app/kg/phases/scan.py
class FilesystemWalker:
    """从 GitNexus filesystem-walker.ts 改写
    
    扫描文件树，计算文件大小，跳过 .gitignore 匹配的文件
    """
    def walk(self, repo_path: str) -> list[ScanResult]:
        ...
```

---

## 第二阶段：符号提取

### 关键决策：用 Python `ast` 替代 Tree-sitter

GitNexus 用 Tree-sitter（C 解析库，Node.js 绑定）解析 20+ 语言。在 Python 中，我们无法直接复用 Tree-sitter WASM 或原生库。

**策略：**
- **Python 文件**：用标准库 `ast` → 100% 准确，免费
- **JavaScript/TypeScript**：用正则 + 简单解析器（类/函数/import 提取），或使用 `esprima-python` / `py-tree-sitter`（可选安装）
- **其他语言**：用正则提取基本符号

```python
# backend/app/kg/phases/symbol_extractor.py
class PythonSymbolExtractor:
    """用 Python ast 提取符号（函数、类、变量、import）"""
    def extract(self, file_path: str, source: str) -> list[Symbol]:
        tree = ast.parse(source)
        ...

class JSSymbolExtractor:
    """用正则提取 JS/TS 基本符号"""
    def extract(self, file_path: str, source: str) -> list[Symbol]:
        # 正则匹配: class / function / import / export
        ...
```

### Import 关系：`import-processor.ts` 改写

```python
class ImportProcessor:
    """分析文件间的 import/require 依赖"""
    def resolve_imports(self, symbols: list[Symbol]) -> list[GraphRelationship]:
        # Python: from x import y → IMPORTS 边
        # JS: import {x} from 'y' → IMPORTS 边
        ...
```

---

## 第三阶段：持久化（替代 LadybugDB）

### PostgreSQL 图谱表

GitNexus 用 LadybugDB（KuzuDB 嵌入式图数据库）。我们在 PostgreSQL 中建表替代：

```sql
-- 节点表
CREATE TABLE kg_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_path TEXT NOT NULL,           -- 本项目代码路径
    node_id TEXT NOT NULL,             -- 图中唯一 ID (如 "file://src/main.py")
    type TEXT NOT NULL,                -- file/folder/class/function/route/...
    name TEXT NOT NULL,
    file_path TEXT,
    start_line INT,
    end_line INT,
    properties JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(repo_path, node_id)
);

-- 关系表
CREATE TABLE kg_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_path TEXT NOT NULL,
    rel_id TEXT NOT NULL,              -- 图中唯一 ID
    type TEXT NOT NULL,                -- CONTAINS/IMPORTS/CALLS/EXTENDS/...
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    properties JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(repo_path, rel_id)
);

-- 全文搜索索引（PostgreSQL FTS）
CREATE INDEX kg_nodes_fts_idx ON kg_nodes
    USING GIN(to_tsvector('english', name || ' ' || COALESCE(properties->>'doc', '')));

CREATE INDEX kg_rels_type_idx ON kg_relationships(repo_path, type);
CREATE INDEX kg_nodes_type_idx ON kg_nodes(repo_path, type);
```

### 持久化类（从 `lbug-adapter.ts` 改写）

```python
class GraphPersistence:
    """将 KnowledgeGraph 存入 PostgreSQL"""
    
    async def save_graph(self, repo_path: str, graph: KnowledgeGraph):
        """批量写入节点和关系"""
        async with async_session_factory() as session:
            # 先清空该 repo 的旧数据
            await session.execute(
                delete(KGNode).where(KGNode.repo_path == repo_path)
            )
            await session.execute(
                delete(KGRelationship).where(KGRelationship.repo_path == repo_path)
            )
            # 批量写入新数据
            for node in graph.iter_nodes():
                session.add(KGNode(repo_path=repo_path, ...))
            for rel in graph.iter_relationships():
                session.add(KGRelationship(repo_path=repo_path, ...))
            await session.commit()
    
    async def query_context(self, repo_path: str, symbol: str) -> dict:
        """查询符号上下文（调用者、被调用者）"""
        ...
```

---

## 第四阶段：搜索

### BM25: `bm25-index.ts` 改写

BM25 算法是纯数学公式，可直接在 Python 中实现：

```python
class BM25Index:
    """从 GitNexus bm25-index.ts 改写"""
    def __init__(self, documents: list[str]):
        self.documents = documents
        self.avgdl = sum(len(d.split()) for d in documents) / len(documents)
        self.k1 = 1.5
        self.b = 0.75
    
    def score(self, query: str, doc_index: int) -> float:
        """BM25 评分公式"""
        ...
```

### RRF 混合搜索: `hybrid-search.ts` 改写

```python
class HybridSearch:
    """RRF 混合搜索，从 hybrid-search.ts 改写"""
    RRF_K = 60
    
    def merge(self, bm25_results, semantic_results) -> list:
        merged = {}
        for rank, r in enumerate(bm25_results):
            merged[r.filePath] = {
                "score": 1 / (self.RRF_K + rank + 1),
                "sources": ["bm25"]
            }
        for rank, r in enumerate(semantic_results):
            score = 1 / (self.RRF_K + rank + 1)
            if r.filePath in merged:
                merged[r.filePath]["score"] += score
                merged[r.filePath]["sources"].append("semantic")
            else:
                merged[r.filePath] = {"score": score, "sources": ["semantic"]}
        return sorted(merged.items(), key=lambda x: -x[1]["score"])[:limit]
```

---

## 第五阶段：MCP 工具

### MCP 工具注册（集成 deepagents 框架）

GitNexus 的 MCP 工具（`tools.ts`）在 Python 中重写，作为 deepagents Skills：

```python
# backend/app/kg/mcp/tools.py
from deep_agents.skills import Skill

class KGSymbolQuerySkill(Skill):
    """查询代码符号 / 搜索"""
    name = "kg_query"
    description = "搜索代码知识图谱，查找符号定义"
    
    async def execute(self, query: str, repo_path: str = None, top_k: int = 10) -> dict:
        ...

class KGContextSkill(Skill):
    """符号上下文：调用者 + 被调用者"""
    name = "kg_context"
    description = "获取符号的调用关系上下文"
    
    async def execute(self, symbol: str, repo_path: str = None) -> dict:
        ...

class KGImpactSkill(Skill):
    """影响分析：修改某符号会影响哪些代码"""
    name = "kg_impact"
    description = "分析修改某符号的影响范围"
    
    async def execute(self, symbol: str, direction: str = "upstream") -> dict:
        ...
```

---

## 与现有代码的整合点

### 1. 替换 `code_repo_service.py` 中的 GitNexus 子进程调用

当前 `code_repo_service.py` 的 `_run_analysis` 调外部 `gitnexus` CLI：

```python
# 当前（使用 GitNexus 子进程）
[GITNEXUS_BIN, "analyze", repo_path]

# 重写后（直接调用 Python 管道）
from app.kg.pipeline import run_pipeline_from_repo
from app.kg.persistence import GraphPersistence

kg = await run_pipeline_from_repo(repo_path, on_progress)
await GraphPersistence(session).save_graph(repo_path, kg)
```

### 2. 前端侧边栏"全栈分析"已存在

侧边栏已有 `全栈分析 → /fullstack-analysis` 导航项，指向 `/projects/{id}/fullstack-analysis`。在此基础上深化页面内容，替换 iframe 为原生 Next.js 组件。

### 3. API 路由已存在

`api/v2/code_repo.py` 已有 `/projects/{id}/code-repo/*` 路由，只需在 Service 层替换实现。

---

## 实施路线图

| 阶段 | 内容 | 工作量 |
|------|------|--------|
| **P1** | KnowledgeGraph 数据结构 + 文件扫描 + 结构构建 | 渐进 |
| **P2** | Python ast 符号提取 + import 关系 | 渐进 |
| **P3** | PostgreSQL 持久化 | 渐进 |
| **P4** | 替换 code_repo_service.py 中的子进程调用 | 渐进 |
| **P5** | BM25 搜索 + 混合搜索 | 渐进 |
| **P6** | MCP 工具集成（query, context, impact） | 渐进 |
| **P7** | 前端图谱可视化页面 | 渐进 |

> 可以增量交付，每个阶段都可用，逐步替换外部 GitNexus 依赖。
