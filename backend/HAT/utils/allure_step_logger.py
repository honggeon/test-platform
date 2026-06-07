'''
Author: hongge
Date: 2026-05-25 16:15:58
LastEditors: hongge
LastEditTime: 2026-06-04 22:39:42
FilePath: /ai-test-agent-system-platform/backend/HAT/utils/allure_step_logger.py
Description:
Version: 0.1
'''

import io
from contextlib import contextmanager

import allure
from loguru import logger


class StepLogCollector:

    def __init__(self):
        self.log_buffer = io.StringIO()  # 创建一个笔记本
        self.sink_id = None  # 笔记本的id  身份证号

    def __enter__(self):
        self.sink_id = logger.add(self.log_buffer, level="DEBUG")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logger.remove(self.sink_id)  # 移除id
        log_context = self.log_buffer.getvalue()  # 获取日志信息
        if log_context.strip():
            allure.attach(
                log_context,
                name="步骤日志",
                attachment_type=allure.attachment_type.TEXT
            )
        self.log_buffer.close()


@contextmanager  # 包装器  支持with语法 普通函数支持with写法
def allure_step_with_log(step_name):  # 用例步骤
    with allure.step(step_name):  # 发送登陆接口 提取数据
        with StepLogCollector() as collector:  # 创建一个笔记本  记录步骤日志
            yield collector  # 暂停执行
