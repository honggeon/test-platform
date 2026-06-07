"""HAT key_dir 路径解析测试"""

import os
from pathlib import Path

import pytest

from app.utils.hat_paths import format_key_dirs_cli, resolve_hat_key_dirs
from HAT.core.globalContext import g_context
from HAT.parse.YamlCaseParser import load_context_from_yaml
from HAT.utils.key_dir import get_key_dirs, init_key_dirs_from_cli, merge_case_key_dir


@pytest.fixture(autouse=True)
def reset_g_context():
    g_context._dic = {}
    yield
    g_context._dic = {}


def test_resolve_hat_key_dirs_merges_global_and_case(tmp_path):
    global_dir = tmp_path / "global_key_dir"
    global_dir.mkdir()
    cases_dir = tmp_path / "cases"
    case_key_dir = cases_dir / "key_dir"
    case_key_dir.mkdir(parents=True)

    resolved = resolve_hat_key_dirs(cases_dir, global_dir)
    assert resolved == [global_dir.resolve(), case_key_dir.resolve()]


def test_format_key_dirs_cli_uses_pathsep(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    formatted = format_key_dirs_cli([dir_a, dir_b])
    assert formatted == f"{dir_a.resolve()}{os.pathsep}{dir_b.resolve()}"


def test_init_key_dirs_from_cli_supports_multiple_paths(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    init_key_dirs_from_cli(format_key_dirs_cli([dir_a, dir_b]))
    assert get_key_dirs() == [str(dir_a.resolve()), str(dir_b.resolve())]


def test_merge_case_key_dir_resolves_relative_to_suite(tmp_path):
    suite = tmp_path / "cases"
    case_key_dir = suite / "key_dir"
    case_key_dir.mkdir(parents=True)
    init_key_dirs_from_cli(str(tmp_path / "global"))
    Path(tmp_path / "global").mkdir(exist_ok=True)

    merge_case_key_dir(suite, "./key_dir")
    assert str(case_key_dir.resolve()) in get_key_dirs()


def test_load_context_strips_key_dir_and_merges(tmp_path):
    suite = tmp_path / "cases"
    suite.mkdir()
    case_key_dir = suite / "key_dir"
    case_key_dir.mkdir()
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    init_key_dirs_from_cli(str(global_dir))

    (suite / "context.yaml").write_text(
        'URL: "http://example.com"\nkey_dir: "./key_dir"\nproject: "PR-1"\n',
        encoding="utf-8",
    )
    load_context_from_yaml(str(suite))

    assert g_context().get_dict("project") == "PR-1"
    assert g_context().get_dict("key_dir") == str(global_dir.resolve())
    assert str(case_key_dir.resolve()) in get_key_dirs()
