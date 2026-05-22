"""
日志分析 Agent 工具集

导出所有日志分析相关工具，供 Agent 工厂统一加载。
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""

from typing import List

from langchain_core.tools import BaseTool

from app.agents.log_analysis.tools.diagnosis_tools import (
    diagnose_failure,
    notify_frontend,
    save_diagnosis_report,
)
from app.agents.log_analysis.tools.log_query_tools import get_log_detail, query_test_logs


def get_log_analysis_tools() -> List[BaseTool]:
    """获取日志分析 Agent 的所有本地工具列表

    返回可用于 deepagents 创建 Agent 的工具列表。
    """
    return [
        query_test_logs,
        get_log_detail,
        diagnose_failure,
        save_diagnosis_report,
        notify_frontend,
    ]
