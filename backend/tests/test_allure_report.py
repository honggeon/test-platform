"""Tests for Allure CLI helpers."""

import sys
from pathlib import Path

from app.utils.allure_report import (
    build_allure_generate_argv,
    parse_allure_results_dir,
)


def test_build_allure_generate_argv_windows_uses_cmd_when_no_which(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        "app.utils.allure_report.shutil.which",
        lambda _name: None,
    )
    argv = build_allure_generate_argv("results", "out")
    assert argv[:3] == ["cmd", "/c", "allure"]
    assert argv[3:] == ["generate", "results", "-o", "out", "--clean"]


def test_build_allure_generate_argv_wraps_bat(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        "app.utils.allure_report.shutil.which",
        lambda _name: r"D:\allure\bin\allure.bat",
    )
    argv = build_allure_generate_argv("results", "out")
    assert argv[0:3] == ["cmd", "/c", r"D:\allure\bin\allure.bat"]


def test_parse_allure_results_dir(tmp_path: Path):
    results_dir = tmp_path / "allure-results"
    results_dir.mkdir()
    (results_dir / "a-result.json").write_text(
        '{"name": "case A", "status": "passed", "start": 100, "stop": 250}',
        encoding="utf-8",
    )
    (results_dir / "b-result.json").write_text(
        '{"name": "case B", "status": "failed", "start": 0, "stop": 50, '
        '"statusDetails": {"message": "assert failed"}}',
        encoding="utf-8",
    )

    parsed = parse_allure_results_dir(results_dir)
    assert parsed is not None
    assert parsed["summary"]["total"] == 2
    assert parsed["summary"]["passed"] == 1
    assert parsed["summary"]["failed"] == 1
    assert parsed["tests"][1]["error"] == "assert failed"
