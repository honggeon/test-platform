# 日志分析 Agent 设计文档

> 版本: v1.1 | 日期: 2026-05-22 | 状态: 修订版（根据评审意见更新）
>
> 评价参考: `docs/log-analysis-agent-design-review.md`

---

## 1. 概述

### 1.1 目标

在 AI 测试平台中新增一个**日志分析 Agent**，能够在测试执行失败时自动触发诊断，结合知识图谱（KG）定位代码位置，输出根因分析和修复建议，并推送结果到前端。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| **日志采集** | 从 MongoDB `api_test_logs` + PG `scenario_step_results` 读取失败日志 |
| **自动触发** | API Agent 执行测试失败后，自动调用日志分析 Agent 进行诊断 |
| **KG 代码定位** | 将错误信息映射到源码文件、函数、行号 |
| **诊断报告** | 输出根因分类、影响范围、修复建议 |
| **A2A 暴露** | 对外暴露 Google A2A Agent Card，供其他 Agent/系统发现 |
| **前端推送** | WebSocket 实时推送诊断进展，报告存入数据库 |

### 1.3 非目标

- 不替代 `healer` skill（那是修复，这是诊断）
- 不修改现有测试执行引擎的核心逻辑
- 不做实时日志流式监控（只在测试失败时触发）

---

## 2. 架构设计

### 2.1 整体架构

```
┌═══════════════════════════════════════════════════════════════════════┐
║  A2A 对外边界（外部 Agent 通过 HTTP 发现和调用）                       ║
╚═══════════════════════════════════════════════════════════════════════╝
                              │
                    ┌─────────▼─────────┐
                    │  A2A Router       │  ← 仅对外暴露，不参与内部调用
                    │  /a2a/agent-card  │
                    │  /a2a/tasks/*     │
                    └─────────┬─────────┘
                              │ 内部复用 TestDiagnosisService
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAPI 后端 (MCP 内部调用)                    │
│                                                                     │
│  ┌──────────────┐     MCP     ┌──────────────────┐                  │
│  │ API Agent     │ ────────→  │ 日志分析 Agent    │                  │
│  │ (deepagents)  │ 触发诊断   │ (deepagents)     │                  │
│  │               │            │                  │                  │
│  │ ┌─Tools─────┐ │ ←──────── │ ┌─Tools────────┐ │                  │
│  │ │diagnose   │ │ 诊断报告   │ │query_logs    │ │                  │
│  │ │(MCP 调用) │ │            │ │get_log_detail│ │                  │
│  │ └───────────┘ │            │ │analyze_fails │ │                  │
│  └──────┬────────┘            │ │report_gen    │ │                  │
│         │                    │ └──────┬───────┘ │                  │
│         │ MCP                 │        │         │                  │
│         ▼                    │        ▼         │                  │
│  ┌──────────┐               │  ┌──────────┐    │                  │
│  │ KG MCP   │               │  │ KG MCP   │    │                  │
│  │ Server   │               │  │ Server   │    │                  │
│  └──────────┘               │  └──────────┘    │                  │
│         │                   │        │         │                  │
│         └───────────────────┴──────────────────┘                  │
│                                                                     │
│  ┌─────────────────────────────┐   ┌───────────────────────────┐  │
│  │ MongoDB                     │   │ PostgreSQL                │  │
│  │  - api_test_logs            │   │  - scenario_step_results  │  │
│  │  - diagnosis_reports (新增) │   │  - diagnosis_reports      │  │
│  └─────────────────────────────┘   └───────────────────────────┘  │
│                                                                     │
│  ┌─────────────────────────────┐                                   │
│  │ WebSocket                   │  → 前端实时推送诊断进展             │
│  │ (Redis Pub/Sub 后端)         │                                   │
│  └─────────────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────┘

图例:
══════  A2A 对外边界（HTTP）
──────  MCP 内部调用（同进程零开销）
- - - → 降级路径（KG 不可用时跳过）
```

### 2.2 数据流：测试失败触发诊断（含异常分支）

```
                              ╔══════════════════════╗
                              ║    API Agent         ║
                              ║  执行测试脚本         ║
                              ╚════════╤═════════════╝
                                       │ 失败 (401/500/timeout)
                                       ▼
                              ╔══════════════════════╗
                              ║  Agent 调用           ║
                              ║  diagnose_run()       ║
                              ╚════════╤═════════════╝
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼ 正常路径          │                   ▼ 异常路径
        ╔═══════════════════╗         │         ╔═══════════════════════╗
        ║ 查询 MongoDB      ║         │         ║ MongoDB/PG 不可用     ║
        ║ api_test_logs     ║         │         ║ → 降级：仅用 Playwright║
        ╚═══════╤═══════════╝         │         ║   stdout 分析          ║
                │                     │         ╚═══════════════════════╝
                ▼                     │                     │
        ╔═══════════════════╗         │                     ▼
        ║ 查询 PG            ║         │         ╔═══════════════════════╗
        ║ scenario_step_     ║         │         ║ 报告标记              ║
        ║ results            ║         │         ║ "数据源不完整"        ║
        ╚═══════╤═══════════╝         │         ╚═══════════════════════╝
                │                     │                     │
                └──────┬──────────────┘                     │
                       ▼                                    │
            ╔══════════════════════╗                         │
            ║  规则引擎分类        ║                         │
            ║  → 命中规则?         ║──── 未命中 ────┐        │
            ║  → LLM 兜底          ║←──────────┘     │        │
            ╚════════╤════════════╝                   │        │
                     │                               │        │
                     ▼                               │        │
            ╔══════════════════════╗                 │        │
            ║  KG 代码定位         ║                 │        │
            ║  → kg_search_code    ║── KG 不可用 ──→ │        │
            ║  → kg_symbol_context ║                 │        │
            ║  → kg_impact_analysis║                 │        │
            ╚════════╤════════════╝                 │        │
                     │ 超时/空结果                    │        │
                     ▼                               ▼        ▼
            ╔══════════════════════════════════════════════════╗
            ║  诊断报告                                       ║
            ║  - 根因类型 / 置信度                             ║
            ║  - 代码位置（可能有 / 可能为空）                    ║
            ║  - 降级标注（如有）                               ║
            ║  - 修复建议                                     ║
            ╚════════╤═══════════════════════════════════════╝
                     │
          ┌──────────┼──────────┬──────────────┐
          ▼          ▼          ▼              ▼
   ┌─────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐
   │ 存 MongoDB│ │ 存 PG  │ │ 推 WebSocket│ │回传 Agent│
   │ 完整报告 │ │ 概要   │ │ 失败也推  │ │(修复脚本) │
   └─────────┘ └────────┘ └──────────┘ └──────────┘
                     │
                     ▼ failure
              ┌──────────┐
              │ 报告标记  │
              │"completed"│
              │ (含降级)   │
              └──────────┘

关键原则：
- 诊断流程在任何阶段的失败都不应导致服务端崩溃。
- 所有外部依赖（MongoDB/PG/KG/LLM）都有超时控制 + 降级逻辑。
- 诊断报告的 status 为 "completed"（正常完成，可能含降级）或 "failed"（诊断引擎自身崩溃）。
- `degradation` 字段反映数据完整度，前端据此展示警告标识。
```

---

## 3. 新增组件清单

### 3.1 组件总览

```
backend/app/agents/log_analysis/          # 日志分析 Agent
├── __init__.py
├── agent.py                              # Agent 工厂（deepagents）
├── tools/
│   ├── __init__.py
│   ├── log_query_tools.py                # 日志查询工具
│   ├── diagnosis_tools.py                # 诊断分析工具
│   └── kg_integration_tools.py           # KG 集成工具（含超时/重试/降级）
└── SKILL.md                              # 诊断领域知识

backend/app/services/
├── test_diagnosis_service.py             # 诊断引擎（核心逻辑）
├── diagnosis_cache.py                    # LLM 结果缓存层（新增）
└── diagnosis_notification_service.py     # 前端推送服务（Redis Pub/Sub 后端）

backend/app/models/mongodb/
└── diagnosis_report.py                   # 诊断报告 MongoDB 模型

backend/app/api/v2/
├── a2a.py                                # A2A 协议端点（阶段二）
└── diagnosis.py                          # 诊断 REST API + WebSocket

backend/app/agents/api/tools/
├── diagnosis_trigger_tools.py            # API Agent 的诊断触发工具
└── a2a_tools.py                          # A2A 客户端工具（阶段二）

backend/workspace/diagnosis/              # 诊断工作区
└── ...

backend/config/
└── failure_rules.yaml                    # 失败分类规则库（可热更新，新增）
```

### 3.2 各组件代码量预估

| 组件 | 文件 | 预估行数 | 复杂度 |
|------|------|---------|--------|
| MongoDB 模型 | `diagnosis_report.py` | 100 行 | 低 |
| 日志查询工具 | `log_query_tools.py` | 150 行 | 低 |
| 诊断分析工具 | `diagnosis_tools.py` | 200 行 | 中 |
| KG 集成工具 | `kg_integration_tools.py` | 280 行 | 中（含超时/重试/降级） |
| 诊断引擎服务 | `test_diagnosis_service.py` | 450 行 | 高（核心）+ 去重逻辑 |
| 诊断缓存 | `diagnosis_cache.py` | 80 行 | 低 |
| 诊断 Agent | `agent.py` | 150 行 | 中 |
| Agent SKILL | `SKILL.md` | 100 行 | 低 |
| 推送服务 | `diagnosis_notification_service.py` | 150 行 | 中（Redis Pub/Sub） |
| 规则库配置 | `failure_rules.yaml` | 60 行 | 低 |
| A2A 端点 | `a2a.py` | 300 行 | 高（协议实现 + 鉴权） |
| REST API | `diagnosis.py` | 150 行 | 中（含 WebSocket） |
| 触发工具 | `diagnosis_trigger_tools.py` | 80 行 | 低 |
| A2A 客户端 | `a2a_tools.py` | 100 行 | 低 |
| **总计** | | **~2360 行** | |

---

## 4. 数据模型设计

### 4.1 MongoDB: `diagnosis_reports` 集合

```python
class DiagnosisReport(BaseModel):
    """诊断报告"""
    report_id: str                         # UUID
    run_id: str                            # 关联的测试运行 ID
    project_id: str                        # 项目 ID
    status: str                            # "pending" / "analyzing" / "completed" / "failed"
    # - pending:   诊断任务已创建，等待执行
    # - analyzing: 正在诊断中（用于幂等性控制）
    # - completed: 诊断流程完整执行，无论是否降级
    # - failed:    诊断引擎自身崩溃（_emergency_report 场景）

    # 幂等性控制
    dedup_key: str                         # f"{run_id}_{project_id}" 唯一索引
    retry_of_report_id: Optional[str]      # 如果是对同一 run 的重新诊断，记录前次 ID

    # 来源信息
    source_type: str                       # "api_test" / "scenario" / "manual"
    test_type: str                         # "single" / "scenario" / "batch"

    # 降级信息
    degradation: dict {
        "has_db_logs": bool,               # MongoDB/PG 是否可用
        "has_kg_locations": bool,          # KG 定位是否成功
        "has_llm_analysis": bool,          # LLM 兜底是否成功
        "fallback_reason": str | None,     # 降级原因描述（如 "KG MCP timeout"）
    }

    # 概要
    summary: dict = {
        "total_failures": int,
        "root_cause_counts": {             # 根因分类统计
            "token_expired": 3,
            "permission_denied": 0,
            "api_changed": 1,
            "data_error": 2,
            "network_timeout": 0,
            "script_error": 1,
            "unknown": 0
        }
    }

    # 诊断详情
    findings: list[dict] = [
        {
            "failure_id": str,
            "endpoint": "/api/v2/users",
            "method": "GET",
            "status_code": 401,
            "error_message": "Token expired",
            "root_cause_type": "token_expired",
            "root_cause_detail": "访问令牌已过期，无自动刷新机制",
            "classifier": "rule",           # "rule" | "llm" — 标识是规则还是 LLM 分类的
            "matching_rule": "token_expired: rule_1",  # 如果规则命中，记录规则 ID
            "code_locations": [
                {
                    "file": "src/middleware/auth.ts",
                    "line": 42,
                    "symbol": "verifyToken",
                    "relevance": "token 验证逻辑所在",
                    "confidence": 0.92,
                    "strategy": "middleware_layer"  # 定位策略标识
                }
            ],
            "affects_apis": ["GET /users", "POST /orders"],
            "fix_suggestions": [
                "在调用前检查 token 是否过期，过期则先调用 /auth/refresh"
            ],
            "llm_cache_hit": False          # 是否命中 LLM 缓存
        }
    ]

    # 元信息
    analysis_duration_ms: int               # 分析耗时
    llm_token_cost: dict {                  # Token 消耗统计
        "prompt_tokens": int,
        "completion_tokens": int,
        "total_tokens": int,
        "total_cost_usd": float,           # 本地 LLM 时为 0（见 llm_provider）
    }
    llm_provider: str = "local"            # "local" / "openai" / "deepseek_api" 等
    # 当 llm_provider == "local" 时，total_cost_usd = 0
    created_at: datetime
    completed_at: Optional[datetime]
```

### 4.2 PostgreSQL: `diagnosis_reports` 表

```python
class DiagnosisReportPG(Base):
    """诊断报告 PG 表（用于关系查询和列表展示）"""
    __tablename__ = "diagnosis_reports"

    id: UUID = primary_key
    project_id: UUID, ForeignKey("projects.id"), index
    run_id: UUID, index
    dedup_key: str, unique, index          # 唯一约束保证幂等性
    report_type: str                       # "auto" / "manual"
    status: str                            # "completed" / "failed" / "analyzing"
    summary_json: JSONB                    # 冗余 summary 方便 SQL 查询
    source_type: str                       # "api_test" / "scenario"
    error_count: int
    degradation_level: str                 # "none" / "partial" / "severe"
    llm_tokens_used: int
    analysis_duration_ms: int
    mongo_id: str                          # MongoDB 的完整数据引用
    created_at: datetime
```

设计理由：
- **MongoDB**：存完整的 findings 大 JSON（灵活、嵌套深、无 Schema 变更成本）
- **PG**：存概要字段用于列表查询、分页、排序（利用 PG 的索引能力）
- **`dedup_key` 唯一约束**：保证同一个 run 不会重复创建诊断，天然幂等
- **`degradation_level`**：PG 层快速过滤降级报告，便于监控

---

## 5. 核心服务设计

### 5.1 `test_diagnosis_service.py` — 诊断引擎

```python
class TestDiagnosisService:
    """日志诊断核心服务"""

    # 短超时：外部依赖快速失败，留给降级路径
    KG_TIMEOUT = 3.0        # KG 单次调用超时 3s
    LLM_TIMEOUT = 10.0      # LLM 兜底超时 10s
    DB_TIMEOUT = 5.0        # 数据库查询超时 5s

    # 重试配置
    KG_RETRY_MAX = 2        # KG 最多重试 2 次
    KG_RETRY_DELAY = 0.5    # 重试间隔 500ms

    # 采样配置
    MAX_LLM_ANALYSIS = 10   # LLM 兜底最多分析 10 条，超过则分层抽样

    def __init__(self, mongodb, db_session, redis_client=None):
        self.mongodb = mongodb
        self.db = db_session
        self.redis = redis_client    # 可选，用于分布式锁

    async def diagnose_run(
        self,
        run_id: str,
        project_id: str,
        options: DiagnosisOptions = None,
    ) -> DiagnosisReport:
        """
        完整诊断流程

        幂等性保证：
        - 用 dedup_key 在 PG 层做唯一约束
        - 同一 run_id 并发请求，第一个成功，后续返回已存在的报告
        - 诊断中若收到重复请求，返回 "analyzing" 状态
        """
        dedup_key = f"{run_id}_{project_id}"

        # 幂等检查
        existing = await self._find_existing_report(dedup_key)
        if existing:
            return existing

        # 分布式锁（可选，有 Redis 时启用）
        if self.redis:
            lock = await self._acquire_lock(dedup_key, ttl=120)
            if not lock:
                # 另一实例正在诊断，等待结果
                return await self._wait_for_report(dedup_key, timeout=120)
            try:
                return await self._execute_diagnosis(run_id, project_id, options)
            finally:
                await self._release_lock(lock)
        else:
            return await self._execute_diagnosis(run_id, project_id, options)

    async def _execute_diagnosis(self, run_id, project_id, options) -> DiagnosisReport:
        """诊断主流程，每步都 try/except 降级"""
        start_time = time.monotonic()
        degradation = {"has_db_logs": True, "has_kg_locations": True,
                       "has_llm_analysis": True, "fallback_reason": None}
        llm_cost = {"prompt_tokens": 0, "completion_tokens": 0, "total_cost_usd": 0}

        try:
            # Phase 1: 采集失败日志（带超时和降级）
            try:
                logs = await asyncio.wait_for(
                    self._collect_failure_logs(run_id), timeout=self.DB_TIMEOUT
                )
            except (asyncio.TimeoutError, Exception) as e:
                logs = []
                degradation["has_db_logs"] = False
                degradation["fallback_reason"] = f"DB 查询失败: {str(e)}"

            if not logs:
                # 降级：仅基于参数中的 test_output 做文本分析
                logs = self._parse_from_test_output(options.get("test_output", ""))
                if not logs:
                    return self._empty_report(run_id, degradation)

            # Phase 2: 分类失败模式
            classified = self._classify_failures(logs)

            # Phase 3: KG 代码定位（批量并行）
            findings = []
            if degradation["has_db_logs"] and classified:
                batch_size = 10  # 每批最多并行 10 条
                for batch_start in range(0, len(classified), batch_size):
                    batch = classified[batch_start:batch_start + batch_size]
                    try:
                        batch_locations = await asyncio.wait_for(
                            asyncio.gather(
                                *[self._locate_in_code(f) for f in batch],
                                return_exceptions=True  # 单条失败不阻断整批
                            ),
                            timeout=self.KG_TIMEOUT + 2.0  # 整批超时 5s
                        )
                    except asyncio.TimeoutError as e:
                        batch_locations = [[] for _ in batch]
                        degradation["has_kg_locations"] = False
                        degradation["fallback_reason"] = f"KG 整批超时: {str(e)}"

                    for failure, locations in zip(batch, batch_locations):
                        if isinstance(locations, Exception):
                            locations = []
                            degradation["has_kg_locations"] = False
                            degradation["fallback_reason"] = f"KG 单条失败: {locations}"
                        findings.append({**failure, "code_locations": locations})
            else:
                for failure in classified:
                    findings.append({**failure, "code_locations": []})

            # Phase 4: 生成修复建议（LLM 兜底部分）
            report = self._generate_report(findings, degradation, llm_cost)

        except Exception as e:
            # 最外层的兜底：任何未预料的异常都生成降级报告
            report = self._emergency_report(run_id, str(e))

        # Phase 5: 持久化（PG 优先，MongoDB 异步补偿）
        report.analysis_duration_ms = int((time.monotonic() - start_time) * 1000)
        try:
            await self._save_report(report)  # 先写 PG（主）+ MongoDB（从）
        except Exception as e:
            logger.error(f"保存诊断报告失败: {e}")

        # Phase 6: 推送（推送失败不阻断流程）
        try:
            await self._notify_frontend(report)
        except Exception as e:
            logger.error(f"推送诊断报告失败: {e}")

        return report

    async def _collect_failure_logs(self, run_id: str) -> list[dict]:
        """从 MongoDB 和 PG 采集失败日志，合并去重"""
        logs = []
        try:
            # 1. 查 MongoDB api_test_logs
            mongo_logs = await self.mongodb.db.get_collection("api_test_logs").find(
                {"test_run_id": run_id, "status": {"$in": ["failed", "error"]}}
            ).to_list(length=100)
            logs.extend(mongo_logs)
        except Exception as e:
            logger.warning(f"MongoDB 查询失败: {e}")
            raise  # 上层统一处理降级

        try:
            # 2. 查 PG scenario_step_results
            async with self.db as session:
                result = await session.execute(
                    select(ScenarioStepResult).where(
                        ScenarioStepResult.run_id == UUID(run_id),
                        ScenarioStepResult.status.in_(["failed", "error"])
                    )
                )
                pg_logs = result.scalars().all()
                logs.extend(self._pg_to_log_dicts(pg_logs))
        except Exception as e:
            logger.warning(f"PG 查询失败: {e}")
            raise

        # 3. 合并去重（按 endpoint + method + status_code 去重）
        return self._dedup_logs(logs)

    async def _save_report(self, report: DiagnosisReport):
        """
        持久化诊断报告（PG 优先策略）

        写入顺序：
        1. 先写 PG（主数据源，利用 dedup_key 唯一约束保证幂等）
        2. PG 成功后写 MongoDB（完整报告）
        3. MongoDB 失败时记录补偿任务

        查询时以 PG 为准：
        - PG 存在 → 报告已保存
        - PG 不存在 → 报告未保存（无需检查 MongoDB）

        补偿任务（MongoDB 写入失败时）：
        - 记录到补偿日志表
        - 后台协程定期重试（最多 3 次，间隔 30s）
        - 补偿失败不影响 PG 查询（前端仍可看到概要信息）
        """
        try:
            # 1. 先写 PG（主）
            pg_report = DiagnosisReportPG(
                id=UUID(report.report_id),
                project_id=UUID(report.project_id),
                run_id=UUID(report.run_id),
                dedup_key=report.dedup_key,
                report_type=report.source_type,
                status=report.status,
                summary_json=report.summary,
                source_type=report.source_type,
                error_count=report.summary.get("total_failures", 0),
                degradation_level=self._calc_degradation_level(report.degradation),
                llm_tokens_used=report.llm_token_cost.get("total_tokens", 0),
                analysis_duration_ms=report.analysis_duration_ms,
                mongo_id=report.report_id,
            )
            async with self.db as session:
                session.add(pg_report)
                await session.commit()
        except Exception as e:
            logger.error(f"PG 写入失败，诊断报告丢弃: {e}")
            raise  # 上层捕获后记录日志，不阻断主流程

        # 2. 再写 MongoDB（从），失败不阻断
        try:
            collection = self.mongodb.db.get_collection("diagnosis_reports")
            await collection.insert_one(report.to_document())
        except Exception as e:
            logger.error(f"MongoDB 写入失败，启动补偿: {e}")
            asyncio.create_task(self._compensate_mongo(report))

    async def _compensate_mongo(self, report: DiagnosisReport, retries=3):
        """补偿写 MongoDB：30s 后重试，最多 3 次"""
        for attempt in range(retries):
            try:
                await asyncio.sleep(30)
                collection = self.mongodb.db.get_collection("diagnosis_reports")
                await collection.insert_one(report.to_document())
                return
            except Exception:
                if attempt == retries - 1:
                    logger.error(f"MongoDB 补偿写入最终失败, report_id={report.report_id}")

    async def _wait_for_report(self, dedup_key: str, timeout=120) -> DiagnosisReport:
        """
        等待其他实例完成诊断（分布式锁冲突时调用）

        轮询间隔 500ms，查询 PG。超时后返回空报告。
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)
            async with self.db as session:
                result = await session.execute(
                    select(DiagnosisReportPG).where(
                        DiagnosisReportPG.dedup_key == dedup_key
                    )
                )
                pg_report = result.scalar_one_or_none()
                if pg_report and pg_report.status == "completed":
                    return await self._load_full_report(pg_report)
                if pg_report and pg_report.status in ("failed",):
                    return await self._load_full_report(pg_report)
        logger.warning(f"等待诊断报告超时, dedup_key={dedup_key}")
        return self._empty_report(dedup_key.split("_")[0], {})

    def _empty_report(self, run_id: str, degradation: dict) -> DiagnosisReport:
        """空的诊断报告（无失败日志时返回）"""
        return DiagnosisReport(
            report_id=str(uuid4()),
            run_id=run_id,
            status="completed",
            summary={"total_failures": 0, "root_cause_counts": {}},
            findings=[],
            degradation=degradation,
            completed_at=datetime.now(timezone.utc),
        )

    def _emergency_report(self, run_id: str, error: str) -> DiagnosisReport:
        """应急报告（诊断引擎自身崩溃时返回）"""
        return DiagnosisReport(
            report_id=str(uuid4()),
            run_id=run_id,
            status="failed",
            summary={"total_failures": 0, "root_cause_counts": {}},
            findings=[],
            degradation={
                "has_db_logs": False, "has_kg_locations": False,
                "has_llm_analysis": False,
                "fallback_reason": f"诊断引擎崩溃: {error[:200]}"
            },
            completed_at=datetime.now(timezone.utc),
        )

    def _dedup_logs(self, logs: list[dict]) -> list[dict]:
        """日志去重（按 endpoint + method + status_code）"""
        seen = set()
        deduped = []
        for log in logs:
            key = (
                log.get("endpoint", ""),
                log.get("method", ""),
                log.get("status", "") or log.get("status_code", ""),
            )
            if key not in seen:
                seen.add(key)
                deduped.append(log)
        return deduped

    def _calc_degradation_level(self, degradation: dict) -> str:
        """计算降级等级"""
        if degradation.get("has_db_logs") and degradation.get("has_kg_locations"):
            return "none"
        if degradation.get("has_db_logs"):
            return "partial"
        return "severe"

    async def _load_full_report(self, pg_report: DiagnosisReportPG) -> DiagnosisReport:
        """从 MongoDB 读取完整报告"""
        collection = self.mongodb.db.get_collection("diagnosis_reports")
        doc = await collection.find_one({"report_id": str(pg_report.mongo_id)})
        if doc:
            return DiagnosisReport(**doc)
        # MongoDB 数据丢失时，从 PG 重建概要报告
        return DiagnosisReport(
            report_id=str(pg_report.id),
            run_id=str(pg_report.run_id),
            project_id=str(pg_report.project_id),
            status=pg_report.status,
            summary=pg_report.summary_json or {},
            findings=[],
            completed_at=datetime.now(timezone.utc),
        )

    def _load_failure_rules(self) -> list[dict]:
        """
        加载失败规则库

        热更新策略：
        - 首次加载时缓存到内存（带 TTL 60s）
        - 每次分类前检查缓存是否过期
        - 过期后重新读取 YAML
        - 提供 POST /api/v2/diagnosis/rules/reload 手动刷新
        - 也可通过文件系统 watch（watchfiles）监听变更
        """
        # 实现略
        pass

    def _match_rule(self, log: dict, rule: dict) -> bool:
        """
        匹配单条规则

        规则匹配逻辑：
        1. status_code 条件：列表为空/为 "*" 时跳过；否则检查 log 的 status_code 是否在列表中
        2. error_patterns 条件：只要有一个正则匹配日志的 error_message 即视为匹配
        3. 两个条件同时满足才算匹配

        匹配优先级（在 _classify_failures 中控制）：
        - 规则按 priority 降序排列
        - 命中即停（高优先级规则优先）
        """
        status_ok = True
        sc_list = rule.get("conditions", {}).get("status_code", [])
        if sc_list and sc_list != ["*"]:
            log_status = str(log.get("status_code", "") or log.get("status", ""))
            status_ok = log_status in [str(s) for s in sc_list]

        error_ok = False
        patterns = rule.get("conditions", {}).get("error_patterns", [])
        if not patterns:
            error_ok = True
        else:
            log_error = str(log.get("error_message", "") or log.get("error", ""))
            import re
            for pat in patterns:
                if re.search(pat, log_error, re.IGNORECASE):
                    error_ok = True
                    break

        return status_ok and error_ok

    def _classify_failures(self, logs: list[dict]) -> list[dict]:
        """
        失败模式分类逻辑

        采用规则 + LLM 混合策略：
        - 规则层（快速）：HTTP 401 → token_expired 等
        - LLM 层（精确）：对规则无法判断的，调用 LLM 分析

        规则库从外部 YAML 加载，支持热更新：
        backend/config/failure_rules.yaml
        """
        # 从外部 YAML 加载规则（含优先级）
        rules = self._load_failure_rules()  # 按 priority 降序排列

        results = []
        llm_candidates = []

        for log in logs:
            matched = False
            for rule in rules:
                if rule["enabled"] and self._match_rule(log, rule):
                    results.append({
                        "log": log,
                        "type": rule["category"],
                        "confidence": rule["confidence"],
                        "classifier": "rule",
                        "matching_rule": rule["id"],
                        "llm_cache_hit": False,
                    })
                    matched = True
                    break  # 高优先级规则优先匹配

            if not matched:
                llm_candidates.append(log)

        # LLM 兜底处理
        if llm_candidates:
            llm_results = self._llm_classify(llm_candidates)
            results.extend(llm_results)

        # 合并日志信息和分类结果
        return self._merge_with_logs(results, logs)
```

### 5.2 失败模式分类策略

```
规则引擎（外部 YAML 配置）:

# backend/config/failure_rules.yaml
rules:
  - id: token_expired_rule_1
    category: token_expired
    priority: 100
    enabled: true
    conditions:
      status_code: [401]
      error_patterns:
        - "token.*expir"
        - "invalid_token"
        - "unauthorized"
        - "jwt.*invalid"
        - "access_token.*invalid"
    confidence: 0.95
    description: "Token 过期或无效"

  - id: permission_denied_rule_1
    category: permission_denied
    priority: 95
    enabled: true
    conditions:
      status_code: [403]
      error_patterns:
        - "forbidden"
        - "insufficient"
        - "permission.*denied"
        - "not.*allowed"
        - "role.*required"
    confidence: 0.90
    description: "权限不足（已认证但无授权）"

  - id: api_changed_rule_1
    category: api_changed
    priority: 90
    enabled: true
    conditions:
      status_code: [404]
      error_patterns:
        - "not found"
        - "no route"
        - "no endpoint"
    confidence: 0.90
    description: "API 端点已变更或下架"

  - id: api_changed_rule_2
    category: api_changed
    priority: 80
    enabled: true
    conditions:
      status_code: [400, 422]
      error_patterns:
        - "column.*not found"
        - "field.*unknown"
        - "unknown column"
    confidence: 0.85
    description: "数据库字段或 API Schema 变更"

  - id: data_error_rule_1
    category: data_error
    priority: 70
    enabled: true
    conditions:
      status_code: [400]
      error_patterns:
        - "validation"
        - "constraint"
        - "not null"
        - "invalid.*format"
    confidence: 0.85
    description: "请求数据格式或验证失败"

  - id: network_timeout_rule_1
    category: network_timeout
    priority: 60
    enabled: true
    conditions:
      status_code: [504, 502, 503]
      error_patterns:
        - "timeout"
        - "ETIMEDOUT"
        - "ECONNREFUSED"
        - "connection refused"
    confidence: 0.90
    description: "网络超时或服务不可用"

  - id: script_error_rule_1
    category: script_error
    priority: 50
    enabled: true
    conditions:
      status_code: []        # 不限制状态码
      error_patterns:
        - "TypeError"
        - "ReferenceError"
        - "SyntaxError"
        - "cannot read property"
        - "is not a function"
    confidence: 0.95
    description: "测试脚本自身代码错误"

LLM 兜底（带缓存）:

诊断缓存 diagnosis_cache.py:
┌──────────────────────────────────────────────────────────┐
│ LLM 分析缓存 (Redis / 内存)                               │
│ Key: sha256(f"{status_code}|{method}|{endpoint}|{error_message}")
│       # 含上下文避免误命中：同样的 "not found" 在不同端点上
│       # 可能有完全不同的根因（api_changed vs data_error）
│ Value: {"type": "token_expired",         │
│         "confidence": 0.92,              │
│         "reason": "..."}                 │
│ TTL:   24h                               │
│                                          │
│ 命中率预估: 同一 error_message 在 24h 内  │
│ 重复率约 30-50%（批量测试的常见错误）      │
└──────────────────────────────────────────┘

LLM 兜底提示词:
"""
你是一个测试失败根因分析专家。
给定以下 HTTP 请求和响应，分析失败的根本原因。

端点: {method} {path}
状态码: {status_code}
响应体: {response_body}
错误消息: {error_message}

请从以下类别中选择：
- token_expired: Token 过期或无效，需要重新认证
- permission_denied: 已认证但权限不足，需要检查角色权限配置
- api_changed: API 端点或参数已变更，与测试脚本不匹配
- data_error: 请求数据格式错误或测试数据不完整
- network_timeout: 网络超时或服务不可用
- script_error: 测试脚本本身的代码错误
- unknown: 无法确定根因

输出格式：JSON {"type": "...", "confidence": 0-1, "reason": "..."}
"""

分层抽样策略（失败数 > MAX_LLM_ANALYSIS 时）:
1. 先按 status_code 分组（401 一组，404 一组...）
2. 每组按 error_message 的相似度聚簇（编辑距离 < 0.3）
3. 每簇抽 1 条送 LLM
4. 同簇的其他失败继承 LLM 分类结果（confidence 下调 0.1）
→ 保证每类失败都有代表性样本，大幅减少 token 消耗

Token 成本估算（以 DeepSeek 为参考）:
+=====================+========+=========+=========+
| 场景                 | 条数   | 输入 tok | 成本    |
+=====================+========+=========+=========+
| 规则层命中           | 10     | 0       | $0.00  |
| LLM 兜底（无缓存）   | 10     | ~3000   | ~$0.006 |
| LLM 兜底（有缓存 50%）| 10     | ~1500   | ~$0.003 |
| 极端场景（30 条失败） | 30     | ~6000   | ~$0.012 |
| + 分层抽样（10 条）   | 30     | ~3000   | ~$0.006 |
+=====================+========+=========+=========+
结论：即使极端场景，单次诊断的 LLM 成本 < $0.02，可以忽略。
```

### 5.3 KG 代码定位策略（含超时/重试/降级）

```python
class KGIntegrationTools:
    """KG 集成工具（带超时、重试和降级）"""

    TIMEOUT = 3.0
    MAX_RETRIES = 2
    RETRY_DELAY = 0.5

    async def search_code(self, *keywords, file_glob=None) -> KGSearcResult:
        """搜索代码（带超时和重试）"""
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    kg_search_code(*keywords, file_glob=file_glob),
                    timeout=self.TIMEOUT
                )
                if result.matches or attempt == self.MAX_RETRIES:
                    return result
            except asyncio.TimeoutError:
                logger.warning(f"KG search timeout (attempt {attempt+1})")
            except Exception as e:
                logger.warning(f"KG search error (attempt {attempt+1}): {e}")

            if attempt < self.MAX_RETRIES:
                await asyncio.sleep(self.RETRY_DELAY)

        return KGSearcResult(matches=[])  # 降级返回空结果

    async def get_symbol_context(self, symbol: str) -> KGSymbolResult:
        """获取符号上下文（带超时和重试）"""
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    kg_get_symbol_context(symbol),
                    timeout=self.TIMEOUT
                )
                if result.found or attempt == self.MAX_RETRIES:
                    return result
            except (asyncio.TimeoutError, Exception):
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(self.RETRY_DELAY)
        return KGSymbolResult(found=False)

    async def impact_analysis(self, symbol: str) -> KGImpactResult:
        """影响分析（带超时和重试）"""
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    kg_impact_analysis(symbol),
                    timeout=self.TIMEOUT
                )
                return result
            except (asyncio.TimeoutError, Exception):
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(self.RETRY_DELAY)
        return KGImpactResult(affected=[])


async def _locate_in_code(self, failure: dict) -> list[CodeLocation]:
    """多策略并行级联定位（4 策略通过 asyncio.gather 并行执行）"""
    kg = KGIntegrationTools()
    endpoint = failure.get("endpoint", "")
    error_msg = failure.get("error_message", "")
    root_cause = failure.get("root_cause_type", "")

    # 准备并行任务
    tasks = []
    strategies = {}  # task_index -> strategy_name

    # 策略 1: 从 Endpoint 路径定位路由层
    path_segments = endpoint.strip("/").split("/")
    for seg in path_segments:
        if seg and seg not in ("api", "v1", "v2"):
            tasks.append(kg.search_code(seg, file_glob="*route*"))
            strategies[len(tasks) - 1] = "route_layer"

    # 策略 2: 从错误关键词定位逻辑层
    import re
    symbols = re.findall(r'[A-Za-z_]\w+', error_msg)
    for sym in symbols[:3]:  # 限制最多 3 个符号（减少并行任务数）
        tasks.append(kg.get_symbol_context(sym))
        strategies[len(tasks) - 1] = "logic_layer"

    # 策略 3: 从根因类型定位中间件层
    keyword_map = {
        "token_expired": ("middleware", "auth", "token"),
        "permission_denied": ("permission", "role", "rbac"),
        "api_changed": (*path_segments[-2:],),
    }
    if root_cause in keyword_map:
        tasks.append(kg.search_code(*keyword_map[root_cause]))
        strategies[len(tasks) - 1] = "middleware_layer"

    # 并行执行所有 KG 调用
    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 收集结果
    locations = []
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            continue  # 单策略失败不阻断
        if hasattr(result, "matches") and result.matches:
            locations.append(self._to_location(result, strategies.get(idx, "unknown")))
        if hasattr(result, "found") and result.found:
            locations.append(self._to_location(result, strategies.get(idx, "unknown")))

    # 策略 4: 影响分析（依赖策略 1-3 的结果，串行执行）
    if locations:
        top_symbol = locations[0].symbol
        try:
            impact = await asyncio.wait_for(
                kg.impact_analysis(top_symbol), timeout=KGIntegrationTools.TIMEOUT
            )
            locations[0].affected_calls = impact.affected
        except (asyncio.TimeoutError, Exception):
            pass  # 影响分析失败不阻断

    return locations
```

### 5.4 诊断任务去重与状态机

```
状态机:

                  ┌──────────┐
                  │ 不存在    │
                  └────┬─────┘
                       │ diagnose_run() 调用
                       ▼
                  ┌──────────┐
                  │ analyzing│  ← PG 已插入记录（dedup_key 唯一约束）
                  └────┬─────┘   重复请求返回 "analyzing" 状态
                       │
              ┌────────┴────────┐
              ▼                 ▼
       ┌──────────┐     ┌──────────┐
       │ completed│     │  failed  │
       └──────────┘     └──────────┘

幂等性保证:
┌─────────────────────────────────────────────────────────┐
│ 1. PG 表 dedup_key 有 UNIQUE 约束                       │
│ 2. INSERT ... ON CONFLICT DO NOTHING 防止并发插入        │
│ 3. 诊断中收到重复请求 → 返回 analyze 状态 + 轮询等待      │
│ 4. 诊断完成后收到重复请求 → 直接返回已存在的报告           │
│ 5. Redis 分布式锁（可选）用于多实例场景                    │
└─────────────────────────────────────────────────────────┘

[新增] 强制重新诊断：
- 用户在界面上点击 "重新诊断"
- 使用新的 dedup_key（在原 key 后加 "_retry_{count}"）
- 旧报告标记为 "superseded"
```

---

## 6. Agent 设计

### 6.1 日志分析 Agent

```python
# backend/app/agents/log_analysis/agent.py

SYSTEM_PROMPT = """# 日志分析专家

你是一个资深的测试日志分析专家。接收失败的测试日志后，你需要：

1. 分析错误日志，判断失败根因
2. 利用知识图谱定位对应的源码位置
3. 生成带有代码标注的诊断报告
4. 给出可操作的修复建议

## 工具

- query_test_logs: 查询测试运行日志
- get_log_detail: 获取单条日志的详细信息
- diagnose_failure: 分析失败根因（含 LLM + 规则引擎）
- kg_search_code: 在源码中搜索关键词（超时 3s，自动重试 2 次）
- kg_symbol_context: 获取符号定义和调用信息
- kg_impact_analysis: 分析符号变更的影响范围
- save_diagnosis_report: 保存诊断报告到数据库
- notify_frontend: 推送诊断进展到前端

## 工作流程

第一步: query_test_logs 获取失败日志列表
第二步: get_log_detail 获取关键失败的详细信息
第三步: diagnose_failure + KG 工具定位代码
第四步: 保存报告 + 推送前端

## 容错原则

- KG 不可用时，跳过代码定位，报告中标注 "代码定位暂不可用"
- 单条日志诊断失败不影响其他日志的分析
- 异常情况要记录到报告的 degradation 字段
"""

@asynccontextmanager
async def make_log_analysis_agent(config=None):
    """创建日志分析 Agent"""
    model = await _load_model(config)
    all_tools = get_log_analysis_tools()

    log_agent = create_agent(
        model=model,
        tools=all_tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=[SkillsMiddleware(backend=..., sources=["/skills/"])],
        backend=workspace_backend,
        context_schema=LogAnalysisContext,
    )
    yield log_agent
```

### 6.2 API Agent 诊断触发机制

```python
# backend/app/agents/api/tools/diagnosis_trigger_tools.py

@tool
async def diagnose_test_run(
    run_id: str,
    project_identifier: str,
    test_output: str = "",
) -> str:
    """
    对测试运行结果进行分析诊断。

    当测试执行失败时调用此工具，它将：
    1. 自动收集失败日志
    2. 调用日志分析引擎定位根因
    3. 通过 KG 定位源码位置
    4. 保存诊断报告并推送前端

    注意：此工具是异步非阻塞的。调用后立即返回 report_id，
    诊断在后台执行。API Agent 无需阻塞等待诊断完成即可继续后续操作。
    如果修复流程需要诊断结果，可通过 report_id 轮询或 WebSocket 获取。

    Args:
        run_id: 测试运行 ID（从 execute_api_script 返回）
        project_identifier: 项目标识符
        test_output: 测试执行的标准输出（可选，用于补充信息）

    Returns:
        立即返回 {"report_id": "...", "status": "analyzing"}，
        不阻塞 API Agent 的主流程。
    """
```

在 API Agent 的 System Prompt 中增加指令：

```
### 测试失败后的处理

当执行测试失败时（execute_api_script 或 run_tests 返回失败状态），
必须按以下步骤处理：

1. 调用 diagnose_test_run(run_id, project_identifier) 启动诊断
   - 此工具立即返回，不阻塞
   - 诊断在后台异步执行
2. 继续执行修复流程（参考 healer skill）
   - 修复时可通过 report_id 引用正在生成的诊断结果
3. 诊断完成后，如果结果包含代码位置，优先尝试在修复时调整对应代码
```

---

## 7. A2A 协议暴露（阶段二）

### 7.1 职责边界与设计原则

```
A2A 协议 vs MCP 调用的职责边界：

┌─────────────────────────────────────────────────────────┐
│                                                         │
│  A2A 对外暴露            MCP 内部调用                    │
│  ────────────            ────────────                    │
│                                                         │
│  目的: 让外部 Agent /    目的: API Agent 内部触发诊断     │
│       系统发现和调用                                     │
│                                                         │
│  协议: HTTP + SSE       协议: stdio（同进程 MCP）        │
│                                                         │
│  鉴权: 需要 API Key     鉴权: 同进程，无需鉴权           │
│                                                         │
│  返回: A2A Task 标准    返回: Python dict                │
│       Schema                                           │
│                                                         │
│  底层复用: 两个入口最终都调用 TestDiagnosisService       │
│  ─────────────────────────────────────────────────────  │
│  核心逻辑同一份，只在外层协议和鉴权上区分                  │
│                                                         │
└─────────────────────────────────────────────────────────┘

为什么不是互斥而是互补？
- API Agent → MCP 调用（同进程，零开销，测试失败自动触发）
- 外部 Agent / CI 系统 → A2A 调用（HTTP，跨进程，手动触发）
- 内部场景永远走 MCP，外部场景永远走 A2A
```

### 7.2 A2A Agent Card

```python
# GET /api/v2/a2a/agent-card
A2A_AGENT_CARD = {
    "name": "TestLogAnalyzer",
    "description": "分析 API 测试日志，定位代码问题",
    "url": "https://host/api/v2/a2a",
    "version": "1.0.0",
    "capabilities": {
        "streaming": True,
        "push_notifications": True,
        "state_transition_webhooks": False,
    },
    "auth": {                       # 新增：鉴权要求
        "type": "api_key",
        "in": "header",
        "key_name": "X-A2A-API-Key"
    },
    "skills": [
        {
            "id": "log_diagnosis",
            "name": "测试日志诊断",
            "description": "分析测试执行日志，输出根因和代码位置",
            "input": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "project_identifier": {"type": "string"},
                    "test_output": {"type": "string"}
                }
            },
            "output": {
                "type": "object",
                "properties": {
                    "report_id": {"type": "string"},
                    "status": {"type": "string"},
                    "summary": {"type": "object"}
                }
            }
        }
    ]
}
```

### 7.3 A2A Task API

```python
# POST /api/v2/a2a/tasks/send          # 创建诊断任务
# GET  /api/v2/a2a/tasks/{task_id}     # 查询任务状态
# GET  /api/v2/a2a/tasks/{task_id}/stream  # SSE 流式推送

A2A_TASK_SCHEMA = {
    "id": str,          # Task ID
    "status": str,      # "pending" | "working" | "completed" | "failed"
    "input": dict,      # 输入参数
    "output": dict,     # 诊断报告
    "metadata": {
        "created_at": datetime,
        "completed_at": datetime,
        "progress": int,     # 0-100
        "stage": str         # "collecting" | "classifying" | "locating" | "reporting"
    }
}

# A2A 端点内部实现：
@router.post("/a2a/tasks/send")
async def create_diagnosis_task(request: A2ATaskRequest):
    """内部复用 TestDiagnosisService"""
    # 1. 鉴权验证（API Key）
    # 2. 创建 Task 记录
    # 3. 异步调用 TestDiagnosisService.diagnose_run()
    # 4. 返回 Task ID（客户端轮询或 SSE）
```

### 7.4 A2A 客户端工具（给 API Agent 用）

```python
# backend/app/agents/api/tools/a2a_tools.py

@tool
async def a2a_diagnose(
    run_id: str,
    project_identifier: str,
    a2a_endpoint: str = "http://localhost:8000/api/v2/a2a",
    api_key: str = "",
) -> str:
    """
    通过 A2A 协议调用日志分析 Agent

    发送诊断任务，轮询等待完成，返回诊断报告。
    这是远程调用方式（与本地 MCP 调用互补）。

    使用场景：
    - 日志分析 Agent 部署在独立服务时
    - 外部 CI/CD 系统调用诊断
    - 需要通过 A2A 协议与第三方系统集成
    """
    # 1. POST /a2a/tasks/send 创建任务
    # 2. 轮询 GET /a2a/tasks/{task_id} 直到 completed/failed
    # 3. 返回诊断报告
```

---

## 8. 前端推送

### 8.1 WebSocket 端点（含可靠性设计）

```python
# backend/app/api/v2/diagnosis.py

# WebSocket 后端选用策略：
# 单实例部署 → 内存 ConnectionManager
# 多实例部署 → Redis Pub/Sub 广播 + ConnectionManager
#
# 推荐：直接上 Redis Pub/Sub，避免后期重构

class ConnectionManager:
    """
    带心跳检测的 WebSocket 连接管理器

    架构：
    - publish 层：诊断引擎通知 → Redis Channel
    - subscribe 层：每个实例的 connection manager 订阅 Redis
    - 每个 WS 连接有独立的心跳协程

    可靠性保证：
    - 心跳间隔 30s，丢失 3 次（90s）判定断开
    - "completed" 事件等待客户端 ack
    - 断线用户下次打开页面时，通过 REST API 获取未读报告
    """
    HEARTBEAT_INTERVAL = 30
    HEARTBEAT_MISS_LIMIT = 3

    def __init__(self, redis_client=None):
        self.active: dict[str, list[WebSocketConnection]] = {}
        self.redis = redis_client

    async def connect(self, project_id: str, websocket):
        """建立连接并启动心跳"""
        conn = WebSocketConnection(websocket)
        self.active.setdefault(project_id, []).append(conn)
        # 启动心跳检测协程
        asyncio.create_task(self._heartbeat_loop(conn, project_id))

    async def _heartbeat_loop(self, conn, project_id):
        """心跳检测"""
        miss_count = 0
        while conn.connected:
            try:
                await asyncio.wait_for(
                    conn.websocket.send_json({"type": "ping"}),
                    timeout=10
                )
                miss_count = 0
            except:
                miss_count += 1
                if miss_count >= self.HEARTBEAT_MISS_LIMIT:
                    self.disconnect(project_id, conn)
                    break
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)

    async def send_progress(self, project_id: str, data: dict):
        """
        推送诊断进展

        如果配置了 Redis：
        - publish 到 channel: "diagnosis:{project_id}"
        - 所有实例的 subscriber 收到后转发到本地连接
        """
        if self.redis:
            await self.redis.publish(f"diagnosis:{project_id}", json.dumps(data))
        else:
            await self._broadcast(project_id, data)

    async def send_completed(self, project_id: str, data: dict):
        """
        推送诊断完成事件（并发 ack，不阻塞引擎）

        1. 并发向所有客户端发送 completed 消息
        2. 每个客户端有独立 3s ack 超时
        3. 未 ack 的客户端记录到未读列表
        4. 发送动作本身不阻塞，总耗时 = 单个 ack 超时而非 N x 超时
        """
        connections = self.active.get(project_id, [])
        if not connections:
            await self._record_unread(project_id, data)
            return

        async def _send_and_wait(conn):
            try:
                await asyncio.wait_for(
                    conn.websocket.send_json(data), timeout=5
                )
                # 等待 ack
                msg = await asyncio.wait_for(
                    conn.websocket.receive_json(), timeout=3
                )
                if msg.get("type") == "ack" and msg.get("report_id") == data.get("report_id"):
                    return True
            except (asyncio.TimeoutError, Exception):
                pass
            return False

        # 并发发送 + 等待 ack
        results = await asyncio.gather(
            *[_send_and_wait(c) for c in connections],
            return_exceptions=True
        )

        unread_connections = [
            c for c, r in zip(connections, results)
            if not r or isinstance(r, Exception)
        ]
        if unread_connections:
            await self._record_unread(project_id, data)


@router.websocket("/ws/diagnosis/{project_id}")
async def diagnosis_websocket(websocket, project_id: str):
    await manager.connect(project_id, websocket)
    # 连接建立后，主动推送未读报告
    unread = await manager.get_unread_reports(project_id)
    if unread:
        await websocket.send_json({
            "type": "unread_reports",
            "reports": unread
        })
    try:
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "pong":
                pass  # 心跳响应
            elif msg.get("type") == "ack":
                await manager.handle_ack(project_id, msg["report_id"])
    except:
        manager.disconnect(project_id, websocket)
```

### 8.2 推送消息格式

```json
{
    "type": "diagnosis_progress",
    "report_id": "uuid-xxx",
    "progress": 45,
    "stage": "locating_code",
    "stage_label": "正在定位代码位置...",
    "findings_so_far": [
        {
            "endpoint": "GET /api/v2/users",
            "root_cause": "token_expired",
            "code_file": "src/middleware/auth.ts:42"
        }
    ]
}
```

```json
{
    "type": "diagnosis_completed",
    "report_id": "uuid-xxx",
    "summary": {
        "total_failures": 3,
        "token_expired": 2,
        "api_changed": 1
    },
    "degradation": {
        "has_kg_locations": false,
        "has_llm_analysis": true,
        "fallback_reason": "KG MCP 服务超时"
    },
    "report_url": "/api/v2/diagnosis/reports/uuid-xxx"
}
```

### 8.3 前端展示示意

```
┌─────────────────────────────────────────────────────┐
│ 🔍 测试诊断报告 · 运行 #R-0032                       │
├─────────────────────────────────────────────────────┤
│                                                      │
│  失败总数: 5    已定位: 4    修复建议: 3              │
│  数据质量: ⚠️ KG 不可用，代码定位为文本推断           │
│                                                      │
│  ┌─ 根因分布 ──────────────────────────────────┐     │
│  │  Token 过期    ████████████ 2                 │     │
│  │  API 变更      ██████      1                 │     │
│  │  数据错误      ██████      1                 │     │
│  │  未知          ██         1                  │     │
│  └──────────────────────────────────────────────┘     │
│                                                      │
│  ┌─ 详细发现 ──────────────────────────────────┐     │
│  │                                                │     │
│  │  ❌ POST /api/v2/orders   [401]               │     │
│  │     ├ 根因: Token 过期                        │     │
│  │     ├ 定位: src/middleware/auth.ts:42         │     │
│  │     │       → verifyToken()                   │     │
│  │     └ 建议: 未实现 refresh_token 机制         │     │
│  │       [查看代码] [标记已处理]                    │     │
│  │                                                │     │
│  │  ❌ GET /api/v2/products/{id}  [404]           │     │
│  │     ├ 根因: API 端点已变更                    │     │
│  │     ├ 定位: src/routes/products.ts:15         │     │
│  │     │       → getProduct()                    │     │
│  │     └ 建议: 接口路径从 /v2 → /v3              │     │
│  │       [查看代码] [标记已处理]                    │     │
│  │                                                │     │
│  └──────────────────────────────────────────────┘     │
│                                                      │
│  [重新诊断] [导出报告] [查看趋势]                      │
└─────────────────────────────────────────────────────┘
```

---

## 9. 日志分析 Agent SKILL

```markdown
# Log Diagnosis Skill

## 触发条件

当以下情况时加载此 SKILL：
- 测试执行返回非 2xx 状态码
- 测试超时
- 测试脚本抛出异常
- 用户要求分析测试日志

## 诊断步骤

### 1. 收集失败信息
```
query_test_logs(run_id=run_id, status_filter="failed")
→ 获取失败日志列表
```

### 2. 逐条分析
```
for each failed log:
    get_log_detail(log_id, include_full_request=true, include_full_response=true)
    diagnose_failure(status_code, request, response, error_message)
    → 根因分类 + 置信度
```

### 3. 代码定位
```
for each diagnosed failure:
    # 分层定位
    路由层: kg_search_code(endpoint_segments, "route")
    逻辑层: kg_symbol_context(symbol_name)
    中间件层: kg_search_code("middleware", root_cause_keywords)
    影响分析: kg_impact_analysis(symbol_name)
    → 代码位置列表（按置信度排序）

注意：KG 调用有 3s 超时和 2 次重试，不可用时跳过定位步骤。
```

### 4. 生成报告
```
save_diagnosis_report(report)
notify_frontend(project_id, report)
```

## 常见失败模式对照表

| 状态码 | 典型错误消息 | 根因类型 | 定位策略 |
|--------|-------------|---------|---------|
| 401 | "Token expired" / "invalid token" | token_expired | search "auth" + "middleware" |
| 403 | "Forbidden" / "insufficient permissions" | permission_denied | search "permission" + "role" + "rbac" |
| 404 | "Route not found" / "no endpoint" | api_changed | search route file by path |
| 400 | "Validation failed" / "missing field" | data_error | search model/validator by field name |
| 500 | "Internal Server Error" | server_error | search controller + stack trace symbols |
| 504 | "Gateway Timeout" | network_timeout | search upstream client config |
| N/A | "TypeError: xxx is not a function" | script_error | N/A (测试脚本自身问题) |
```

---

## 10. 与现有系统的集成

### 10.1 API Agent Prompt 更新

```python
# 在 agent.py 中添加 diagnose_test_run 工具的引用
# 现有 SkillsMiddleware 会自动加载新工具

# 需要部署的操作：
# 1. 添加 diagnosis_trigger_tools.py 到 tool_registry.py 的 get_local_tools()
# 2. 更新 agent.py 的 SYSTEM_PROMPT，增加"测试失败后的处理"章节
# 3. 重新部署 LangGraph Agent API（重启端口 2026 服务）

# Prompt 版本管理策略：
# - SYSTEM_PROMPT 是静态文本，修改后需重启 LangGraph 服务
# - 关键诊断逻辑在 test_diagnosis_service.py 中，热更新不需要重启 Agent
# - SKILL.md 文件支持热加载（SkillsMiddleware 在每次调用时重新读取）
```

### 10.2 LangGraph 配置更新

```json
// langgraph.json 新增 assistant（阶段二）
{
    "assistants": [
        {
            "assistant_id": "log_analysis_agent",
            "graph": "backend/app/agents/log_analysis/agent.py:make_log_analysis_agent",
            "config": {
                "workspace_root": "backend/workspace/diagnosis"
            }
        }
    ]
}
```

### 10.3 与 Allure 报告的关系

```
诊断报告和 Allure 报告的关系：
- Allure：记录"测试执行了什么"（请求/响应、断言、截图）
- 诊断：回答"为什么失败"（根因、代码位置、修复建议）
- 两者互补：在 Allure 报告中嵌入诊断报告 ID，在诊断报告中引用 Allure 附件

具体实现：
- Allure 报告的 report_path（MinIO ZIP）可以存储到诊断报告的 metadata 中
- 前端在展示诊断报告时，提供"查看 Allure 报告"的链接
```

### 10.4 API 端点注册

```python
# backend/app/main.py 或 router 注册文件中新增
from app.api.v2 import diagnosis as diagnosis_router
from app.api.v2 import a2a as a2a_router

app.include_router(diagnosis_router.router)
app.include_router(a2a_router.router)  # 阶段二
```

---

## 11. 实施计划

### 阶段一：核心诊断功能（7-9 天，含容错和降级）

| 步骤 | 任务 | 产出 | 依赖 |
|------|------|------|------|
| 1.1 | 建 MongoDB + PG 诊断报告模型 | `diagnosis_report.py`, migration | MongoDB/PG 连接 |
| 1.2 | 实现日志查询工具（带超时） | `log_query_tools.py` | 步骤 1.1 |
| 1.3 | 实现规则库配置文件 | `failure_rules.yaml` | 无 |
| 1.4 | 实现诊断引擎（含去重/降级/缓存） | `test_diagnosis_service.py`, `diagnosis_cache.py` | 步骤 1.2+1.3 |
| 1.5 | 实现 KG 集成工具（超时/重试） | `kg_integration_tools.py` | KG MCP Server |
| 1.6 | 实现日志分析 Agent | `agent.py` + `SKILL.md` | 步骤 1.4+1.5 |
| 1.7 | API Agent 触发集成 | `diagnosis_trigger_tools.py` + Prompt 更新 | 步骤 1.6 |
| 1.8 | 单元测试 + 集成测试 | `tests/test_diagnosis*.py` | 所有以上 |

### 阶段二：A2A + 前端推送（4-5 天）

| 步骤 | 任务 | 产出 | 依赖 |
|------|------|------|------|
| 2.1 | 实现 WebSocket 推送（含 Redis Pub/Sub + 心跳） | `diagnosis_notification_service.py` | FastAPI + Redis |
| 2.2 | 实现诊断 REST API | `diagnosis.py` | 阶段一 |
| 2.3 | 实现 A2A Agent Card + Task API + 鉴权 | `a2a.py` | FastAPI |
| 2.4 | 实现 A2A 客户端工具 | `a2a_tools.py` | 步骤 2.3 |
| 2.5 | 注册 LangGraph 新 assistant | `langgraph.json` 更新 | 阶段一 |
| 2.6 | 前端连接 WebSocket + 诊断组件 | 前端代码 | 步骤 2.1 |

### 阶段三：优化与完善（3-4 天）

| 步骤 | 任务 | 说明 |
|------|------|------|
| 3.1 | 规则库监控面板 | 规则命中率统计，便于优化规则 |
| 3.2 | 诊断报告趋势分析 | 按周/月统计根因分布，推送到前端 |
| 3.3 | 与 Allure 报告集成 | 在诊断中引用 Allure 截图/附件 |
| 3.4 | 前端组件完善 | 诊断树交互、代码跳转、标记已处理 |
| 3.5 | 性能基准测试 | 使用 locust 做压力测试 |
| 3.6 | 安全审计 | 敏感数据脱敏 + 权限校验 |

---

## 12. 安全与隐私

### 12.1 敏感数据处理

```
诊断过程中涉及的敏感数据：
┌────────────────────────────────────────────────────┐
│ 数据类别        示例               处理方式          │
├────────────────────────────────────────────────────┤
│ Authorization 头  "Bearer xxx..."   LLM 调用前脱敏   │
│ 密码字段         "password": "***"  LLM 调用前脱敏   │
│ Token/API Key    "access_token"     存库前脱敏       │
│ 用户 PII         身份证号/手机号     LLM 调用前脱敏   │
│ 请求/响应体      业务数据           按需脱敏          │
└────────────────────────────────────────────────────┘

脱敏策略:
1. 在 _collect_failure_logs() 中，对 headers/body 执行脱敏
2. 脱敏规则：移除/替换已知敏感字段的值（不修改字段名，保留分析信息）
3. 完整原始日志始终在 MongoDB 中保留（诊断引擎不删除它）
4. 诊断报告中只存脱敏后的快照

敏感字段列表（可配置）:
SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key", "token"}
SENSITIVE_BODY_FIELDS = {"password", "secret", "token", "accessToken",
                         "refreshToken", "creditCard", "phone", "idCard"}
```

### 12.2 LLM 数据合规

```
- 默认配置下，LLM 调用使用本地 DeepSeek 服务（数据不出服务器）
- 如果切换到外部 LLM（如 OpenAI），需明确告知用户数据将传输到第三方
- 诊断引擎提供 dry_run 模式：只走规则引擎，不走 LLM 兜底
- 所有发送给 LLM 的数据都经过脱敏处理
```

### 12.3 A2A 鉴权

```
A2A 端点鉴权方案：
┌──────────────────────────────────────────────┐
│ 方式: API Key（静态，配置在环境变量中）         │
│                                               │
│ 请求头: X-A2A-API-Key: <key>                 │
│                                               │
│ 配置: A2A_API_KEYS=["key1", "key2"]          │
│                                               │
│ 未鉴权的请求: 401 + "Missing or invalid API   │
│               key"                            │
│                                               │
│ 鉴权范围: 所有 A2A 端点，包括 Agent Card       │
│ （Agent Card 在公网暴露时需要鉴权）             │
└──────────────────────────────────────────────┘
```

### 12.4 最小权限原则

```
- 日志分析 Agent 对 MongoDB 只有读权限
- 对 PostgreSQL 只有诊断报告表的读写权限
- 对 KG MCP Server 只有搜索和查询权限（无写权限）
- A2A 调用日志分析 Agent 只允许触发诊断，不能读写其他数据
```

---

## 13. 性能验证方案

### 13.1 测试环境

```
硬件:
- CPU: 4 核
- 内存: 8 GB
- 网络: 内网 1Gbps

组件:
- MongoDB: 与生产环境同规格
- PG: 与生产环境同规格
- KG MCP Server: 同实例
- LLM: DeepSeek（本地服务）

基线数据:
- 100 条 `api_test_logs` 记录（50 条失败）
- 50 条 `scenario_step_results` 记录（30 条失败）
- KG 已索引 5000+ 源码文件
```

### 13.2 性能基准工具

```bash
# 使用 locust 做压力测试
# locustfile: tests/load_test/diagnosis_load_test.py

# 单次诊断延迟测试
$ pytest tests/test_diagnosis_perf.py -k "test_diagnose_10_failures" --benchmark

# 并发诊断测试
$ locust -f tests/load_test/diagnosis_load_test.py \
  --host http://localhost:8000 \
  --users 10 --spawn-rate 1 --run-time 60s
```

### 13.3 性能指标与通过标准

| 指标 | 目标 | 测试方法 | 通过标准 |
|------|------|---------|---------|
| 规则层分类延迟 | < 100ms | pytest-benchmark 10条失败 | P90 < 100ms |
| KG 定位延迟（单条） | < 1s | pytest-benchmark 单条失败 | P95 < 1s |
| KG 定位延迟（10 条） | < 10s | pytest-benchmark 10条失败 | P95 < 10s |
| LLM 分析延迟（单条） | < 5s | pytest-benchmark 单条兜底 | P95 < 5s |
| 前端推送延迟 | < 200ms | 手动测量 WebSocket 到 console | P99 < 200ms |
| 完整诊断（10 条规则命中） | < 5s | 测试脚本全链路计时 | P95 < 5s |
| 完整诊断（10 条含 LLM） | < 15s | 测试脚本全链路计时 | P95 < 15s |
| 并发 10 请求 | 不阻塞 | locust 压力测试 | 错误率 < 1%, P95 < 30s |

### 13.4 优化预案

```
如果指标未达标，按优先级执行：

1. LLM 兜底延迟 > 5s
   → 降低 LLM 超时到 5s，超时则标记为 "unknown"
   → 增加缓存命中率（延长 TTL 到 48h）

2. KG 定位延迟 > 1s
   → 降低超时到 2s
   → 将 4 个策略改为并行执行（asyncio.gather）
   → 增加 KG MCP Server 的并发连接数

3. 诊断整体 > 15s
   → 并行化日志采集 + 分类（asyncio.gather）
   → 减少 LLM 兜底采样数从 10 降到 5
   → 启用 redis 缓存所有规则匹配结果

4. WebSocket 推送延迟 > 200ms
   → 消息批量化（多个 finding 打包推送）
   → 增加推送协程的并发数
```

---

## 14. 风险与权衡

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| KG 精度不足导致代码定位偏差 | 中 | 中 | 多策略级联 + 置信度打分 + 降级标注 |
| LLM 分析耗时过长（>30s） | 中 | 高 | 先用规则引擎快速分类，LLM 兜底有超时控制 + WebSocket 推送进度 |
| A2A Python 实现有不兼容 | 高 | 中 | 先做内部 MCP 调用再扩展 A2A；MCP 调用始终可用，A2A 是可选增强 |
| 大量失败日志诊断 token 消耗 | 中 | 低 | 分层抽样 + LLM 缓存 + 规则层优先；极端场景成本 < $0.02 |
| 防火墙限制 KG 查询 | 低 | 中 | MongoDB 日志本身包含足够信息，KG 定位作为增强层 |
| 日志 Agent 与 API Agent 上下文冲突 | 低 | 中 | 独立 Agent 实例，独立 context window |
| 规则库膨胀导致匹配性能下降 | 低（远期） | 低 | 规则支持启用/禁用开关；匹配时按 priority 排序，命中即停 |
| WebSocket 多实例部署消息丢失 | 中 | 中 | Redis Pub/Sub 广播 + reconnection pull 未读报告 |

---

## 15. 部署检查清单与数据生命周期

### 15.1 启动时强制校验

```
┌─────────────────────────────────────────────────────────┐
│ 部署检查清单                                              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 环境变量                                                  │
│ [ ] PUBLIC_API_URL: A2A Agent Card 的 url 字段来源        │
│     → f"{settings.PUBLIC_API_URL}/api/v2/a2a"           │
│ [ ] INSTANCE_COUNT: 实例数量（>1 时 Redis 强制）           │
│ [ ] REDIS_URL: Redis 连接地址（多实例时必须配置）           │
│ [ ] A2A_API_KEYS: A2A 鉴权 Key 列表                      │
│ [ ] DIAGNOSIS_REPORT_TTL_DAYS: 报告保留天数（默认 90）    │
│                                                         │
│ 启动时校验                                                │
│ [ ] INSTANCE_COUNT > 1 且 REDIS_URL 未配置 → 报错退出    │
│ [ ] MongoDB 连接是否正常                                  │
│ [ ] PG diagnosis_reports 表是否存在                       │
│ [ ] failure_rules.yaml 是否存在且格式有效                  │
│                                                         │
│ 可选增强                                                  │
│ [ ] watchfiles 安装（规则库热更新监听）                     │
│ [ ] LLM 缓存 Redis 配置（多实例共享缓存）                   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 15.2 诊断报告数据生命周期

```
保留期限: 90 天（由 DIAGNOSIS_REPORT_TTL_DAYS 控制）

清理策略:
- MongoDB: 每 24h 执行 TTL 索引清理（MongoDB 原生 TTL index）
- PG: 每 24h 定时任务 DELETE FROM diagnosis_reports
       WHERE created_at < NOW() - INTERVAL '90 days'

归档方案（可选）:
- 90 天前的报告迁移到 MinIO 冷存储（JSON 格式）
- PG 中只保留最简记录：id + created_at + minio_path
- 前端查看归档报告时从 MinIO 按需加载

注意事项:
- 删除前检查是否有关联的测试运行仍然活跃
- 归档操作在业务低峰期执行（如凌晨 3 点）
- 提供手动 "保留此报告" 功能（前端标记，跳过清理）
```

---

## 16. 验证标准

### 16.1 功能验收

| 测试场景 | 预期结果 |
|---------|---------|
| 模拟 401 失败的测试运行 | Agent 检测到 token_expired，定位到 middleware/auth.ts |
| 模拟 403 失败的测试运行 | Agent 检测到 permission_denied，定位到 permission/role 模块 |
| 模拟 404 失败的测试运行 | Agent 检测到 api_changed，定位到 routes/xxx.ts |
| 模拟混合失败（2个 401 + 1个 500）| 报告包含 3 条发现，根因分类正确 |
| 规则引擎命中 | 报告 classifier 字段为 "rule"，记录 matching_rule ID |
| LLM 兜底命中 | 报告 classifier 字段为 "llm"，记录 llm_cache_hit |
| 相同 error_message 重复诊断 | 第二条命中 LLM 缓存，cost 为 0 |
| 无失败日志的健康运行 | 返回空报告，不启动分析流程 |
| MongoDB 不可用 | 报告 degradation.has_db_logs=false，基于 test_output 降级分析 |
| KG 不可用（超时/空结果） | 报告 degradation.has_kg_locations=false，代码定位为空 |
| 极端情况（最外层 try/except） | 返回 emergency_report（status=failed），不抛服务器异常 |
| 同一 run 并发诊断请求 | 第一次创建，后续返回 existing/analyzing，不重复 |
| WebSocket 断线重连 | 重连后推送未读报告列表 |
| 诊断结果推送到前端 | WebSocket 收到 progress + completed 事件 |
| A2A 外部调用 | GET agent-card 返回正确 schema，带鉴权信息 |
| A2A 未鉴权请求 | 返回 401 |
| API Agent 失败后自动触发 | 执行失败后，诊断报告自动生成并关联到 run_id |
| 规则库热更新 | 修改 YAML 后，最多 60s 内生效（TTL 缓存过期即重新加载） |
| 多实例部署未配 Redis | 启动时报错退出 |

### 16.2 性能标准

| 指标 | 目标 | 测试方法 | 最小样本量 |
|------|------|---------|-----------|
| 规则层分类延迟 | < 100ms | pytest-benchmark 10条失败 | 30 次 |
| KG 定位延迟（单条） | < 1s | pytest-benchmark 单条失败 | 30 次 |
| KG 定位延迟（10 条并行） | < 5s | pytest-benchmark 10条失败 | 30 次 |
| LLM 分析延迟（单条兜底） | < 5s | pytest-benchmark 单条兜底 | 30 次 |
| 前端推送延迟 | < 200ms | 手动测量 WebSocket 到 console | 50 次 |
| 完整诊断（10 条规则命中） | < 5s | 测试脚本全链路计时 | 30 次 |
| 完整诊断（10 条含 LLM） | < 15s | 测试脚本全链路计时 | 30 次 |
| 并发 10 请求 | 错误率 < 1%, P95 < 30s | locust 压力测试 | 持续 60s |
