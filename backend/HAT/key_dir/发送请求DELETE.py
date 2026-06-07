import requests
import allure
from HAT.core.globalContext import g_context


class 发送请求DELETE:
    """自定义关键字：发送 DELETE 请求"""

    def __init__(self, request):
        self.request = request

    @allure.step("发送请求DELETE")
    def 发送请求DELETE(self, **kwargs):
        self.show_log("发送请求DELETE", kwargs)

        请求地址 = kwargs.get("请求地址", "")
        请求头 = kwargs.get("请求头", {})

        session = g_context().get_dict("session")
        if session is None:
            session = requests.session()
            g_context().set_dict("session", session)

        response = session.delete(url=请求地址, headers=请求头)
        g_context().set_dict("响应结果", response)
        g_context().set_dict("status_code", str(response.status_code))

        self.show_log("响应结果", {
            "status_code": response.status_code,
            "body": response.text[:500]
        })

        return response

    @staticmethod
    def show_log(title, content):
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"-------Log{title}-----")
        logger.debug(f"{title}:{content}")
        logger.debug(f"-------END Log{title}-----")
