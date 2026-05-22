"""
API Agent 工具模块

本目录包含所有 API 测试智能体的工具定义，按功能分类组织。
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from .openapi_tools import (
    list_api_endpoints,
    get_endpoint_details,
    get_multiple_endpoints_details,
    get_folder_structure,
)

from .test_artifacts_tools import (
    save_test_plan,
    save_test_cases,
    save_test_script,
    get_endpoint_artifacts,
    get_artifact_content,
)

from .test_execution_tools import (
    run_tests,
    run_test_suite,
    parse_test_results,
)

from .script_tools import (
    get_api_script_info,
    download_api_script,
    delete_api_script,
)

from .script_execution_tools import (
    execute_api_script,
    get_test_execution_status,
)

from .batch_tools import (
    batch_generate_tests,
    batch_run_tests,
)

from .scenario_tools import (
    create_test_scenario,
    update_test_scenario,
    add_scenario_step,
    update_scenario_step,
    add_data_mapping,
    add_step_extractor,
    add_step_assertion,
    get_scenario_details,
    list_test_scenarios,
    execute_scenario,
)

__all__ = [
    # OpenAPI 文档管理工具
    "list_api_endpoints",
    "get_endpoint_details",
    "get_multiple_endpoints_details",
    "get_folder_structure",

    # 测试成果物管理工具
    "save_test_plan",
    "save_test_cases",
    "save_test_script",
    "get_endpoint_artifacts",
    "get_artifact_content",

    # 测试执行工具
    "run_tests",
    "run_test_suite",
    "parse_test_results",

    # 脚本管理工具
    "get_api_script_info",
    "download_api_script",
    "delete_api_script",

    # 脚本执行工具
    "execute_api_script",
    "get_test_execution_status",

    # 批量操作工具
    "batch_generate_tests",
    "batch_run_tests",

    # 场景测试工具
    "create_test_scenario",
    "update_test_scenario",
    "add_scenario_step",
    "update_scenario_step",
    "add_data_mapping",
    "add_step_extractor",
    "add_step_assertion",
    "get_scenario_details",
    "list_test_scenarios",
    "execute_scenario",
]
