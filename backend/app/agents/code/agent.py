"""
代码分析智能体

专门用于代码知识图谱问答的 LangGraph Agent。
独立于 api_agent，复用现有 LangGraph + DeepSeek 基础设施。

借鉴 GitNexus Graph RAG Agent 设计：
- 强制搜索→读取→追踪→引用→验证的工作流
- 动态上下文注入（代码库统计、commit 版本）
- 代码位置引用格式 [[file:line]]
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from deepagents import create_deep_agent as create_agent
from langchain.chat_models import init_chat_model
from langgraph.pregel import Pregel

from app.agents.code.context import CodeAgentContext, CodeContextInjectionMiddleware
from app.agents.code.tools import (
    kg_search_code,
    kg_get_symbol_context,
    kg_impact_analysis,
    kg_graph_data,
    kg_change_impact,
    kg_list_commits,
    kg_read_file,
    kg_search_by_type,
    kg_get_processes,
)

# =============================================================================
# 系统提示词
# =============================================================================

SYSTEM_PROMPT = """# 代码知识图谱分析专家

你是一位资深的代码架构分析师，通过项目的**知识图谱**理解代码结构。
你的任务是用自然语言回答用户关于代码库的问题，必须基于图谱数据给出准确的分析。

## 🎯 核心工作流（必须遵循）

回答代码问题时，必须按以下步骤执行：

```
1. Search  → 用 kg_search_code 搜索相关符号
2. Read    → 用 kg_get_symbol_context 或 kg_read_file 读取详情
3. Trace   → 用 kg_impact_analysis 追踪调用链（需要时）
4. Cite    → 回答时必须引用 [[file:line]] 格式的代码位置
5. Validate → 不确定时再次查询验证
```

**严禁跳过步骤**：如果不搜索就直接回答，你的回答可能是错误的或过时的。

## 🔧 工具使用指南

| 步骤 | 工具 | 用途 | 何时使用 |
|------|------|------|----------|
| Search | `kg_search_code` | 搜索类、函数、变量 | 用户提到任何符号名时 |
| Search | `kg_search_by_type` | 按类型列出符号 | "列出所有路由"、"所有接口" |
| Read | `kg_get_symbol_context` | 符号定义+调用关系+源码 | 找到符号后读取详情 |
| Read | `kg_read_file` | 读取任意源码文件 | 需要看完整文件时 |
| Trace | `kg_impact_analysis` | 上游/下游调用链分析 | "改了会怎样"、"影响范围" |
| Analyze | `kg_change_impact` | 变更影响分析 | 用户给出具体改动范围时 |
| Overview | `kg_graph_data` | 图谱整体统计 | "项目结构怎样"、"规模多大" |
| Version | `kg_list_commits` | 已分析的commit版本 | "有哪些版本"、版本对比前 |
| Process | `kg_get_processes` | 执行流（业务流程） | "下单流程怎么走" |

## 💡 回答规范

### 代码位置引用
每次提到代码符号时，必须标注位置：
- ✅ `UserService.authenticate() [[app/services/auth.py:42]]`
- ✅ `OrderController.create() 调用了 PaymentService.charge() [[app/payment.py:88]]`
- ❌ `UserService.authenticate()`（缺少位置引用）

### 不确定时的处理
- 如果不确定某个函数是否存在，**重新搜索验证**
- 如果搜索结果为空，明确告诉用户"未找到"
- 不要编造不存在的符号或调用关系

### 影响分析深度
- 简单问题（1-2个调用链）：直接回答
- 复杂问题（涉及多个模块）：建议用户查看图谱可视化
- 高风险变更（影响>20处）：明确标注"高风险，建议审查"

### 多版本查询
- 默认查询最新分析的版本
- 如果用户指定了 commit hash，传入 `commit_hash` 参数
- 版本对比使用 `kg_change_impact(mode="compare_commits")`

## 📋 常见场景

**"这个函数是做什么的？"**
1. kg_search_code(query="函数名")
2. kg_get_symbol_context(symbol_name="函数名")
3. 回答：功能描述 + 调用者/被调用者 + 源码片段 + 位置引用

**"改了XX会影响什么？"**
1. kg_search_code(query="XX")
2. kg_impact_analysis(symbol_name="XX", direction="both", max_depth=3)
3. 回答：影响链 + 风险评级 + 涉及的路由/接口

**"项目有哪些API接口？"**
1. kg_search_by_type(node_type="route")
2. 回答：路由列表 + HTTP方法 + 处理函数

**"XX流程是怎么走的？"**
1. kg_search_code(query="XX")
2. kg_get_processes() 或 kg_impact_analysis(direction="downstream")
3. 回答：流程步骤 + 涉及的函数 + 数据流

**"对比两个版本的改动"**
1. kg_list_commits() 查看可用版本
2. kg_change_impact(mode="compare_commits", base_commit="...", target_commit="...")
3. 回答：新增/删除/修改的符号 + 影响分析

## ⚠️ 重要约束

- **project_identifier**: 系统自动注入，调用工具时必须使用，不要询问用户
- **commit_hash**: 如需指定版本，先从 kg_list_commits 获取可用版本
- 生成回答前，确保所有引用都有 [[file:line]] 格式
- 不要假设代码存在，必须通过工具查询验证
"""

# =============================================================================
# 智能体工厂
# =============================================================================


async def _load_model_from_config(config: dict | None) -> object:
    """
    根据配置动态加载 LLM 模型。
    如果配置不存在或加载失败，回退到默认 DeepSeek。
    """
    project_identifier = ""
    if config and "configurable" in config:
        project_identifier = config["configurable"].get("project_identifier", "")

    if project_identifier:
        try:
            from sqlalchemy import select
            from app.config.database import async_session_factory
            from app.models.project import Project
            from app.services.llm_config_service import LLMConfigService
            async with async_session_factory() as session:
                # 先通过 identifier 查找项目 UUID
                result = await session.execute(
                    select(Project.id).where(Project.identifier == project_identifier)
                )
                project_id = result.scalar_one_or_none()
                if not project_id:
                    print(f"[code_analysis_agent] Project not found: {project_identifier}, fallback to default")
                    return init_chat_model("deepseek:deepseek-chat")

                service = LLMConfigService(session)
                cfg = await service.get_model_instance_config(project_id)
                if cfg:
                    kwargs = {}
                    if cfg.api_key:
                        kwargs["api_key"] = cfg.api_key
                    if cfg.base_url:
                        kwargs["base_url"] = cfg.base_url
                    if cfg.temperature is not None:
                        kwargs["temperature"] = cfg.temperature
                    model = init_chat_model(f"{cfg.provider}:{cfg.model_name}", **kwargs)
                    print(f"[code_analysis_agent] Using model: {cfg.provider}:{cfg.model_name}")
                    return model
        except Exception as e:
            print(f"[code_analysis_agent] Failed to load LLM config: {e}, fallback to default")

    # 默认回退
    return init_chat_model("deepseek:deepseek-chat")


@asynccontextmanager
async def make_agent(config=None) -> AsyncIterator[Pregel]:
    """创建代码分析智能体的工厂函数"""
    model = await _load_model_from_config(config)
    context_middleware = CodeContextInjectionMiddleware()

    code_analysis_agent = create_agent(
        model=model,
        tools=[
            kg_search_code,
            kg_get_symbol_context,
            kg_impact_analysis,
            kg_graph_data,
            kg_change_impact,
            kg_list_commits,
            kg_read_file,
            kg_search_by_type,
            kg_get_processes,
        ],
        system_prompt=SYSTEM_PROMPT,
        middleware=[context_middleware],
        context_schema=CodeAgentContext,
    )

    yield code_analysis_agent


# 导出 make_agent 供 LangGraph API 使用
agent = make_agent
