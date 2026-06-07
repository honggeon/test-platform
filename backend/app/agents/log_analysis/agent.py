"""
日志分析智能体

该智能体负责测试失败日志的自动诊断：
- 查询失败日志（MongoDB + PostgreSQL）
- 规则引擎 + LLM 兜底进行根因分类
- 利用知识图谱定位源码位置
- 生成诊断报告并推送前端

架构设计：
- Agent: 工作流编排与诊断决策
- Skills: 诊断领域知识与最佳实践指导
- Tools: 原子操作（数据库查询、KG 搜索、报告管理）
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from deepagents import create_deep_agent as create_agent
from deepagents.middleware import SkillsMiddleware
from langchain.chat_models import init_chat_model
from langgraph.pregel import Pregel

from app.agents.log_analysis.tools import get_log_analysis_tools
from app.config.settings import settings
from app.utils.filesystem import FixedFilesystemBackend

# =============================================================================
# 后端配置
# =============================================================================

skills_root = Path(settings.log_analysis_skills_root).resolve()
skills_backend = FixedFilesystemBackend(root_dir=skills_root, virtual_mode=True)

workspace_root = Path(settings.log_analysis_workspace_root).resolve()
workspace_backend = FixedFilesystemBackend(root_dir=workspace_root, virtual_mode=True)


# =============================================================================
# 上下文定义
# =============================================================================

@dataclass
class LogAnalysisContext:
    """日志分析智能体运行时上下文"""
    project_identifier: str = ""
    run_id: str = ""


# =============================================================================
# 系统提示词
# =============================================================================

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
- save_diagnosis_report: 保存诊断报告到数据库
- notify_frontend: 推送诊断进展到前端

## 工作流程
第一步: query_test_logs 获取失败日志列表
第二步: get_log_detail 获取关键失败的详细信息
第三步: diagnose_failure 分析根因
第四步: 保存报告 + 推送前端

## 容错原则
- KG 不可用时，跳过代码定位，报告中标注 "代码定位暂不可用"
- 单条日志诊断失败不影响其他日志的分析
- 异常情况要记录到报告的 degradation 字段
"""


# =============================================================================
# 智能体工厂
# =============================================================================

@asynccontextmanager
async def make_agent(config=None) -> AsyncIterator[Pregel]:
    """
    创建日志分析智能体的工厂函数。

    使用 asynccontextmanager 模式确保智能体生命周期内资源正确管理。
    """
    model = init_chat_model("deepseek:deepseek-chat")
    all_tools = get_log_analysis_tools()

    log_agent = create_agent(
        model=model,
        tools=all_tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=[SkillsMiddleware(backend=skills_backend, sources=["/"])],
        backend=workspace_backend,
        context_schema=LogAnalysisContext,
    )
    yield log_agent


# 导出 make_agent 供 LangGraph API 使用
agent = make_agent
