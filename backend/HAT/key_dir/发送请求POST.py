'''
Author: hongge
Date: 2026-05-25 16:15:56
LastEditors: hongge
LastEditTime: 2026-06-04 22:38:25
FilePath: /ai-test-agent-system-platform/backend/HAT/key_dir/发送请求POST.py
Description:
Version: 0.1
'''

import allure
from loguru import logger

from HAT.core.globalContext import g_context


class 发送请求POST:
    def __init__(self, request):
        self.request = request

    @allure.step("发送请求POST")
    def 发送请求POST(self, **kwargs):
        url = kwargs.get('请求地址', None)
        params = kwargs.get('URL参数', None)
        headers = kwargs.get('请求头', None)
        data = kwargs.get('请求数据', None)
        files = kwargs.get('文件列表', [])
        data_type = kwargs.get('请求类型', "data").lower()  # 默认请求类型
        request_data = {
            "url": url,
            "params": params,
            "headers": headers,
            "files": files,
        }
        # 如果json   request_data['json']= data
        if data_type == "json":
            request_data["json"] = data
        elif data_type == "data":  # request_data['json']= data
            request_data["data"] = data
        else:
            raise Exception("请求类型错误")
        try:
            # self.request  必须是什么值才能发请求？  requests.request()   requests.session().request()
            response = self.request.request("post", **request_data)
            print("登陆响应数据", response.json())
            g_context().set_dict("响应结果", response)
            # 保存数据的逻辑  xxx
        except Exception as e:
            logger.error("发送请求有问题")
            raise
