'''
Author: Developer dev@example.com
Date: 2026-05-26 13:27:34
LastEditors: Developer dev@example.com
LastEditTime: 2026-06-03 14:42:17
FilePath: /ai-test-agent-system-platform/backend/HAT/core/TestRunner.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
'''
import copy

import allure
import pytest
from tqdm import tqdm

from HAT.context.ApiCaseContext import ApiCaseContext
from HAT.core.globalContext import g_context
from HAT.extend.script import run_script
from HAT.utils.VarRender import refresh
from HAT.utils.allure_step_logger import allure_step_with_log
from HAT.utils.step_runner import execute_step, parse_step


class TestRunner:
    def test_case_execute(self, caseinfo):
        base_info = caseinfo.get("基础配置", {})

        keywords = None
        if base_info.get("用例类型") == "ApiCase" or caseinfo.get("用例步骤"):
            keywords = ApiCaseContext().init_keywords()

        allure.dynamic.parameter("caseinfo", "")
        allure.dynamic.feature(base_info.get("一级模块", "默认模块"))
        allure.dynamic.story(base_info.get("二级模块", "默认模块"))
        allure.dynamic.title(
            base_info.get("用例标题")
            or base_info.get("场景名称")
            or base_info.get("用例名称")
            or "默认用例标题"
        )

        local_context = caseinfo.get("local_context", {})
        context = copy.deepcopy(g_context().show_dict())
        context.update(local_context)

        pre_script = refresh(caseinfo.get("前置脚本", None), context)
        if pre_script:
            for script in eval(pre_script):
                run_script.exec_script(script, g_context().show_dict())

        steps = caseinfo.get("用例步骤", None)

        with tqdm(total=len(steps), desc="开始执行") as pbar:
            for step in steps:
                step_name, _ = parse_step(step)
                pbar.set_description(
                    f'{base_info.get("用例标题") or base_info.get("场景名称", "")}-当前步骤:{step_name}'
                )
                pbar.update(1)
                with allure_step_with_log(step_name):
                    print("步骤", step_name)
                    execute_step(keywords, step, local_context)

        local_context = caseinfo.get("local_context", {})
        context = copy.deepcopy(g_context().show_dict())
        context.update(local_context)

        pre_script = refresh(caseinfo.get("后置脚本", None), context)
        if pre_script:
            for script in eval(pre_script):
                run_script.exec_script(script, g_context().show_dict())
