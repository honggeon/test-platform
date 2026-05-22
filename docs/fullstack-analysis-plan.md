# 全栈分析功能实施计划

> 目标：将 GitNexus 的核心能力完整迁移到当前 Python/FastAPI + Next.js 架构，**不阉割功能**，**分阶段交付**。
>
> 创建时间：2026-05-20

---

## 一、核心原则

1. **不重复造轮子**
   - Tree-sitter Worker Pool → 不复刻，用 Python `ast` + 正则（架构已定）
   - LadybugDB (KuzuDB) → 不复刻，用 PostgreSQL（已有）
   - 社区检测算法 → 不复刻，用 `networkx`（已安装）
   - 前端页面 → 不复刻，在现有 `fullstack-analysis/page.tsx` 上扩展
   - REST API → 不复刻，在现有路由上追加字段/端点

2. **分三批交付**
   - 第一批：Pipeline 完整化（10 阶段分析管道）
   - 第二批：搜索质量升级 + 缺陷修复
   - 第三批：前端体验增强（社区着色、执行流面板等）

3. **持续可运行**
   - 每个批次完成后，分析管道应能端到端运行
   - 新阶段初期可为"骨架/占位"，逐步填充实现

---

## 二、GitNexus 功能全景对照

### Pipeline 阶段（13 个阶段）

| GitNexus 阶段 | 当前状态 | 决策 |
|--------------|---------|------|
| `scan` | ✅ `phases/scan.py` | 保持 |
| `structure` | ✅ `phases/structure.py` | 保持 |
| `markdown` | ❌ 缺失 | **第一批**：提取 Markdown 标题和交叉链接 |
| `cobol` | ❌ 缺失 | **跳过**：除非项目涉及大型机代码 |
| `parse` | ⚠️ 简化版 | 当前 `symbols.py` + `calls.py` 已覆盖核心解析，**不复刻** Worker Pool / Binding Accumulator |
| `routes` | ❌ 缺失 | **第一批**：Next.js / FastAPI / Flask / Django / PHP / 装饰器路由提取 |
| `tools` | ❌ 缺失 | **第一批**：MCP/RPC Tool 定义检测 |
| `orm` | ❌ 缺失 | **第一批**：Prisma / SQLAlchemy / Django ORM 查询提取 |
| `crossFile` | ❌ 缺失 | **跳过**：依赖 Binding Accumulator，在 Python ast 下 ROI 极低 |
| `scopeResolution` | ❌ 缺失 | **跳过**：等同于重写类型系统，当前正则+ast已满足80%场景 |
| `mro` | ❌ 缺失 | **第一批**：C3 线性化 + METHOD_OVERRIDES/IMPLEMENTS |
| `communities` | ❌ 缺失 | **第一批**：Louvain 社区检测（networkx） |
| `processes` | ❌ 缺失 | **第一批**：BFS 执行流检测 + Process 节点 |

### 搜索层

| 功能 | 当前状态 | 决策 |
|------|---------|------|
| PostgreSQL FTS | ✅ `search/__init__.py` | 保持 |
| BM25 评分 | ❌ 缺失 | **第二批**：内存 BM25 索引 |
| 语义搜索 (Embedding) | ❌ 缺失 | **跳过**：当前无 Embedding 基础设施 |
| RRF 混合搜索 | ❌ 缺失 | **第二批**：FTS + BM25 融合 |

### Agent / MCP 层

| 功能 | 当前状态 | 决策 |
|------|---------|------|
| MCP Server | ✅ `kg/mcp/server.py` | 保持 |
| LangChain Tools | ✅ `agents/api/tools/kg_tools.py` | 保持 |
| Graph RAG Agent | ❌ 缺失 | **第三批之后**：独立大功能，需单独批次 |
| 多 LLM 提供商 | ❌ 缺失 | **第三批之后**：同上 |

### 前端层

| 功能 | 当前状态 | 决策 |
|------|---------|------|
| 基础图谱可视化 | ✅ `CodeGraphView.tsx` | 保持 |
| 社区着色 | ❌ 缺失 | **第三批**：按 Community 分组着色 |
| 深度过滤 / 爆炸半径 | ❌ 缺失 | **第三批**：交互式过滤 |
| Process 执行流面板 | ❌ 缺失 | **第三批**：ProcessesPanel |
| AI 聊天面板 | ❌ 缺失 | **跳过**：需配合 Graph RAG Agent |

---

## 三、第一批：Pipeline 完整化

### 3.1 新增文件清单

```
backend/app/kg/phases/
├── heritage_processor.py      # EXTENDS/IMPLEMENTS 提取
├── mro.py                     # C3 线性化 + METHOD_OVERRIDES/IMPLEMENTS
├── route_extractor.py         # 路由提取 + NODE_ROUTE + HANDLES_ROUTE
├── tool_extractor.py          # Tool 定义检测 + NODE_TOOL
├── orm_extractor.py           # ORM 查询提取 + QUERIES 边
├── communities.py             # Louvain 社区检测 + NODE_COMMUNITY + MEMBER_OF
├── process_extractor.py       # BFS 执行流 + NODE_PROCESS + STEP_IN_PROCESS + ENTRY_POINT_OF
└── markdown.py                # Markdown 标题提取（轻量）
```

### 3.2 修改现有文件

```
backend/app/kg/
├── types.py                   # 补充 NODE_ROUTE, NODE_PROCESS, NODE_COMMUNITY, NODE_TOOL
├── pipeline.py                # ALL_PHASES 扩展到 10+ 阶段
├── graph.py                   # 如有需要，补充辅助查询方法
```

### 3.3 各阶段详细设计

#### `heritage_processor.py`

**输入**：`PipelineOutput`（含 graph, scan_results）
**输出**： graph 中新增 `EXTENDS` / `IMPLEMENTS` 关系

**Python 实现**：
- 遍历所有 `.py` 文件，用 `ast.parse` 提取 `ClassDef.bases`
- 如果父名在图中存在且类型为 `interface` → `IMPLEMENTS`
- 否则 → `EXTENDS`
- 自环检测（子类 == 父类时跳过）

**JS/TS 实现**：
- 正则匹配 `class X extends Y implements Z1, Z2`
- 如果父名在该文件已提取为 interface → `IMPLEMENTS`
- 否则 → `EXTENDS`

**节点 ID 约定**：
- 子类：`class://{file_path}::{class_name}`
- 父类：先尝试 `class://{file_path}::{parent_name}`（同文件），再全局搜索同名 class/interface

#### `mro.py`

**输入**：含 `EXTENDS` 边的 graph
**输出**：新增 `METHOD_OVERRIDES` / `METHOD_IMPLEMENTS` 关系

**算法**：
1. 用 `networkx` 构建继承关系有向图（EXTENDS 边）
2. 对每个 class 节点，计算 C3 线性化（或简化 DFS 拓扑序）得到 MRO 链
3. 遍历该 class 的所有 method 节点：
   - 沿 MRO 链向上查找同名 method
   - 如果找到 → `METHOD_OVERRIDES` 边（子类方法 → 父类方法）
4. 遍历该 class 实现的所有 interface：
   - 对接口中的每个方法，查找类中同名方法
   - 如果找到 → `METHOD_IMPLEMENTS` 边

**性能注意**：class 数量通常 < 1000，networkx 完全可承受。

#### `route_extractor.py`

**输入**：`PipelineOutput`（含 graph, scan_results）
**输出**：`route_registry: dict[str, RouteEntry]` + graph 中新增 `Route` 节点 + `HANDLES_ROUTE` 边

**框架检测策略**：

| 框架 | 检测方式 | 示例 |
|------|---------|------|
| Next.js App Router | 文件路径模式 | `app/xxx/page.tsx` → `/xxx` |
| Next.js API Routes | 文件路径模式 | `pages/api/xxx.ts` → `/api/xxx` |
| FastAPI | 装饰器正则 | `@app.get("/users")` → `/users` |
| Flask | 装饰器正则 | `@app.route("/users")` → `/users` |
| Django | urls.py 正则 | `path("users", ...)` → `/users` |
| PHP Laravel | 文件路径 + 路由定义 | `routes/web.php` |
| Express | 方法调用正则 | `app.get('/users', ...)` |

**Node 属性**：
- `type = NODE_ROUTE`
- `name = URL 路径`
- `properties.method = GET/POST/PUT/DELETE`
- `properties.framework = nextjs/fastapi/flask/...`

#### `tool_extractor.py`

**输入**：`PipelineOutput`
**输出**：`tool_defs: list[ToolDef]` + graph 中新增 `Tool` 节点

**检测模式**：
1. 文件名包含 `tool` 的 `.ts/.js/.py` 文件
2. 正则匹配 `name: 'xxx', description: 'xxx'` 或 `@tool` 装饰器
3. MCP Server 定义中的 `inputSchema` 模式

**ToolDef 结构**：
```python
@dataclass
class ToolDef:
    name: str
    file_path: str
    description: str
    handler_node_id: Optional[str] = None
```

#### `orm_extractor.py`

**输入**：`PipelineOutput`
**输出**：graph 中新增 `CodeElement` 节点（ORM Model）+ `QUERIES` 边（文件 → Model）

**检测模式**：
- **Prisma**：`.prisma` 文件中 `model X { ... }`
- **SQLAlchemy**：`class X(Base): __tablename__ = '...'`
- **Django ORM**：`class X(models.Model):`
- **Supabase**：`supabase.from('xxx')` 调用

**边类型**：`QUERIES`（查询关系）

#### `communities.py`

**输入**：含 `IMPORTS` + `CALLS` + `DEFINED_IN` 边的 graph
**输出**：新增 `Community` 节点 + `MEMBER_OF` 边

**算法**：
1. 过滤出非 File 类型的符号节点（class/function/method/variable）
2. 以这些符号为节点，以 `CALLS` 和 `IMPORTS` 为边构建 networkx 无向图
3. 调用 `networkx.algorithms.community.greedy_modularity_communities`
4. 为每个社区生成 `Community` 节点
5. 为社区内每个符号添加 `MEMBER_OF` 边

**Community 节点属性**：
- `heuristicLabel`：根据社区内最常见的文件路径前缀生成
- `symbolCount`：社区内符号数量
- `cohesion`：社区内部边数 / 总边数

#### `process_extractor.py`

**输入**：含 `CALLS` 边 + `Route` 节点的 graph
**输出**：新增 `Process` 节点 + `STEP_IN_PROCESS` 边 + `ENTRY_POINT_OF` 边

**算法**：
1. 识别 Entry Points：
   - 所有 `Route` 节点关联的 handler 文件中的顶层函数
   - `main()`, `if __name__ == "__main__"` 块
   - `__init__.py` 中的公开函数
2. 从每个 Entry Point 做 BFS 沿 `CALLS` 边追踪调用链
3. 将长度 ≥ `min_steps`（默认 3）的调用链聚合为一个 `Process`
4. 为调用链上的每个符号添加 `STEP_IN_PROCESS` 边
5. 如果 Entry Point 来自 Route，添加 `ENTRY_POINT_OF(Route → Process)`

**Process 节点属性**：
- `processType`: `api_handler` / `cli` / `background_job`
- `stepCount`: 调用链长度
- `entryPointId`: 入口函数节点 ID
- `communities`: 该 Process 跨越的 Community ID 列表

#### `markdown.py`

**输入**：所有 `.md` / `.mdx` 文件
**输出**：graph 中新增 `MarkdownSection` 节点 + `CONTAINS` 边（File → Section）+ `LINKS_TO` 边（交叉链接）

**轻量实现**：
- 正则匹配 `#{1,4} .+` 提取标题
- 匹配 `[text](path)` 提取交叉链接
- 不追求完全对齐 GitNexus 的 Markdown 处理器（复杂表格/代码块解析）

### 3.4 Pipeline DAG 定义

```python
ALL_PHASES: list[PipelinePhase] = [
    PipelinePhase(name="scan",        handler=_scan_phase,        deps=[],            description="扫描文件系统"),
    PipelinePhase(name="structure",   handler=_structure_phase,   deps=["scan"],      description="构建文件/目录树"),
    PipelinePhase(name="markdown",    handler=_markdown_phase,    deps=["structure"], description="提取 Markdown 结构"),
    PipelinePhase(name="symbols",     handler=symbols_and_imports_phase, deps=["structure"], description="提取符号并解析 Import"),
    PipelinePhase(name="calls",       handler=calls_phase,        deps=["symbols"],   description="分析函数调用关系"),
    PipelinePhase(name="heritage",    handler=heritage_phase,     deps=["symbols"],   description="提取继承/实现关系"),
    PipelinePhase(name="mro",         handler=mro_phase,          deps=["heritage"],  description="计算方法解析顺序"),
    PipelinePhase(name="routes",      handler=routes_phase,       deps=["structure"], description="提取 API 路由"),
    PipelinePhase(name="tools",       handler=tools_phase,        deps=["symbols"],   description="检测 Tool 定义"),
    PipelinePhase(name="orm",         handler=orm_phase,          deps=["symbols"],   description="提取 ORM 查询"),
    PipelinePhase(name="communities", handler=communities_phase,  deps=["calls", "mro"], description="代码社区检测"),
    PipelinePhase(name="processes",   handler=processes_phase,    deps=["calls", "routes", "communities"], description="执行流检测"),
]
```

---

## 四、第二批：搜索质量升级 + 缺陷修复

### 4.1 新增文件

```
backend/app/kg/search/
├── bm25_index.py              # BM25 内存索引
└── hybrid_search.py           # RRF 混合搜索
```

### 4.2 修改文件

```
backend/app/kg/search/__init__.py    # CodeSearcher 集成 hybrid
backend/app/kg/phases/call_processor.py  # 修复 _get_enclosing_class, _get_node_id
backend/app/kg/persistence.py        # 添加 GIN 索引 + 复合索引
backend/app/kg/migration.py          # 数据库迁移脚本（如单独管理）
```

### 4.3 BM25 设计

- 从 PostgreSQL 加载 `name + COALESCE(properties->>'doc', '')` 作为文档
- 按 `type` 分组构建多个 BM25Index（file/function/class/method/interface）
- k1=1.5, b=0.75

### 4.4 Hybrid Search 设计

- `fts_results`：PostgreSQL `ts_rank` 排序
- `bm25_results`：BM25 评分排序
- RRF 融合：`score = 1/(60 + rank)`，两项分数相加
- 返回 Top-K

### 4.5 Call Processor 修复

- **`_get_enclosing_class`**：在 `analyze_file` 中预先遍历 `tree.body`，建立 `node → parent` 映射（用 `ast.NodeVisitor` 或手动遍历），然后查询函数节点的父链找到 `ClassDef`
- **`_get_node_id`**：根据父节点映射，如果函数在 ClassDef 内 → `method://`，否则 → `func://`
- **跨文件调用**：利用 `ImportResolver` 已解析的 import 关系，尝试将 `module.func()` 映射到对应文件中的函数

---

## 五、第三批：前端体验增强

### 5.1 新增组件

```
ui/components/kg/
├── CommunityFilter.tsx        # 社区筛选 + 着色逻辑
└── ProcessPanel.tsx           # 执行流列表
```

### 5.2 修改文件

```
ui/app/projects/[projectId]/fullstack-analysis/page.tsx
```

### 5.3 具体增强点

1. **社区着色**：
   - 调用 `search_by_type` 获取 `community` 类型节点
   - 获取选中符号的 `MEMBER_OF` 关系
   - `CodeGraphView` 的 `nodes` 传入 `community` 字段，按社区分配颜色

2. **Process 面板**：
   - 新增标签页"执行流"
   - 调用 API 获取 Process 列表（需新增 `/processes` 端点）
   - 点击 Process 高亮其包含的调用链

3. **影响分析增强**：
   - 当前只看 `CALLS`
   - 扩展为同时看 `METHOD_OVERRIDES`：如果修改父类方法，提示"影响 N 个子类重写"

4. **路由展示**：
   - 搜索结果中 `Route` 类型显示 `🌐` 图标
   - 上下文面板显示"处理的端点：GET /users"

---

## 六、API 变更清单

### 新增端点（第三批）

```
GET /projects/{id}/code-analysis/processes
  → 返回 Process 节点列表

GET /projects/{id}/code-analysis/communities
  → 返回 Community 节点列表
```

### 现有端点增强

```
GET /projects/{id}/code-analysis/search
  → 新增 mode 参数："fts" | "bm25" | "hybrid"（默认 hybrid）

GET /projects/{id}/code-analysis/context?symbol=xxx
  → 返回 relationships 中新增 EXTENDS/METHOD_OVERRIDES/MEMBER_OF 类型
```

---

## 七、数据库索引优化

在 `migration.py` 或 `persistence.py` 的初始化逻辑中添加：

```sql
-- GIN 全文搜索索引
CREATE INDEX IF NOT EXISTS kg_nodes_fts_idx ON kg_nodes
  USING GIN(to_tsvector('english', name || ' ' || COALESCE(properties->>'doc', '')));

-- 复合索引
CREATE INDEX IF NOT EXISTS kg_nodes_repo_type_idx ON kg_nodes(repo_path, type);
CREATE INDEX IF NOT EXISTS kg_rels_repo_type_idx ON kg_relationships(repo_path, type);
CREATE INDEX IF NOT EXISTS kg_rels_source_target_idx ON kg_relationships(source_node_id, target_node_id);
```

---

## 八、进度追踪

| 批次 | 模块 | 状态 | 备注 |
|------|------|------|------|
| 第一批 | `heritage_processor.py` | 🔄 待实现 | |
| 第一批 | `mro.py` | 🔄 待实现 | |
| 第一批 | `route_extractor.py` | 🔄 待实现 | |
| 第一批 | `tool_extractor.py` | 🔄 待实现 | |
| 第一批 | `orm_extractor.py` | 🔄 待实现 | |
| 第一批 | `communities.py` | 🔄 待实现 | |
| 第一批 | `process_extractor.py` | 🔄 待实现 | |
| 第一批 | `markdown.py` | 🔄 待实现 | 轻量 |
| 第一批 | `pipeline.py` 整合 | 🔄 待实现 | 注册新阶段 |
| 第一批 | `types.py` 补充 | 🔄 待实现 | 新节点/关系类型 |
| 第二批 | `bm25_index.py` | ⏳ 未开始 | |
| 第二批 | `hybrid_search.py` | ⏳ 未开始 | |
| 第二批 | `call_processor.py` 修复 | ⏳ 未开始 | |
| 第二批 | 数据库索引 | ⏳ 未开始 | |
| 第三批 | 前端社区着色 | ⏳ 未开始 | |
| 第三批 | 前端 Process 面板 | ⏳ 未开始 | |
| 第三批 | 影响分析增强 | ⏳ 未开始 | |

---

## 九、风险与决策记录

| 决策 | 原因 | 可逆性 |
|------|------|--------|
| 跳过 `crossFile` / `scopeResolution` | 依赖 Binding Accumulator，在 Python ast 下需重写类型系统，ROI 极低 | 可逆：未来引入 `pyright`/`mypy` 库时可补 |
| 跳过语义搜索 | 无 Embedding 基础设施，且 BM25 + FTS 已覆盖 80% 场景 | 可逆：未来接向量数据库时可补 |
| 跳过 COBOL | 小众语言，无相关项目需求 | 不可逆：如需求出现需重新评估 |
| 用 networkx 替代手写 Louvain | 已安装，工业级，减少 bug | 不可逆：但网络算法库之间替换容易 |
| 不复刻 Wiki 生成器 | 与"全栈分析"核心链路无关，独立功能 | 可逆：未来单独批次实现 |

---

## 十、明日续作指南

如果你是明天继续开发：

1. **读取本计划文档**：`docs/fullstack-analysis-plan.md`
2. **检查代码骨架**：先看 `backend/app/kg/phases/` 下是否有新增的空壳文件
3. **运行验证**：`python -m backend.app.kg.pipeline`（如支持 CLI）或触发一次分析
4. **按批次实现**：建议先完成第一批全部骨架的"最小可用实现"（能跑通不报错），再逐个填充算法细节

如果你是让我（AI）继续：
直接告诉我"继续第一批"，我会基于此文档立即开始编码。
