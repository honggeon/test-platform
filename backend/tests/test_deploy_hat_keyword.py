"""deploy_hat_keyword 工具测试"""

import pytest

from app.agents.api.tools.test_artifacts_tools import _validate_hat_keyword_module


VALID_MODULE = '''
import allure
from HAT.core.globalContext import g_context

class 生成签名:
    def __init__(self, request):
        self.request = request

    def 生成签名(self, **kwargs):
        g_context().set_dict("sign", "ok")
'''


def test_validate_hat_keyword_module_accepts_valid_template():
    assert _validate_hat_keyword_module("生成签名", VALID_MODULE) is None


def test_validate_hat_keyword_module_rejects_missing_class():
    error = _validate_hat_keyword_module("生成签名", "x = 1")
    assert error is not None
    assert "缺少" in error


def test_validate_hat_keyword_module_rejects_wrong_import():
    bad = VALID_MODULE.replace("globalContext", "ApiCaseContext")
    error = _validate_hat_keyword_module("生成签名", bad)
    assert error is not None
    assert "globalContext" in error
