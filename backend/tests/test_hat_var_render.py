"""HAT 变量渲染工具测试"""
from HAT.utils.VarRender import preprocess_random_tokens, refresh


def test_preprocess_random_uuid():
    raw = 'name: "kb-{{ $random_uuid }}"'
    processed = preprocess_random_tokens(raw)
    assert "$random_uuid" not in processed
    assert "kb-" in processed


def test_preprocess_random_alphabetic():
    raw = 'name: "role_{{ $random.alphabetic(8) }}"'
    processed = preprocess_random_tokens(raw)
    assert "$random" not in processed
    assert "role_" in processed


def test_refresh_random_alphabetic_does_not_crash():
    context = {}
    result = refresh({"name": "测试角色_{{ $random.alphabetic(8) }}"}, context)
    assert "$random" not in result
