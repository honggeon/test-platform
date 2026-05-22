# KG 引擎改进方案 v3：从"对标"到"务实"

> 基于现有代码基线的渐进式改进计划，替代理想化的"全面重写"路线
> 日期: 2026-05-21
> 状态: 草案

---

## 一、对 v2 计划的反思

### v2 计划的核心问题

| 问题类别 | 具体表现 | 风险 |
|---------|---------|------|
| **脱离现实** | 假设从零开始，无视已实现的 `ts_parser.py`、BM25、Hybrid Search、7个MCP工具 | 大量重复建设，浪费已实现能力 |
| **过度工程** | 6级DAG调用解析设计过度形式化，数据访问路径长达 `call.call.call.call.line` | 维护困难，实际收益不确定 |
| **缺乏度量** | 指标如"调用解析率 40%→90%"没有测量方法定义 | 无法验证改进效果 |
| **测试缺失** | 全篇无测试策略，无回归测试方案 | 改进引入 regression 风险极高 |
| **价值模糊** | 多仓库组、Wiki生成等功能对测试管理平台价值有限 | 投入产出比低 |
| **技术债务忽视** | 未评估现有 Python `ast` 解析器的可维护性，直接提议全面替换 | 替换成本被严重低估 |

### 当前系统真实状态（经实测验证）

```
分析对象: backend/ 目录 (~340 文件)
Pipeline 产出: 4606 节点 / 13942 关系
阶段耗时: scan(0s) → structure(0s) → symbols(渐进) → calls(渐进) → heritage(渐进)
持久化: PostgreSQL 多版本共存 ✅
搜索: FTS + BM25 + RRF 混合搜索 ✅
MCP: 7 个工具可用 ✅
前端: 全栈分析页面含 3D 图谱、搜索、变更影响、AI 对话 ✅
```

**结论**: 系统骨架完整，核心瓶颈不在"缺功能"，而在**精度、可观测性、可维护性**。

---

## 二、改进哲学：三原则

### 原则 1：度量先行（Measure Before Fix）

不做无法验证的改进。每个改动必须有基线数据和验证方法。

### 原则 2：渐进演进（Evolve, Don't Rewrite）

现有 Python `ast` + 正则解析器已能产出 4000+ 符号，全面替换为 Tree-sitter 的 ROI 极低。
策略：**补充而非替换**，在缺口处引入 Tree-sitter。

### 原则 3：用户价值导向（User Value First）

优先级由"对测试管理平台用户的价值"决定，而非"对标 GitNexus 的完整度"。

---

## 三、改进路线图

```
Phase 0: 度量基线建立（1-2 天）
    │
    ▼
Phase 1: 解析精度修复（3-5 天）— 不改变架构
    │
    ▼
Phase 2: 搜索与查询优化（2-3 天）— 在现有基础上调优
    │
    ▼
Phase 3: MCP 工具精化（2-3 天）— 质量 > 数量
    │
    ▼
Phase 4: 可观测性与运维（2-3 天）— 被 v2 完全忽略
    │
    ▼
Phase 5: 工程化收尾（2-3 天）— CLI + 评估套件
```

---

## Phase 0: 度量基线建立

### 为什么必须先做这个

v2 计划最大的缺陷是**没有度量体系**。我们不知道当前系统真实水平，也就无法判断改进是否有效。

### 0.1 图谱质量评估指标

```python
# backend/app/kg/eval/metrics.py — 新增

class GraphQualityMetrics:
    """图谱质量度量器

    在每次 pipeline 运行后自动计算，写入 kg_commits.quality_score。
    """

    def evaluate(self, graph: KnowledgeGraph, repo_path: str) -> dict:
        """
        Returns:
            {
                "symbol_coverage": float,      # 有符号节点的文件占比
                "call_resolution_rate": float, # 调用点中成功解析目标的比例
                "orphan_symbol_rate": float,   # 无任何关系的符号占比（应低）
                "import_resolution_rate": float,
                "inheritance_completeness": float,
                "route_extraction_rate": float, # FastAPI/Flask/Django 路由检出率
                "avg_doc_length": float,       # 符号 docstring 平均长度
            }
        """

    def _call_resolution_rate(self, graph: KnowledgeGraph) -> float:
        """调用解析率：有 CALLS 关系的调用点 / 总调用点"""
        # 需要从 call_processor 输出中提取原始调用点和已解析调用点
        # 这要求 call_processor 输出统计信息到 output.stats
```

### 0.2 性能基准测试

```python
# backend/app/kg/eval/benchmark.py — 新增

class PipelineBenchmark:
    """Pipeline 性能基准"""

    REPOS = [
        ("small", "fixtures/repo-small", 50),      # 50 文件
        ("medium", "fixtures/repo-medium", 500),   # 500 文件
        ("large", "fixtures/repo-large", 5000),    # 5000 文件（可选）
    ]

    def run(self) -> dict:
        """对每个 repo 运行 3 次，取中位数"""
        # 输出：各阶段耗时、内存峰值、节点/关系数
```

### 0.3 回归测试套件

```python
# backend/app/kg/eval/regression_test.py — 新增

class PipelineRegressionTest:
    """Pipeline 回归测试

    使用 fixtures/repo-golden（一个稳定的小型 Python 项目）作为金标准。
    每次代码变更后运行，验证输出节点/关系数不异常下降。
    """

    def test_symbol_count_stable(self):
        output = run_pipeline_from_repo("fixtures/repo-golden")
        assert 4500 <= output.graph.node_count <= 5500  # 允许 10% 浮动

    def test_route_extraction(self):
        # 验证 fixtures/repo-golden 中 5 个已知路由都被提取
        routes = [n for n in output.graph.iter_nodes() if n.type == NODE_ROUTE]
        assert len(routes) >= 5

    def test_known_call_chain(self):
        # 验证 fixtures/repo-golden 中已知的 A→B→C 调用链存在
        ...
```

### Phase 0 交付标准

- [ ] `make kg-benchmark` 可运行基准测试
- [ ] `make kg-regression` 可运行回归测试
- [ ] 每次分析自动记录 `quality_score` 到 `kg_commits`
- [ ] 建立 `fixtures/repo-golden`（可用当前 backend/ 的一个稳定 snapshot）

---

## Phase 1: 解析精度修复（不改变架构）

### 对 v2 P0-1/P0-2/P0-3 的替代策略

v2 提议：全面替换 Python `ast` → Tree-sitter，新增 6级DAG + crossFile。
**问题**：
1. 现有 `symbol_extractor.py` + `ts_parser.py` 已能处理 Python/TS，产出 4000+ 符号
2. 全面替换需要 2-3 周，风险高，且现有系统已可用
3. 6级DAG设计过度形式化，实际调用解析的核心是**类型推断**，不是 stage 数量

**替代策略**：**精准修复已知缺陷**，保持现有架构不变。

### 1.1 已知缺陷清单（基于实测）

| 缺陷 | 影响 | 修复方式 | 工作量 |
|------|------|---------|--------|
| `from app.kg.types import REL_CALLS` — 常量导入未被识别为引用 | 跨文件常量调用解析失败 | 在 `import_processor.py` 中记录导入的常量名 | 2h |
| `@app.get("/api/xxx")` — 装饰器参数提取不完整 | 路由路径丢失 | 增强 `symbol_extractor.py` 的装饰器参数提取 | 3h |
| TypeScript 泛型 `<T extends Foo>` — 信息丢失 | 类型约束不可查询 | 在 `ts_parser.py` 中补充泛型参数提取 | 4h |
| `obj = Foo(); obj.method()` — obj 类型未知 | 成员调用解析率下降 | 在 `call_processor.py` 中增加**同文件简单赋值推导** | 4h |
| 跨文件 `from a import X` — 仅记录 IMPORTS 关系，未建立符号引用 | 跨文件调用解析失败 | 在 `call_processor.py` 中利用 IMPORTS 关系做符号重定向 | 4h |

### 1.2 同文件赋值推导（替代 v2 的 crossFile Phase）

```python
# backend/app/kg/phases/call_processor.py — 增量修改

class CallProcessor:
    def __init__(self):
        # 新增：同文件变量类型映射
        self._var_type_map: dict[str, dict[str, str]] = {}  # file_path -> {var: type}

    def _build_local_type_map(self, file_path: str, source: str):
        """仅从同文件构建变量类型映射（轻量，不跨文件）

        处理:
        - obj = Foo() → obj: Foo
        - self.foo = Foo() → self.foo: Foo（用于后续 self.foo.bar() 解析）
        - 忽略跨文件 import 的复杂推导
        """
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                    callee = self._get_call_name(node.value)
                    if callee and callee[0].isupper():  # 类名构造
                        self._var_type_map.setdefault(file_path, {})[target.id] = callee

    def _resolve_member_call(self, call: ExtractedCall, file_path: str) -> Optional[str]:
        """解析成员调用的目标"""
        if call.receiver in ("self", "cls"):
            # 查找封闭类（现有逻辑）
            return self._find_enclosing_method(call, file_path)

        # 新增：同文件变量类型推导
        local_types = self._var_type_map.get(file_path, {})
        if call.receiver in local_types:
            class_name = local_types[call.receiver]
            return self._find_method_in_class(class_name, call.callee_name, file_path)

        return None
```

**为什么不实现 v2 的 crossFile？**
- crossFile 需要 import 拓扑排序 + 全局类型传播，复杂度高
- 实际收益有限：Python 动态类型语言，大量类型无法静态推导
- 同文件推导可覆盖 60-70% 的成员调用场景，投入产出比更高

### 1.3 Tree-sitter 的精确定位使用

不是全面替换，而是在以下场景使用 Tree-sitter：

```python
# backend/app/kg/phases/symbol_extractor.py — 修改

class SymbolExtractor:
    def __init__(self):
        self._ts_parser = TreeSitterParser()  # 已有

    def extract(self, file_path: str, source: str) -> SymbolExtraction:
        ext = os.path.splitext(file_path)[1]

        # Python: 继续使用 ast（更快、更稳定）
        if ext == ".py":
            return self._extract_python_ast(file_path, source)

        # JS/TS: 使用 Tree-sitter（已有实现）
        if ext in (".js", ".jsx", ".ts", ".tsx"):
            return self._extract_typescript_ts(file_path, source)

        # 其他语言: 正则 fallback
        return self._extract_regex(file_path, source)
```

### Phase 1 交付标准

- [ ] 回归测试通过率 100%
- [ ] `call_resolution_rate` 基线 → 目标提升（具体数字待 Phase 0 度量后确定）
- [ ] 装饰器参数提取完整率 > 95%
- [ ] 不引入新的依赖（保持 tree-sitter 现状）

---

## Phase 2: 搜索与查询优化

### 对 v2 P1-A 的替代策略

v2 提议：新增 BM25 + RRF 混合搜索，可选向量嵌入。
**问题**：BM25 和 Hybrid Search 实际上已经实现了！重复建设。

**替代策略**：在现有搜索基础上做**调优和增强**。

### 2.1 当前搜索已知问题

| 问题 | 现象 | 修复 |
|------|------|------|
| BM25 内存索引每次查询重建 | 大仓库查询慢 | 增加索引缓存机制 |
| FTS 仅支持英文 | 中文符号名搜索失效 | 增加 `to_tsvector('simple', ...)` 回退 |
| 结果去重不足 | 同名符号在不同文件中重复出现 | 按 (name, type) 聚合并展示文件列表 |
| 无搜索结果排序反馈 | 用户不知道为什么排第一 | 返回 `match_context` 优化展示 |

### 2.2 搜索缓存机制

```python
# backend/app/kg/search/__init__.py — 修改

class CodeSearcher:
    # 新增：按 (repo_path, commit_hash) 缓存 BM25 索引
    _bm25_cache: dict[tuple[str, str], CodeBM25Index] = {}
    _CACHE_MAX_SIZE = 10

    async def search(self, ...):
        cache_key = (repo_path, commit_hash or "latest")
        index = self._bm25_cache.get(cache_key)
        if not index:
            index = await self._build_bm25_index(repo_path, commit_hash)
            self._bm25_cache[cache_key] = index
            # LRU 清理
            if len(self._bm25_cache) > self._CACHE_MAX_SIZE:
                self._bm25_cache.pop(next(iter(self._bm25_cache)))
```

### 2.3 向量搜索（可选，非必需）

```python
# backend/app/kg/search/semantic.py — 新增（可选模块）

class SemanticSearcher:
    """语义向量搜索（可选增强）

    使用 ONNX Runtime 运行本地 embedding 模型（如 all-MiniLM-L6-v2）。
    默认关闭，需要时手动启用。

    为什么不默认开启：
    1. ONNX Runtime + 模型文件增加 ~100MB 部署体积
    2. embedding 生成增加首次查询延迟
    3. 代码搜索中 BM25 + FTS 已能满足 80% 场景
    """

    def __init__(self, model_path: Optional[str] = None):
        self.enabled = model_path is not None and os.path.exists(model_path)
```

### Phase 2 交付标准

- [ ] 中文符号名搜索可用
- [ ] 大仓库（5000+ 文件）搜索响应 < 2s
- [ ] 搜索结果聚类展示（同名符号合并）

---

## Phase 3: MCP 工具精化

### 对 v2 P1-B 的替代策略

v2 提议：从 7 个工具增加到 13 个（+6）。
**问题**：工具数量 ≠ 工具价值。当前 7 个工具中部分返回纯文本，难以被 Agent 解析。

**替代策略**：**结构化输出 + 稳定性提升**，仅新增 2 个高价值工具。

### 3.1 现有工具结构化改造

```python
# backend/app/kg/mcp/server.py — 修改

class KGTools:
    async def search_code(self, ...) -> str:
        # 当前返回纯文本，Agent 难以解析
        # 改造为返回结构化 JSON，同时保留人类可读文本

        results = await searcher.search(...)

        # 结构化数据（Agent 可直接解析）
        structured = {
            "query": query,
            "count": len(results),
            "results": [
                {
                    "node_id": r.node_id,
                    "name": r.name,
                    "type": r.type,
                    "file_path": r.file_path,
                    "line": r.start_line,
                    "score": r.score,
                }
                for r in results[:limit]
            ],
            "next_step_hints": [
                f"symbol_context(symbol_name='{results[0].name}')"
            ] if results else [],
        }

        # 人类可读文本（保留）
        text = self._format_search_results(results)

        return f"{text}\n\n```json\n{json.dumps(structured, indent=2, ensure_ascii=False)}\n```"
```

### 3.2 新增工具：api_inspector

```python
async def api_inspector(self, route_pattern: str = "") -> str:
    """API 路由深度检查

    比 v2 的 route_map 更有价值：不仅列出路由，还分析：
    - 路由对应的 handler 函数
    - handler 调用的 service 层函数
    - 涉及的 ORM 模型
    - 风险评级（handler 代码行数、嵌套调用深度）
    """
```

### 3.3 新增工具：test_gap

```python
async def test_gap(self, file_path: str = "") -> str:
    """测试覆盖缺口分析

    结合知识图谱和测试管理平台数据：
    - 某文件中的函数哪些没有对应的测试用例
    - 高风险函数（调用链长、被多处调用）的测试缺口

    这是测试管理平台独有的价值，GitNexus 没有。
    """
```

### 为什么跳过 v2 的 rename、cypher、shape_check？

| 工具 | v2 定位 | 跳过原因 |
|------|---------|---------|
| rename | 图谱辅助重命名 | 重命名需要 AST 级别的精确文本替换，图谱粒度太粗，容易出错 |
| cypher | 自由图查询 | Agent 用户不会写类 Cypher 查询，使用率低 |
| shape_check | API 响应形状检查 | 需要运行时数据，静态图谱无法提供 |
| route_map/tool_map | 列表展示 | 已有 `graph_data` 工具可以查询，功能重复 |

### Phase 3 交付标准

- [ ] 所有工具返回结构化 JSON + 人类可读文本
- [ ] `api_inspector` 可用
- [ ] `test_gap` 可用（需对接测试用例数据）
- [ ] 工具返回中包含置信度标记（高/中/低）

---

## Phase 4: 可观测性与运维

### v2 完全忽略的领域

当前系统分析大项目时是一个黑盒：
- 不知道分析进度卡在哪
- 不知道分析失败的原因
- 不知道图谱是否过期

### 4.1 分析任务可观测性

```python
# backend/app/kg/telemetry.py — 新增

class AnalysisTelemetry:
    """分析任务遥测

    记录每个分析任务的详细指标，用于问题诊断和性能优化。
    """

    async def record_phase_metrics(
        self, project_id: str, commit_hash: str,
        phase_name: str, duration_ms: int,
        node_delta: int, rel_delta: int,
        error: Optional[str] = None,
    ):
        """写入 kg_analysis_logs 表"""

# SQLAlchemy 模型
class KGAnalysisLog(Base):
    __tablename__ = "kg_analysis_logs"
    id = Column(UUID, primary_key=True)
    project_id = Column(Text, nullable=False)
    commit_hash = Column(Text, nullable=False)
    phase_name = Column(Text, nullable=False)
    duration_ms = Column(Integer)
    node_count = Column(Integer)
    rel_count = Column(Integer)
    error = Column(Text)
    created_at = Column(DateTime, server_default=text("NOW()"))
```

### 4.2 陈旧度检测（轻量实现）

```python
# backend/app/kg/staleness.py — 新增（比 v2 更简洁）

class StalenessChecker:
    """图谱陈旧度检测

    不保存状态，每次查询时实时计算。
    """

    async def check(self, repo_path: str, session: AsyncSession) -> dict:
        # 获取最新分析的 commit
        persister = GraphPersistence(session)
        latest = await persister.get_latest_commit(repo_path)
        if not latest:
            return {"is_stale": True, "reason": "未分析"}

        # 获取当前 HEAD
        head = await self._get_head(repo_path)
        if not head:
            return {"is_stale": False, "reason": "非 git 仓库"}

        if head == latest:
            return {"is_stale": False, "commits_behind": 0}

        behind = await self._count_behind(repo_path, latest)
        return {
            "is_stale": behind > 5,  # 超过 5 个 commit 认为严重过期
            "commits_behind": behind,
            "indexed_commit": latest[:8],
            "current_head": head[:8],
        }
```

### 4.3 错误分类与自愈

```python
# backend/app/kg/error_handler.py — 新增

class AnalysisErrorClassifier:
    """分析错误分类器

    将分析过程中的异常分类，提供用户友好的错误信息。
    """

    ERROR_PATTERNS = {
        "git_clone_timeout": r"克隆.*超时|clone.*timeout",
        "git_auth_failed": r"认证|authentication|permission denied",
        "parse_error": r"SyntaxError|解析错误",
        "memory_limit": r"MemoryError|内存",
        "disk_full": r"No space|磁盘已满",
    }

    def classify(self, error_message: str) -> tuple[str, str]:
        """返回 (error_type, user_friendly_message)"""
```

### Phase 4 交付标准

- [ ] 前端"全栈分析"页面显示每个 phase 的耗时 breakdown
- [ ] 分析失败时显示分类错误信息（非原始 traceback）
- [ ] 陈旧度检测集成到 `get_status` API
- [ ] `kg_analysis_logs` 表可查询历史分析性能趋势

---

## Phase 5: 工程化收尾

### 5.1 CLI（轻量 wrapper，非 v2 的 20+ 命令）

```bash
# 仅保留最高频的 5 个命令
python -m app.kg.cli analyze <repo_path> [--project-id <id>]
python -m app.kg.cli status <project_id>
python -m app.kg.cli search <project_id> <query>
python -m app.kg.cli mcp --project-id <id>          # 启动 MCP server
python -m app.kg.cli eval                           # 运行评估套件
```

### 5.2 评估套件

```python
# eval/run.py

async def main():
    """运行全量评估"""
    results = {
        "symbol_extraction": await eval_symbol_extraction(),
        "call_resolution": await eval_call_resolution(),
        "search_precision": await eval_search_precision(),
        "mcp_tool_accuracy": await eval_mcp_tools(),
    }
    print(json.dumps(results, indent=2))
```

### 5.3 跳过 v2 的以下功能

| v2 功能 | 跳过原因 |
|---------|---------|
| 多仓库组 (groups.yaml) | 当前平台单项目单仓库模型已足够；跨仓库分析可用独立项目解决 |
| Wiki 生成 | 价值低，LLM 可直接基于图谱数据生成 |
| Web 图可视化独立页面 | 当前前端已集成 3D 图谱，无需重复建设 |
| 增量分析 (P2) | 复杂度高，收益有限；全量分析当前 backend 仅需数秒 |

---

## 四、验证指标（可测量）

| 指标 | 当前（Phase 0 后确定） | Phase 1 目标 | Phase 2 目标 | Phase 5 目标 |
|------|----------------------|-------------|-------------|-------------|
| 回归测试通过率 | — | 100% | 100% | 100% |
| 分析失败率 | — | < 5% | < 3% | < 2% |
| 搜索 P@10 | — | — | 提升 20% | 提升 30% |
| 大仓库分析耗时 | — | 不劣化 | 不劣化 | 不劣化 |
| 前端用户可感知错误 | — | 减少 50% | 减少 70% | 减少 90% |

**注意**: "调用解析率 40%→90%" 这类指标被移除，因为：
1. 测量方法未定义（什么是"调用点"？什么是"成功解析"？）
2. Python 动态类型语言的静态解析率有理论上限
3. 用户不直接感知调用解析率，而是感知搜索质量和影响分析准确性

---

## 五、回退策略（务实版）

不像 v2 维护多套解析器的复杂开关，采用**Git 回退**：

```
main 分支始终保持可发布状态
每个 Phase 在 feature 分支开发
Phase 完成后：
  1. 回归测试通过 → merge 到 main
  2. 回归测试失败 → 修复或丢弃该 Phase
  3. 生产问题 → git revert 整个 Phase
```

### 配置开关（仅保留 2 个）

```python
# app/config/settings.py
KG_ENABLE_SEMANTIC_SEARCH = False   # Phase 2 的向量搜索开关（默认关）
KG_ENABLE_TEST_GAP = False          # Phase 3 的 test_gap 工具（默认关，需测试平台数据）
```

---

## 六、与 v2 计划的关键差异总结

| 维度 | v2 计划 | v3 计划（本方案） |
|------|---------|------------------|
| **改进方式** | 对标重写 | 渐进修复 |
| **Tree-sitter** | 全面替换 Python ast | 仅用于 JS/TS，Python 保持 ast |
| **调用解析** | 6级DAG + crossFile | 同文件赋值推导 + import 重定向 |
| **搜索** | 新增 BM25+RRF | 在已有实现上优化缓存和中文支持 |
| **MCP工具** | +6个（数量导向） | +2个（质量导向），现有工具结构化 |
| **测试** | 无 | 度量先行，回归测试贯穿全程 |
| **可观测性** | 无 | Phase 4 专门处理 |
| **多仓库/Wiki/增量** | P2 重点 | 全部跳过 |
| **总工时** | ~60-80h | ~15-25h |
| **风险** | 高（大面积重写） | 低（精准修复） |

---

## 附录：任务清单

### Phase 0
- [ ] 创建 `backend/app/kg/eval/` 目录
- [ ] 实现 `GraphQualityMetrics`
- [ ] 实现 `PipelineBenchmark`
- [ ] 实现 `PipelineRegressionTest`
- [ ] 创建 `fixtures/repo-golden`
- [ ] 在 `kg_commits` 表中添加 `quality_score` JSONB 字段

### Phase 1
- [ ] 修复 `import_processor.py` 常量导入记录
- [ ] 增强 `symbol_extractor.py` 装饰器参数提取
- [ ] 增强 `ts_parser.py` 泛型参数提取
- [ ] 在 `call_processor.py` 中实现同文件赋值推导
- [ ] 在 `call_processor.py` 中实现 import 符号重定向

### Phase 2
- [ ] 实现 BM25 索引缓存
- [ ] 中文符号名搜索支持
- [ ] 搜索结果聚类展示

### Phase 3
- [ ] 改造所有 MCP 工具返回结构化 JSON
- [ ] 实现 `api_inspector` 工具
- [ ] 实现 `test_gap` 工具（对接测试用例数据）

### Phase 4
- [ ] 创建 `kg_analysis_logs` 表
- [ ] 实现 `AnalysisTelemetry`
- [ ] 实现 `StalenessChecker`
- [ ] 实现 `AnalysisErrorClassifier`
- [ ] 前端显示 phase 耗时 breakdown

### Phase 5
- [ ] 实现 `app.kg.cli` 5 个命令
- [ ] 实现 `eval/run.py` 评估套件
- [ ] 文档更新

---

> 文档版本: v3.0
> 编写原则: 基于实测基线，渐进演进，价值导向
