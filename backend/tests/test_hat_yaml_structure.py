"""HAT YAML 结构校验测试"""

from pathlib import Path

from app.utils.hat_yaml_lint import lint_hat_case_dir, lint_hat_yaml_content


def test_rejects_config_tests_structure():
    content = """
config:
  base_url: "{{URL}}"
tests:
  - name: TC-01
    request:
      method: GET
"""
    errors = lint_hat_yaml_content(content, "bad.yaml", check_hat_structure=True)
    assert errors
    assert any("非 HAT 结构" in e for e in errors)


def test_accepts_hat_structure():
    content = """
基础配置:
  用例类型: ApiCase
  用例标题: demo
用例步骤:
  - 步骤:
      操作类型: 发送请求GET
      请求地址: "{{URL}}/api"
"""
    errors = lint_hat_yaml_content(content, "0_demo.yaml", check_hat_structure=True)
    assert errors == []


def test_case_dir_requires_numbered_yaml(tmp_path: Path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "context.yaml").write_text("URL: '{{API_BASE_URL}}'\n", encoding="utf-8")
    (case_dir / "list.yaml").write_text(
        "config:\n  x: 1\ntests: []\n",
        encoding="utf-8",
    )
    errors = lint_hat_case_dir(case_dir, strict=True)
    assert any("数字前缀" in e for e in errors)


def test_case_dir_passes_with_numbered_hat_yaml(tmp_path: Path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "context.yaml").write_text("URL: '{{API_BASE_URL}}'\n", encoding="utf-8")
    (case_dir / "0_login.yaml").write_text(
        "基础配置:\n  用例类型: ApiCase\n  用例标题: login\n"
        "用例步骤:\n  - s:\n      操作类型: 发送请求POST\n"
        "      请求地址: '{{URL}}'\n",
        encoding="utf-8",
    )
    assert lint_hat_case_dir(case_dir, strict=True) == []
