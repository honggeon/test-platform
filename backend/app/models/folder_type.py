"""
文件夹类型枚举
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from enum import Enum


class FolderType(str, Enum):
    """文件夹类型"""
    TEST_CASE = "test_case"  # 测试用例文件夹
    API_TEST = "api_test"    # API测试文件夹
    WEB_TEST = "web_test"    # Web测试文件夹
    SCENARIO_TEST = "scenario_test"  # 场景测试文件夹
