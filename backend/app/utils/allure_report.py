"""Allure CLI helpers and result parsing (cross-platform)."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any


def build_allure_generate_argv(results_dir: Path | str, output_dir: Path | str) -> list[str]:
    """
    Build argv for `allure generate` that works on Windows (.cmd/.bat shims).

    asyncio.create_subprocess_exec cannot invoke bare `allure` on Windows when it
    resolves to a .cmd shim; use cmd /c or the explicit .bat path instead.
    """
    results_dir = str(results_dir)
    output_dir = str(output_dir)
    generate_args = ["generate", results_dir, "-o", output_dir, "--clean"]

    configured = os.environ.get("ALLURE_BIN", "").strip()
    if configured:
        return _wrap_allure_executable(configured, generate_args)

    found = shutil.which("allure")
    if found:
        return _wrap_allure_executable(found, generate_args)

    if sys.platform == "win32":
        return ["cmd", "/c", "allure", *generate_args]

    return ["allure", *generate_args]


def _wrap_allure_executable(exe: str, args: list[str]) -> list[str]:
    if sys.platform == "win32" and exe.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", exe, *args]
    return [exe, *args]


def parse_allure_results_dir(results_dir: Path) -> dict[str, Any] | None:
    """Parse HAT/pytest Allure *-result.json files into a structured report."""
    if not results_dir.exists():
        return None

    result_files = sorted(results_dir.glob("*-result.json"))
    if not result_files:
        return None

    tests: list[dict[str, Any]] = []
    passed = failed = skipped = broken = 0
    total_duration_ms = 0

    for path in result_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        status = data.get("status", "unknown")
        if status == "passed":
            passed += 1
        elif status == "failed":
            failed += 1
        elif status == "skipped":
            skipped += 1
        elif status == "broken":
            broken += 1

        start = data.get("start") or 0
        stop = data.get("stop") or 0
        duration_ms = max(0, stop - start)
        total_duration_ms += duration_ms

        tests.append({
            "name": data.get("name") or data.get("fullName") or path.stem,
            "status": status,
            "duration_ms": duration_ms,
            "error": _extract_allure_failure(data),
        })

    if not tests:
        return None

    return {
        "summary": {
            "total": len(tests),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "broken": broken,
            "total_duration_ms": total_duration_ms,
        },
        "tests": tests,
    }


def _extract_allure_failure(data: dict[str, Any]) -> str | None:
    status_details = data.get("statusDetails") or {}
    message = status_details.get("message")
    if message:
        return str(message)

    for step in data.get("steps") or []:
        if step.get("status") in {"failed", "broken"}:
            details = step.get("statusDetails") or {}
            if details.get("message"):
                return str(details["message"])
    return None
