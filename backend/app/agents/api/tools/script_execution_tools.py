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
from app.config.minio_client import MinIOClient


# ============================================================================
# 测试目录配置
# ============================================================================

# 测试服务器根目录
WORKSPACE_TESTS_ROOT = Path(settings.api_workspace_root) / "tests"


def get_workspace_tests_dir() -> Path:
    """
    获取 workspace 测试目录路径

    Returns:
        workspace 测试目录的绝对路径
    """
    return WORKSPACE_TESTS_ROOT


def get_project_root() -> Path:
    """
    获取项目根目录（用于在 workspace 测试目录中找到 package.json）

    Returns:
        项目根目录的绝对路径
    """
    return Path(settings.api_workspace_root)


@tool
async def execute_api_script(
    local_script_path: str,
    framework: str = "playwright",
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
        framework: 测试框架 (playwright, jest, pytest)
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
        # 清理路径：去除开头的斜杠或反斜杠，标准化分隔符
        cleaned_path = local_script_path.strip().strip('/').strip('\\')
        script_path = Path(cleaned_path)
        project_root = Path(settings.api_workspace_root).resolve()
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

            if not found and not script_path.suffix:
                # 尝试自动添加 .spec.ts 扩展名（所有策略都不命中时）
                for strategy_name, base_path in strategies:
                    candidate_with_ext = base_path.parent / f"{base_path.name}.spec.ts"
                    if candidate_with_ext.exists():
                        print(f"[API Script Execution] 路径匹配(加扩展名): {strategy_name} -> {candidate_with_ext}")
                        script_path = candidate_with_ext
                        found = True
                        break

        # 3. 验证脚本文件存在
        if not script_path.exists():
            return json.dumps({
                "success": False,
                "error": f"脚本文件不存在: {script_path}"
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

        return json.dumps(result, ensure_ascii=False, indent=2)

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
    try:
        start_time = datetime.now()

        # 确定测试命令
        is_windows = sys.platform == "win32"
        # tests_relative 支持子目录（如 PR-1/api-tests/list.spec.ts），空时兜底用文件名
        test_target = tests_relative or script_filename

        if framework == "playwright":
            if reporter == "html":
                # HTML + JSON + Allure: html给原始报告，json给解析，allure给前端展示，trace抓请求详情
                if is_windows:
                    cmd = f'npx playwright test {test_target} --reporter=html,json,allure-playwright --trace=on'
                else:
                    cmd = ["npx", "playwright", "test", test_target, "--reporter=html,json,allure-playwright", "--trace=on"]
            else:
                if is_windows:
                    cmd = f'npx playwright test {test_target} --reporter={reporter},json,allure-playwright --trace=on'
                else:
                    cmd = ["npx", "playwright", "test", test_target, f"--reporter={reporter},json,allure-playwright", "--trace=on"]
        elif framework == "jest":
            if reporter == "html":
                if is_windows:
                    cmd = f'npm test -- {test_target} --reporter=html'
                else:
                    cmd = ["npm", "test", "--", test_target, "--reporter=html"]
            else:
                if is_windows:
                    cmd = f"npm test -- {test_target} --reporter={reporter}"
                else:
                    cmd = ["npm", "test", "--", test_target, f"--reporter={reporter}"]
        elif framework == "pytest":
            if is_windows:
                cmd = f"pytest {test_target} --reporter={reporter}"
            else:
                cmd = ["pytest", test_target, f"--reporter={reporter}"]
        else:
            return {
                "success": False,
                "error": f"不支持的测试框架: {framework}"
            }

        print(f"[API Script Execution] 执行命令: {cmd if is_windows else ' '.join(cmd)}")
        print(f"[API Script Execution] 项目根目录: {project_root}")
        print(f"[API Script Execution] 测试目录: {tests_dir}")

        # 准备环境变量（设置 CI=1 禁用 Playwright HTML reporter 自动打开浏览器）
        env = os.environ.copy()
        if reporter == "html":
            env['CI'] = '1'

        # ============================================================
        # 自动注入测试环境配置（来自 DB，不经过 LLM，保护私密 URL）
        # 脚本中统一使用 process.env.API_BASE_URL / process.env.FOLDER_ID
        # ============================================================
        if project_identifier:
            try:
                async with async_session_factory() as inject_session:
                    from sqlalchemy import select as sel
                    from app.models.project import Project as ProjModel
                    from app.repositories.test_environment_repo import TestEnvironmentRepository
                    proj_result = await inject_session.execute(
                        sel(ProjModel).where(ProjModel.identifier == project_identifier)
                    )
                    project = proj_result.scalar_one_or_none()
                    if project:
                        # 1. 注入默认环境 URL
                        if not env.get('API_BASE_URL'):
                            repo = TestEnvironmentRepository(inject_session)
                            env_obj = await repo.get_default(project.id)
                            # 没有默认环境时，使用第一个环境作为兜底
                            if not env_obj:
                                envs = await repo.list_by_project(project.id)
                                if envs:
                                    env_obj = envs[0]
                            if env_obj and env_obj.base_url:
                                env['API_BASE_URL'] = env_obj.base_url.rstrip('/')
                                print(f"[API Script Execution] 已注入 API_BASE_URL (来自项目默认环境)")

                        # 2. 注入 folder_id（优先从 endpoint 获取）
                        if endpoint_id and not env.get('FOLDER_ID'):
                            ep_result = await inject_session.execute(
                                sel(APIEndpoint).where(APIEndpoint.id == UUID(endpoint_id))
                            )
                            endpoint = ep_result.scalar_one_or_none()
                            if endpoint and endpoint.folder_id:
                                env['FOLDER_ID'] = str(endpoint.folder_id)
                                print(f"[API Script Execution] 已注入 FOLDER_ID (来自端点 {endpoint_id})")
            except Exception as e:
                print(f"[API Script Execution] 注入环境配置失败(非致命): {e}")
        # ============================================================

        # 执行测试（异步，不阻塞事件循环）
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=tests_dir or project_root,
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

                # 保存到 MinIO
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
            workspace_root = Path(settings.api_workspace_root)
            # allure-results 可能在 workspace_root 或 tests_dir 下
            allure_results_dir = workspace_root / "allure-results"
            if not (allure_results_dir.exists() and any(allure_results_dir.iterdir())):
                # 检查 tests_dir 下的 allure-results
                alt_dir = Path(tests_dir or "") / "allure-results" if tests_dir else None
                if alt_dir and alt_dir.exists() and any(alt_dir.iterdir()):
                    allure_results_dir = alt_dir
            if allure_results_dir.exists() and any(allure_results_dir.iterdir()):
                import shutil
                timestamp_ts = int(datetime.now().timestamp())
                allure_report_dir = workspace_root / f"allure-report-{timestamp_ts}"

                proc_allure = await asyncio.create_subprocess_exec(
                    "allure", "generate", str(allure_results_dir),
                    "-o", str(allure_report_dir), "--clean",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc_allure.communicate(), timeout=60)

                if allure_report_dir.exists():
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
