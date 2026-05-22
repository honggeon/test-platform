"""
API v2 模块

包含 v2 版本的所有 API 端点
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from . import projects, folders, test_cases, test_runs, test_results, test_plans, attachments, configurations, llm_config, api_tests, api_tests_extended, api_endpoints, scenarios, web_tests, web_functions, test_reports, code_repo, code_analysis, diagnosis

__all__ = [
    "projects",
    "folders",
    "test_cases",
    "test_runs",
    "test_results",
    "test_plans",
    "attachments",
    "configurations",
    "llm_config",
    "api_tests",
    "api_tests_extended",
    "api_endpoints",
    "scenarios",
    "web_tests",
    "web_functions",
    "test_reports",
    "code_analysis",
    "diagnosis",
]

