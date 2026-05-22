"""
API 测试执行工具

提供测试执行、结果收集等功能
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


import json
import asyncio
import os
import traceback
from pathlib import Path
from typing import Optional
from datetime import datetime

from langchain_core.tools import tool

# 工作目录路径：复用 api_test_executor.py 中的配置
from app.config import settings

# MinIO 客户端
from app.config.minio_client import MinIOClient


WORKSPACE_DIR = Path(settings.api_workspace_root)


def _parse_playwright_json(stdout: str) -> Optional[dict]:
    """
    从 Playwright 输出中解析 JSON 报告。
    
    Playwright 的 --reporter=json 会将 JSON 输出到 stdout，
    当使用 --reporter=list,json 时，list 输出和 json 输出都到 stdout，
    JSON 对象总是在最后。此函数尝试从末尾提取 JSON。
    """
    # 尝试直接解析整个 stdout
    text = stdout.strip()
    if not text:
        return None

    # 尝试从 stdout 末尾提取 JSON 对象
    # JSON 报告格式：{"suites": [...]} 或 {"config": {...}, "suites": [...]}
    # 它可能被 list reporter 的输出包围
    brace_depth = 0
    json_start = -1
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
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            pass

    # 尝试直接解析
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _extract_test_results(playwright_report: dict) -> dict:
    """
    从 Playwright JSON 报告中提取结构化测试结果。

    Args:
        playwright_report: Playwright JSON 报告字典

    Returns:
        包含提取结果的字典
    """
    suites = playwright_report.get("suites", [])
    all_tests = []
    total_passed = 0
    total_failed = 0
    total_skipped = 0
    total_duration = 0

    def walk_suite(suite: dict, suite_path: list[str]):
        """递归遍历 suites 和 specs"""
        title = suite.get("title", "")
        current_path = suite_path + [title] if title else suite_path
        file_path = suite.get("file", "")

        # 处理 specs (测试用例)
        for spec in suite.get("specs", []):
            spec_title = spec.get("title", "unnamed")
            ok = spec.get("ok", True)
            test_name = " > ".join(current_path + [spec_title]) if current_path else spec_title

            for test in spec.get("tests", []):
                project_name = test.get("projectName", "default")
                expected_status = test.get("expectedStatus", "passed")
                
                for result in test.get("results", []):
                    status = result.get("status", "unknown")
                    duration = result.get("duration", 0)
                    total_duration += duration

                    error_message = None
                    error_stack = None
                    errors = result.get("errors", result.get("error", []))
                    if errors:
                        if isinstance(errors, list) and len(errors) > 0:
                            err = errors[0]
                            if isinstance(err, dict):
                                error_message = err.get("message", str(err))
                                error_stack = err.get("stack")
                            else:
                                error_message = str(err)
                        elif isinstance(errors, dict):
                            error_message = errors.get("message", str(errors))
                            error_stack = errors.get("stack")

                    test_info = {
                        "name": test_name,
                        "project": project_name,
                        "status": status,
                        "expected_status": expected_status,
                        "ok": ok,
                        "duration_ms": duration,
                        "error": error_message,
                        "stack": error_stack,
                    }
                    all_tests.append(test_info)

                    if status == "passed":
                        total_passed += 1
                    elif status == "failed" or status == "timedOut":
                        total_failed += 1
                    elif status == "skipped" or status == "interrupted":
                        total_skipped += 1

        # 递归处理子 suites
        for child in suite.get("suites", []):
            walk_suite(child, current_path)

    for suite in suites:
        walk_suite(suite, [])

    return {
        "summary": {
            "total": len(all_tests),
            "passed": total_passed,
            "failed": total_failed,
            "skipped": total_skipped,
            "total_duration_ms": total_duration,
        },
        "tests": all_tests,
        "timestamp": datetime.now().isoformat(),
    }


def _build_readable_summary(structured: dict) -> str:
    """从结构化结果构建人类可读的摘要"""
    s = structured["summary"]
    lines = [
        f"Test Results Summary",
        f"{'=' * 60}",
        f"  Total:     {s['total']}",
        f"  Passed:    {s['passed']}",
        f"  Failed:    {s['failed']}",
        f"  Skipped:   {s['skipped']}",
        f"  Duration:  {s['total_duration_ms'] / 1000:.2f}s",
        f"{'=' * 60}",
    ]

    # Failed tests details
    failed = [t for t in structured["tests"] if t["status"] in ("failed", "timedOut")]
    if failed:
        lines.append("")
        lines.append("FAILED TESTS:")
        lines.append("-" * 60)
        for t in failed:
            lines.append(f"  [FAIL] {t['name']}")
            if t.get("error"):
                # show first 200 chars of error
                err = t["error"][:200]
                lines.append(f"         Error: {err}")

    # Passed tests list
    passed = [t for t in structured["tests"] if t["status"] == "passed"]
    if passed:
        lines.append("")
        lines.append("PASSED TESTS:")
        lines.append("-" * 60)
        for t in passed:
            dur = t["duration_ms"] / 1000
            lines.append(f"  [PASS] {t['name']} ({dur:.2f}s)")

    return "\n".join(lines)


@tool
async def run_tests(
    test_path: str,
    framework: str = "playwright",
    reporter: str = "list",
    project_identifier: str = "default",
) -> str:
    """
    运行 API 测试并收集结果，自动生成结构化报告并保存到 MinIO

    Args:
        test_path: 测试文件路径或目录
        framework: 测试框架 (playwright, jest, pytest)
        reporter: 报告格式 (list, json, html)
        project_identifier: 项目标识符，用于 MinIO 存储路径

    Returns:
        JSON 格式的测试执行结果，包含结构化数据和 MinIO 报告 URL

    Example:
        >>> result = await run_tests(
        ...     test_path="./tests/api",
        ...     framework="playwright",
        ...     reporter="json",
        ...     project_identifier="my-project"
        ... )
    """
    try:
        # 确定测试命令
        if framework == "playwright":
            # 使用 json + allure-playwright 双 reporter + 追踪详细请求
            cmd = ["npx", "playwright", "test", test_path, "--reporter=json,allure-playwright", "--trace=on"]
        elif framework == "jest":
            cmd = ["npm", "test", "--", test_path, f"--reporter={reporter}"]
        elif framework == "pytest":
            cmd = ["pytest", test_path, f"--reporter={reporter}"]
        else:
            return json.dumps({
                "success": False,
                "error": f"不支持的测试框架: {framework}"
            }, ensure_ascii=False, indent=2)

        # 准备环境变量
        env = os.environ.copy()
        env['CI'] = '1'
        # 脚本中常用的 API_BASE_URL 默认值
        if 'API_BASE_URL' not in env:
            env['API_BASE_URL'] = 'http://localhost:8000'

        # 执行测试（异步，不阻塞事件循环）
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(WORKSPACE_DIR),
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
            return json.dumps({
                "success": False,
                "error": "测试执行超时（5分钟）"
            }, ensure_ascii=False, indent=2)

        stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ''
        stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ''
        return_code = proc.returncode

        # 解析 Playwright JSON 报告
        report_url = None
        structured = None
        if framework == "playwright" and stdout.strip():
            playwright_report = _parse_playwright_json(stdout)
            if playwright_report:
                structured = _extract_test_results(playwright_report)
                readable_summary = _build_readable_summary(structured)

                # 保存到 MinIO
                try:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    object_name = f"test-reports/{project_identifier}/{timestamp}/report.json"
                    report_data = json.dumps({
                        "playwright_report": playwright_report,
                        "structured": structured,
                        "project_identifier": project_identifier,
                        "framework": framework,
                        "test_path": test_path,
                        "exit_code": return_code,
                        "generated_at": datetime.now().isoformat(),
                    }, ensure_ascii=False, indent=2)

                    MinIOClient.upload_bytes(
                        object_name=object_name,
                        data=report_data.encode('utf-8'),
                        content_type="application/json",
                    )

                    # 生成 presigned URL 用于直接访问
                    from datetime import timedelta
                    presigned_url = MinIOClient.get_presigned_url(
                        object_name=object_name,
                        expires=timedelta(days=7),
                    )
                    report_url = presigned_url

                except Exception as minio_err:
                    # MinIO 保存失败不阻塞主流程
                    print(f"[WARN] Failed to save report to MinIO: {minio_err}")

        # 生成 Allure HTML 报告（如果有 allure-results 目录）
        allure_report_url = None
        allure_minio_path = None
        try:
            allure_results_dir = WORKSPACE_DIR / "allure-results"
            if allure_results_dir.exists() and any(allure_results_dir.iterdir()):
                import shutil
                timestamp_ts = int(datetime.now().timestamp())
                allure_report_dir = WORKSPACE_DIR / f"allure-report-{timestamp_ts}"

                # 生成 HTML 报告
                proc_allure = await asyncio.create_subprocess_exec(
                    "allure", "generate", str(allure_results_dir),
                    "-o", str(allure_report_dir), "--clean",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc_allure.communicate(), timeout=60)

                if allure_report_dir.exists():
                    # 打包为 zip
                    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                    zip_path = WORKSPACE_DIR / f"allure-report-{timestamp_str}.zip"
                    shutil.make_archive(str(zip_path.with_suffix('')), 'zip', str(allure_report_dir))
                    if zip_path.exists():
                        # 上传到 MinIO
                        allure_minio_path = f"allure-reports/{project_identifier}/{timestamp_str}/report.zip"
                        with open(zip_path, 'rb') as f:
                            MinIOClient.upload_bytes(
                                object_name=allure_minio_path,
                                data=f.read(),
                                content_type="application/zip",
                            )
                        # 生成 presigned URL
                        from datetime import timedelta
                        allure_report_url = MinIOClient.get_presigned_url(
                            object_name=allure_minio_path,
                            expires=timedelta(days=7),
                        )
                        # 清理临时文件
                        shutil.rmtree(allure_report_dir, ignore_errors=True)
                        zip_path.unlink(missing_ok=True)

                # 清理 allure-results
                shutil.rmtree(allure_results_dir, ignore_errors=True)
        except Exception as allure_err:
            print(f"[WARN] Allure report generation failed: {allure_err}")

        # 构建返回结果
        result = {
            "success": return_code == 0,
            "exit_code": return_code,
            "framework": framework,
            "test_path": test_path,
            "timestamp": datetime.now().isoformat(),
        }

        if structured:
            result["summary"] = structured["summary"]
            result["tests"] = structured["tests"]
            result["readable_output"] = _build_readable_summary(structured)
            if report_url:
                result["report_url"] = report_url
                result["minio_path"] = f"test-reports/{project_identifier}/{datetime.now().strftime('%Y%m%d_%H%M%S')}/report.json"
        else:
            # 回退：返回原始输出 + 解析的 list 结果
            result["stdout"] = stdout
            result["stderr"] = stderr

        if allure_report_url:
            result["allure_report_url"] = allure_report_url
            result["allure_minio_path"] = allure_minio_path

        return json.dumps(result, ensure_ascii=False, indent=2)

    except asyncio.TimeoutError:
        return json.dumps({
            "success": False,
            "error": "测试执行超时（5分钟）"
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"测试执行失败: {str(e)}\n{traceback.format_exc()}"
        }, ensure_ascii=False, indent=2)


@tool
async def run_test_suite(
    project_identifier: str,
    endpoint_ids: list[str],
    framework: str = "playwright"
) -> str:
    """
    批量运行多个端点的测试

    Args:
        project_identifier: 项目标识符
        endpoint_ids: 端点 ID 列表
        framework: 测试框架

    Returns:
        JSON 格式的批量测试执行结果
    """
    try:
        results = []
        success_count = 0
        failed_count = 0

        for endpoint_id in endpoint_ids:
            # 构建测试路径
            test_path = f"./api-tests/{project_identifier}/endpoints/{endpoint_id}"

            # 运行测试
            result = await run_tests(
                test_path=test_path,
                framework=framework,
                reporter="json",
                project_identifier=project_identifier,
            )

            result_data = json.loads(result)
            results.append({
                "endpoint_id": endpoint_id,
                "result": result_data
            })

            if result_data.get("success"):
                success_count += 1
            else:
                failed_count += 1

        return json.dumps({
            "success": True,
            "summary": {
                "total": len(endpoint_ids),
                "success": success_count,
                "failed": failed_count
            },
            "results": results
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"批量测试执行失败: {str(e)}"
        }, ensure_ascii=False, indent=2)


@tool
async def parse_test_results(
    result_output: str
) -> str:
    """
    解析测试输出并提取关键信息

    Args:
        result_output: 测试运行的原始输出

    Returns:
        JSON 格式的解析结果
    """
    try:
        # 尝试解析 JSON 输出
        if result_output.strip().startswith("{"):
            data = json.loads(result_output)
            return json.dumps({
                "success": True,
                "parsed": True,
                "data": data
            }, ensure_ascii=False, indent=2)

        # 解析文本输出
        lines = result_output.split("\n")
        passed = []
        failed = []
        skipped = []

        for line in lines:
            if "✓" in line or "PASS" in line or "passed" in line:
                passed.append(line.strip())
            elif "✗" in line or "FAIL" in line or "failed" in line:
                failed.append(line.strip())
            elif "○" in line or "skipped" in line:
                skipped.append(line.strip())

        return json.dumps({
            "success": True,
            "parsed": True,
            "summary": {
                "passed": len(passed),
                "failed": len(failed),
                "skipped": len(skipped)
            },
            "details": {
                "passed": passed[:10],  # 最多返回10个
                "failed": failed[:10],
                "skipped": skipped[:10]
            }
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"解析测试结果失败: {str(e)}"
        }, ensure_ascii=False, indent=2)
