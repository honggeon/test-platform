# Agent URL 脱敏闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or executing-plans.

**Goal:** 确保真实测试环境 URL 仅在后端执行层使用，所有进入 LLM 上下文的数据（工具返回值、附件、Allure、结构化报告）均脱敏为 `{{API_BASE_URL}}`。

**Architecture:** 统一 `test_environment_url` 模块提供「解析真实 URL（执行用）」与「脱敏（Agent 可见用）」两套 API。执行时在临时目录注入；返回前对 stdout/Allure/JSON 做批量替换。`get_artifact_content` 在出口脱敏。

**Tech Stack:** Python, FastAPI Agent Tools, HAT/Allure, MinIO

---

## 泄露面分析

| 路径 | 风险 | 策略 |
|------|------|------|
| `execute_api_script` stdout/stderr | 高 | 多 URL 批量 mask |
| Allure `*-result.json` / attachment.txt | 高 | 生成 HTML 前 sanitize 目录 |
| `get_artifact_content` | 中 | 按 project_id 解析 URL 列表后 mask |
| `parse_test_results` | 中 | 解析前后 mask |
| `run_tests` 返回值 | 高 | 同 execute |
| MinIO 结构化报告 | 低（Agent 经 attachment 读） | attachment 出口 mask |
| FilesystemBackend 直读 workspace | 低（context 已是占位符） | Phase 2：allure 目录读保护 |

---

## Task 1: 扩展脱敏核心模块

**Files:**
- Modify: `backend/app/utils/test_environment_url.py`
- Test: `backend/tests/test_environment_url.py`

- [ ] `resolve_project_sensitive_urls(project_identifier)` — 项目全部环境 URL + fallback
- [ ] `resolve_sensitive_urls_by_project_id(project_id)` — 供 attachment 使用
- [ ] `mask_sensitive_urls(text, urls)` — 多 URL、长尾优先
- [ ] `mask_agent_payload(data, urls)` — 递归 dict/list/str
- [ ] `sanitize_allure_results_dir(path, urls)` — 原地脱敏 json/txt

---

## Task 2: 执行工具出口脱敏

**Files:**
- Modify: `backend/app/agents/api/tools/script_execution_tools.py`
- Modify: `backend/app/agents/api/tools/test_execution_tools.py`

- [ ] 执行前解析 `sensitive_urls` 列表
- [ ] stdout/stderr / structured report 使用 `mask_agent_payload`
- [ ] Allure generate **之前**调用 `sanitize_allure_results_dir`
- [ ] `execute_api_script` 最终 JSON 返回值整体 mask

---

## Task 3: 附件与解析工具脱敏

**Files:**
- Modify: `backend/app/agents/api/tools/test_artifacts_tools.py`
- Modify: `backend/app/agents/api/tools/test_execution_tools.py` (`parse_test_results`)

- [ ] `get_artifact_content` 返回前 mask content
- [ ] `parse_test_results` 增加 `project_identifier` 参数并 mask

---

## Task 4: 测试与验证

- [ ] 单元测试：多 URL mask、Allure 目录 sanitize、payload 递归
- [ ] `pytest tests/test_environment_url.py`

---

## 设计原则（Agent 侧）

1. **脚本/ context.yaml** 只含 `{{API_BASE_URL}}`，Agent 不手动替换
2. **真实 URL** 仅存在于：DB、环境变量、执行子进程、临时目录
3. **Agent 可见** = 工具返回值 + attachment +（未来）filesystem 读 — 全部过脱敏层
