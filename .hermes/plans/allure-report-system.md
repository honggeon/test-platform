# Allure 报告系统实现计划

## 目标
在前端展示类似 Allure 的测试报告，每一步请求/返回都能看到，按项目和功能组织。

## 实现步骤

### 1. 安装基础设施
- 安装 Allure CLI（Java-based）
- workspace/api/ 下安装 allure-playwright npm 包
- 验证 allure generate 可用

### 2. 修改测试工具，使用 allure-playwright reporter
- `run_tests` 工具：添加 `--reporter=allure-playwright`
- `execute_api_script` 工具：添加 `--reporter=allure-playwright`
- 执行后用 `allure generate` 生成 HTML 报告
- 将 HTML 报告目录上传到 MinIO（zip 打包）

### 3. 后端 API 端点
- `GET /api/v2/projects/{id}/allure-reports` — 列出现有 Allure 报告
- `GET /api/v2/projects/{id}/allure-reports/{report_id}/files/{path}` — 代理 Allure 报告的静态文件（HTML/JS/CSS）

### 4. 前端报告页
- 嵌入 iframe 展示 Allure HTML 报告
- 或者用 iframe 加载后端代理的 Allure 页面

## Allure 报告包含内容
- Overview：通过率、耗时、环境
- Suites：按 describe 分组展示
- Behaviors：按功能模块展示
- Test case 详情：每个 API 请求的 URL、方法、Headers、Request Body、Response Status、Response Body、Assertions
- Timeline：执行时序
- Graphs：图表统计
