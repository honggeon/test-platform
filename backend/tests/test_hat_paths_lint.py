"""HAT 路径与 YAML 校验工具测试"""

from pathlib import Path

from app.utils.hat_paths import (
    build_canonical_case_rel_dir,
    derive_case_slug,
    detect_misplaced_linux_path,
    sanitize_workspace_relative_path,
    slugify_case_name,
)
from app.utils.hat_yaml_lint import lint_hat_yaml_content, lint_hat_case_dir


def test_slugify_case_name():
    assert slugify_case_name("GET /api/v2/projects/{id}/api-endpoints") == \
        "get_api_v2_projects_id_api_endpoints"


def test_derive_case_slug():
    slug = derive_case_slug(
        "GET",
        "/api/v2/projects/{project_identifier}/api-endpoints",
        "GET /api/v2/projects/{project_identifier}/api-endpoints",
    )
    assert "get" in slug
    assert "api" in slug


def test_build_canonical_case_rel_dir():
    rel = build_canonical_case_rel_dir("PR-1", "list_api_endpoints")
    assert rel == "tests/PR-1/api-tests/list_api_endpoints"


def test_sanitize_linux_home_path():
    raw = (
        "/home/hongge/test-platform/ai-test-agent-system-platform/"
        "backend/workspace/api/tests/PR-1/api-tests/list_api_endpoints"
    )
    cleaned = sanitize_workspace_relative_path(raw)
    assert cleaned == "tests/PR-1/api-tests/list_api_endpoints"


def test_detect_misplaced_linux_path():
    assert detect_misplaced_linux_path("/home/hongge/foo") is True
    assert detect_misplaced_linux_path("tests/PR-1/api-tests/foo") is False


def test_lint_rejects_length_jsonpath():
    content = """
用例步骤:
  - 提取:
      操作类型: 提取数据JSON
      表达式: "$.length()"
      变量名: count
"""
    errors = lint_hat_yaml_content(content, "bad.yaml")
    assert errors
    assert any("length" in e for e in errors)


def test_lint_accepts_index_jsonpath(tmp_path: Path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "0_test.yaml").write_text(
        '用例步骤:\n  - 提取:\n      操作类型: 提取数据JSON\n'
        '      表达式: "$[0].id"\n      变量名: first_id\n',
        encoding="utf-8",
    )
    assert lint_hat_case_dir(case_dir) == []
