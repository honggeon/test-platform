#!/usr/bin/env python3
"""
HAT 路径修复验证脚本（Windows / Linux 通用）

在虚拟环境中从 backend/ 目录运行:
    python scripts/verify_hat_paths.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.utils.hat_paths import (  # noqa: E402
    format_key_dirs_cli,
    get_api_workspace_root,
    get_api_workspace_tests_dir,
    get_hat_home,
    get_hat_key_dir,
    get_run_hat_path,
    resolve_hat_cases_dir,
    resolve_hat_key_dirs,
    sanitize_workspace_relative_path,
)
from app.config.settings import settings  # noqa: E402


NESTED_CASE_SRC = (
    BACKEND_DIR
    / "workspace/api/home/hongge/test-platform/ai-test-agent-system-platform"
    / "backend/workspace/api/tests/hat_workspace/373945ca-e53e-48f2-9863-3c4e764f4bc7"
)
VERIFY_CASE_DIR = (
    BACKEND_DIR / "workspace/api/tests/hat_verify/373945ca-e53e-48f2-9863-3c4e764f4bc7"
)
WORKSPACE_ROOT = get_api_workspace_root()


def check_path_resolution() -> list[str]:
    errors: list[str] = []

    run_hat = get_run_hat_path()
    key_dir = get_hat_key_dir()
    hat_home = get_hat_home()

    print("=== 路径解析 ===")
    print(f"  hat_home:    {hat_home}")
    print(f"  run_hat.py:  {run_hat} (exists={run_hat.exists()})")
    print(f"  key_dir:     {key_dir} (exists={key_dir.exists()})")
    print(f"  conftest.py: {hat_home / 'conftest.py'} (exists={(hat_home / 'conftest.py').exists()})")

    if not run_hat.exists():
        errors.append(f"run_hat.py 不存在: {run_hat}")
    if not key_dir.exists():
        errors.append(f"key_dir 不存在: {key_dir}")
    if not (hat_home / "conftest.py").exists():
        errors.append(f"conftest.py 不存在: {hat_home / 'conftest.py'}")

    sanitized = sanitize_workspace_relative_path(
        "/home/hongge/test-platform/ai-test-agent-system-platform/backend/workspace/api/tests/hat_workspace/373945ca-e53e-48f2-9863-3c4e764f4bc7",
        WORKSPACE_ROOT,
    )
    expected = "tests/hat_workspace/373945ca-e53e-48f2-9863-3c4e764f4bc7"
    print(f"  sanitize:    {sanitized!r}")
    if sanitized != expected:
        errors.append(f"路径 sanitize 失败: 期望 {expected!r}, 实际 {sanitized!r}")

    cases = resolve_hat_cases_dir(
        "tests/hat_verify/373945ca-e53e-48f2-9863-3c4e764f4bc7",
        get_api_workspace_tests_dir(),
        WORKSPACE_ROOT,
    )
    print(f"  cases_dir:   {cases}")
    if not cases.exists():
        errors.append(f"用例目录不存在: {cases}")

    return errors


def prepare_verify_case() -> None:
    if NESTED_CASE_SRC.exists() and not VERIFY_CASE_DIR.exists():
        VERIFY_CASE_DIR.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(NESTED_CASE_SRC, VERIFY_CASE_DIR)
        print(f"=== 已复制用例到: {VERIFY_CASE_DIR} ===")
    elif VERIFY_CASE_DIR.exists():
        print(f"=== 用例目录已存在: {VERIFY_CASE_DIR} ===")
    else:
        VERIFY_CASE_DIR.parent.mkdir(parents=True, exist_ok=True)
        print(f"=== 警告: 嵌套用例源不存在，跳过复制: {NESTED_CASE_SRC} ===")

    context_yaml = VERIFY_CASE_DIR / "context.yaml"
    if context_yaml.exists():
        content = context_yaml.read_text(encoding="utf-8")
        if "{{API_BASE_URL}}" in content or "{{URL}}" in content:
            content = content.replace("{{API_BASE_URL}}", "http://localhost:8000")
            content = content.replace("{{URL}}", "http://localhost:8000")
            context_yaml.write_text(content, encoding="utf-8")


async def run_hat_direct() -> list[str]:
    errors: list[str] = []
    run_hat = get_run_hat_path()
    key_dir = get_hat_key_dir()
    hat_home = get_hat_home()
    cases_dir = resolve_hat_cases_dir(
        "tests/hat_verify/373945ca-e53e-48f2-9863-3c4e764f4bc7",
        get_api_workspace_tests_dir(),
        WORKSPACE_ROOT,
    )
    key_dirs = resolve_hat_key_dirs(cases_dir, key_dir)
    print(f"  key_dirs:    {[str(p) for p in key_dirs]}")

    cmd = [
        sys.executable,
        str(run_hat),
        "--type=yaml",
        f"--cases={cases_dir}",
        f"--keyDir={format_key_dirs_cli(key_dirs)}",
        "-v",
        "--tb=short",
    ]
    print("=== 直接运行 run_hat.py ===")
    print(f"  cwd: {hat_home}")
    print(f"  cmd: {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(hat_home),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, stderr_b = await proc.communicate()
    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    safe_out = stdout.encode("ascii", errors="replace").decode("ascii")
    safe_err = stderr.encode("ascii", errors="replace").decode("ascii")
    print(safe_out[-3000:] if len(safe_out) > 3000 else safe_out)
    if safe_err.strip():
        print("--- stderr ---")
        print(safe_err[-1500:] if len(safe_err) > 1500 else safe_err)

    print(f"  return_code: {proc.returncode}")

    if "collected" not in stdout and "collected" not in stderr:
        errors.append("pytest 未收集到测试用例")
    if proc.returncode not in (0, 1):
        errors.append(f"非预期返回码: {proc.returncode} (stderr: {safe_err[:200]})")

    return errors


async def run_via_execute_tool() -> list[str]:
    errors: list[str] = []
    try:
        from app.agents.api.tools.script_execution_tools import execute_api_script
    except ImportError as exc:
        errors.append(f"无法导入 execute_api_script: {exc}")
        return errors
    rel_path = "tests/hat_verify/373945ca-e53e-48f2-9863-3c4e764f4bc7"
    print("=== 通过 execute_api_script 工具 ===")
    print(f"  local_script_path: {rel_path}")

    result_json = await execute_api_script.ainvoke({
        "local_script_path": rel_path,
        "framework": "hat",
        "reporter": "list",
        "project_identifier": "PR-1",
    })
    result = json.loads(result_json)
    exec_result = result.get("execution_result", {})
    stdout = exec_result.get("stdout", "")
    stderr = exec_result.get("stderr", "")
    print(f"  success: {result.get('success')}")
    print(f"  return_code: {exec_result.get('return_code')}")
    if stdout:
        safe = stdout.encode("ascii", errors="replace").decode("ascii")
        print(safe[-2000:] if len(safe) > 2000 else safe)
    if stderr.strip():
        print("--- stderr ---")
        safe_err = stderr.encode("ascii", errors="replace").decode("ascii")
        print(safe_err[-1000:] if len(safe_err) > 1000 else safe_err)

    if not result.get("success") and exec_result.get("return_code") not in (0, 1):
        errors.append(f"execute_api_script 失败: {result.get('error') or exec_result.get('error')}")
    if "run_hat.py" in (stdout + stderr) and "不存在" in (stdout + stderr):
        errors.append("execute_api_script 未找到 run_hat.py")
    if not stdout and not stderr and result.get("error"):
        errors.append(result["error"])

    return errors


async def main() -> int:
    print(f"Platform: {sys.platform}")
    print(f"Python:   {sys.executable}")
    print(f"Backend:  {BACKEND_DIR}\n")

    prepare_verify_case()
    all_errors: list[str] = []
    all_errors.extend(check_path_resolution())
    all_errors.extend(await run_hat_direct())
    all_errors.extend(await run_via_execute_tool())

    print("\n=== 验证结果 ===")
    if all_errors:
        for err in all_errors:
            print(f"  FAIL: {err}")
        return 1

    print("  全部通过（路径解析 + run_hat 执行 + execute_api_script 工具链）")
    print("  注: 若 API 服务未启动，用例断言失败(return_code=1)属正常，关键是 pytest 能收集并执行")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
