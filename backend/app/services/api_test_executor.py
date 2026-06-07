"""
API 测试执行器

负责异步执行 API 测试并收集结果
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


import asyncio
import json
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.utils.allure_report import build_allure_generate_argv
from app.models.api_test import APITest, APITestRun, APITestResult
from app.repositories.api_test_repo import (
    APITestRepository,
    APITestRunRepository,
    APITestResultRepository,
)
from app.config.minio_client import MinIOClient
from app.schemas.enums import TestResultStatus
from app.models.mongodb.api_test_log import APITestDetailLog


class APITestExecutor:
    """
    API 测试执行器

    负责执行 Playwright API 测试并收集结果
    """

    def __init__(self, session: AsyncSession, mongodb=None):
        self.session = session
        self.mongodb = mongodb
        self.api_test_repo = APITestRepository(session)
        self.api_test_run_repo = APITestRunRepository(session)
        self.api_test_result_repo = APITestResultRepository(session)

    async def execute_test(
        self,
        api_test_id: UUID,
        execution_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        执行 API 测试（异步）

        Args:
            api_test_id: API 测试 ID
            execution_config: 执行配置

        Returns:
            str: 测试运行 ID
        """
        # 1. 获取 API 测试
        api_test = await self.api_test_repo.get_by_id(api_test_id)
        if not api_test:
            raise ValueError(f"API 测试不存在: {api_test_id}")

        # 2. 创建测试运行记录
        identifier = await self.api_test_run_repo.get_next_identifier(api_test_id)
        test_run = await self.api_test_run_repo.create(
            project_id=api_test.project_id,
            api_test_id=api_test_id,
            identifier=identifier,
            status="pending",
            execution_config=execution_config or {},
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
            skipped_tests=0,
        )

        run_id = test_run.id

        # 3. 在后台执行测试
        asyncio.create_task(
            self._execute_in_background(
                run_id=run_id,
                api_test=api_test,
                execution_config=execution_config or {},
            )
        )

        return str(run_id)

    async def _execute_in_background(
        self,
        run_id: UUID,
        api_test: APITest,
        execution_config: Dict[str, Any],
    ):
        """
        Execute test in background.

        Workflow:
        1. Update status to RUNNING
        2. Download test script from MinIO
        3. Prepare execution environment
        4. Run Playwright test
        5. Parse test results
        6. Save results to database
        7. Update run status
        """
        try:
            # 1. 更新状态为 RUNNING
            await self.api_test_run_repo.update(
                await self.api_test_run_repo.get_by_id(run_id),
                status="running"
            )

            # 2. 下载测试脚本
            script_content = MinIOClient.download_file(api_test.script_path)
            script_content = script_content.decode("utf-8")

            # 3. 准备执行环境
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # 写入测试脚本
                script_file = temp_path / "api-test.spec.ts"
                script_file.write_text(script_content, encoding="utf-8")

                # 创建配置文件（如果需要）
                playwright_config = self._generate_playwright_config(execution_config)
                config_file = temp_path / "playwright.config.ts"
                config_file.write_text(playwright_config, encoding="utf-8")

                # 软链工作区的 node_modules，确保 @playwright/test 可解析
                workspace_node_modules = Path(settings.api_workspace_root) / "node_modules"
                if workspace_node_modules.exists():
                    temp_node_modules = temp_path / "node_modules"
                    if not temp_node_modules.exists():
                        temp_node_modules.symlink_to(
                            workspace_node_modules,
                            target_is_directory=True,
                        )
                        print(f"[APITestExecutor] 已创建 node_modules 软链: {temp_node_modules} -> {workspace_node_modules}")

                # 4. 执行测试
                result = await self._run_playwright_test(
                    temp_dir, execution_config
                )

                # 5. 解析结果并保存
                await self._process_test_results(
                    run_id=run_id,
                    api_test=api_test,
                    test_result=result,
                )

                # 6. 生成 Allure 报告
                report_path = await self._generate_allure_report(
                    run_id=run_id,
                    work_dir=temp_dir,
                )

                # 7. 更新为完成状态
                await self.api_test_run_repo.update(
                    await self.api_test_run_repo.get_by_id(run_id),
                    status="completed",
                    report_path=report_path,
                )

        except Exception as e:
            # 更新为失败状态
            await self.api_test_run_repo.update(
                await self.api_test_run_repo.get_by_id(run_id),
                status="failed",
                error_message=str(e)
            )
            # 记录错误日志
            print(f"测试执行失败: {e}")

    def _generate_playwright_config(self, execution_config: Dict[str, Any]) -> str:
        """生成 Playwright 配置文件"""
        return f"""
import {{ defineConfig, devices }} from '@playwright/test';

export default defineConfig({{
  testDir: './',
  fullyParallel: true,
  forbidOnly: false,
  retries: process.env.CI ? 2 : 0,
  use: {{
    launchOptions: {{
      slowMo: 3000,
    }},
  }},
  projects: [
    {{
      name: 'api-tests',
      use: {{
        baseURL: '{execution_config.get('base_url', 'http://localhost:8000')}',
      }},
    }},
  ],
}});
"""

    async def _run_playwright_test(
        self,
        work_dir: Path,
        execution_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        运行 Playwright 测试并生成 Allure 报告

        Args:
            work_dir: 工作目录
            execution_config: 执行配置

        Returns:
            dict: 测试结果
        """
        try:
            # 检查 npx 是否可用
            npx_check = subprocess.run(
                ["npx", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if npx_check.returncode != 0:
                raise Exception("npx 不可用，请确保 Node.js 已安装")

            # 运行 Playwright 测试，使用 Allure 报告
            result = subprocess.run(
                [
                    "npx", "playwright", "test",
                    "--reporter=@playwright/test/allure-playwright",  # 使用 Allure 报告器
                    f"--output={work_dir}/allure-results",  # Allure 结果目录
                ],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=execution_config.get("timeout", 300),  # 5 分钟超时
            )

            # 读取 JSON 格式的测试结果（如果同时配置了 json 报告器）
            json_results_file = work_dir / "results.json"
            if json_results_file.exists():
                with open(json_results_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                # 如果没有 JSON 结果，返回执行状态
                return {
                    "status": "passed" if result.returncode == 0 else "failed",
                    "error": result.stderr,
                    "stdout": result.stdout,
                }

        except subprocess.TimeoutExpired as e:
            return {
                "status": "failed",
                "error": f"测试执行超时: {str(e)}",
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": f"测试执行失败: {str(e)}",
            }

    async def _process_test_results(
        self,
        run_id: UUID,
        api_test: APITest,
        test_result: Dict[str, Any],
    ):
        """
        处理测试结果

        Args:
            run_id: 测试运行 ID
            api_test: API 测试
            test_result: Playwright 测试结果
        """
        try:
            # 解析 Playwright 结果
            suites = test_result.get("suites", [])
            total_tests = 0
            passed_tests = 0
            failed_tests = 0
            skipped_tests = 0

            for suite in suites:
                specs = suite.get("specs", [])
                for spec in specs:
                    tests = spec.get("tests", [])
                    for test in tests:
                        total_tests += 1

                        status = TestResultStatus.PASSED
                        if test.get("ok", False):
                            passed_tests += 1
                        else:
                            failed_tests += 1
                            status = TestResultStatus.FAILED

                        # 保存测试结果
                        await self._save_test_result(
                            run_id=run_id,
                            api_test=api_test,
                            test_name=test.get("title", ""),
                            status=status,
                            results=test.get("results", []),
                        )

            # 更新运行统计
            await self.api_test_run_repo.update(
                await self.api_test_run_repo.get_by_id(run_id),
                total_tests=total_tests,
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                skipped_tests=skipped_tests,
            )

        except Exception as e:
            print(f"处理测试结果失败: {e}")

    async def _save_test_result(
        self,
        run_id: UUID,
        api_test: APITest,
        test_name: str,
        status: TestResultStatus,
        _results: List[Dict[str, Any]],
    ):
        """
        保存单个测试结果

        Args:
            run_id: 测试运行 ID
            api_test: API 测试
            test_name: 测试名称
            status: 测试状态
            _results: 测试结果详情（预留，用于提取断言和执行时间）
        """
        try:
            # 提取端点和 HTTP 方法（从测试名称中解析）
            endpoint, method = self._parse_endpoint_from_test_name(test_name)

            # 创建测试结果记录
            await self.api_test_result_repo.create(
                test_run_id=run_id,
                api_test_id=api_test.id,
                scenario_name=test_name,
                endpoint=endpoint,
                method=method,
                status=status,
                request_summary={
                    "url": api_test.test_config.get("base_url", ""),
                    "method": method,
                },
                response_summary={
                    "status_code": 200 if status == TestResultStatus.PASSED else 500,
                },
                error_message=None if status == TestResultStatus.PASSED else "测试失败",
                duration_ms=0,  # TODO: 从测试结果中提取
                retry_count=0,
            )

        except Exception as e:
            print(f"保存测试结果失败: {e}")

    def _parse_endpoint_from_test_name(self, test_name: str) -> tuple[str, str]:
        """
        Parse endpoint and HTTP method from test name.

        Input:  "GET /api/v1/users"
        Output: ("/api/v1/users", "GET")
        """
        import re

        # Try to match pattern: "METHOD /path" or "METHOD path"
        match = re.match(r'^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(.+)$', test_name)
        if match:
            method = match.group(1)
            endpoint = match.group(2)
            return endpoint, method

        # Default to GET if no explicit method found
        return test_name, "GET"

    async def _generate_allure_report(
        self,
        run_id: UUID,
        work_dir: Path,
    ) -> Optional[str]:
        """
        生成 Allure 测试报告

        Args:
            run_id: 测试运行 ID
            work_dir: 工作目录（包含 allure-results）

        Returns:
            str: 报告目录路径 (MinIO)
        """
        try:
            allure_results_dir = work_dir / "allure-results"

            # 检查 Allure 结果是否存在
            if not allure_results_dir.exists():
                print("未找到 Allure 测试结果")
                return None

            # 生成 HTML 报告到临时目录
            allure_report_dir = work_dir / "allure-report"
            allure_cmd = build_allure_generate_argv(allure_results_dir, allure_report_dir)
            allure_proc = subprocess.run(
                allure_cmd,
                capture_output=True,
                timeout=30,
            )
            if allure_proc.returncode != 0:
                stderr = allure_proc.stderr.decode("utf-8", errors="replace")[:500]
                print(f"Allure generate 失败: rc={allure_proc.returncode}, stderr={stderr}")
                return None

            # 将报告打包为 ZIP 并上传到 MinIO
            import zipfile
            zip_path = work_dir / "allure-report.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in allure_report_dir.rglob('*'):
                    if file.is_file():
                        arcname = file.relative_to(allure_report_dir)
                        zipf.write(file, arcname)

            # 上传到 MinIO
            report_path = f"api-test-reports/{run_id}/allure-report.zip"
            with open(zip_path, 'rb') as f:
                MinIOClient.upload_bytes(
                    object_name=report_path,
                    data=f.read(),
                    content_type="application/zip",
                )

            return report_path

        except Exception as e:
            print(f"生成 Allure 报告失败: {e}")
            return None

    async def save_detail_log(
        self,
        test_result_id: UUID,
        test_run_id: UUID,
        api_test_id: UUID,
        scenario_name: str,
        endpoint: str,
        method: str,
        request: Dict[str, Any],
        response: Dict[str, Any],
        status: str,
        duration_ms: int,
    ) -> str:
        """
        保存详细日志到 MongoDB

        Args:
            test_result_id: 测试结果 ID
            test_run_id: 测试运行 ID
            api_test_id: API 测试 ID
            scenario_name: 场景名称
            endpoint: 端点
            method: HTTP 方法
            request: 请求数据
            response: 响应数据
            status: 状态
            duration_ms: 执行时长

        Returns:
            str: MongoDB 日志 ID
        """
        if not self.mongodb:
            return None

        try:
            log = APITestDetailLog(
                log_id=str(uuid4()),
                test_result_id=test_result_id,
                test_run_id=test_run_id,
                api_test_id=api_test_id,
                scenario_name=scenario_name,
                endpoint=endpoint,
                method=method,
                request=request,
                response=response,
                assertions=[],  # TODO: 从测试结果中提取断言
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                duration_ms=duration_ms,
                status=status,
                error=None if status == "passed" else {"message": "测试失败"},
            )

            # 保存到 MongoDB
            collection = self.mongodb.db.get_collection("api_test_logs")
            result = await collection.insert_one(log.to_document())

            return str(result.inserted_id)

        except Exception as e:
            print(f"保存详细日志失败: {e}")
            return None

    async def generate_test_report(
        self,
        run_id: UUID,
    ) -> Optional[str]:
        """
        生成测试报告（已废弃，使用 _generate_allure_report 代替）

        Args:
            run_id: 测试运行 ID

        Returns:
            str: 报告文件路径 (MinIO)
        """
        # 此方法已集成到 _execute_in_background 中
        # 保留是为了向后兼容
        test_run = await self.api_test_run_repo.get_by_id(run_id)
        if test_run and test_run.report_path:
            return test_run.report_path
        return None
