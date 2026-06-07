"""HAT 步骤解析测试"""
from HAT.utils.step_runner import normalize_step_fields, parse_step, split_request_and_post


def test_parse_step_canonical_format():
    step = {"用户登录": {"操作类型": "发送请求POST", "请求地址": "/login"}}
    name, value = parse_step(step)
    assert name == "用户登录"
    assert value["操作类型"] == "发送请求POST"


def test_parse_step_flat_format():
    step = {
        "用例名称": "用户登录",
        "操作类型": "发送请求POST",
        "请求体": {"email": "a@b.com"},
    }
    name, value = parse_step(step)
    assert name == "用户登录"
    assert value["操作类型"] == "发送请求POST"
    assert "用例名称" not in value


def test_normalize_request_body_alias():
    step = {"操作类型": "发送请求POST", "请求体": {"x": 1}}
    normalized = normalize_step_fields(step)
    assert normalized["请求数据"] == {"x": 1}
    assert normalized["请求类型"] == "json"


def test_split_request_and_post():
    step = {
        "操作类型": "发送请求POST",
        "请求地址": "/login",
        "断言文本相等": {"期望结果": "200", "实际结果": "{{status_code}}"},
    }
    request_part, post_part = split_request_and_post(step)
    assert request_part["操作类型"] == "发送请求POST"
    assert "断言文本相等" in post_part
