"""HAT 关键字增强测试"""

from HAT.keywords.api_keywords import (
    Keywords,
    _drop_empty_query_params,
    _normalize_compare_text,
)


def test_drop_empty_query_params():
    assert _drop_empty_query_params({"folder_id": "", "tag": "x"}) == {"tag": "x"}
    assert _drop_empty_query_params({"folder_id": None, "a": "1"}) == {"a": "1"}
    assert _drop_empty_query_params({}) is None


def test_normalize_compare_text_nfkc():
    assert _normalize_compare_text("参数验证失败") == _normalize_compare_text("参数验证失败")


def test_assert_text_being_contained():
    kw = Keywords(request=None)
    kw.断言文本被包含(期望结果="/api/v2/projects/", 实际结果="/api/v2/projects/PR-1/x")
