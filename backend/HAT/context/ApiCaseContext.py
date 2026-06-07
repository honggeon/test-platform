'''
Author: Developer dev@example.com
Date: 2026-05-25 16:15:56
LastEditors: Developer dev@example.com
LastEditTime: 2026-06-03 14:41:04
FilePath: /ai-test-agent-system-platform/backend/HAT/context/ApiCaseContext.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
'''
import requests

from HAT.core.globalContext import g_context
from HAT.keywords.api_keywords import Keywords

_global_request_obj=None
class ApiCaseContext:
    def __init__(self):
        self.request=None
        self.keywords=None

    # 复用session
    def init_keywords(self):
        #到哪是session复用还是不复用
        session_reuse=g_context().get_dict("session_reuse")#获取全局变量session_reuse的值
        # 如果session_reuse是复用 True 就创建一个 session 保存在全局变量中 后续用例中复用
        if session_reuse is not None and session_reuse==True:
            global  _global_request_obj
            if _global_request_obj is None:#如果全局变量没有值，新建session对象
                _global_request_obj=requests.session()#第一次是没有session的，第二次有session的
            self.request=_global_request_obj#使用全局实例
        else:#如果session_reuse是false  每次都创建session对象
            self.request=requests.session()
        self.keywords=Keywords(self.request)
        return self.keywords




    def release(self):
        pass