# 测试报告系统实现计划

## 目标
在前端按项目和功能展示测试报告，类似 Allure，包含每个步骤的详细信息（通过/失败、耗时、错误原因、断言详情）。

## 现有基础
- `run_tests` 工具 → 仅返回文本，无结构化报告
- `execute_api_script` 工具 → 可生成 HTML 报告存 MinIO
- `api_test_executor.py` → 生成 Allure 报告存 MinIO
- 前端已有 `test-reports/page.tsx`（仅显示汇总卡片，无详情）
- 后端已有 `TestResult` API

## 实现步骤

### Phase 1: Backend - run_tests 输出结构化 JSON
- 修改 `run_tests`：使用 `--reporter=json` 获取结构化结果
- 解析 JSON 输出，提取每个测试用例的名称、状态、耗时、错误信息
- 将结构化结果保存到 MinIO（`test-reports/{project}/{timestamp}/report.json`）
- 同时保存每个测试的完整 stdout/stderr 作为 step 详情

### Phase 2: Backend - API 端点
- `GET /api/v2/projects/{id}/test-reports` → 按时间倒序列出报告
- `GET /api/v2/projects/{id}/test-reports/{report_id}` → 报告详情（测试用例列表、步骤）
- `GET /api/v2/projects/{id}/test-reports/{report_id}/cases/{case_id}` → 单个用例详情（请求、响应、断言）

### Phase 3: Frontend - 报告查看页
- 报告列表页：项目下所有报告，含时间戳、通过/失败/总数统计
- 报告详情页：测试用例表格 + 通过率
- 用例展开面板：请求 URL、方法、状态码、响应时间、断言结果、错误信息
- 按功能模块分组（通过测试文件的路径）

### Phase 4: 集成到 Agent
- `run_tests` 返回报告中包含 MinIO 报告链接
- 大模型回复时直接提供报告查看 URL
