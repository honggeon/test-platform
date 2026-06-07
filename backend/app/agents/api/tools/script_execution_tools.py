"""
API 测试脚本执行工具

提供在测试目录中执行 API 测试脚本的功能
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


import os
import sys
import json
import asyncio
import subprocess
import tempfile
import zipfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy import select

from app.config.minio_client import MinIOClient

from app.config import settings
from app.config.database import async_session_factory
from app.models.attachment import Attachment, AttachmentEntityType
from app.models.api_endpoint import APIEndpoint
from app.models.test_execution_log import TestExecutionLog
from app.utils.hat_paths import (
    format_key_dirs_cli,
    get_api_workspace_root,
    get_api_workspace_tests_dir,
    get_hat_home,
    get_hat_key_dir,
    get_run_hat_path,
    resolve_hat_cases_dir,
    resolve_hat_key_dirs,
    sanitize_workspace_relative_path,
    build_execute_path_hint,
    detect_misplaced_linux_path,
    is_valid_hat_case_dir,
)
from app.utils.allure_report import build_allure_generate_argv, parse_allure_results_dir
from app.utils.test_environment_url import (
    mask_agent_payload,
    mask_sensitive_urls,
    prepare_hat_cases_with_url,
    resolve_project_base_url,
    resolve_project_sensitive_urls,
    sanitize_allure_results_dir,
    _is_explicit_public_api_configured,
)


# ============================================================================
# 测试目录配置
# ============================================================================

# 测试服务器根目录（延迟解析，避免 CWD 影响）
def get_workspace_tests_dir() -> Path:
    """
    获取 workspace 测试目录路径

    Returns:
        workspace 测试目录的绝对路径
    """
    return get_api_workspace_tests_dir()


def get_project_root() -> Path:
    """
    获取 API workspace 根目录

    Returns:
        workspace 根目录的绝对路径
    """
    return get_api_workspace_root()


@tool
async def execute_api_script(
    local_script_path: str,
    framework: str = "hat",
    reporter: str = "html",
    project_identifier: str = "PR-1",
    endpoint_id: Optional[str] = None,
    user_id: str = "system"
) -> str:
    """
    执行已下载到测试目录的 API 测试脚本

    此工具会：
    1. 验证脚本文件存在于 workspace 测试目录
    2. 执行测试（Playwright/Jest/Pytest）
    3. 生成测试报告（HTML/JSON）
    4. 将测试报告保存到 MinIO
    5. 在数据库中创建测试报告附件记录
    6. 更新端点的测试运行次数
    7. 清理临时报告文件

    Args:
        local_script_path: 本地脚本文件的完整路径（相对或绝对路径）
        framework: 测试框架 (playwright, jest, pytest, hat)
        reporter: 报告格式 (html, json, list)
        project_identifier: 项目标识符，用于保存测试报告
        endpoint_id: 端点 ID（可选，用于更新测试统计）

    Returns:
        JSON 格式的执行结果，包含：
        - success: 是否成功
        - script_path: 执行的脚本路径
        - execution_result: 执行结果（stdout, stderr, duration, return_code）
        - report_attachment_id: 测试报告附件 ID（如果生成了报告）
        - error: 错误信息（如果有）

    Example:
        >>> result = await execute_api_script(
        ...     local_script_path="backend/workspace/api/tests/login_test.spec.ts",
        ...     framework="playwright",
        ...     reporter="html",
        ...     project_identifier="PR-3",
        ...     endpoint_id="5ea81a5f-c97b-4a36-a680-13637f1b9eed"
        ... )
    """
    try:
        # 1. 解析脚本路径
        cleaned_path = sanitize_workspace_relative_path(local_script_path)
        script_path = Path(cleaned_path)
        project_root = get_api_workspace_root()
        workspace_tests_dir = get_workspace_tests_dir()

        # 2. 标准化路径：多策略查找脚本文件
        if script_path.is_absolute():
            # 绝对路径：直接使用
            pass
        else:
            # 相对路径：按优先级尝试多种解析策略
            #   download_api_script 返回 local_path 是相对于 workspace_root 的
            #   （如 "tests/xxx.spec.ts"），但 execute_api_script 需要在 workspace_tests_dir
            #   中查找。直接 workspace_tests_dir / script_path 会产生双重重叠的 "tests/tests/"
            found = False
            strategies = [
                # 策略1: workspace_tests_dir / script_path（适用于纯文件名，如 "xxx.spec.ts"）
                ("workspace_tests_dir / script_path", workspace_tests_dir / script_path),
                # 策略2: workspace_tests_dir / script_path.name（去掉前缀，适用于 "tests/xxx.spec.ts"）
                ("workspace_tests_dir / basename(script_path)", workspace_tests_dir / script_path.name),
                # 策略3: project_root / script_path（适用于相对于 workspace_root 的路径）
                ("project_root / script_path", project_root / script_path),
                # 策略4: resolve() 相对 CWD
                ("CWD / script_path (resolve)", script_path.resolve()),
            ]
            for strategy_name, candidate_path in strategies:
                if candidate_path.exists():
                    print(f"[API Script Execution] 路径匹配: {strategy_name} -> {candidate_path}")
                    script_path = candidate_path
                    found = True
                    break

            if not found:
                # HAT 用例目录：尝试匹配含 context.yaml 的目录
                for strategy_name, candidate_path in strategies:
                    dir_candidate = candidate_path
                    if candidate_path.suffix:
                        dir_candidate = candidate_path.parent
                    if dir_candidate.is_dir() and (
                        (dir_candidate / "context.yaml").exists()
                        or any(dir_candidate.glob("[0-9]*_*.yaml"))
                    ):
                        print(f"[API Script Execution] 目录匹配: {strategy_name} -> {dir_candidate}")
                        script_path = dir_candidate
                        found = True
                        break

            if not found and not script_path.suffix:
                # 尝试自动添加 .spec.ts 扩展名（所有策略都不命中时）
                for strategy_name, base_path in strategies:
                    candidate_with_ext = base_path.parent / f"{base_path.name}.spec.ts"
                    if candidate_with_ext.exists():
                        print(f"[API Script Execution] 路径匹配(加扩展名): {strategy_name} -> {candidate_with_ext}")
                        script_path = candidate_with_ext
                        found = True
                        break

        # 3. 验证脚本文件/目录存在
        if not script_path.exists():
            hint_lines = [
                f"请使用 workspace 相对路径，例如: {build_execute_path_hint(project_identifier)}",
                "禁止 Linux 绝对路径（/home/...），文件应位于 backend/workspace/api/tests/ 下",
                "禁止 write_file 写 HAT 用例，须用 deploy_hat_case 或 deploy_hat_scenario 部署",
            ]
            # Agent filesystem 曾误写到 backend/backend/workspace/api（与 execute 根目录不一致）
            mirror_root = project_root.parent / "backend" / "workspace" / "api"
            if mirror_root.exists() and local_script_path:
                mirror_candidate = mirror_root / sanitize_workspace_relative_path(
                    local_script_path, mirror_root
                )
                if mirror_candidate.exists():
                    hint_lines.append(
                        f"检测到用例在 Agent 误写目录 {mirror_candidate}；"
                        "请用 deploy_hat_scenario 重新部署到 canonical workspace，"
                        "或调用 list_hat_case_dirs 查看可执行路径。"
                    )
            if detect_misplaced_linux_path(local_script_path):
                sanitized = sanitize_workspace_relative_path(local_script_path, project_root)
                candidate = resolve_hat_cases_dir(
                    sanitized,
                    workspace_tests_dir,
                    project_root,
                )
                hint_lines.append(f"规范化后尝试路径: {sanitized}")
                if candidate.exists():
                    hint_lines.append(f"已存在目录: {candidate}，请改用 local_script_path={sanitized!r}")
            return json.dumps({
                "success": False,
                "error": f"脚本路径不存在: {script_path}",
                "hint": " ".join(hint_lines),
                "recommended_path_format": build_execute_path_hint(project_identifier),
            }, ensure_ascii=False, indent=2)

        if script_path.is_dir() and framework != "hat":
            return json.dumps({
                "success": False,
                "error": f"目录路径仅支持 framework='hat'，当前为: {framework}"
            }, ensure_ascii=False, indent=2)

        if framework == "hat":
            hat_cases_probe = script_path if script_path.is_dir() else script_path.parent
            if not is_valid_hat_case_dir(hat_cases_probe, workspace_tests_dir):
                return json.dumps({
                    "success": False,
                    "error": (
                        "HAT 执行路径过宽或无效，禁止执行 tests 根目录。"
                        "请指定单个用例目录，例如 "
                        f"{build_execute_path_hint(project_identifier, 'scenario_conversation_flow')}"
                    ),
                    "received_path": local_script_path,
                    "resolved_path": str(hat_cases_probe),
                    "recommended_path_format": build_execute_path_hint(project_identifier),
                }, ensure_ascii=False, indent=2)

        script_filename = script_path.name

        print(f"[API Script Execution] 准备执行脚本: {script_path}")

        # 4. 计算相对路径
        #    相对于 project_root — 用于日志和外部引用
        try:
            relative_path = script_path.resolve().relative_to(project_root)
        except ValueError:
            relative_path = script_path.name

        #    相对于 workspace_tests_dir — 用于 Playwright 命令（支持子目录）
        try:
            tests_relative_path = script_path.resolve().relative_to(workspace_tests_dir.resolve())
        except ValueError:
            tests_relative_path = Path(script_filename)  # 兜底：只用文件名

        print(f"[API Script Execution] 项目根目录: {project_root}")
        print(f"[API Script Execution] 测试目录: {workspace_tests_dir}")
        print(f"[API Script Execution] 测试内路径: {tests_relative_path}")

        # 5. 执行脚本
        execution_result = await _execute_script_internal(
            script_path=str(relative_path),
            script_filename=script_filename,
            tests_relative=str(tests_relative_path),
            framework=framework,
            reporter=reporter,
            project_root=str(project_root),
            tests_dir=str(workspace_tests_dir),  # 固定测试目录
            project_identifier=project_identifier,
            endpoint_id=endpoint_id
        )

        # 6. 保存测试报告到 MinIO
        report_attachment_id = None
        if endpoint_id and reporter == "html" and execution_result.get("report_path"):
            # 获取端点信息
            async with async_session_factory() as db:
                endpoint_result = await db.execute(
                    select(APIEndpoint).where(APIEndpoint.id == UUID(endpoint_id))
                )
                endpoint = endpoint_result.scalar_one_or_none()

            if endpoint:
                report_attachment_id = await _save_test_report(
                    endpoint_id=endpoint_id,
                    project_identifier=project_identifier,
                    endpoint=endpoint,
                    report_path=execution_result["report_path"],
                    execution_result=execution_result,
                    project_root=str(project_root)
                )

        # 7. 更新端点的测试运行次数（无论是否生成报告，有 endpoint_id 就更新）
        if endpoint_id:
            try:
                async with async_session_factory() as db:
                    endpoint_result = await db.execute(
                        select(APIEndpoint).where(APIEndpoint.id == UUID(endpoint_id))
                    )
                    endpoint = endpoint_result.scalar_one_or_none()

                    if endpoint:
                        # 递增测试运行次数
                        endpoint.total_test_runs = (endpoint.total_test_runs or 0) + 1

                        # 更新最后运行状态
                        if execution_result.get("success"):
                            endpoint.last_run_status = "success"
                        else:
                            endpoint.last_run_status = "failed"

                        await db.commit()
                        print(f"[API Script Execution] 已更新端点 {endpoint_id} 的测试运行次数")
            except Exception as e:
                print(f"[API Script Execution] 更新端点测试运行次数失败: {e}")

        # 8. 写入执行日志
        exec_status = "success" if execution_result.get("success") else "failed"
        try:
            async with async_session_factory() as db:
                from sqlalchemy import select
                from app.models.project import Project
                proj_result = await db.execute(
                    select(Project.id).where(Project.identifier == project_identifier)
                )
                proj_uuid = proj_result.scalar_one_or_none()
                if proj_uuid:
                    log = TestExecutionLog(
                        project_id=proj_uuid,
                        endpoint_id=UUID(endpoint_id) if endpoint_id else None,
                        user_id=user_id,
                        status=exec_status,
                        duration_ms=execution_result.get("duration", 0) * 1000,
                        return_code=execution_result.get("return_code"),
                        script_name=script_filename,
                        framework=framework,
                        report_attachment_id=UUID(report_attachment_id) if report_attachment_id else None,
                    )
                    db.add(log)
                    await db.commit()
        except Exception as e:
            print(f"[API Script Execution] 写入执行日志失败: {e}")

        # 9. 返回结果
        result = {
            "success": True,
            "script_path": str(script_path),
            "script_filename": script_filename,
            "execution_result": execution_result
        }

        if report_attachment_id:
            result["report_attachment_id"] = report_attachment_id
            result["message"] = "脚本执行完成，测试报告已保存"

        if endpoint_id:
            result["endpoint_id"] = endpoint_id

        masked_result = mask_agent_payload(result, await resolve_project_sensitive_urls(project_identifier))
        masked_result["environment_status"] = {
            "base_url_injected": True,
            "display_base_url": "{{API_BASE_URL}}",
            "public_api_configured": _is_explicit_public_api_configured(),
            "hint": (
                "PUBLIC_API_URL/.env 已在服务端加载并注入。"
                "若仍 ConnectionError，优先检查 YAML 的「请求地址」是否为完整 API 路径"
                "（如 {{URL}}/api/v2/projects/...），而非重复检查 .env。"
            ),
        }
        return json.dumps(masked_result, ensure_ascii=False, indent=2)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return json.dumps({
            "success": False,
            "error": f"执行脚本时发生错误: {str(e)}"
        }, ensure_ascii=False, indent=2)


async def _execute_script_internal(
    script_path: str,
    script_filename: str,
    framework: str,
    reporter: str,
    project_root: str,
    tests_relative: str = "",
    tests_dir: str = "",
    project_identifier: str = "",
    endpoint_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    内部执行脚本函数

    Args:
        script_path: 脚本文件相对路径（相对于 project_root）
        script_filename: 脚本文件名
        tests_relative: 相对于 tests_dir 的路径（支持子目录，如 "PR-1/api-tests/list.spec.ts"）
        framework: 测试框架
        reporter: 报告格式
        project_root: 项目根目录
        tests_dir: 固定测试目录（脚本在此生成并执行）
        project_identifier: 项目标识符，用于注入测试环境配置
        endpoint_id: 端点 ID，用于注入 folder_id 等上下文参数

    Returns:
        执行结果字典
    """
    temp_hat_root: Path | None = None
    try:
        start_time = datetime.now()
        sensitive_base_url = await resolve_project_base_url(project_identifier)
        sensitive_urls = await resolve_project_sensitive_urls(project_identifier)

        resolved_folder_id: str | None = None
        if endpoint_id:
            try:
                async with async_session_factory() as inject_session:
                    ep_result = await inject_session.execute(
                        select(APIEndpoint).where(APIEndpoint.id == UUID(endpoint_id))
                    )
                    endpoint = ep_result.scalar_one_or_none()
                    if endpoint and endpoint.folder_id:
                        resolved_folder_id = str(endpoint.folder_id)
            except Exception as e:
                print(f"[API Script Execution] 预读取 FOLDER_ID 失败(非致命): {e}")

        # 确定测试命令（统一使用 list，兼容 Windows / Linux）
        test_target = tests_relative or script_filename
        exec_cwd = tests_dir or project_root

        if framework == "playwright":
            if reporter == "html":
                cmd = [
                    "npx", "playwright", "test", test_target,
                    "--reporter=html,json,allure-playwright", "--trace=on",
                ]
            else:
                cmd = [
                    "npx", "playwright", "test", test_target,
                    f"--reporter={reporter},json,allure-playwright", "--trace=on",
                ]
        elif framework == "jest":
            if reporter == "html":
                cmd = ["npm", "test", "--", test_target, "--reporter=html"]
            else:
                cmd = ["npm", "test", "--", test_target, f"--reporter={reporter}"]
        elif framework == "pytest":
            cmd = ["pytest", test_target, "-v"]
        elif framework == "hat":
            hat_home = get_hat_home()
            run_hat_path = get_run_hat_path()
            key_dir = get_hat_key_dir()

            if not run_hat_path.exists():
                return {
                    "success": False,
                    "error": f"run_hat.py 不存在: {run_hat_path}",
                }

            cases_dir = resolve_hat_cases_dir(
                test_target, tests_dir or project_root, project_root
            )
            if not is_valid_hat_case_dir(cases_dir, tests_dir or project_root):
                return {
                    "success": False,
                    "error": (
                        "HAT cases 目录无效或过宽（可能指向了整个 tests 目录）。"
                        "请传入 tests/{project}/api-tests/{case_slug}/ 形式的单用例路径。"
                    ),
                    "resolved_cases_dir": str(cases_dir),
                    "test_target": test_target,
                }

            from app.utils.hat_auth import ensure_hat_bearer_token_env
            from app.utils.hat_yaml_lint import run_hat_preflight

            ensure_hat_bearer_token_env()
            lint_errors = run_hat_preflight(cases_dir, strict=True)
            if lint_errors:
                return {
                    "success": False,
                    "error": "HAT 用例 YAML 校验失败",
                    "lint_errors": lint_errors,
                    "cases_dir": str(cases_dir),
                }

            exec_cases_dir, temp_hat_root = prepare_hat_cases_with_url(
                cases_dir,
                sensitive_base_url,
                folder_id=resolved_folder_id,
                project_identifier=project_identifier,
            )
            key_dirs = resolve_hat_key_dirs(exec_cases_dir, key_dir)
            cases_dir_str = str(exec_cases_dir)
            exec_cwd = str(hat_home)
            if temp_hat_root:
                print(
                    "[API Script Execution] 已在临时目录注入 HAT context.yaml URL "
                    f"(workspace 保留占位符): {exec_cases_dir}"
                )

            cmd = [
                sys.executable,
                str(run_hat_path),
                "--type=yaml",
                f"--cases={cases_dir_str}",
                f"--keyDir={format_key_dirs_cli(key_dirs)}",
                "-v",
                "--clean-alluredir",
                "--alluredir=allure-results",
            ]
        else:
            return {
                "success": False,
                "error": f"不支持的测试框架: {framework}"
            }

        print(f"[API Script Execution] 执行命令: {' '.join(cmd)}")
        print(f"[API Script Execution] 工作目录: {exec_cwd}")
        print(f"[API Script Execution] 项目根目录: {project_root}")
        print(f"[API Script Execution] 测试目录: {tests_dir}")

        # 准备环境变量（设置 CI=1 禁用 Playwright HTML reporter 自动打开浏览器）
        env = os.environ.copy()
        if reporter == "html":
            env['CI'] = '1'

        # 注入测试环境变量（不经过 LLM；HAT conftest 的 apply_hat_runtime_urls 优先读 API_BASE_URL）
        env["API_BASE_URL"] = sensitive_base_url
        print(f"[API Script Execution] 已注入 API_BASE_URL={sensitive_base_url}")

        for cred_key in (
            "HAT_TEST_EMAIL",
            "HAT_TEST_PASSWORD",
            "HAT_TEST_ACCOUNT",
            "HAT_ADMIN_EMAIL",
            "HAT_ADMIN_PASSWORD",
        ):
            cred_val = os.environ.get(cred_key)
            if cred_val:
                env[cred_key] = cred_val

        from app.utils.hat_auth import ensure_hat_bearer_token_env
        from app.utils.test_environment_url import resolve_bearer_token

        if framework == "hat":
            ensure_hat_bearer_token_env()
        bearer_token = resolve_bearer_token()
        if bearer_token and not env.get("HAT_BEARER_TOKEN"):
            env["HAT_BEARER_TOKEN"] = bearer_token
            print("[API Script Execution] 已注入 HAT_BEARER_TOKEN (长度已隐藏)")

        if project_identifier:
            env.setdefault("PROJECT_IDENTIFIER", project_identifier)
            env.setdefault("project_identifier", project_identifier)

        if resolved_folder_id and not env.get("FOLDER_ID"):
            env["FOLDER_ID"] = resolved_folder_id
            env["folder_id"] = resolved_folder_id
            print(f"[API Script Execution] 已注入 FOLDER_ID={resolved_folder_id}")
        elif endpoint_id and not env.get("FOLDER_ID"):
            try:
                async with async_session_factory() as inject_session:
                    ep_result = await inject_session.execute(
                        select(APIEndpoint).where(APIEndpoint.id == UUID(endpoint_id))
                    )
                    endpoint = ep_result.scalar_one_or_none()
                    if endpoint and endpoint.folder_id:
                        env["FOLDER_ID"] = str(endpoint.folder_id)
                        env["folder_id"] = str(endpoint.folder_id)
                        print(f"[API Script Execution] 已注入 FOLDER_ID (来自端点 {endpoint_id})")
            except Exception as e:
                print(f"[API Script Execution] 注入 FOLDER_ID 失败(非致命): {e}")

        # 执行测试（异步，不阻塞事件循环）
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=exec_cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=300
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "success": False,
                "error": "脚本执行超时（超过5分钟）"
            }

        stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ''
        stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ''

        # ============================================================
        # 脱敏：将 stdout/stderr 中的真实测试环境 URL 替换为占位符
        # 防止执行日志中的敏感 URL 通过 Agent 工具返回值暴露给 LLM
        # ============================================================
        stdout = mask_sensitive_urls(stdout, sensitive_urls)
        stderr = mask_sensitive_urls(stderr, sensitive_urls)

        return_code = proc.returncode

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"[API Script Execution] 执行完成，返回码: {return_code}")
        print(f"[API Script Execution] 执行时间: {duration:.2f}s")

        # 检查是否生成了 HTML 报告
        report_path = None
        if reporter == "html":
            report_dir = Path(tests_dir or project_root) / "playwright-report"
            index_html = report_dir / "index.html"
            if index_html.exists():
                report_path = str(report_dir)
                print(f"[API Script Execution] HTML 报告已生成: {report_path}")

        # 从 stdout 解析 Playwright JSON 报告，保存结构化结果到 MinIO
        structured_report_minio = None
        try:
            # 尝试从 stdout 末尾提取 JSON 报告
            text = stdout.strip()
            brace_depth = 0
            json_start = -1
            json_end = -1
            for i in range(len(text) - 1, -1, -1):
                ch = text[i]
                if ch == '}':
                    if brace_depth == 0:
                        json_end = i
                    brace_depth += 1
                elif ch == '{':
                    brace_depth -= 1
                    if brace_depth == 0:
                        json_start = i
                        break
            if json_start >= 0:
                json_str = text[json_start:json_end + 1]
                pw_report = json.loads(json_str)

                # 提取测试结果（递归遍历嵌套的 suites）
                test_results = []
                stats = pw_report.get("stats", {})
                top_suites = pw_report.get("suites", [])

                def extract_specs(suite_list):
                    results = []
                    for suite in suite_list:
                        # 当前 suite 的 specs
                        for spec in suite.get("specs", []):
                            for t in spec.get("tests", []):
                                result = t.get("results", [{}])[0] if t.get("results") else {}
                                results.append({
                                    "name": spec.get("title", ""),
                                    "file": suite.get("file", ""),
                                    "project": t.get("projectName", ""),
                                    "status": result.get("status", t.get("status", "unknown")),
                                    "expected_status": t.get("expectedStatus", "passed"),
                                    "ok": t.get("ok", result.get("status") == "expected") if result else True,
                                    "duration_ms": result.get("duration", 0),
                                    "error": result.get("error", {}).get("message") if result.get("error") else None,
                                    "stack": result.get("error", {}).get("stack") if result.get("error") else None,
                                })
                        # 递归子 suites
                        sub_suites = suite.get("suites", [])
                        if sub_suites:
                            results.extend(extract_specs(sub_suites))
                    return results

                test_results = extract_specs(top_suites)

                # 构建结构化报告
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                structured_report = {
                    "generated_at": datetime.now().isoformat(),
                    "framework": framework,
                    "test_path": test_target,
                    "exit_code": return_code,
                    "project_identifier": project_identifier,
                    "structured": {
                        "summary": {
                            "total": stats.get("total", len(test_results)),
                            "passed": stats.get("expected", 0),
                            "failed": stats.get("unexpected", 0),
                            "skipped": stats.get("skipped", 0),
                            "total_duration_ms": int(duration * 1000) if duration else 0,
                        },
                        "tests": test_results,
                    },
                }

                structured_report = mask_agent_payload(structured_report, sensitive_urls)

                # 保存到 MinIO（供人查阅；Agent 经 get_artifact_content 读时会再次脱敏）
                minio_path = f"test-reports/{project_identifier}/{timestamp_str}/report.json"
                MinIOClient.upload_bytes(
                    object_name=minio_path,
                    data=json.dumps(structured_report, ensure_ascii=False, indent=2).encode("utf-8"),
                    content_type="application/json",
                )
                structured_report_minio = minio_path
                print(f"[API Script Execution] 结构化报告已保存到 MinIO: {minio_path}")
        except Exception as parse_e:
            print(f"[API Script Execution] JSON 报告解析/保存失败(非致命): {parse_e}")

        # HAT：从 allure-results 生成结构化 JSON 报告（Playwright 走 stdout JSON）
        if framework == "hat" and not structured_report_minio:
            try:
                hat_allure_dir = get_hat_home() / "allure-results"
                hat_structured = parse_allure_results_dir(hat_allure_dir)
                if hat_structured:
                    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                    structured_report = {
                        "generated_at": datetime.now().isoformat(),
                        "framework": framework,
                        "test_path": test_target,
                        "exit_code": return_code,
                        "project_identifier": project_identifier,
                        "structured": hat_structured,
                    }
                    structured_report = mask_agent_payload(structured_report, sensitive_urls)
                    minio_path = f"test-reports/{project_identifier or 'default'}/{timestamp_str}/report.json"
                    MinIOClient.upload_bytes(
                        object_name=minio_path,
                        data=json.dumps(structured_report, ensure_ascii=False, indent=2).encode("utf-8"),
                        content_type="application/json",
                    )
                    structured_report_minio = minio_path
                    print(f"[API Script Execution] HAT 结构化报告已保存到 MinIO: {minio_path}")
            except Exception as hat_report_err:
                print(f"[API Script Execution] HAT 结构化报告保存失败(非致命): {hat_report_err}")

        result_dict = {
            "success": return_code == 0,
            "return_code": return_code,
            "duration": duration,
            "stdout": stdout,
            "stderr": stderr,
            "report_path": report_path,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat()
        }
        if structured_report_minio:
            result_dict["structured_report_minio"] = structured_report_minio

        # 生成 Allure HTML 报告
        allure_report_url = None
        allure_minio_path = None
        try:
            workspace_root = get_api_workspace_root()
            allure_candidates = [
                get_hat_home() / "allure-results",
                workspace_root / "allure-results",
            ]
            if tests_dir:
                allure_candidates.append(Path(tests_dir) / "allure-results")

            allure_results_dir = None
            for candidate in allure_candidates:
                if candidate.exists() and any(candidate.iterdir()):
                    allure_results_dir = candidate
                    break
            if allure_results_dir:
                import shutil
                sanitize_allure_results_dir(allure_results_dir, sensitive_urls)
                timestamp_ts = int(datetime.now().timestamp())
                allure_report_dir = workspace_root / f"allure-report-{timestamp_ts}"

                allure_cmd = build_allure_generate_argv(allure_results_dir, allure_report_dir)
                proc_allure = await asyncio.create_subprocess_exec(
                    *allure_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                allure_stdout, allure_stderr = await asyncio.wait_for(
                    proc_allure.communicate(), timeout=60
                )
                if proc_allure.returncode != 0:
                    print(
                        "[API Script Execution] Allure generate 失败: "
                        f"rc={proc_allure.returncode}, "
                        f"stderr={allure_stderr.decode('utf-8', errors='replace')[:500]}"
                    )

                if allure_report_dir.exists() and (allure_report_dir / "index.html").exists():
                    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                    zip_path = workspace_root / f"allure-report-{timestamp_str}.zip"
                    shutil.make_archive(str(zip_path.with_suffix('')), 'zip', str(allure_report_dir))
                    if zip_path.exists():
                        pid = project_identifier or "default"
                        allure_minio_path = f"allure-reports/{pid}/{timestamp_str}/report.zip"
                        with open(zip_path, 'rb') as f:
                            MinIOClient.upload_bytes(
                                object_name=allure_minio_path,
                                data=f.read(),
                                content_type="application/zip",
                            )
                        from datetime import timedelta
                        allure_report_url = MinIOClient.get_presigned_url(
                            object_name=allure_minio_path,
                            expires=timedelta(days=7),
                        )
                        result_dict["allure_report_url"] = allure_report_url
                        result_dict["allure_minio_path"] = allure_minio_path
                        shutil.rmtree(allure_report_dir, ignore_errors=True)
                        zip_path.unlink(missing_ok=True)

                shutil.rmtree(allure_results_dir, ignore_errors=True)
        except Exception as allure_err:
            print(f"[API Script Execution] Allure 报告生成失败(非致命): {allure_err}")

        return result_dict

    except asyncio.TimeoutError:
        # 内部的 asyncio.wait_for 已处理超时，此处保留以防嵌套调用
        return {
            "success": False,
            "error": "脚本执行超时（超过5分钟）"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"执行脚本时发生错误: {str(e)}"
        }
    finally:
        if temp_hat_root:
            shutil.rmtree(temp_hat_root, ignore_errors=True)


async def _save_test_report(
    endpoint_id: str,
    project_identifier: str,
    endpoint: APIEndpoint,
    report_path: str,
    execution_result: Dict[str, Any],
    project_root: str
) -> Optional[str]:
    """
    保存测试报告到 MinIO 并创建附件记录

    Args:
        endpoint_id: 端点 ID
        project_identifier: 项目标识符
        endpoint: 端点对象
        report_path: 报告目录路径
        execution_result: 执行结果
        project_root: 项目根目录

    Returns:
        附件 ID，如果保存失败则返回 None
    """
    try:
        # 1. 将报告目录打包成 ZIP
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"api_test_report_{timestamp}.zip"
        zip_path = Path(project_root) / zip_filename

        print(f"[API Report] 打包测试报告: {report_path} -> {zip_path}")

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            report_dir = Path(report_path)
            for file_path in report_dir.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(report_dir)
                    zipf.write(file_path, arcname)

        # 2. 读取 ZIP 文件内容
        with open(zip_path, 'rb') as f:
            zip_bytes = f.read()

        # 3. 上传到 MinIO
        object_name = f"api-tests/{project_identifier}/endpoints/{endpoint_id}/test-report-{timestamp}.zip"
        MinIOClient.upload_bytes(
            object_name=object_name,
            data=zip_bytes,
            content_type="application/zip"
        )

        print(f"[API Report] 报告已上传到 MinIO: {object_name}")

        # 4. 创建附件记录
        async with async_session_factory() as session:
            # 生成报告描述
            duration = execution_result.get("duration", 0)
            stdout = execution_result.get("stdout", "")

            # 尝试解析测试结果
            passed_count = stdout.count("✓") + stdout.count("passed")
            failed_count = stdout.count("✘") + stdout.count("failed")

            description = f"API 测试报告 - {endpoint.display_name}\n"
            description += f"执行时间: {duration:.2f}秒\n"
            if passed_count > 0 or failed_count > 0:
                description += f"通过: {passed_count} | 失败: {failed_count}"

            # 创建附件
            attachment = Attachment(
                entity_type=AttachmentEntityType.API_TEST_REPORT,
                entity_id=UUID(endpoint_id),
                project_id=endpoint.project_id,
                file_name=f"api-test-report-{timestamp}.zip",
                file_size=len(zip_bytes),
                content_type="application/zip",
                object_name=object_name,
                description=description,
                created_by="api-agent"
            )

            session.add(attachment)
            await session.commit()
            await session.refresh(attachment)

            print(f"[API Report] 附件记录已创建: {attachment.id}")

            # 5. 清理临时 ZIP 文件
            try:
                zip_path.unlink()
                print(f"[API Report] 临时 ZIP 文件已清理: {zip_path}")
            except Exception as e:
                print(f"[API Report] 清理临时 ZIP 文件失败: {e}")

            # 6. 清理报告目录
            try:
                shutil.rmtree(report_path)
                print(f"[API Report] 报告目录已清理: {report_path}")
            except Exception as e:
                print(f"[API Report] 清理报告目录失败: {e}")

            return str(attachment.id)

    except Exception as e:
        print(f"[API Report] 保存测试报告失败: {e}")
        import traceback
        traceback.print_exc()
        return None


@tool
async def get_test_execution_status(
    execution_id: str
) -> str:
    """
    获取测试执行状态（占位符，未来可扩展为异步执行查询）

    Args:
        execution_id: 执行 ID

    Returns:
        JSON 格式的执行状态
    """
    return json.dumps({
        "success": True,
        "execution_id": execution_id,
        "status": "completed",
        "message": "当前版本仅支持同步执行，不支持异步状态查询"
    }, ensure_ascii=False, indent=2)
